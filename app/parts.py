"""Parts (stub) + file upload & storage — the first object-storage resource (M1.2).

Files belong to a **Part** (never a quote/line-item) and a Part can stand alone
(DECISIONS.md 2026-06-25). M1.2 ships a minimal ``part`` owner plus full file
management: upload (one or more files in a request), list, download, set/swap the
PRIMARY, and delete. Everything is org-scoped through ``get_session`` so RLS makes
isolation a DB guarantee (the M0.2 pattern, inherited verbatim).

Semantics encoded here (DECISIONS.md 2026-06-25):
  * **Auto-PRIMARY:** when a part has no PRIMARY, the highest-geometric-rank file
    among the uploaded set becomes PRIMARY (CAD > mesh > 2D-vector > print); ties
    resolve to first-uploaded. Later uploads to a part that already has a PRIMARY
    are SUPPORTING until explicitly swapped.
  * **One PRIMARY per part:** ``part.primary_file_id`` is the authority; ``part_
    file.role`` is kept in sync in the same transaction (a swap clears the old role
    before setting the new, so the partial unique index never sees two primaries).
  * **Hard delete:** removing a file purges the row and (post-commit, via a
    background task) the object-store blob. Deleting the current PRIMARY is blocked
    while any SUPPORTING file remains — swap first; the pointer is nulled only when
    the PRIMARY is the part's last file.
  * **Validation at the edge:** the supported-file allow-list + a magic-byte sniff
    (PDF/ZIP/STEP) + the 200 MB cap; rejections use the standard error envelope.

Permission gates mirror M1.1: writes need ``quote_edit`` (managing a part's files
is editing the quote's content); reads need only an authenticated org session.
"""

from __future__ import annotations

import contextlib
import os
import urllib.parse
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .config import Settings
from .deps import get_app_settings, get_session, get_storage
from .errors import AppError
from .file_types import (
    MAGIC_SNIFF_BYTES,
    FileCategory,
    classify,
    primary_rank,
    sniff_matches_extension,
)
from .models import FileRole, Part, PartFile
from .storage import ObjectStorage, object_key

parts_router = APIRouter(prefix="/api/parts", tags=["parts", "files"])

_LIST_LIMIT_DEFAULT = 100
_LIST_LIMIT_MAX = 500
_FILENAME_MAX = 255


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class PartOut(BaseModel):
    """A part as returned to clients (M1.2 stub shape)."""

    id: uuid.UUID
    primary_file_id: uuid.UUID | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class PartFileOut(BaseModel):
    """An uploaded part file as returned to clients."""

    id: uuid.UUID
    part_id: uuid.UUID
    filename: str
    file_type: str
    content_type: str | None
    size_bytes: int
    role: FileRole
    is_redacted: bool
    created_at: datetime


def _part_out(part: Part) -> PartOut:
    return PartOut(
        id=part.id,
        primary_file_id=part.primary_file_id,
        archived=part.deleted_at is not None,
        created_at=part.created_at,
        updated_at=part.updated_at,
    )


def _part_file_out(pf: PartFile) -> PartFileOut:
    return PartFileOut(
        id=pf.id,
        part_id=pf.part_id,
        filename=pf.filename,
        file_type=pf.file_type,
        content_type=pf.content_type,
        size_bytes=pf.size_bytes,
        role=FileRole(pf.role),
        is_redacted=pf.is_redacted,
        created_at=pf.created_at,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _safe_filename(raw: str | None) -> str:
    """Sanitise an upload filename to a bare basename (no path, no traversal).

    Rejects an empty/``.``/``..``/over-long name, or one containing control
    characters, with a clean 422 — these would otherwise let a crafted name escape
    the per-part object-key prefix or inject into the ``Content-Disposition`` header
    on download (CR, LF, NUL, …)."""
    if not raw:
        raise AppError("invalid_filename", "A filename is required.", status_code=422)
    name = os.path.basename(raw.replace("\\", "/")).strip()
    if not name or name in {".", ".."} or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise AppError("invalid_filename", "Invalid filename.", status_code=422)
    if len(name) > _FILENAME_MAX:
        raise AppError(
            "invalid_filename", f"Filename exceeds {_FILENAME_MAX} characters.", status_code=422
        )
    return name


def _received_size(upload: UploadFile) -> int:
    """The actual number of bytes received for ``upload`` (the multipart parser has
    already spooled the whole body), measured from the spooled file — not the
    client-supplied ``upload.size``, which may be absent."""
    f = upload.file
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)
    return size


async def _get_part_or_404(
    session: AsyncSession, part_id: uuid.UUID, *, for_update: bool = False
) -> Part:
    """Fetch a part in the active org, or raise 404 (RLS scopes the lookup).

    ``for_update`` takes a row lock (``SELECT … FOR UPDATE``) so a file mutation
    (upload / set-primary / delete) serializes against concurrent mutations on the
    same part — otherwise a last-primary delete racing an upload could strand
    supporting files with a NULL primary, or racing swaps could surface a raw
    unique-index error (CodeRabbit PR #8)."""
    part = await session.get(Part, part_id, with_for_update=for_update or None)
    if part is None:
        raise AppError("not_found", "Part not found.", status_code=status.HTTP_404_NOT_FOUND)
    return part


async def _get_part_file_or_404(
    session: AsyncSession, part_id: uuid.UUID, file_id: uuid.UUID
) -> PartFile:
    """Fetch one file of a part, or raise 404."""
    pf = await session.get(PartFile, file_id)
    if pf is None or pf.part_id != part_id:
        raise AppError("not_found", "File not found.", status_code=status.HTTP_404_NOT_FOUND)
    return pf


def _content_disposition(filename: str) -> str:
    """An ``attachment`` Content-Disposition carrying the filename safely.

    Provides an ASCII fallback plus RFC 5987 ``filename*`` so non-ASCII names
    (umlauts in German part names) survive."""
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "")
    quoted = urllib.parse.quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quoted}"


# --------------------------------------------------------------------------- #
# Parts (minimal stub — M1.5 fleshes this out)
# --------------------------------------------------------------------------- #
@parts_router.post("", status_code=status.HTTP_201_CREATED)
async def create_part(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> PartOut:
    """Create an empty part to attach files to (the M1.2 owner for uploads)."""
    part = Part(org_id=principal.active_org_id)
    session.add(part)
    await session.flush()
    return _part_out(part)


@parts_router.get("")
async def list_parts(
    session: Annotated[AsyncSession, Depends(get_session)],
    include_archived: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=_LIST_LIMIT_MAX)] = _LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PartOut]:
    """List the active org's parts (RLS-scoped)."""
    stmt = select(Part)
    if not include_archived:
        stmt = stmt.where(Part.deleted_at.is_(None))
    stmt = stmt.order_by(Part.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [_part_out(p) for p in result.scalars()]


@parts_router.get("/{part_id}")
async def get_part(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PartOut:
    """Fetch one part."""
    return _part_out(await _get_part_or_404(session, part_id))


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #
@parts_router.get("/{part_id}/files")
async def list_part_files(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PartFileOut]:
    """List a part's files (PRIMARY first, then by upload time)."""
    await _get_part_or_404(session, part_id)
    stmt = (
        select(PartFile)
        .where(PartFile.part_id == part_id)
        # PRIMARY sorts before SUPPORTING ('primary' < 'supporting' lexically), then
        # oldest-first — a stable order for the Files panel.
        .order_by(PartFile.role, PartFile.created_at)
    )
    result = await session.execute(stmt)
    return [_part_file_out(pf) for pf in result.scalars()]


@parts_router.post("/{part_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_part_files(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    files: Annotated[list[UploadFile], File()],
) -> list[PartFileOut]:
    """Upload one or more files to a part.

    Each file is validated at the edge (allow-list + magic sniff + size cap) before
    anything is stored, so a bad file in the batch rejects the whole request without
    leaving orphan blobs. If the part has no PRIMARY, the highest-geometric-rank
    uploaded file becomes PRIMARY (ties → first uploaded)."""
    part = await _get_part_or_404(session, part_id, for_update=True)
    if not files:
        raise AppError("no_files", "No files were provided.", status_code=422)

    # --- Phase 1: validate every file (no storage writes yet) ---
    validated: list[tuple[UploadFile, str, str]] = []  # (file, safe_name, category_value)
    for upload in files:
        # Filenames are not echoed in error bodies — they can carry customer/part
        # identifiers (CLAUDE.md §5: no PII in errors).
        name = _safe_filename(upload.filename)
        category = classify(name)
        if category is None:
            raise AppError(
                "unsupported_file_type",
                "File type not supported.",
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
        # Enforce the cap on the ACTUAL received bytes (the multipart parser already
        # spooled the whole body), BEFORE writing anything to storage — don't trust a
        # possibly-absent client-supplied ``upload.size``.
        if _received_size(upload) > settings.max_upload_bytes:
            raise AppError(
                "file_too_large",
                f"File exceeds the {settings.max_upload_mb} MB limit.",
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        header = await upload.read(MAGIC_SNIFF_BYTES)
        await upload.seek(0)
        if not sniff_matches_extension(name, header):
            raise AppError(
                "file_type_mismatch",
                "File contents do not match the declared extension.",
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
        validated.append((upload, name, category.value))

    # --- Phase 2: store blobs + create rows (clean up blobs on any failure) ---
    stored_keys: list[str] = []
    rows: list[PartFile] = []
    try:
        for upload, name, category_value in validated:
            file_id = uuid.uuid4()
            key = object_key(principal.active_org_id, part_id, file_id, name)
            # Cap already enforced pre-store in Phase 1; ``size`` here is the
            # authoritative byte count actually written.
            size = await storage.put(key, upload.file, content_type=upload.content_type)
            stored_keys.append(key)
            row = PartFile(
                id=file_id,
                org_id=principal.active_org_id,
                part_id=part_id,
                storage_key=key,
                filename=name,
                file_type=category_value,
                content_type=upload.content_type,
                size_bytes=size,
                role=FileRole.supporting,
            )
            session.add(row)
            rows.append(row)

        # Insert the part_file rows BEFORE pointing part.primary_file_id at one of
        # them: that FK is a plain column (no ORM relationship), so the unit of work
        # doesn't know to order the INSERTs ahead of the part UPDATE on its own.
        await session.flush()
        _assign_primary_if_absent(part, rows)
        await session.flush()
    except AppError:
        await _discard_blobs(storage, stored_keys)
        raise
    except IntegrityError as exc:
        await _discard_blobs(storage, stored_keys)
        if "uq_part_file_one_primary" in str(exc.orig):
            raise AppError(
                "primary_conflict",
                "Another file became the PRIMARY for this part; retry.",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise

    return [_part_file_out(row) for row in rows]


def _assign_primary_if_absent(part: Part, rows: list[PartFile]) -> None:
    """If the part has no PRIMARY, promote the highest-rank uploaded file to PRIMARY
    (ties → first uploaded). No-op when a PRIMARY already exists."""
    if part.primary_file_id is not None or not rows:
        return
    # Rank by the already-validated stored category (NOT NULL), not by re-classifying
    # the filename — `file_type` was set from the Phase-1 `classify()`, so this can't
    # be None and needs no type-ignore.
    winner = max(rows, key=lambda r: primary_rank(FileCategory(r.file_type)))
    winner.role = FileRole.primary
    part.primary_file_id = winner.id


async def _discard_blobs(storage: ObjectStorage, keys: list[str]) -> None:
    """Best-effort cleanup of blobs stored before a failure (the rows roll back).

    Cleanup must never mask the original error, so any delete failure is swallowed."""
    for key in keys:
        with contextlib.suppress(Exception):
            await storage.delete(key)


@parts_router.get("/{part_id}/files/{file_id}/download")
async def download_part_file(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
) -> StreamingResponse:
    """Stream a file back byte-identically (M1.2 acceptance: round-trips intact)."""
    pf = await _get_part_file_or_404(session, part_id, file_id)
    return StreamingResponse(
        storage.stream(pf.storage_key),
        media_type=pf.content_type or "application/octet-stream",
        headers={"Content-Disposition": _content_disposition(pf.filename)},
    )


@parts_router.post("/{part_id}/files/{file_id}/primary")
async def set_primary_file(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> PartFileOut:
    """Make this file the part's PRIMARY (swap). Idempotent if it already is.

    Clears the previous PRIMARY's role *before* setting the new one, so the partial
    unique index never momentarily sees two primaries."""
    part = await _get_part_or_404(session, part_id, for_update=True)
    target = await _get_part_file_or_404(session, part_id, file_id)
    if part.primary_file_id == target.id:
        return _part_file_out(target)

    if part.primary_file_id is not None:
        previous = await session.get(PartFile, part.primary_file_id)
        if previous is not None:
            previous.role = FileRole.supporting
            await session.flush()  # statement-level: zero primaries before the next set

    target.role = FileRole.primary
    part.primary_file_id = target.id
    await session.flush()
    return _part_file_out(target)


@parts_router.delete("/{part_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part_file(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    background: BackgroundTasks,
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Response:
    """Hard-delete a file (row + blob).

    Deleting the current PRIMARY is blocked while any SUPPORTING file remains (swap
    first); the pointer is nulled only when the PRIMARY is the part's last file. The
    blob is purged by a background task that runs *after* the DB commit, so a failed
    commit never deletes a still-referenced object."""
    part = await _get_part_or_404(session, part_id, for_update=True)
    target = await _get_part_file_or_404(session, part_id, file_id)

    if part.primary_file_id == target.id:
        others = await session.scalar(
            select(func.count())
            .select_from(PartFile)
            .where(PartFile.part_id == part_id, PartFile.id != target.id)
        )
        if others:
            raise AppError(
                "primary_delete_blocked",
                "Set another file as PRIMARY before deleting this one.",
                status_code=status.HTTP_409_CONFLICT,
            )
        # Last file: clear the pointer first so the FK doesn't block the row delete.
        part.primary_file_id = None
        await session.flush()

    key = target.storage_key
    await session.delete(target)
    await session.flush()
    background.add_task(storage.delete, key)  # purge the blob post-commit
    return Response(status_code=status.HTTP_204_NO_CONTENT)
