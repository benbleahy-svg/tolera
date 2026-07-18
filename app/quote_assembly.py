"""M4.13 — AI: Agentic Quote Assembly (spec ``#ai-quote-assembly``).

"This is a repeat part I know well — can the system do the mechanical work so
I just verify?" When the M4.12 requote entry exists (an Exact-File /
Exact-Geometric baseline on a draft quote), the estimating banner offers to
draft the line item from the most recent quote. Two explicit-accept paths:

* **Review** — imports router + pricing; every value is chipped "AI-drafted"
  in the UI until the estimator reviews it.
* **Accept All** — the same import in one click, backed by a **60-second
  undo** (Redis key ``undo:quote_assembly:{line_item_id}``, TTL 60 s) that
  reverts to a blank line item. Suppressed **server-side** whenever the
  deterministic diff shows a material change
  (``geometry_delta.significant`` OR ``finding_diff.material_changes ≠ []``)
  — plus a conservative currency guard (DECISIONS 2026-07-18).

Both paths stamp every copied row ``source = imported`` +
``source_quote_id`` (migration 0037) — row-level provenance for the variable
drawer and audit trail. The copy is deterministic (no LLM anywhere near it);
Claude only contributes the combined review brief, produced by the M4.12
synthesis job. Nothing is ever copied without a click (AI-Governor).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .ai_settings import get_ai_flags
from .auth import Principal
from .authz import Permission, require
from .config import get_settings
from .costing import recalculate_component
from .deps import get_session
from .errors import AppError
from .models import (
    AddOn,
    Component,
    Discount,
    ExpediteOption,
    Operation,
    PricingItem,
    Quote,
    QuoteItem,
    QuoteStatus,
    ValueSource,
)
from .part_library import copy_component_router
from .pricing import attach_default_pricing

logger = logging.getLogger(__name__)

assembly_router = APIRouter(prefix="/api/quotes", tags=["quote-assembly"])

#: Spec #ai-quote-assembly: "Sixty-second undo provides a safety net."
UNDO_TTL_SECONDS = 60


def undo_key(line_item_id: uuid.UUID) -> str:
    """The spec-named Redis key: ``undo:quote_assembly:{line_item_id}``."""
    return f"undo:quote_assembly:{line_item_id}"


# --------------------------------------------------------------------------- #
# The deterministic Accept-All gate (never consults LLM output)
# --------------------------------------------------------------------------- #


def accept_all_blockers(entry: dict[str, Any], *, target_currency: str) -> list[str]:
    """Why Accept All is suppressed for this cached requote entry ([] = eligible).

    Spec: suppressed server-side when ``diff.geometry_delta.significant = true
    OR diff.finding_diff.material_changes ≠ []``. Two conservative guards on
    top (ASSUMED, DECISIONS 2026-07-18): a source quote in another currency
    (CHF rates into a EUR quote is silently-wrong money — only Review is
    offered), and a pre-M4.13 cached entry that predates the currency stamp
    (fail-closed until the diff is refreshed).
    """
    blockers: list[str] = []
    diff = entry.get("diff") or {}
    if (diff.get("geometry_delta") or {}).get("significant"):
        blockers.append("geometry_significant")
    if (diff.get("finding_diff") or {}).get("material_changes"):
        blockers.append("material_changes")
    source_currency = (entry.get("matched") or {}).get("currency")
    if source_currency is None:
        blockers.append("entry_stale")
    elif source_currency != target_currency:
        blockers.append("currency_mismatch")
    return blockers


async def enrich_entries(
    session: AsyncSession, quote: Quote, payload: dict[str, Any]
) -> dict[str, Any]:
    """Add the read-time ``assembly_state`` block to each requote entry.

    Computed fresh on every read (flags can change between task run and
    display); the *enforced* copy of the same rule lives in
    :func:`assembly_import` — the UI state is never the gate.
    """
    flags = await get_ai_flags(session, quote.org_id)
    offered = flags.master_enabled and flags.quote_assembly_enabled
    enriched: list[dict[str, Any]] = []
    for stored in payload["entries"]:
        # Annotate a COPY — `_entries_out` hands back the dicts stored in
        # ``quote.requote_diff``, and a dirty quote row would otherwise
        # serialize this read-time advisory state into the durable cache.
        entry = dict(stored)
        blockers = accept_all_blockers(entry, target_currency=quote.currency)
        entry["assembly_state"] = {
            "offered": offered,
            "accept_all_eligible": offered and not blockers,
            "blockers": blockers,
            "quote_count": int(entry.get("quote_count") or 0),
            "undo_ttl_seconds": UNDO_TTL_SECONDS,
        }
        enriched.append(entry)
    return {**payload, "entries": enriched}


# --------------------------------------------------------------------------- #
# The undo store (register/resolve seam — Redis in prod, fake in tests)
# --------------------------------------------------------------------------- #


class UndoStoreUnavailableError(RuntimeError):
    """The undo store is unreachable — the key's fate is UNKNOWN. Callers map
    this to a retryable 503, never to the definitive 410 of an expired key."""


class UndoStore(Protocol):
    """The 60-second undo window: ``arm`` on Accept All, ``take`` (single-use
    get-and-delete) on undo. A missing/expired key means the window closed;
    ``take`` raises :class:`UndoStoreUnavailableError` when it cannot tell."""

    async def arm(self, key: str, value: dict[str, Any], ttl_seconds: int) -> bool: ...

    async def take(self, key: str) -> dict[str, Any] | None: ...


class RedisUndoStore:
    """TTL key on the app Redis (``settings.redis_url``). Degrades gracefully
    (the ``email_ingest`` pattern): an outage costs the undo chip, never the
    import — the copy itself is already committed and reviewable."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url

    async def arm(self, key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(self._url, socket_connect_timeout=1, socket_timeout=1)
            try:
                await client.set(key, json.dumps(value), ex=ttl_seconds)
                return True
            finally:
                await client.aclose()
        except Exception:
            logger.warning("assembly_undo_arm_failed", extra={"key": key})
            return False

    async def take(self, key: str) -> dict[str, Any] | None:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(self._url, socket_connect_timeout=1, socket_timeout=1)
            try:
                raw = await client.getdel(key)
            finally:
                await client.aclose()
        except Exception as exc:
            # An outage is NOT an expired key: the caller must answer 503
            # (retry within the window), never a definitive 410.
            logger.warning("assembly_undo_take_failed", extra={"key": key})
            raise UndoStoreUnavailableError(str(exc)) from exc
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None


_undo_store: UndoStore | None = None


def register_undo_store(store: UndoStore | None) -> None:
    """Install (or clear) the process-wide undo store — tests."""
    global _undo_store
    _undo_store = store


def resolve_undo_store() -> UndoStore:
    if _undo_store is not None:
        return _undo_store
    return RedisUndoStore(get_settings().redis_url)


# --------------------------------------------------------------------------- #
# The pricing copy (router copy lives in part_library.copy_component_router)
# --------------------------------------------------------------------------- #

# Explicit allow-lists (the _OPERATION_COPY_FIELDS discipline): a future
# column is a conscious decision here, not silently dragged along. Per-break
# cells are NOT copied — the target's breaks are its own (they come from the
# new RFQ's quantities); recalculation mints fresh calc cells.
_PRICING_ITEM_COPY_FIELDS = (
    "source_def_id",
    "name",
    "calc_type",
    "category",
    "is_custom",
    "custom_category_name",
    "color",
    "formula",
    "default_pct",
    "position",
    "is_from_factory",
)
_DISCOUNT_COPY_FIELDS = (
    "source_def_id",
    "name",
    "formula",
    "default_pct",
    "position",
    "is_from_factory",
)
_ADD_ON_COPY_FIELDS = (
    "source_def_id",
    "name",
    "formula",
    "default_price",
    "default_is_required",
    "calc_is_required",
    "manual_is_required",
    "calc_name",
    "position",
    "is_from_factory",
)
_EXPEDITE_COPY_FIELDS = ("days_faster", "markup_pct", "position")


async def copy_component_pricing(
    session: AsyncSession,
    *,
    source: Component,
    target: Component,
    source_quote_id: uuid.UUID,
) -> None:
    """REPLACE the target's pricing stack (items, discounts, add-ons,
    expedites) with copies of the source's, stamped ``source = imported`` +
    ``source_quote_id``. Cells cascade away with the deleted rows and are
    reminted by recalculation for the target's own quantity breaks.

    RLS already pins the session to one org; the explicit org guard and
    org-scoped predicates are §5 belt-and-braces."""
    if source.org_id != target.org_id:
        raise AppError(
            "not_found", "Source component not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    for model, fields, tagged in (
        (PricingItem, _PRICING_ITEM_COPY_FIELDS, True),
        (Discount, _DISCOUNT_COPY_FIELDS, True),
        (AddOn, _ADD_ON_COPY_FIELDS, True),
        # Expedite options carry no provenance columns (no override drawer).
        (ExpediteOption, _EXPEDITE_COPY_FIELDS, False),
    ):
        rows = (
            await session.scalars(
                select(model)
                .where(model.component_id == source.id, model.org_id == source.org_id)
                .order_by(model.position, model.created_at, model.id)
            )
        ).all()
        await session.execute(
            delete(model).where(model.component_id == target.id, model.org_id == target.org_id)
        )
        for src in rows:
            values: dict[str, Any] = {field: getattr(src, field) for field in fields}
            if tagged:
                values["source"] = ValueSource.imported
                values["source_quote_id"] = source_quote_id
            session.add(model(org_id=target.org_id, component_id=target.id, **values))
    await session.flush()


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


class AssemblyImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_id: uuid.UUID
    path: Literal["accept_all", "review"]


class AssemblyUndoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_id: uuid.UUID


async def _locked_draft_quote(session: AsyncSession, quote_id: uuid.UUID) -> Quote:
    quote = await session.get(Quote, quote_id, with_for_update=True)
    if quote is None or quote.deleted_at is not None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    if quote.status != QuoteStatus.draft:
        raise AppError(
            "quote_locked",
            "This quote is no longer a draft; the assembly gate is frozen.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return quote


def _entry_of(quote: Quote, part_id: uuid.UUID) -> dict[str, Any]:
    entries = (quote.requote_diff or {}).get("entries") or {}
    entry = entries.get(str(part_id))
    if entry is None:
        raise AppError(
            "no_requote_entry",
            "No requote diff exists for this part.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return dict(entry)


def _persist_entry(quote: Quote, entry: dict[str, Any]) -> None:
    cache = dict(quote.requote_diff or {})
    entries = dict(cache.get("entries") or {})
    entries[str(entry["part_id"])] = entry
    quote.requote_diff = {**cache, "entries": entries}


async def _target_and_item(
    session: AsyncSession, quote: Quote, entry: dict[str, Any]
) -> tuple[Component, uuid.UUID]:
    target = await session.get(Component, uuid.UUID(entry["target_component_id"]))
    item_id = None
    if target is not None:
        item_id = await session.scalar(
            select(QuoteItem.id).where(
                QuoteItem.root_component_id == target.id, QuoteItem.quote_id == quote.id
            )
        )
    if target is None or item_id is None:
        raise AppError(
            "target_gone",
            "The line item this entry was computed for no longer exists — refresh the diff.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return target, item_id


@assembly_router.post("/{quote_id}/assembly/import")
async def assembly_import(
    quote_id: uuid.UUID,
    payload: AssemblyImportIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, Any]:
    """The explicit-accept import: copy the baseline quote's router + pricing
    onto this line item **in this one transaction**, stamped
    ``source = imported`` + ``source_quote_id``. ``accept_all`` re-checks the
    deterministic gate server-side (the UI's eligibility flag is advisory)
    and arms the 60-second undo; ``review`` imports the same values for
    field-by-field review — no undo, the chips are the safety net."""
    from .requote_diff import _entries_out

    quote = await _locked_draft_quote(session, quote_id)
    flags = await get_ai_flags(session, quote.org_id)
    if not (flags.master_enabled and flags.quote_assembly_enabled):
        raise AppError(
            "assembly_disabled",
            "Agentic Quote Assembly is disabled for this organization.",
            status_code=status.HTTP_409_CONFLICT,
        )
    entry = _entry_of(quote, payload.part_id)
    blockers = accept_all_blockers(entry, target_currency=quote.currency)
    # Cross-currency (or currency-unknown/stale) copies are rejected on EVERY
    # path — CHF rates in a EUR quote are wrong money whether or not each
    # value gets an individual review chip (DECISIONS 2026-07-18, tightened in
    # PR #67 review: reject outright until a conversion policy exists).
    if "currency_mismatch" in blockers or "entry_stale" in blockers:
        raise AppError(
            "currency_mismatch",
            "The historical quote uses a different currency (or the cached diff "
            "predates the currency stamp) — no values were imported.",
            status_code=status.HTTP_409_CONFLICT,
            details={"blockers": blockers},
        )
    if payload.path == "accept_all" and blockers:
        raise AppError(
            "accept_all_suppressed",
            "Accept All is not available — the diff shows a material change; "
            "review the import field by field instead.",
            status_code=status.HTTP_409_CONFLICT,
            details={"blockers": blockers},
        )
    target, item_id = await _target_and_item(session, quote, entry)
    source = await session.get(Component, uuid.UUID(entry["matched"]["component_id"]))
    if source is None or source.org_id != quote.org_id:
        raise AppError(
            "source_gone",
            "The matched historical component no longer exists — refresh the diff.",
            status_code=status.HTTP_409_CONFLICT,
        )
    source_quote_id = uuid.UUID(entry["matched"]["quote_id"])

    await copy_component_router(
        session, source=source, target=target, source_quote_id=source_quote_id
    )
    await copy_component_pricing(
        session, source=source, target=target, source_quote_id=source_quote_id
    )
    await recalculate_component(session, quote.org_id, target.id)

    now = datetime.now(UTC)
    record: dict[str, Any] = {
        "path": payload.path,
        "at": now.isoformat(),
        "user_id": str(principal.user_id),
        "source_quote_id": str(source_quote_id),
        "source_quote_number": entry["matched"].get("quote_number"),
        "undone_at": None,
        "undo_expires_at": None,
    }
    if payload.path == "accept_all":
        armed = await resolve_undo_store().arm(
            undo_key(item_id),
            {"quote_id": str(quote.id), "part_id": str(payload.part_id)},
            UNDO_TTL_SECONDS,
        )
        if armed:
            record["undo_expires_at"] = (now + timedelta(seconds=UNDO_TTL_SECONDS)).isoformat()
    entry["assembly"] = record
    _persist_entry(quote, entry)
    return await enrich_entries(session, quote, _entries_out(quote))


@assembly_router.post("/{quote_id}/assembly/undo")
async def assembly_undo(
    quote_id: uuid.UUID,
    payload: AssemblyUndoIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, Any]:
    """Within 60 s of Accept All: revert the line item to its blank state —
    no operations, org-default pricing (what ``add_quote_item`` creates). The
    key is single-use; a missing/expired key is 410 GONE and the import
    stands (it is committed, tagged, and reviewable)."""
    from .requote_diff import _entries_out

    quote = await _locked_draft_quote(session, quote_id)
    entry = _entry_of(quote, payload.part_id)
    record = entry.get("assembly")
    if not isinstance(record, dict) or record.get("path") != "accept_all":
        raise AppError(
            "nothing_to_undo",
            "No Accept-All import exists for this part.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    target, item_id = await _target_and_item(session, quote, entry)
    if record.get("undone_at"):
        raise AppError(
            "undo_expired",
            "The undo window has closed — remove or edit the imported values directly.",
            status_code=status.HTTP_410_GONE,
        )

    await session.execute(
        delete(Operation).where(
            Operation.component_id == target.id, Operation.org_id == quote.org_id
        )
    )
    for model in (PricingItem, Discount, AddOn, ExpediteOption):
        await session.execute(
            delete(model).where(model.component_id == target.id, model.org_id == quote.org_id)
        )
    await session.flush()
    await attach_default_pricing(session, quote.org_id, target.id)
    await recalculate_component(session, quote.org_id, target.id)

    record = {**record, "undone_at": datetime.now(UTC).isoformat()}
    entry["assembly"] = record
    _persist_entry(quote, entry)

    # Consume the single-use key LAST: if any of the DB work above had failed,
    # the key would survive for a retry inside the window. A missing/expired
    # key here raises — and the whole transaction (the blanking) rolls back,
    # so an expired undo leaves the import standing. A store OUTAGE is a
    # different answer: 503 (retryable, transaction also rolls back), never
    # the definitive 410.
    try:
        taken = await resolve_undo_store().take(undo_key(item_id))
    except UndoStoreUnavailableError as exc:
        raise AppError(
            "undo_store_unavailable",
            "The undo service is temporarily unreachable — try again in a moment.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    if taken is None:
        raise AppError(
            "undo_expired",
            "The undo window has closed — remove or edit the imported values directly.",
            status_code=status.HTTP_410_GONE,
        )
    logger.info(
        "assembly_undo_applied",
        extra={"quote_id": str(quote.id), "line_item_id": str(item_id)},
    )
    return await enrich_entries(session, quote, _entries_out(quote))
