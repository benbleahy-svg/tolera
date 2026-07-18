"""Part-Library matching buckets + historical import (M2.12 — spec `#partlib`).

The "N Matching Parts" modal contract. Four buckets are computed on demand
(the spec's own alternative to a ``part_matches`` cache — indexed org-scoped
equality probes are cheap at this scale):

* **exact_file** — another part shares a ``file_hash`` (byte-identical upload);
* **file_name** — shares a ``filename_normalized`` stem;
* **part_number** — manual part# (``part.part_number``) or STEP-extracted
  ``part_number_extracted`` agree (case-insensitive);
* **historical** — identity match (part# or name) that has actually been
  quoted, with click-through refs to the prior quotes (the import source);
* **exact_geometric** (M4.11) — same ``gs1`` geometry signature
  (``part.geom_hash``, topology-tolerant per the M4.0 probe): the same
  manufactured geometry regardless of originating CAD/export;
* **similar_geometries** (M4.11) — pgvector L2 nearest-neighbour over the
  ``gv1`` scalar feature vector (``part.geometry_vector``) under the
  calibrated threshold; identical-signature parts are excluded ("similar"
  means non-identical, spec ``#partlib``). While a CAD subject's async
  interrogation is still queued/running the two geometry buckets report
  ``processing`` instead of a false empty result.

Selecting a match copies the historical router — the ``Operation`` rows with
their calc/manual pairs, Kalk ``cost_formula`` snapshots and
``variable_overrides`` — onto the current component and reprices. Manual
values keep winning via COALESCE, so the UI's yellow "source: manual"
highlight survives the copy. Per-quantity manual cell costs are NOT copied
(the target's quantity breaks are its own); add-ons are quote-level and stay.

RLS scopes every lookup to the active org; a foreign org's byte-identical
file must never surface (cross-org test-plan case).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .costing import recalculate_component
from .deps import get_session
from .errors import AppError
from .file_types import FileCategory, primary_rank
from .geometry.vector import SIMILAR_L2_THRESHOLD
from .models import (
    Component,
    FileRole,
    InterrogationRun,
    InterrogationStatus,
    Node,
    Operation,
    Part,
    PartFile,
    Quote,
    QuoteItem,
    ValueSource,
)
from .operations import ComponentCosting, _component_costing, _get_component_or_404
from .operations import _lock_editable_quote as _lock_editable_quote_of
from .parts import PartOut, _get_part_or_404, _part_out

library_router = APIRouter(prefix="/api", tags=["part-library"])

# Bucket order mirrors the PP modal (DemoB/09): file → geometric → name →
# part# → similar; Tolera's historical bucket (prior quotes by part#/name,
# the import source) closes the list.
_BUCKET_ORDER = (
    "exact_file",
    "exact_geometric",
    "file_name",
    "part_number",
    "similar_geometries",
    "historical",
)
_GEOMETRY_BUCKETS = {"exact_geometric", "similar_geometries"}

# Cards shown per bucket; the count still reports the full match total.
_BUCKET_CARD_CAP = 50
# Prior-quote refs per match card (latest first — the click-through links).
_QUOTE_REFS_PER_CARD = 5


class MatchQuoteRef(BaseModel):
    """One prior quote using the matched part — the import click-through."""

    quote_id: uuid.UUID
    number: str
    quote_item_id: uuid.UUID
    component_id: uuid.UUID


class MatchCard(BaseModel):
    part_id: uuid.UUID
    part_number: str | None
    revision: str | None
    name: str | None
    primary_filename: str | None
    archived: bool
    quote_count: int
    quotes: list[MatchQuoteRef]


class MatchBucket(BaseModel):
    key: str
    status: Literal["ready", "processing"]
    count: int
    matches: list[MatchCard]


class MatchSubject(BaseModel):
    """The part under inspection, as previewed at the left of the modal."""

    part_number: str | None
    revision: str | None
    name: str | None
    primary_filename: str | None


class MatchesOut(BaseModel):
    part_id: uuid.UUID
    subject: MatchSubject
    total: int
    buckets: list[MatchBucket]


async def _subject_keys(session: AsyncSession, part: Part) -> dict[str, set[str]]:
    """The subject's deterministic match keys, read from its files + identity."""
    rows = (
        await session.execute(
            select(
                PartFile.file_hash, PartFile.filename_normalized, PartFile.part_number_extracted
            ).where(PartFile.part_id == part.id)
        )
    ).all()
    hashes = {r[0] for r in rows if r[0]}
    names = {r[1] for r in rows if r[1]}
    part_numbers = {r[2].lower() for r in rows if r[2]}
    if part.part_number:
        part_numbers.add(part.part_number.lower())
    return {"hashes": hashes, "names": names, "part_numbers": part_numbers}


def _live_other_parts(subject_id: uuid.UUID) -> Any:
    """Filter fragment: candidate parts — not the subject, not deleted.

    Archived parts DO match (they are history and can be re-quoted, KB
    `navigate-and-manage-the-part-library`); deleted parts never do."""
    return (Part.id != subject_id) & (Part.deleted_at.is_(None))


async def _parts_with_file_key(
    session: AsyncSession, subject_id: uuid.UUID, column: Any, keys: set[str]
) -> list[uuid.UUID]:
    """Part ids owning a file whose ``column`` value is in ``keys``."""
    if not keys:
        return []
    stmt = (
        select(PartFile.part_id)
        .join(Part, Part.id == PartFile.part_id)
        .where(column.in_(keys), _live_other_parts(subject_id))
        .group_by(PartFile.part_id)
    )
    return list((await session.scalars(stmt)).all())


async def _parts_by_part_number(
    session: AsyncSession, subject_id: uuid.UUID, keys: set[str]
) -> list[uuid.UUID]:
    """Parts whose manual part# OR extracted file part# matches ``keys``."""
    if not keys:
        return []
    manual = select(Part.id).where(
        func.lower(Part.part_number).in_(keys), _live_other_parts(subject_id)
    )
    extracted = (
        select(PartFile.part_id)
        .join(Part, Part.id == PartFile.part_id)
        .where(func.lower(PartFile.part_number_extracted).in_(keys), _live_other_parts(subject_id))
    )
    ids = set((await session.scalars(manual)).all())
    ids.update((await session.scalars(extracted)).all())
    return list(ids)


async def _quote_refs(
    session: AsyncSession, part_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MatchQuoteRef]]:
    """Prior-quote references per part (latest first), via the 4-layer chain
    Part → Component → QuoteItem → Quote. Trashed quotes don't count."""
    if not part_ids:
        return {}
    rows = (
        await session.execute(
            select(
                Component.part_id,
                Quote.id,
                Quote.number,
                QuoteItem.id,
                Component.id,
            )
            .join(QuoteItem, QuoteItem.root_component_id == Component.id)
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .where(Component.part_id.in_(part_ids), Quote.deleted_at.is_(None))
            .order_by(Quote.created_at.desc(), QuoteItem.position)
        )
    ).all()
    refs: dict[uuid.UUID, list[MatchQuoteRef]] = {}
    for part_id, quote_id, number, item_id, component_id in rows:
        refs.setdefault(part_id, []).append(
            MatchQuoteRef(
                quote_id=quote_id,
                number=number,
                quote_item_id=item_id,
                component_id=component_id,
            )
        )
    return refs


async def _cards(session: AsyncSession, part_ids: list[uuid.UUID]) -> dict[uuid.UUID, MatchCard]:
    """Hydrate match cards (identity + primary filename + quote refs)."""
    if not part_ids:
        return {}
    parts = (await session.scalars(select(Part).where(Part.id.in_(part_ids)))).all()
    primary_rows = (
        await session.execute(
            select(PartFile.part_id, PartFile.filename).where(
                PartFile.part_id.in_(part_ids), PartFile.role == FileRole.primary
            )
        )
    ).all()
    primary_names: dict[uuid.UUID, str] = dict(tuple(row) for row in primary_rows)
    refs = await _quote_refs(session, part_ids)
    cards: dict[uuid.UUID, MatchCard] = {}
    for part in sorted(parts, key=lambda p: p.created_at, reverse=True):
        part_refs = refs.get(part.id, [])
        # quote_count = distinct quotes (an item list can repeat a quote).
        quote_count = len({r.quote_id for r in part_refs})
        cards[part.id] = MatchCard(
            part_id=part.id,
            part_number=part.part_number,
            revision=part.revision,
            name=part.name,
            primary_filename=primary_names.get(part.id),
            archived=part.archived_at is not None,
            quote_count=quote_count,
            quotes=part_refs[:_QUOTE_REFS_PER_CARD],
        )
    return cards


@library_router.get("/parts/{part_id}/matches")
async def get_part_matches(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MatchesOut:
    """The matching buckets for one part (the "N Matching Parts" modal)."""
    part = await _get_part_or_404(session, part_id)
    keys = await _subject_keys(session, part)

    exact_file = await _parts_with_file_key(session, part_id, PartFile.file_hash, keys["hashes"])
    file_name = await _parts_with_file_key(
        session, part_id, PartFile.filename_normalized, keys["names"]
    )
    part_number = await _parts_by_part_number(session, part_id, keys["part_numbers"])

    # Historical: identity match (part# or name) that has been quoted.
    identity_ids = set(part_number)
    if part.name:
        name_matches = (
            await session.scalars(
                select(Part.id).where(
                    func.lower(Part.name) == part.name.lower(), _live_other_parts(part_id)
                )
            )
        ).all()
        identity_ids.update(name_matches)
    refs = await _quote_refs(session, list(identity_ids))
    historical = [pid for pid in identity_ids if refs.get(pid)]

    # Geometry buckets (M4.11): signature equality + pgvector NN. RLS scopes
    # both probes to the active org like every other bucket.
    primary_file = None
    if part.primary_file_id is not None:
        primary_file = await session.get(PartFile, part.primary_file_id)
    exact_geometric: list[uuid.UUID] = []
    similar_geometries: list[uuid.UUID] = []
    geometry_processing = False
    if part.geom_hash is None:
        # A CAD PRIMARY without a signature: "processing" only while the
        # async job is actually queued/running — a failed run (multi-body,
        # parse error) reads as ready-and-empty, never a stuck spinner.
        is_cad = primary_file is not None and (
            FileCategory(primary_file.file_type) is FileCategory.brep_cad
        )
        if is_cad:
            run_status = await session.scalar(
                select(InterrogationRun.status)
                .where(InterrogationRun.part_id == part.id)
                .order_by(InterrogationRun.created_at.desc(), InterrogationRun.id.desc())
                .limit(1)
            )
            geometry_processing = run_status in (
                InterrogationStatus.queued,
                InterrogationStatus.running,
            )
    else:
        exact_geometric = list(
            (
                await session.scalars(
                    select(Part.id).where(
                        Part.geom_hash == part.geom_hash, _live_other_parts(part_id)
                    )
                )
            ).all()
        )
        if part.geometry_vector is not None:
            # If the planner takes the HNSW path, a plain ordered scan yields
            # at most ef_search candidates BEFORE the org/hash filters —
            # iterative scan (pgvector >= 0.8) keeps fetching until the LIMIT
            # is genuinely filled, so filtered recall doesn't degrade as other
            # tenants' vectors grow the table.
            await session.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
            distance = Part.geometry_vector.l2_distance(part.geometry_vector)
            similar_geometries = list(
                (
                    await session.scalars(
                        select(Part.id)
                        .where(
                            _live_other_parts(part_id),
                            Part.geometry_vector.is_not(None),
                            # "Similar" is non-identical — the twins live in
                            # exact_geometric (spec #partlib).
                            Part.geom_hash.is_distinct_from(part.geom_hash),
                            distance <= SIMILAR_L2_THRESHOLD,
                        )
                        .order_by(distance, Part.id)
                        # Bounded fuzzy bucket: count caps with the cards.
                        .limit(_BUCKET_CARD_CAP)
                    )
                ).all()
            )

    all_ids = list(
        {*exact_file, *file_name, *part_number, *historical, *exact_geometric, *similar_geometries}
    )
    cards = await _cards(session, all_ids)

    ready: dict[str, list[uuid.UUID]] = {
        "exact_file": exact_file,
        "exact_geometric": exact_geometric,
        "file_name": file_name,
        "part_number": part_number,
        "similar_geometries": similar_geometries,
        "historical": historical,
    }
    buckets: list[MatchBucket] = []
    for key in _BUCKET_ORDER:
        if key in _GEOMETRY_BUCKETS and geometry_processing:
            buckets.append(MatchBucket(key=key, status="processing", count=0, matches=[]))
            continue
        ids = ready[key]
        if key == "similar_geometries":
            # Nearest-first — the SQL's distance order IS the ranking here;
            # a much-quoted distant part must not evict a close neighbour.
            ordered = [cards[pid] for pid in ids]
        else:
            # Most-quoted first (the demo's card order), id as a tiebreak.
            ordered = sorted(
                (cards[pid] for pid in ids),
                key=lambda c: (c.quote_count, c.part_id.hex),
                reverse=True,
            )
        buckets.append(
            MatchBucket(key=key, status="ready", count=len(ids), matches=ordered[:_BUCKET_CARD_CAP])
        )

    primary_filename = primary_file.filename if primary_file is not None else None
    return MatchesOut(
        part_id=part_id,
        subject=MatchSubject(
            part_number=part.part_number,
            revision=part.revision,
            name=part.name,
            primary_filename=primary_filename,
        ),
        total=len(all_ids),
        buckets=buckets,
    )


# --------------------------------------------------------------------------- #
# Import historical work (spec#partlib "What selecting a historical match does")
# --------------------------------------------------------------------------- #

# Everything that defines the router row is copied verbatim; ids/FKs are minted
# fresh on the target. Listed explicitly so a future Operation column is a
# conscious decision here, not silently dragged along (or silently dropped).
_OPERATION_COPY_FIELDS = (
    "operation_def_id",
    "name",
    "category",
    "position",
    "calculation_mode",
    "run_rate",
    "labour_rate",
    "setup_basis",
    "setup_cost",
    "calc_setup_mins",
    "manual_setup_mins",
    "calc_runtime_mins",
    "manual_runtime_mins",
    "calc_attend_mins",
    "manual_attend_mins",
    "surcharge_pct",
    "yield_factor",
    "is_outside_service",
    "is_finish",
    "is_from_factory",
    "notes",
    "cost_formula",
)


class ImportRouterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_component_id: uuid.UUID


async def source_quote_id_of(session: AsyncSession, component: Component) -> uuid.UUID | None:
    """The quote a source component belongs to — the ``source_quote_id``
    provenance stamp (M4.13). ``None`` for a component without a line item
    (e.g. a BOM child); the copy still happens, just untagged."""
    quote_id: uuid.UUID | None = await session.scalar(
        select(QuoteItem.quote_id).where(QuoteItem.root_component_id == component.id)
    )
    return quote_id


async def copy_component_router(
    session: AsyncSession,
    *,
    source: Component,
    target: Component,
    source_quote_id: uuid.UUID | None,
) -> None:
    """REPLACE the target's material/operation rows with copies of the
    source's (importing a router means reusing it, not merging two). Every
    copied row is stamped ``source = imported`` + the *immediate* source
    quote (spec ``#ai-quote-assembly``: "all imported values carry
    source = imported"). The source rows are never touched."""
    source_ops = (
        await session.scalars(
            select(Operation)
            .where(Operation.component_id == source.id)
            .order_by(Operation.position, Operation.created_at, Operation.id)
        )
    ).all()
    # Replace, not merge: the old router's rows go (their cells cascade).
    await session.execute(delete(Operation).where(Operation.component_id == target.id))
    for src in source_ops:
        copied = Operation(
            org_id=target.org_id,
            component_id=target.id,
            # A wholesale router import is not the estimator hand-adding each op,
            # so it must not feed the M3.10 rule-suggestion pattern detector
            # (spec ``#ai-rule-suggest``: "added directly by the estimator").
            added_manually=False,
            source=ValueSource.imported,
            source_quote_id=source_quote_id,
            # JSONB dict is copied, never shared, so later edits don't alias.
            variable_overrides=dict(src.variable_overrides),
            **{field: getattr(src, field) for field in _OPERATION_COPY_FIELDS},
        )
        session.add(copied)
    await session.flush()


# --------------------------------------------------------------------------- #
# Merge Parts as Supporting Files (KB navigate-and-manage-the-part-library)
# --------------------------------------------------------------------------- #
class MergePartsIn(BaseModel):
    """Merge N parts into one: the primary part keeps its identity; every other
    part's files move onto it as SUPPORTING files."""

    model_config = ConfigDict(extra="forbid")

    part_ids: list[uuid.UUID]
    primary_part_id: uuid.UUID


@library_router.post("/parts/merge")
async def merge_parts(
    payload: MergePartsIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> PartOut:
    """Merge selected parts as supporting files of the chosen primary part.

    The KB flow for a print/model pair whose names didn't auto-bundle
    (``5-X-9__B.pdf`` + ``5-X-9.STEP``). Source parts are emptied and leave
    the library (soft-deleted — irreversible, like the delete lifecycle).
    A source that is referenced by a quote or a BOM refuses the merge: its
    quote/BOM context must not silently lose its part."""
    ids = list(dict.fromkeys(payload.part_ids))  # de-dupe, keep order
    if len(ids) < 2:
        raise AppError("invalid_merge", "Select at least two parts.", status_code=422)
    if payload.primary_part_id not in ids:
        raise AppError(
            "invalid_merge", "The primary part must be among the selected parts.", status_code=422
        )
    parts = (
        await session.scalars(
            select(Part).where(Part.id.in_(ids), Part.deleted_at.is_(None)).with_for_update()
        )
    ).all()
    if len(parts) != len(ids):
        raise AppError("not_found", "Part not found.", status_code=404)
    primary_part = next(p for p in parts if p.id == payload.primary_part_id)
    source_ids = [p.id for p in parts if p.id != primary_part.id]

    # Guard: a quoted part (Component) or a BOM child (non-root Node) stays.
    # Race note (DECISIONS.md 2026-07-15): only the part rows are locked; a
    # concurrent Component insert referencing a source could slip past. Today
    # that path doesn't exist (line items always mint fresh parts) — revisit
    # with a DB-level guard when "add library part to quote" lands.
    in_use = await session.scalar(
        select(func.count()).select_from(Component).where(Component.part_id.in_(source_ids))
    )
    in_bom = await session.scalar(
        select(func.count())
        .select_from(Node)
        .where(Node.part_id.in_(source_ids), Node.parent_node_id.is_not(None))
    )
    if in_use or in_bom:
        raise AppError(
            "part_in_use",
            "A selected part is used by a quote or BOM and cannot be merged away.",
            status_code=409,
        )

    for source in parts:
        if source.id == primary_part.id:
            continue
        source.primary_file_id = None  # release the composite FK before moving
    await session.flush()
    moved = (
        await session.scalars(
            select(PartFile).where(PartFile.part_id.in_(source_ids)).with_for_update()
        )
    ).all()
    for pf in moved:
        pf.part_id = primary_part.id
        pf.role = FileRole.supporting
    await session.flush()

    # If the primary part had no PRIMARY file, the best moved file takes it.
    if primary_part.primary_file_id is None and moved:
        winner = max(moved, key=lambda r: primary_rank(FileCategory(r.file_type)))
        winner.role = FileRole.primary
        primary_part.primary_file_id = winner.id

    now = datetime.now(UTC)
    for source in parts:
        if source.id != primary_part.id:
            source.deleted_at = now
    await session.flush()
    return _part_out(primary_part)


@library_router.post("/components/{component_id}/import-router")
async def import_router(
    component_id: uuid.UUID,
    payload: ImportRouterIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    """Copy a historical component's router onto this one and reprice.

    REPLACES the target's existing material/operation rows (importing a router
    means reusing it, not merging two). The source — typically a prior quote
    found via the historical bucket — is never touched; its quote may be in
    any status. Manual overrides ride along on the copied rows; per-quantity
    manual cell costs stay behind (the target's breaks are its own).
    """
    if payload.source_component_id == component_id:
        raise AppError("invalid_source", "A component cannot import from itself.", status_code=422)
    target = await _get_component_or_404(session, component_id)
    await _lock_editable_quote_of(session, target)
    source = await session.get(Component, payload.source_component_id)
    if source is None:
        raise AppError("not_found", "Source component not found.", status_code=404)

    await copy_component_router(
        session,
        source=source,
        target=target,
        source_quote_id=await source_quote_id_of(session, source),
    )
    await recalculate_component(session, target.org_id, target.id)
    return await _component_costing(session, target)
