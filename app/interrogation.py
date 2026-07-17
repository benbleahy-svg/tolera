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
weight. ``inputs_hash`` = the org default profile's fingerprint (M4.7); the
material-specific most-specific resolution arrives with M4.8.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
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
from .geometry import RECOGNIZED_FAMILIES
from .geometry.vector import build_geometry_vector
from .models import (
    Component,
    CustomInterrogation,
    CustomInterrogationOperationDef,
    InterrogationRun,
    InterrogationStatus,
    Material,
    MaterialFamily,
    OperationDef,
    Part,
    PartFile,
    PartGeometry,
    Process,
    ProcessFamily,
    ProcessOperation,
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


async def resolve_part_family(session: AsyncSession, part_id: uuid.UUID) -> str | None:
    """The part's unambiguous recognizer family, if any (M4.2 — the
    ``resolve_part_material_id`` precedent): exactly one distinct
    recognizer-backed process family across its quote components → that one;
    zero or several → ``None`` (the dims-only pass, never a guessed family)."""
    rows = (
        await session.scalars(
            select(Process.family)
            .join(Component, Component.process_id == Process.id)
            .where(Component.part_id == part_id)
            .distinct()
        )
    ).all()
    families = [str(f) for f in rows if str(f) in RECOGNIZED_FAMILIES]
    return families[0] if len(families) == 1 else None


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
    not fail the request — the run stays ``queued``). TODO(M4.2+): a staleness
    sweep for runs stranded ``queued``/``running`` by a broker outage or a
    retry-exhausted worker crash; until then the manual re-trigger is the
    recovery path."""
    if material_id is None:
        material_id = await resolve_part_material_id(session, part.id)
    if family is None:
        family = await resolve_part_family(session, part.id)
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


async def maybe_enqueue_for_process(
    session: AsyncSession, component: Component
) -> InterrogationRun | None:
    """Spec ``#sheetmetal``: "When a sheet-metal process is set, an
    interrogation block shows the auto-detected flat pattern + attributes" —
    assigning a recognizer-family process (re-)interrogates the part's PRIMARY
    CAD with that family. Skips when an equivalent run for (part, file, family)
    already exists, so re-assignments never pile up duplicate jobs."""
    if component.process_id is None:
        return None
    family = await session.scalar(select(Process.family).where(Process.id == component.process_id))
    if family is None or str(family) not in RECOGNIZED_FAMILIES:
        return None
    part = await session.get(Part, component.part_id)
    if part is None or part.deleted_at is not None or part.primary_file_id is None:
        return None
    pf = await session.get(PartFile, part.primary_file_id)
    if pf is None or FileCategory(pf.file_type) != FileCategory.brep_cad:
        return None
    # A queued run resolves the CURRENT profile when it executes — but with
    # the material frozen on its own row (M4.8), so an in-flight run only
    # covers this trigger when it carries the part's CURRENT material;
    # otherwise a material switch under a queued/running run would leave the
    # old material's thresholds standing with no successor. A run under a
    # just-edited profile's predecessor stays accepted (its fingerprint isn't
    # visible mid-flight; matching on it would double-enqueue every in-flight
    # run — the duplicate-dispatch pile-up this dedupe prevents), and once it
    # commits the next trigger sees the hash mismatch below and re-runs. A
    # succeeded run only counts if it was computed under the current profile
    # inputs — otherwise a threshold/toggle/link edit would keep serving stale
    # warnings on re-assignment (M4.7; material-specific resolution M4.8).
    current_material_id = await resolve_part_material_id(session, part.id)
    current_fp = inputs_fingerprint(
        await resolve_interrogation_inputs(
            session,
            family=str(family),
            material_id=current_material_id,
            part_id=part.id,
        )
    )
    existing = await session.scalar(
        select(InterrogationRun.id)
        .where(
            InterrogationRun.part_id == part.id,
            InterrogationRun.file_id == pf.id,
            InterrogationRun.family == str(family),
            (
                InterrogationRun.status.in_(
                    [InterrogationStatus.queued, InterrogationStatus.running]
                )
                & InterrogationRun.material_id.is_not_distinct_from(current_material_id)
            )
            | (
                (InterrogationRun.status == InterrogationStatus.succeeded)
                & (InterrogationRun.inputs_hash == current_fp)
            ),
        )
        .limit(1)
    )
    if existing is not None:
        return None
    return await enqueue_interrogation(session, part=part, file=pf, family=str(family))


async def clear_extracted_geometry(session: AsyncSession, part: Part) -> None:
    """Drop the extraction when the PRIMARY changes: the old file's signature
    and dims no longer describe this part. Manual overrides survive (they are
    the human's, not the file's); a queued run for the new PRIMARY refills the
    raw side on success — and a non-CAD PRIMARY simply has no geometry."""
    part.geom_hash = None
    # The similarity vector describes the old PRIMARY too — a stale one would
    # keep serving this part as a "similar geometry" match (M4.11).
    part.geometry_vector = None
    geom = await session.scalar(select(PartGeometry).where(PartGeometry.part_id == part.id))
    if geom is None:
        return
    overrides = geom.overrides or {}
    for field in _ALL_FIELDS:
        if field not in overrides:
            setattr(geom, field, None)
    geom.raw = None


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


def inputs_fingerprint(inputs: dict[str, Any] | None) -> str:
    """Canonical hash of a resolved ``InterrogationInputs`` set — the
    ``inputs_hash`` leg of the §5.4 cache key. Empty/None -> ``''`` (the
    engine-defaults sentinel every pre-M4.7 run carries)."""
    if not inputs:
        return ""
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_most_specific(
    candidates: Sequence[Any],
    *,
    material_id: uuid.UUID | None,
    material_family_id: uuid.UUID | None,
    material_class_id: uuid.UUID | None,
    op_links: Mapping[uuid.UUID, AbstractSet[uuid.UUID]],
    process_operation_def_ids: AbstractSet[uuid.UUID],
) -> Any | None:
    """The §4 MOST-SPECIFIC pick over a family's ``CustomInterrogation`` rows.

    Material rank per row = its most specific link on the part's material
    chain: material (3) > family (2) > class (1) > the org default (0); a row
    whose links all miss the chain is no candidate, and an unlinked row ranks
    0 only when it IS the default or enters via an op match. Op-def links
    (``op_links``: profile id → linked op-def ids) are an eligibility filter —
    an op-linked row is a candidate only when the part's process routing
    contains one of its ops — and an op match outranks the bare default at
    equal material rank (ASSUMED: filter-not-rank, KB is silent). Ties break
    oldest-first then by id, so re-resolution is deterministic (ASSUMED —
    acceptance requires determinism, no source names the ordering).
    """
    best: Any | None = None
    best_key: tuple[int, bool, float, str] | None = None
    for row in candidates:
        linked_ops = op_links.get(row.id, frozenset())
        if linked_ops and not (linked_ops & process_operation_def_ids):
            continue
        has_material_links = (
            row.material_id is not None
            or row.material_family_id is not None
            or row.material_class_id is not None
        )
        if not has_material_links:
            # Rank 0 is the org DEFAULT's slot. An unlinked non-default
            # profile (authoring in progress, or a viewer-pick bundle à la
            # the KB Laser/Punch example) must not silently compete with it —
            # it becomes auto-resolvable only through an op-def match.
            if not row.is_default and not linked_ops:
                continue
            rank = 0
        elif row.material_id is not None and row.material_id == material_id:
            rank = 3
        elif row.material_family_id is not None and row.material_family_id == material_family_id:
            rank = 2
        elif row.material_class_id is not None and row.material_class_id == material_class_id:
            rank = 1
        else:
            continue
        # Negate the tie-breakers so one max() comparison prefers OLDEST.
        key = (rank, bool(linked_ops), -row.created_at.timestamp(), str(row.id))
        if best_key is None or _key_beats(key, best_key):
            best, best_key = row, key
    return best


def _key_beats(a: tuple[int, bool, float, str], b: tuple[int, bool, float, str]) -> bool:
    # id descends lexicographically after the negated timestamp, so invert it:
    # higher rank / op-matched / older created_at / SMALLER id wins.
    return (a[0], a[1], a[2], _InvertedStr(a[3])) > (b[0], b[1], b[2], _InvertedStr(b[3]))


class _InvertedStr(str):
    """Orders descending under ``>`` — the smaller original string wins."""

    def __gt__(self, other: str) -> bool:
        return str.__lt__(self, other)


async def resolve_interrogation_inputs(
    session: AsyncSession,
    *,
    family: str,
    material_id: uuid.UUID | None,
    part_id: uuid.UUID | None,
) -> dict[str, Any] | None:
    """Resolve the ``InterrogationInputs`` the engine runs with (M4.8):
    the most-specific ``CustomInterrogation`` for the part's material among
    the org's rows for this family — or None (engine defaults) when the org
    has none that applies. Org scoping rides the session RLS.

    The material chain (family/class) comes from the run's material; the
    process-op context is every non-deleted op def routed by a process of
    this family on the part's quote components.
    """
    material_family_id: uuid.UUID | None = None
    material_class_id: uuid.UUID | None = None
    if material_id is not None:
        chain = (
            await session.execute(
                select(Material.family_id, MaterialFamily.class_id)
                .join(MaterialFamily, MaterialFamily.id == Material.family_id)
                .where(Material.id == material_id)
            )
        ).first()
        if chain is not None:
            material_family_id, material_class_id = chain
    process_op_ids: set[uuid.UUID] = set()
    if part_id is not None:
        process_op_ids = set(
            (
                await session.scalars(
                    select(ProcessOperation.operation_def_id)
                    .join(Process, Process.id == ProcessOperation.process_id)
                    .join(Component, Component.process_id == Process.id)
                    .join(OperationDef, OperationDef.id == ProcessOperation.operation_def_id)
                    .where(
                        Component.part_id == part_id,
                        Process.family == family,
                        Process.deleted_at.is_(None),
                        OperationDef.deleted_at.is_(None),
                    )
                    .distinct()
                )
            ).all()
        )
    profiles = (
        await session.scalars(
            select(CustomInterrogation).where(CustomInterrogation.family == family)
        )
    ).all()
    op_links: dict[uuid.UUID, set[uuid.UUID]] = {}
    if profiles:
        link_rows = (
            await session.execute(
                select(
                    CustomInterrogationOperationDef.custom_interrogation_id,
                    CustomInterrogationOperationDef.operation_def_id,
                ).where(
                    CustomInterrogationOperationDef.custom_interrogation_id.in_(
                        [p.id for p in profiles]
                    )
                )
            )
        ).all()
        for profile_id, op_def_id in link_rows:
            op_links.setdefault(profile_id, set()).add(op_def_id)
    winner = select_most_specific(
        profiles,
        material_id=material_id,
        material_family_id=material_family_id,
        material_class_id=material_class_id,
        op_links=op_links,
        process_operation_def_ids=process_op_ids,
    )
    return dict(winner.inputs) if winner is not None else None


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
            # Claim the run row FOR UPDATE before any work: Celery acks late, so
            # the broker may deliver the same run twice. The second delivery
            # blocks here until the first commits, then re-reads ``succeeded``
            # and skips — a committed success is never overwritten. A crash
            # redelivery (row left ``running``, lock long gone) reclaims it.
            run = await session.get(InterrogationRun, run_id, with_for_update=True)
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

            # M4.8: resolve the most-specific interrogation profile for this
            # family + the run's material (falling back to the org default,
            # then engine defaults) and stamp its hash BEFORE the cache probe,
            # so a threshold, toggle or link edit changes the cache key and
            # never serves a result computed under the old profile. No
            # applicable profile / no family -> engine defaults, hash stays ''.
            inputs: dict[str, Any] | None = None
            if run.family is not None:
                inputs = await resolve_interrogation_inputs(
                    session,
                    family=run.family,
                    material_id=run.material_id,
                    part_id=run.part_id,
                )
                run.inputs_hash = inputs_fingerprint(inputs)

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
                # Deep-enough copy: ``dimensions`` is mutated below (weight), and a
                # shallow dict would alias the cached run's stored JSON — any future
                # JSONB mutation-tracking would then rewrite the OLDER run's audit
                # copy with this run's density-derived weight.
                result = {**cached.result, "dimensions": dict(cached.result["dimensions"])}
                result.pop("cached_from", None)
                result["cached_from"] = str(cached.id)
            else:
                try:
                    analysis = geometry.analyze(
                        blob, family=run.family, density_g_cm3=density, inputs=inputs
                    )
                except MultiBodyError as exc:
                    return _fail(run, "multi_body", str(exc))
                except StepParseError as exc:
                    return _fail(run, "parse_error", str(exc))
                except GeometryError as exc:
                    return _fail(run, "internal", str(exc))
                result = asdict(analysis)
            # Weight is derived arithmetic — always recomputed from THIS run's
            # density so a cache hit can't carry another material's weight.
            dims = result["dimensions"]
            dims["weight"] = dims["volume"] / 1000.0 * density if density is not None else None

            # Lock the part before persisting: (a) serializes against a manual-dim
            # PATCH (which locks the same row) so an override committed mid-run is
            # never overwritten with raw; (b) lets us verify this run's file is
            # STILL the PRIMARY — a run for file A finishing after the PRIMARY
            # swapped to file B must not stamp A's geometry onto the part.
            part = await session.get(Part, run.part_id, with_for_update=True)
            if part is None or part.deleted_at is not None:
                return _fail(run, "part_gone", "The part was deleted before the run finished.")
            if part.primary_file_id != run.file_id:
                return _fail(
                    run, "superseded", "The PRIMARY file changed while this run was in flight."
                )
            run.result = result
            run.status = InterrogationStatus.succeeded
            run.finished_at = datetime.now(UTC)
            part.geom_hash = geom_hash
            # gv1 similarity vector (M4.11) — derived from the same result on
            # both the fresh and cache-hit paths, so a re-run can't go stale.
            part.geometry_vector = build_geometry_vector(result)
            await _apply_to_geometry(session, run, result)
            return {
                "run_id": str(run.id),
                "part_id": str(part.id),
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
    if out.get("status") == "succeeded" and out.get("part_id"):
        # M4.12: a fresh geometry signature may pair the part with a prior
        # quote (exact file/geometric match) — chain the requote-diff job,
        # which no-ops when there is no draft quote or no baseline.
        from .requote_diff import enqueue_requote_diff

        enqueue_requote_diff(uuid.UUID(org_id), uuid.UUID(out["part_id"]))
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
    #: fingerprint of the resolved profile inputs ('' = engine defaults)
    inputs_hash: str
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
        inputs_hash=run.inputs_hash,
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
    """The latest interrogation run for the part's CURRENT PRIMARY file.

    Scoped to ``part.primary_file_id`` so a swap to a different (or non-CAD)
    PRIMARY never keeps reporting the previous file's result — ``none`` until
    the new PRIMARY has a run of its own."""
    part = await _get_part_or_404(session, part_id)
    if part.primary_file_id is None:
        return InterrogationStatusOut(part_id=part_id, status="none", run=None)
    run = await session.scalar(
        select(InterrogationRun)
        .where(
            InterrogationRun.part_id == part_id,
            InterrogationRun.file_id == part.primary_file_id,
        )
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
            f"family must be one of {', '.join(sorted(f.value for f in ProcessFamily))}.",
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
