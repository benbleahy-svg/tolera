"""Interrogation jobs — GeometryService runs on part PRIMARY CAD files (M4.1).

The async slice of INTERROGATION-ENGINE-SPEC §5: a PRIMARY ``brep_cad`` upload
(or an explicit re-trigger) queues an :class:`~app.models.InterrogationRun`;
the Celery task parses the body behind the :mod:`app.geometry` boundary and
persists the dimensions extraction into ``part_geometry`` — filling ``raw`` and
refreshing only NON-overridden effective columns (calc-vs-override,
DECISIONS.md 2026-06-26) — plus the versioned signature onto ``part.geom_hash``.

Trigger paths (spec §1 / KB ``interrogations-basics``): the viewer/manual path
lives here and does NOT feed costing; the Kalk ``analyze_*()`` path arrives
with the per-family recognizers (M4.2+). Results are cached per
``(org, geom_hash, family, inputs_hash)`` (§5.4) — weight is always recomputed
from the caller's density, so a cached copy never smuggles another material's
weight. ``inputs_hash`` stays ``''`` until custom interrogations (M4.8).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .celery_app import celery_app
from .db import make_engine, make_sessionmaker, org_scoped_session, run_after_commit
from .deps import get_session
from .errors import AppError
from .file_types import FileCategory
from .models import (
    Component,
    InterrogationRun,
    InterrogationStatus,
    Material,
    Part,
    PartFile,
    PartGeometry,
    ProcessFamily,
)
from .storage import ObjectStorage
from .task_resources import resolve as resolve_task_resources
from .tasks import BaseTask

logger = logging.getLogger("app.interrogation")

interrogation_router = APIRouter(prefix="/api/parts", tags=["interrogation"])

_MB = 1024 * 1024

#: Ingest size gates per family (INTERROGATION-ENGINE-SPEC §5.1; KB
#: interrogations-basics limits table). ``None`` = ungated (Additive).
FAMILY_SIZE_LIMITS_BYTES: dict[str, int | None] = {
    ProcessFamily.MILLING: 20 * _MB,
    ProcessFamily.LATHE: 20 * _MB,
    ProcessFamily.WIRE_EDM: 20 * _MB,
    ProcessFamily.CAST_URETHANE: 20 * _MB,
    ProcessFamily.SHEET_METAL: 50 * _MB,
    ProcessFamily.TUBE_LASER: 50 * _MB,
    ProcessFamily.ADDITIVE: None,
}

#: The family-agnostic core-dims pass (M4.1: ``family`` is not known at upload
#: time) takes the permissive gate; M4.2+ applies the family's own limit.
DEFAULT_SIZE_LIMIT_BYTES: int | None = 50 * _MB

#: The PartGeometry columns an interrogation may refresh (catalog §1 + §2 weight).
_DIM_FIELDS = ("size_x", "size_y", "size_z", "max_dim", "med_dim", "min_dim")
_ALL_FIELDS = (*_DIM_FIELDS, "area", "volume", "weight")


def size_limit_bytes(family: str | None) -> int | None:
    if family is None:
        return DEFAULT_SIZE_LIMIT_BYTES
    return FAMILY_SIZE_LIMITS_BYTES.get(family, DEFAULT_SIZE_LIMIT_BYTES)


# --------------------------------------------------------------------------- #
# Enqueue (shared by the upload hook, the set-primary swap and the POST)
# --------------------------------------------------------------------------- #
async def resolve_part_material_id(session: AsyncSession, part_id: uuid.UUID) -> uuid.UUID | None:
    """The part's unambiguous material, if any: exactly one distinct material
    across its quote components → that one; zero or several → ``None`` (the
    engine never guesses a density)."""
    rows = (
        await session.scalars(
            select(Component.material_id)
            .where(Component.part_id == part_id, Component.material_id.is_not(None))
            .distinct()
        )
    ).all()
    return rows[0] if len(rows) == 1 else None


async def enqueue_interrogation(
    session: AsyncSession,
    *,
    part: Part,
    file: PartFile,
    family: str | None = None,
    material_id: uuid.UUID | None = None,
) -> InterrogationRun:
    """Create a queued run and hand it to Celery post-commit (the pdf_text
    precedent: a rolled-back request enqueues nothing; a broker outage must
    not fail the request — the run stays ``queued`` for a later sweep)."""
    if material_id is None:
        material_id = await resolve_part_material_id(session, part.id)
    run = InterrogationRun(
        org_id=part.org_id,
        part_id=part.id,
        file_id=file.id,
        family=family,
        material_id=material_id,
    )
    session.add(run)
    await session.flush()
    run_after_commit(session, partial(_enqueue_task, part.org_id, run.id))
    return run


async def maybe_enqueue_for_primary(
    session: AsyncSession, part: Part, file: PartFile
) -> InterrogationRun | None:
    """Auto-trigger when a ``brep_cad`` file is (now) the part's PRIMARY —
    the PRIMARY is the geometry source of truth (DECISIONS.md 2026-06-25)."""
    if part.primary_file_id != file.id or FileCategory(file.file_type) != FileCategory.brep_cad:
        return None
    return await enqueue_interrogation(session, part=part, file=file)


def _enqueue_task(org_id: uuid.UUID, run_id: uuid.UUID) -> None:
    try:
        interrogate_part_task.delay(str(org_id), str(run_id))
    except Exception:
        logger.warning(
            "interrogation_enqueue_failed",
            extra={"org_id": str(org_id), "run_id": str(run_id)},
            exc_info=True,
        )


# --------------------------------------------------------------------------- #
# The job core (runs org-scoped in the worker; RLS holds exactly as in a request)
# --------------------------------------------------------------------------- #
async def _read_blob(storage: ObjectStorage, key: str) -> bytes:
    return b"".join([chunk async for chunk in storage.stream(key)])


def _fail(run: InterrogationRun, code: str, detail: str) -> dict[str, Any]:
    run.status = InterrogationStatus.failed
    run.error_code = code
    run.error_detail = detail
    run.finished_at = datetime.now(UTC)
    return {"run_id": str(run.id), "status": "failed", "error_code": code}


def _rounded(value: float | None) -> Decimal | None:
    # 6 dp in mm/mm²/mm³/g = far below shop tolerance; keeps stored values readable.
    return None if value is None else Decimal(str(round(value, 6)))


async def _apply_to_geometry(
    session: AsyncSession, run: InterrogationRun, result: dict[str, Any]
) -> None:
    """Fill ``part_geometry.raw`` and refresh effective columns the human has
    NOT overridden (the M1.5 storage model: effective = COALESCE(override, raw))."""
    geom = await session.scalar(select(PartGeometry).where(PartGeometry.part_id == run.part_id))
    if geom is None:
        geom = PartGeometry(org_id=run.org_id, part_id=run.part_id, overrides={})
        session.add(geom)
        await session.flush()
    dims = result["dimensions"]
    overrides = geom.overrides or {}
    for field in _ALL_FIELDS:
        if field not in overrides:
            setattr(geom, field, _rounded(dims.get(field)))
    geom.raw = result


async def run_interrogation(
    db_url: str, storage: ObjectStorage, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict[str, Any]:
    """One interrogation job. Idempotent: a succeeded run is never redone; a
    failed/interrupted run re-runs to the same result (same body, same inputs)."""
    from .geometry import GeometryError, MultiBodyError, StepParseError, get_engine

    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        async with org_scoped_session(sessionmaker, org_id) as session:
            run = await session.get(InterrogationRun, run_id)
            if run is None:
                return {"skipped": "run_gone", "run_id": str(run_id)}
            if run.status == InterrogationStatus.succeeded:
                return {"skipped": "already_succeeded", "run_id": str(run_id)}
            pf = await session.get(PartFile, run.file_id)
            if pf is None:
                return _fail(run, "file_gone", "The CAD file was deleted before the run.")
            limit = size_limit_bytes(run.family)
            if limit is not None and pf.size_bytes > limit:
                return _fail(
                    run,
                    "file_too_large",
                    f"{pf.size_bytes} bytes exceeds the {limit}-byte interrogation gate.",
                )
            run.status = InterrogationStatus.running
            run.started_at = datetime.now(UTC)
            await session.flush()

            try:
                blob = await _read_blob(storage, pf.storage_key)
            except Exception:
                return _fail(run, "blob_gone", "The stored file could not be read.")

            density: float | None = None
            if run.material_id is not None:
                material = await session.get(Material, run.material_id)
                if material is not None and material.density is not None:
                    density = float(material.density)

            geometry = get_engine()
            try:
                geom_hash = geometry.compute_signature(blob)
            except MultiBodyError as exc:
                return _fail(run, "multi_body", str(exc))
            except StepParseError as exc:
                return _fail(run, "parse_error", str(exc))
            except GeometryError as exc:  # pragma: no cover — future engine errors
                return _fail(run, "internal", str(exc))
            run.geom_hash = geom_hash

            cached = await session.scalar(
                select(InterrogationRun)
                .where(
                    InterrogationRun.org_id == run.org_id,
                    InterrogationRun.id != run.id,
                    InterrogationRun.geom_hash == geom_hash,
                    InterrogationRun.family.is_not_distinct_from(run.family),
                    InterrogationRun.inputs_hash == run.inputs_hash,
                    InterrogationRun.status == InterrogationStatus.succeeded,
                    InterrogationRun.result.is_not(None),
                )
                .order_by(InterrogationRun.created_at)
                .limit(1)
            )
            if cached is not None and cached.result is not None:
                result = dict(cached.result)
                result.pop("cached_from", None)
                result["cached_from"] = str(cached.id)
            else:
                analysis = geometry.analyze(blob, family=run.family, density_g_cm3=density)
                result = asdict(analysis)
            # Weight is derived arithmetic — always recomputed from THIS run's
            # density so a cache hit can't carry another material's weight.
            dims = result["dimensions"]
            dims["weight"] = dims["volume"] / 1000.0 * density if density is not None else None

            run.result = result
            run.status = InterrogationStatus.succeeded
            run.finished_at = datetime.now(UTC)
            part = await session.get(Part, run.part_id)
            if part is not None:
                part.geom_hash = geom_hash
            await _apply_to_geometry(session, run, result)
            return {
                "run_id": str(run.id),
                "status": "succeeded",
                "cached": cached is not None,
            }
    finally:
        await engine.dispose()


def _run_on_own_loop(coro: Any) -> Any:
    """Worker process (no loop) → plain ``asyncio.run``; eager-in-request →
    a fresh loop on a helper thread (the file_split/part_index seam)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@celery_app.task(base=BaseTask, name="app.interrogate_part", bind=True)
def interrogate_part_task(self: Any, org_id: str, run_id: str) -> dict[str, Any]:
    """Celery wrapper around :func:`run_interrogation`."""
    result = _run_on_own_loop(
        run_interrogation(
            *resolve_task_resources(),
            org_id=uuid.UUID(org_id),
            run_id=uuid.UUID(run_id),
        )
    )
    out = cast("dict[str, Any]", result)
    # Structured completion log — ids only, never filenames or geometry values.
    logger.info("interrogation_finished", extra={"org_id": org_id, "run_id": run_id, **out})
    return out


# --------------------------------------------------------------------------- #
# API — status ("interrogating…") + manual re-trigger (viewer path)
# --------------------------------------------------------------------------- #
class InterrogationRunOut(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    file_id: uuid.UUID
    family: str | None
    material_id: uuid.UUID | None
    geom_hash: str | None
    status: str
    error_code: str | None
    error_detail: str | None
    result: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class InterrogationStatusOut(BaseModel):
    """The part view's interrogation state: ``none`` (no CAD/run yet) or the
    latest run's status — ``queued``/``running`` render as ``interrogating…``."""

    part_id: uuid.UUID
    status: str
    run: InterrogationRunOut | None


class InterrogateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: str | None = None
    material_id: uuid.UUID | None = None


async def _get_part_or_404(session: AsyncSession, part_id: uuid.UUID) -> Part:
    part = await session.get(Part, part_id)
    if part is None or part.deleted_at is not None:
        raise AppError("not_found", "Part not found.", status_code=status.HTTP_404_NOT_FOUND)
    return part


def _run_out(run: InterrogationRun) -> InterrogationRunOut:
    return InterrogationRunOut(
        id=run.id,
        part_id=run.part_id,
        file_id=run.file_id,
        family=run.family,
        material_id=run.material_id,
        geom_hash=run.geom_hash,
        status=run.status,
        error_code=run.error_code,
        error_detail=run.error_detail,
        result=run.result,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@interrogation_router.get("/{part_id}/interrogation")
async def get_interrogation_status(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InterrogationStatusOut:
    """The latest interrogation run for a part (``none`` when no run exists)."""
    await _get_part_or_404(session, part_id)
    run = await session.scalar(
        select(InterrogationRun)
        .where(InterrogationRun.part_id == part_id)
        .order_by(InterrogationRun.created_at.desc(), InterrogationRun.id.desc())
        .limit(1)
    )
    if run is None:
        return InterrogationStatusOut(part_id=part_id, status="none", run=None)
    return InterrogationStatusOut(part_id=part_id, status=run.status, run=_run_out(run))


@interrogation_router.post("/{part_id}/interrogate", status_code=status.HTTP_202_ACCEPTED)
async def trigger_interrogation(
    part_id: uuid.UUID,
    payload: InterrogateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> InterrogationStatusOut:
    """Manually (re-)interrogate a part's PRIMARY CAD file — the viewer
    trigger path (KB interrogations-basics): does not feed costing."""
    part = await _get_part_or_404(session, part_id)
    if payload.family is not None and payload.family not in set(ProcessFamily):
        raise AppError(
            "unknown_family",
            f"family must be one of {sorted(ProcessFamily)}.",
            status_code=422,
        )
    if part.primary_file_id is None:
        raise AppError(
            "no_primary_cad",
            "This part has no PRIMARY CAD file to interrogate.",
            status_code=422,
        )
    pf = await session.get(PartFile, part.primary_file_id)
    if pf is None or FileCategory(pf.file_type) != FileCategory.brep_cad:
        raise AppError(
            "no_primary_cad",
            "This part's PRIMARY file is not a CAD solid (STEP).",
            status_code=422,
        )
    if payload.material_id is not None:
        material = await session.get(Material, payload.material_id)
        if material is None:
            raise AppError(
                "unknown_material",
                "No such material in this organization.",
                status_code=422,
            )
    run = await enqueue_interrogation(
        session, part=part, file=pf, family=payload.family, material_id=payload.material_id
    )
    return InterrogationStatusOut(part_id=part_id, status=run.status, run=_run_out(run))
