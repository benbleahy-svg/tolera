"""Split PDF into single-page files (M2.5 — spec `#pdf-capabilities`, Pages).

The server-side sibling of the viewer's local page *Extract* (M2.1): splitting
persists one new **supporting** file per page on the same part, provenance-linked
via ``source_file_id``; the original stays byte-untouched and keeps its role.
Auto-bundling pages to distinct parts is M2.12; per-page interrogation is M4.

Flow (DECISIONS.md 2026-07-13): the POST validates the stored PDF at the edge
(1-page / non-PDF / corrupt / encrypted / over-ceiling → 422 envelope, nothing
persisted) and enqueues a Celery task — long work never blocks a request
(CLAUDE.md §5). The task writes page blobs, commits all rows in one transaction
(all-or-nothing; written blobs are discarded on failure), and reports progress
via task meta. The status GET is *feature-scoped* (`…/split/{task_id}`), not a
generic jobs API (OPEN in DECISIONS.md until M3 brings a second consumer); it
resolves the part file through the org-scoped session and additionally requires
the task meta to name this file, so a guessed task id never leaks cross-org.
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, cast

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .celery_app import celery_app
from .db import make_engine, make_sessionmaker, org_scoped_session
from .deps import get_session, get_storage
from .errors import AppError
from .models import FileRole, PartFile
from .part_index import extract_pdf_text, file_sha256, normalize_filename
from .parts import _discard_blobs, _get_part_file_or_404
from .pdf_split import PdfSplitError, split_pdf_pages, validate_pdf_split
from .storage import ObjectStorage, object_key
from .task_resources import resolve as resolve_task_resources
from .tasks import BaseTask

logger = logging.getLogger("app.file_split")

split_router = APIRouter(prefix="/api/parts", tags=["files"])


class SourceFileGoneError(Exception):
    """The source file vanished between enqueue and run (deleted meanwhile)."""


async def _read_blob(storage: ObjectStorage, key: str) -> bytes:
    return b"".join([chunk async for chunk in storage.stream(key)])


def _page_filename(source_name: str, page_no: int) -> str:
    """``halter.pdf`` → ``halter-p<N>.pdf`` (DECISIONS.md 2026-07-13 naming)."""
    stem = source_name[:-4] if source_name.lower().endswith(".pdf") else source_name
    return f"{stem}-p{page_no}.pdf"


async def run_split(
    db_url: str,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Split the stored PDF into per-page supporting files — the task's core.

    Runs under the caller's org via ``org_scoped_session`` (RLS holds in the
    worker exactly as in a request). All rows commit in one transaction; on any
    failure the already-written blobs are discarded, so a retry starts clean.
    """
    engine = make_engine(db_url)
    stored_keys: list[str] = []
    try:
        sessionmaker = make_sessionmaker(engine)
        async with org_scoped_session(sessionmaker, org_id) as session:
            pf = await session.get(PartFile, file_id)
            if pf is None or pf.part_id != part_id:
                raise SourceFileGoneError("source file no longer exists")
            pages = split_pdf_pages(await _read_blob(storage, pf.storage_key))
            total = len(pages)
            file_ids: list[str] = []
            for page_no, page_bytes in enumerate(pages, start=1):
                new_id = uuid.uuid4()
                name = _page_filename(pf.filename, page_no)
                key = object_key(org_id, part_id, new_id, name)
                size = await storage.put(
                    key, io.BytesIO(page_bytes), content_type="application/pdf"
                )
                stored_keys.append(key)
                session.add(
                    PartFile(
                        id=new_id,
                        org_id=org_id,
                        part_id=part_id,
                        storage_key=key,
                        filename=name,
                        file_type=pf.file_type,  # same category: a PDF print
                        content_type="application/pdf",
                        size_bytes=size,
                        role=FileRole.supporting,
                        source_file_id=file_id,
                        # Match-index fields (M2.12): pages are indexed like any
                        # upload — inline here, we already hold the bytes in a
                        # worker context (no second task round-trip).
                        file_hash=file_sha256(page_bytes),
                        filename_normalized=normalize_filename(name),
                        pdf_text=extract_pdf_text(page_bytes),
                    )
                )
                file_ids.append(str(new_id))
                if progress is not None:
                    progress(page_no, total)
        # Transaction committed on clean context exit.
        return {
            "file_ids": file_ids,
            "done": total,
            "total": total,
            "org_id": str(org_id),
            "file_id": str(file_id),
        }
    except Exception:
        await _discard_blobs(storage, stored_keys)
        raise
    finally:
        await engine.dispose()


def _run_on_own_loop(coro: Any) -> Any:
    """Run ``coro`` to completion whether or not a loop is already running.

    A worker process has no running loop → plain ``asyncio.run``. An *eager*
    task (tests) runs inside the API's event loop, where ``asyncio.run`` would
    raise — hand the coroutine its own loop on a throwaway thread instead."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@celery_app.task(base=BaseTask, name="app.split_pdf", bind=True)
def split_pdf_task(self: Any, org_id: str, part_id: str, file_id: str) -> dict[str, Any]:
    """Celery wrapper around :func:`run_split` with progress in the task meta."""
    binding = {"org_id": org_id, "file_id": file_id}
    # Captured up front: ``self.request`` is thread-local, and progress() may run
    # on another thread (eager mode hands the coroutine its own loop/thread).
    task_id = self.request.id
    # Redelivery guard (CLAUDE.md §5: tasks idempotent). With acks_late +
    # reject_on_worker_lost, a worker dying after the DB commit but before the
    # ack redelivers this task — if our own SUCCESS is already stored, return it
    # instead of minting a duplicate page set. (User re-runs get a fresh task id,
    # so DECISIONS.md 2026-07-13 "re-run adds another set" is unaffected.)
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)

    def progress(done: int, total: int) -> None:
        self.update_state(
            task_id=task_id, state="PROGRESS", meta={"done": done, "total": total, **binding}
        )

    try:
        result = _run_on_own_loop(
            run_split(
                *resolve_task_resources(),
                org_id=uuid.UUID(org_id),
                part_id=uuid.UUID(part_id),
                file_id=uuid.UUID(file_id),
                progress=progress,
            )
        )
    except (PdfSplitError, SourceFileGoneError) as exc:
        # Deterministic rejections neither retry nor raise: they RETURN a
        # failure dict that carries the org/file binding, so the status GET can
        # enforce task→file binding on failures too. Celery's FAILURE state
        # (whose payload is just the exception, unbindable) stays reserved for
        # transient/infra deaths that exhaust BaseTask's retries.
        code = exc.code if isinstance(exc, PdfSplitError) else "source_file_gone"
        logger.info(
            "pdf_split_rejected",
            extra={
                "org_id": org_id,
                "part_id": part_id,
                "source_file_id": file_id,
                "code": code,
                "task_id": task_id,
            },
        )
        return {"failed": True, "error_code": code, **binding}
    out = cast("dict[str, Any]", result)
    # Structured completion log (request-id lives on the enqueuing request; the
    # task carries the tenant ids). No filenames — they can carry customer data.
    logger.info(
        "pdf_split_completed",
        extra={
            "org_id": org_id,
            "part_id": part_id,
            "source_file_id": file_id,
            "pages": out["total"],
            "task_id": task_id,
        },
    )
    return out


# --------------------------------------------------------------------------- #
# HTTP contract
# --------------------------------------------------------------------------- #
class SplitAccepted(BaseModel):
    """202 body: the handle the viewer polls."""

    task_id: str


class SplitProgress(BaseModel):
    done: int
    total: int


class SplitError(BaseModel):
    """Terminal task failure as *state*, not an HTTP error — the GET itself is a
    200. Mirrors the §5 envelope's code/message fields so clients map it the
    same way; ``details`` is deliberately absent (nothing safe to carry)."""

    code: str
    message: str


class SplitStatusOut(BaseModel):
    """Task state as the viewer's progress/success toasts consume it."""

    state: str  # queued | in_progress | succeeded | failed
    progress: SplitProgress | None = None
    file_ids: list[str] | None = None
    error: SplitError | None = None


@split_router.post("/{part_id}/files/{file_id}/split", status_code=status.HTTP_202_ACCEPTED)
async def split_part_file(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> SplitAccepted:
    """Validate the stored PDF and enqueue the split (202 + task id)."""
    pf = await _get_part_file_or_404(session, part_id, file_id)
    try:
        validate_pdf_split(await _read_blob(storage, pf.storage_key))
    except PdfSplitError as exc:
        raise AppError(exc.code, str(exc), status_code=422) from exc
    task = split_pdf_task.delay(str(principal.active_org_id), str(part_id), str(file_id))
    return SplitAccepted(task_id=task.id)


def _status_from_result(result: AsyncResult, file_id: uuid.UUID) -> SplitStatusOut:
    """Map Celery task state onto the API contract, binding meta to this file."""
    state = result.state
    info = result.info  # meta dict for PROGRESS/SUCCESS; the exception for FAILURE
    if isinstance(info, dict) and info.get("file_id") not in (None, str(file_id)):
        # A real task id, but for another file (possibly another org): same
        # answer as an unknown id — no cross-file/cross-org reads.
        raise AppError("not_found", "Task not found.", status_code=status.HTTP_404_NOT_FOUND)
    if state == "SUCCESS":
        if info.get("failed"):
            # A deterministic rejection, returned as a bound dict by the task —
            # the file-binding check above already vetted it.
            return SplitStatusOut(
                state="failed",
                error=SplitError(
                    code=info.get("error_code", "split_failed"), message="Split failed."
                ),
            )
        return SplitStatusOut(
            state="succeeded",
            progress=SplitProgress(done=info["done"], total=info["total"]),
            file_ids=list(info["file_ids"]),
        )
    if state == "FAILURE":
        # Only transient/infra deaths land here (deterministic rejections return
        # bound dicts). The exception payload can't carry the file binding, so
        # expose nothing beyond a generic failure — no code, no exception text.
        return SplitStatusOut(
            state="failed", error=SplitError(code="split_failed", message="Split failed.")
        )
    if state in ("STARTED", "PROGRESS", "RETRY"):
        progress = (
            SplitProgress(done=info["done"], total=info["total"])
            if isinstance(info, dict) and "done" in info
            else None
        )
        return SplitStatusOut(state="in_progress", progress=progress)
    return SplitStatusOut(state="queued")  # PENDING: not started (or unknown id)


@split_router.get("/{part_id}/files/{file_id}/split/{task_id}")
async def split_status(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    task_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SplitStatusOut:
    """Poll a split task — drives the viewer's progress/success toasts.

    Deliberately session-only (no ``require``): reading split *status* matches
    the read semantics of file list/download, which any org member has; only
    the mutating POST needs ``quote_edit``."""
    await _get_part_file_or_404(session, part_id, file_id)  # org/file gate (404 cross-org)
    return _status_from_result(AsyncResult(task_id, app=celery_app), file_id)
