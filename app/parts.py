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
import json
import os
import urllib.parse
import uuid
from datetime import datetime
from decimal import Decimal
from functools import partial
from typing import Annotated, Any, Literal

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
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .config import Settings
from .deps import get_app_settings, get_session, get_storage
from .dimensions import (
    DimensionError,
    evaluate_area,
    evaluate_length,
    evaluate_mass,
    evaluate_volume,
)
from .errors import AppError
from .file_types import (
    MAGIC_SNIFF_BYTES,
    FileCategory,
    classify,
    primary_rank,
    sniff_matches_extension,
)
from .models import (
    FileAnnotationLayer,
    FileRole,
    Node,
    ObtainMethod,
    Part,
    PartFile,
    PartGeometry,
)
from .storage import ObjectStorage, object_key

parts_router = APIRouter(prefix="/api/parts", tags=["parts", "files"])

_LIST_LIMIT_DEFAULT = 100
_LIST_LIMIT_MAX = 500
_FILENAME_MAX = 255


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class PartOut(BaseModel):
    """A part as returned to clients (M1.5 4-layer shape: identity + flags)."""

    id: uuid.UUID
    primary_file_id: uuid.UUID | None
    name: str | None
    part_number: str | None
    revision: str | None
    description: str | None
    is_assembly: bool
    obtain_method: ObtainMethod
    export_controlled: bool
    archived: bool
    created_at: datetime
    updated_at: datetime


class PartUpdate(BaseModel):
    """Patch a part's identity + flags. Only provided fields change (``exclude_unset``);
    an explicit ``null`` clears an identity field. Identity is free-text, not unique
    (matching is M2; DECISIONS.md 2026-06-26)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    part_number: str | None = None
    revision: str | None = None
    description: str | None = None
    is_assembly: bool | None = None
    obtain_method: ObtainMethod | None = None
    export_controlled: bool | None = None


# The IN/MM toggle CLAUDE.md §5 explicitly permits ("a toggle may exist, default never
# imperial"): it only sets the *default* unit for a bare number (a typed unit like
# ``1 meter`` overrides it), the default is ``mm``, and the stored value is ALWAYS metric
# (mm) — so downstream Kalk/DFM never see imperial. This is presentation, not a stored
# imperial path (DECISIONS.md 2026-06-26 "PartGeometry manual-dims storage model").
DimUnit = Literal["mm", "in"]
# Dim fields that take a linear value (mm); area/volume/weight are handled separately.
_LENGTH_DIMS = ("size_x", "size_y", "size_z", "max_dim", "med_dim", "min_dim")
# A raw dim input: a number, or a string carrying math + an optional unit.
DimInput = str | float | int | None


class PartGeometryUpdate(BaseModel):
    """Set manual geometry dims. Each field auto-evaluates math (``2.27 + .359``) and
    typed units (``1 meter``) via the safe parser; values store as metric. Partial:
    only provided fields change, ``null`` clears one (DECISIONS.md 2026-06-26)."""

    model_config = ConfigDict(extra="forbid")

    unit: DimUnit = "mm"
    size_x: DimInput = None
    size_y: DimInput = None
    size_z: DimInput = None
    max_dim: DimInput = None
    med_dim: DimInput = None
    min_dim: DimInput = None
    area: DimInput = None
    volume: DimInput = None
    weight: DimInput = None


class PartGeometryOut(BaseModel):
    """A part's manual geometry (effective metric values + which dims a human set)."""

    part_id: uuid.UUID
    size_x: float | None
    size_y: float | None
    size_z: float | None
    max_dim: float | None
    med_dim: float | None
    min_dim: float | None
    area: float | None
    volume: float | None
    weight: float | None
    overrides: dict[str, Any]


class BomNodeOut(BaseModel):
    """One node of a part's BOM tree. M1.5 returns a single root node; M4 fills depth."""

    node_id: uuid.UUID
    part_id: uuid.UUID
    qty_relative_to_parent: int
    is_root: bool
    children: list[BomNodeOut]


# Resolve the self-reference (``from __future__ import annotations`` makes it a string).
BomNodeOut.model_rebuild()


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
        name=part.name,
        part_number=part.part_number,
        revision=part.revision,
        description=part.description,
        is_assembly=part.is_assembly,
        obtain_method=part.obtain_method,
        export_controlled=part.export_controlled,
        archived=part.deleted_at is not None,
        created_at=part.created_at,
        updated_at=part.updated_at,
    )


def _f(value: Decimal | None) -> float | None:
    """Numeric (Decimal from the DB) → float for the JSON contract; metric throughout."""
    return float(value) if value is not None else None


def _geometry_out(part_id: uuid.UUID, geom: PartGeometry | None) -> PartGeometryOut:
    """Shape a part's geometry for clients; an unset geometry reads as all-null."""
    if geom is None:
        return PartGeometryOut(
            part_id=part_id,
            size_x=None,
            size_y=None,
            size_z=None,
            max_dim=None,
            med_dim=None,
            min_dim=None,
            area=None,
            volume=None,
            weight=None,
            overrides={},
        )
    return PartGeometryOut(
        part_id=geom.part_id,
        size_x=_f(geom.size_x),
        size_y=_f(geom.size_y),
        size_z=_f(geom.size_z),
        max_dim=_f(geom.max_dim),
        med_dim=_f(geom.med_dim),
        min_dim=_f(geom.min_dim),
        area=_f(geom.area),
        volume=_f(geom.volume),
        weight=_f(geom.weight),
        overrides=dict(geom.overrides or {}),
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
# Parts — the 4-layer model (M1.5)
# --------------------------------------------------------------------------- #
async def create_root_part(session: AsyncSession, org_id: uuid.UUID) -> Part:
    """Create a Part **and its root Node** (the 4-layer model; M1.5).

    Every part is the root of a (currently single-node) BOM tree: the root node has no
    parent and quantity 1, linked back to the part as the tree root. M4 grows child
    nodes; the contract is established here. Shared by the standalone Part-Library create
    and the quote add-line-item flow so both paths build the same structure."""
    part = Part(org_id=org_id)
    session.add(part)
    await session.flush()
    session.add(
        Node(
            org_id=org_id,
            part_id=part.id,
            parent_node_id=None,
            qty_relative_to_parent=1,
            root_part_id=part.id,
        )
    )
    await session.flush()
    return part


async def _get_or_create_geometry(session: AsyncSession, part: Part) -> PartGeometry:
    """The part's 1:1 geometry row, created empty on first manual edit."""
    geom = await session.scalar(select(PartGeometry).where(PartGeometry.part_id == part.id))
    if geom is None:
        geom = PartGeometry(org_id=part.org_id, part_id=part.id, overrides={})
        session.add(geom)
        await session.flush()
    return geom


async def _node_subtree(session: AsyncSession, node: Node) -> BomNodeOut:
    """Build a node and its descendants (M1.5: leaves only — no children yet)."""
    child_rows = (
        await session.scalars(
            select(Node).where(Node.parent_node_id == node.id).order_by(Node.created_at)
        )
    ).all()
    children = [await _node_subtree(session, child) for child in child_rows]
    return BomNodeOut(
        node_id=node.id,
        part_id=node.part_id,
        qty_relative_to_parent=node.qty_relative_to_parent,
        is_root=node.parent_node_id is None,
        children=children,
    )


async def build_bom_tree(session: AsyncSession, part_id: uuid.UUID) -> BomNodeOut | None:
    """The BOM tree rooted at a part's root node, or ``None`` if it has no node."""
    root = await session.scalar(
        select(Node).where(Node.part_id == part_id, Node.parent_node_id.is_(None))
    )
    if root is None:
        return None
    return await _node_subtree(session, root)


@parts_router.post("", status_code=status.HTTP_201_CREATED)
async def create_part(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> PartOut:
    """Create a part (the M1.2 file owner; now also the root of a BOM tree, M1.5)."""
    part = await create_root_part(session, principal.active_org_id)
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


@parts_router.patch("/{part_id}")
async def update_part(
    part_id: uuid.UUID,
    payload: PartUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> PartOut:
    """Update a part's identity + flags (incl. the EU dual-use export flag)."""
    part = await _get_part_or_404(session, part_id, for_update=True)
    changes = payload.model_dump(exclude_unset=True)
    # Identity fields are nullable (an explicit null clears them); the flag/enum columns
    # are NOT NULL, so reject an explicit null with a clean 422 rather than a leaked 500.
    for field in ("is_assembly", "obtain_method", "export_controlled"):
        if field in changes and changes[field] is None:
            raise AppError("invalid_value", f"{field} cannot be null.", status_code=422)
    for field, value in changes.items():
        setattr(part, field, value)
    await session.flush()
    return _part_out(part)


# --------------------------------------------------------------------------- #
# Geometry (manual dims — the geometry↔Kalk contract; M1.5)
# --------------------------------------------------------------------------- #
@parts_router.get("/{part_id}/geometry")
async def get_part_geometry(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PartGeometryOut:
    """Read a part's geometry (all-null until dims are set)."""
    await _get_part_or_404(session, part_id)
    geom = await session.scalar(select(PartGeometry).where(PartGeometry.part_id == part_id))
    return _geometry_out(part_id, geom)


def _apply_dim(
    geom: PartGeometry,
    overrides: dict[str, Any],
    field: str,
    raw: DimInput,
    evaluator: Any,
    unit: str,
) -> None:
    """Evaluate one manual dim and store it (metric) + record its override provenance;
    ``None`` clears the dim. Raises :class:`DimensionError` on bad math / a negative."""
    if raw is None:
        setattr(geom, field, None)
        overrides.pop(field, None)
        return
    value = evaluator(raw)
    if value < 0:
        raise DimensionError("A dimension must not be negative.")
    setattr(geom, field, Decimal(str(value)))
    overrides[field] = {"input": str(raw), "unit": unit}


@parts_router.patch("/{part_id}/geometry")
async def update_part_geometry(
    part_id: uuid.UUID,
    payload: PartGeometryUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> PartGeometryOut:
    """Set manual geometry dims (math/unit auto-evaluated server-side, stored metric).

    Partial: only provided fields change; ``null`` clears one. Each value is parsed by
    the safe evaluator (never ``eval()``) — bad math or a negative is a clean 422."""
    part = await _get_part_or_404(session, part_id, for_update=True)
    geom = await _get_or_create_geometry(session, part)
    overrides = dict(geom.overrides or {})
    unit = payload.unit
    # Length/area/volume follow the IN/MM toggle; weight is mass (grams).
    evaluators: dict[str, tuple[Any, str]] = {
        **{f: (partial(evaluate_length, default_unit=unit), unit) for f in _LENGTH_DIMS},
        "area": (partial(evaluate_area, default_unit=unit), unit),
        "volume": (partial(evaluate_volume, default_unit=unit), unit),
        "weight": (partial(evaluate_mass, default_unit="g"), "g"),
    }
    try:
        for field, (evaluator, unit_label) in evaluators.items():
            if field in payload.model_fields_set:
                _apply_dim(geom, overrides, field, getattr(payload, field), evaluator, unit_label)
    except DimensionError as exc:
        raise AppError("invalid_dimension", str(exc), status_code=422) from exc
    geom.overrides = overrides
    await session.flush()
    return _geometry_out(part_id, geom)


# --------------------------------------------------------------------------- #
# BOM tree (M1.5: single root node; M4 grows depth)
# --------------------------------------------------------------------------- #
@parts_router.get("/{part_id}/bom")
async def get_part_bom(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BomNodeOut:
    """Return a part's BOM tree (the hierarchy rooted at its root node)."""
    await _get_part_or_404(session, part_id)
    tree = await build_bom_tree(session, part_id)
    if tree is None:
        raise AppError("not_found", "No BOM tree for this part.", status_code=404)
    return tree


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


@parts_router.post("/{part_id}/files/{file_id}/redacted-copy", status_code=status.HTTP_201_CREATED)
async def create_redacted_copy(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    file: Annotated[UploadFile, File()],
) -> PartFileOut:
    """Store the viewer-rendered redacted copy of a PDF (M2.4, spec
    #pdf-capabilities Redact: "saves a NEW supporting file — original
    retained"). The client rasterizes affected pages so redacted content is
    irrecoverable in the copy; this endpoint never touches the source blob
    or the PRIMARY assignment, and flags the copy ``is_redacted`` so the M6
    external-share scoping can key on it."""
    await _get_part_or_404(session, part_id, for_update=True)
    source = await _get_part_file_or_404(session, part_id, file_id)
    if not source.filename.lower().endswith(".pdf"):
        raise AppError(
            "unsupported_file_type",
            "Redacted copies exist for PDF prints only.",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    if _received_size(file) > settings.max_upload_bytes:
        raise AppError(
            "file_too_large",
            f"File exceeds the {settings.max_upload_mb} MB limit.",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )
    header = await file.read(MAGIC_SNIFF_BYTES)
    await file.seek(0)
    if not header.startswith(b"%PDF-"):
        raise AppError(
            "file_type_mismatch",
            "The redacted copy is not a valid PDF.",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    stem = source.filename[: -len(".pdf")]
    name = _safe_filename(f"{stem}-redacted.pdf")
    new_id = uuid.uuid4()
    key = object_key(principal.active_org_id, part_id, new_id, name)
    size = await storage.put(key, file.file, content_type="application/pdf")
    try:
        row = PartFile(
            id=new_id,
            org_id=principal.active_org_id,
            part_id=part_id,
            storage_key=key,
            filename=name,
            file_type=source.file_type,
            content_type="application/pdf",
            size_bytes=size,
            role=FileRole.supporting,
            is_redacted=True,
        )
        session.add(row)
        await session.flush()
    except Exception:
        await _discard_blobs(storage, [key])
        raise
    return _part_file_out(row)


# --------------------------------------------------------------------------- #
# Annotation layer (M2.2, spec #pdf-capabilities Annotate/Shapes)
# --------------------------------------------------------------------------- #
# Caps logged in DECISIONS.md 2026-07-12 (annotation-layer bounds).
_MAX_ANNOTATION_OBJECTS = 2000
_MAX_ANNOTATION_OBJECT_BYTES = 20_000  # bounds freehand point clouds / text blobs

_ANNOTATION_TYPES = frozenset(
    {
        "underline",
        "highlight",
        "rectangle",
        "free_text",
        "freehand_highlight",
        "freehand",
        "note",
        "squiggly",
        "strikeout",
        "shape_rectangle",
        "line",
        "polyline",
        "arrow",
        "arc",
        "ellipse",
        "polygon",
    }
)


class AnnotationObject(BaseModel):
    """One markup object, validated at the edge (Pydantic v2 per §5) —
    the shape mirrors the viewer's Annotation type."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=64)]
    page: Annotated[int, Field(ge=1)]
    type: str
    style: dict[str, Any]
    rect: dict[str, float] | None = None
    points: list[dict[str, float]] | None = None
    at: dict[str, float] | None = None
    text: Annotated[str | None, Field(max_length=10_000)] = None

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in _ANNOTATION_TYPES:
            raise ValueError(f"unknown annotation type {value!r}")
        return value


class AnnotationLayerPayload(BaseModel):
    """The viewer's whole markup layer — replaced atomically on save."""

    model_config = ConfigDict(extra="forbid")

    objects: Annotated[list[AnnotationObject], Field(max_length=_MAX_ANNOTATION_OBJECTS)]

    @field_validator("objects")
    @classmethod
    def _bound_object_size(cls, objects: list[AnnotationObject]) -> list[AnnotationObject]:
        for obj in objects:
            if len(json.dumps(obj.model_dump(exclude_none=True))) > _MAX_ANNOTATION_OBJECT_BYTES:
                raise ValueError("annotation object exceeds the size bound")
        return objects


@parts_router.get("/{part_id}/files/{file_id}/annotations")
async def get_annotation_layer(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Any:
    await _get_part_file_or_404(session, part_id, file_id)
    layer = await session.scalar(
        select(FileAnnotationLayer).where(FileAnnotationLayer.part_file_id == file_id)
    )
    return layer.data if layer is not None else {"objects": []}


@parts_router.put("/{part_id}/files/{file_id}/annotations")
async def put_annotation_layer(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: AnnotationLayerPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    """Persist the layer (upsert; the viewer saves the whole document)."""
    await _get_part_file_or_404(session, part_id, file_id)
    data = {"objects": [obj.model_dump(exclude_none=True) for obj in payload.objects]}
    # atomic upsert — concurrent first saves must not race the unique key
    await session.execute(
        pg_insert(FileAnnotationLayer)
        .values(org_id=principal.active_org_id, part_file_id=file_id, data=data)
        .on_conflict_do_update(index_elements=["part_file_id"], set_={"data": data})
    )
    await session.flush()
    return data


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
