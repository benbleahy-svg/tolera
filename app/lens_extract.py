"""Lens extraction task + HTTP surface (M3.1 — spec ``#lens-engine`` / ``#lens-finding``).

Follows the M2.5 split pattern end-to-end (DECISIONS.md 2026-07-15: job polling
stays feature-scoped): the POST validates at the edge and enqueues a Celery
task — long work never blocks a request (CLAUDE.md §5); the task runs under the
caller's org via ``org_scoped_session`` (RLS holds in the worker); the status
GET resolves the file through the org-scoped session and requires the task meta
to name this file, so a guessed task id never leaks cross-org.

Two invariants are enforced HERE, before any model is involved:

* **EU routing / export control** (spec ``#lens-models``, ``#ai-settings``): a
  part flagged ``export_controlled`` (EU dual-use — DECISIONS.md 2026-06-26) is
  rejected at the POST edge *and* re-checked inside the task — zero provider
  calls either way; the file never leaves the DPA region.
* **Replace-suggested re-run semantics** (CLAUDE.md §5 never-destroy-human-
  input): a new run deletes only prior ``suggested`` rows for the file;
  accepted/rejected/edited rows are human decisions and survive.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, cast

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .celery_app import celery_app
from .db import make_engine, make_sessionmaker, org_scoped_session
from .deps import get_session, get_storage
from .errors import AppError
from .export_control import record_ai_skip, record_ai_skip_standalone
from .lens import NotExtractableError, extract_page_texts, run_document_extraction
from .lens_provider import LensProviderError
from .lens_provider import resolve as resolve_lens_provider
from .models import (
    ExportControlSubject,
    ExtractionFinding,
    FindingStatus,
    Part,
    PartFile,
)
from .parts import _get_part_file_or_404
from .storage import ObjectStorage
from .task_resources import resolve as resolve_task_resources
from .tasks import BaseTask

logger = logging.getLogger("app.lens_extract")

extract_router = APIRouter(prefix="/api/parts", tags=["lens"])


class SourceFileGoneError(Exception):
    """The file vanished between enqueue and run (hard-deleted meanwhile)."""


async def _read_blob(storage: ObjectStorage, key: str) -> bytes:
    return b"".join([chunk async for chunk in storage.stream(key)])


def _confidence(value: float) -> Decimal:
    """Clamp-free quantization to the column's numeric(5,4) — the RawFinding
    validator already bounds it to [0, 1]."""
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


async def run_extraction(
    db_url: str,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    part_id: uuid.UUID,
    file_id: uuid.UUID,
) -> dict[str, Any]:
    """Run the two-pass extraction and persist findings — the task's core.

    All rows commit in one transaction: delete-prior-suggested + inserts are
    all-or-nothing, so a retry starts clean and never half-replaces a run.
    """
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        async with org_scoped_session(sessionmaker, org_id) as session:
            pf = await session.get(PartFile, file_id)
            if pf is None or pf.part_id != part_id:
                raise SourceFileGoneError("source file no longer exists")
            part = await session.get(Part, pf.part_id)
            # Restricted path (defence in depth behind the POST-edge check —
            # the flag may have been set between enqueue and run): flagged
            # files are skipped BEFORE any bytes leave for a provider.
            if part is not None and part.export_controlled:
                # M6.9: record the refusal against the FILE — this path is about
                # a specific document's bytes, and "which prints were withheld"
                # is the question an export-control audit actually asks.
                await record_ai_skip(
                    session,
                    org_id=org_id,
                    subject_type=ExportControlSubject.part_file,
                    subject_id=file_id,
                    route="lens_extract.worker",
                )
                return {
                    "skipped": True,
                    "reason": "export_controlled",
                    "org_id": str(org_id),
                    "file_id": str(file_id),
                }

            pdf = await _read_blob(storage, pf.storage_key)
            provider = resolve_lens_provider()
            result = await run_document_extraction(provider, pdf)

            # Serialize concurrent runs on the same file (double-click POST →
            # two workers): without this, B's delete can run before A's inserts
            # commit and BOTH suggested sets survive — breaking the
            # replace-suggested contract (ship-review). Held until commit.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"lens_extract:{file_id}"},
            )
            # Replace prior *suggested* rows only (human-touched rows survive).
            await session.execute(
                delete(ExtractionFinding).where(
                    ExtractionFinding.source_file_id == file_id,
                    ExtractionFinding.status == FindingStatus.suggested,
                )
            )
            finding_ids: list[str] = []
            for f in result.findings:
                row = ExtractionFinding(
                    id=uuid.uuid4(),
                    org_id=org_id,
                    source_file_id=file_id,
                    page=f.page,
                    category=f.category,
                    type=f.type,
                    raw_text=f.raw_text,
                    value=f.value,
                    normalized_value=f.normalized_value,
                    units=f.units,
                    tolerance=f.tolerance.model_dump() if f.tolerance else None,
                    role=f.role,
                    gdt=f.gdt.model_dump() if f.gdt else None,
                    bbox=f.bbox.model_dump() if f.bbox else None,
                    confidence=_confidence(f.confidence),
                )
                session.add(row)
                finding_ids.append(str(row.id))
        # Transaction committed on clean context exit.
        return {
            "skipped": False,
            "finding_ids": finding_ids,
            "finding_count": len(finding_ids),
            "dropped_count": result.dropped_count,
            "pages_analyzed": result.pages_analyzed,
            "org_id": str(org_id),
            "file_id": str(file_id),
        }
    finally:
        await engine.dispose()


def _run_on_own_loop(coro: Any) -> Any:
    """Run ``coro`` whether or not a loop is running (worker vs eager tests) —
    the M2.5 pattern (see ``file_split._run_on_own_loop``)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# Time limit overrides the global 300 s: a 10-print-page document makes up to
# 12 sequential vision-model calls (quote-setup + classify + 10 pages), which
# a realistic drawing pack cannot finish in 5 minutes (ship-review).
@celery_app.task(
    base=BaseTask, name="app.lens_extract", bind=True, soft_time_limit=1500, time_limit=1800
)
def lens_extract_task(self: Any, org_id: str, part_id: str, file_id: str) -> dict[str, Any]:
    """Celery wrapper around :func:`run_extraction` (idempotent, §5)."""
    binding = {"org_id": org_id, "file_id": file_id}
    task_id = self.request.id
    # Redelivery guard: a worker dying after commit but before ack redelivers —
    # return the stored SUCCESS instead of minting a duplicate finding set.
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    try:
        result = _run_on_own_loop(
            run_extraction(
                *resolve_task_resources(),
                org_id=uuid.UUID(org_id),
                part_id=uuid.UUID(part_id),
                file_id=uuid.UUID(file_id),
            )
        )
    except (NotExtractableError, LensProviderError, SourceFileGoneError) as exc:
        # Deterministic rejections RETURN a bound failure dict (never retry,
        # never Celery-FAILURE — that state's payload can't carry the binding).
        if isinstance(exc, NotExtractableError | LensProviderError):
            code = exc.code
        else:
            code = "source_file_gone"
        logger.info(
            "lens_extract_rejected",
            extra={"code": code, "task_id": task_id, "part_id": part_id, **binding},
        )
        return {"failed": True, "error_code": code, **binding}
    out = cast("dict[str, Any]", result)
    # Counts + ids only — findings carry customer print content (§5 logging).
    logger.info(
        "lens_extract_completed",
        extra={
            "part_id": part_id,
            "task_id": task_id,
            "skipped": out.get("skipped"),
            "finding_count": out.get("finding_count", 0),
            "dropped_count": out.get("dropped_count", 0),
            **binding,
        },
    )
    # M3.8 §6.1: "after AI/interrogation finishes, matching rules create review
    # items". Extraction is what changes the data the rules read, so it is what
    # re-runs them. Chained *after* run_extraction's commit — the generator opens
    # its own session and must see the findings. Only on the real success path:
    # a `skipped` (nothing extractable) or `failed` return changed no findings.
    # Dispatched best-effort: review items are derived data, so a broker hiccup
    # must not fail an extraction that already committed (a later upload, or the
    # panel's refresh, regenerates them).
    if not out.get("skipped") and not out.get("failed"):
        try:
            from .review_items import review_items_generate_task

            review_items_generate_task.delay(org_id, part_id)
        except Exception:  # never fail an extraction that already committed
            logger.warning("review_items_dispatch_failed", extra={"part_id": part_id, **binding})
    return {**out, **binding}


# --------------------------------------------------------------------------- #
# HTTP contract (feature-scoped — DECISIONS.md 2026-07-15)
# --------------------------------------------------------------------------- #
class ExtractAccepted(BaseModel):
    """202 body: the handle the client polls."""

    task_id: str


class ExtractError(BaseModel):
    code: str
    message: str


class ExtractStatusOut(BaseModel):
    """Task state: ``skipped`` is the export-control restricted path — a
    non-error outcome (the panel falls back to manual entry)."""

    state: str  # queued | in_progress | succeeded | skipped | failed
    finding_count: int | None = None
    dropped_count: int | None = None
    error: ExtractError | None = None


class FindingOut(BaseModel):
    """One persisted finding, as M3.2's panel will consume it."""

    id: uuid.UUID
    source_file_id: uuid.UUID | None
    component_id: uuid.UUID | None
    page: int | None
    category: str
    type: str
    raw_text: str | None
    value: str | None
    normalized_value: str | None
    units: str | None
    tolerance: dict[str, Any] | None
    role: str | None
    gdt: dict[str, Any] | None
    bbox: dict[str, Any] | None
    confidence: float
    status: str


async def _get_part_and_file_or_404(
    session: AsyncSession, part_id: uuid.UUID, file_id: uuid.UUID
) -> tuple[Part, PartFile]:
    pf = await _get_part_file_or_404(session, part_id, file_id)
    part = await session.get(Part, part_id)
    if part is None:  # unreachable while the FK holds; belt for the type checker
        raise AppError("not_found", "Part not found.", status_code=status.HTTP_404_NOT_FOUND)
    return part, pf


@extract_router.post("/{part_id}/files/{file_id}/extract", status_code=status.HTTP_202_ACCEPTED)
async def extract_part_file(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ExtractAccepted:
    """Validate at the edge and enqueue the extraction (202 + task id)."""
    part, pf = await _get_part_and_file_or_404(session, part_id, file_id)
    if part.export_controlled:
        # Restricted path (no-external-LLM mode, v1): the print must not leave
        # the DPA region, so extraction is refused outright — manual entry.
        # M6.9: audited in its OWN committed transaction. ``org_scoped_session``
        # rolls back on error, so an entry added to ``session`` here would vanish
        # with the 422 — and the refusal is precisely what must be on record.
        await record_ai_skip_standalone(
            request.app.state.sessionmaker,
            org_id=principal.active_org_id,
            subject_type=ExportControlSubject.part_file,
            subject_id=file_id,
            route="lens_extract.request",
            actor_user_id=principal.user_id,
        )
        raise AppError(
            "export_controlled",
            "Dieses Teil ist als exportkontrolliert markiert — KI-Extraktion ist "
            "deaktiviert; Felder bitte manuell erfassen.",
            status_code=422,
        )
    try:
        extract_page_texts(await _read_blob(storage, pf.storage_key))
    except NotExtractableError as exc:
        raise AppError(
            "not_extractable",
            "Aus dieser Datei kann kein Text extrahiert werden (kein durchsuchbares PDF).",
            status_code=422,
        ) from exc
    task = lens_extract_task.delay(str(principal.active_org_id), str(part_id), str(file_id))
    return ExtractAccepted(task_id=task.id)


def _status_from_result(result: AsyncResult, file_id: uuid.UUID) -> ExtractStatusOut:
    """Map Celery state onto the contract, binding task meta to this file."""
    state = result.state
    info = result.info
    if isinstance(info, dict) and info.get("file_id") != str(file_id):
        # Real task id, another file/task type (possibly another org): same
        # answer as an unknown id. Strict key-required binding (tighter than
        # the M2.5 form) — every dict this task stores carries file_id.
        raise AppError("not_found", "Task not found.", status_code=status.HTTP_404_NOT_FOUND)
    if state == "SUCCESS" and not isinstance(info, dict):
        # A foreign task's plain return value — unbindable, answer as unknown.
        raise AppError("not_found", "Task not found.", status_code=status.HTTP_404_NOT_FOUND)
    if state == "SUCCESS":
        if info.get("failed"):
            return ExtractStatusOut(
                state="failed",
                error=ExtractError(
                    code=info.get("error_code", "extract_failed"), message="Extraction failed."
                ),
            )
        if info.get("skipped"):
            return ExtractStatusOut(state="skipped", finding_count=0, dropped_count=0)
        return ExtractStatusOut(
            state="succeeded",
            finding_count=info.get("finding_count", 0),
            dropped_count=info.get("dropped_count", 0),
        )
    if state == "FAILURE":
        # Only transient/infra deaths land here; nothing bindable to expose.
        return ExtractStatusOut(
            state="failed", error=ExtractError(code="extract_failed", message="Extraction failed.")
        )
    if state in ("STARTED", "PROGRESS", "RETRY"):
        return ExtractStatusOut(state="in_progress")
    return ExtractStatusOut(state="queued")  # PENDING: not started (or unknown id)


@extract_router.get("/{part_id}/files/{file_id}/extract/{task_id}")
async def extract_status(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    task_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExtractStatusOut:
    """Poll an extraction task. Session-only (read semantics, M2.5 precedent);
    the org/file gate 404s cross-org before any task state is consulted."""
    await _get_part_file_or_404(session, part_id, file_id)
    return _status_from_result(AsyncResult(task_id, app=celery_app), file_id)


@extract_router.get("/{part_id}/files/{file_id}/findings")
async def list_findings(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[FindingOut]:
    """The file's persisted findings (suggestions + human-resolved) — the read
    surface M3.2's Found-in-Files panel consumes. Org-scoped via RLS."""
    await _get_part_file_or_404(session, part_id, file_id)
    rows = (
        (
            await session.execute(
                select(ExtractionFinding)
                .where(ExtractionFinding.source_file_id == file_id)
                .order_by(ExtractionFinding.page, ExtractionFinding.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        FindingOut(
            id=row.id,
            source_file_id=row.source_file_id,
            component_id=row.component_id,
            page=row.page,
            category=row.category.value,
            type=row.type,
            raw_text=row.raw_text,
            value=row.value,
            normalized_value=row.normalized_value,
            units=row.units,
            tolerance=row.tolerance,
            role=row.role,
            gdt=row.gdt,
            bbox=row.bbox,
            confidence=float(row.confidence),
            status=row.status.value,
        )
        for row in rows
    ]
