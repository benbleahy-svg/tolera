"""The Dashboard **work queue** — "What needs me now" (spec ``#newscope`` §2; M6.1).

One merged, role-aware, prioritised list across the five sources the spec names:
quotes needing my action · tasks assigned to me · review items assigned to me ·
vendor RFQs awaiting send/ingest · @mentions. Every row says **why it surfaced**
(reason chips) and carries its **urgency score with the contributing factors**,
so the ordering is explainable rather than magic. The scoring math itself lives
in :mod:`app.urgency` (pure, Decimal, unit-tested); this module is the source
collection + the signals that feed it.

Four things worth knowing before changing anything here:

* **Determinism.** ``days_to_due`` is derived once per request from a single UTC
  *date*, and the final sort is fully specified (score, then due date, then
  recency, then id) — so the same seed yields the same order on every render,
  which is the block's acceptance criterion. Nothing else about the row depends
  on the clock.
* **One comparable scale.** A task/review-item/mention row hanging off a quote
  inherits that quote's value, flag and unresolved-count signals; only its due
  date is its own. Without that, a blocking review item on a €250k expedited job
  would score below an idle draft.
* **Tenancy.** Every source but one reads through the caller's org-scoped session
  (RLS pins ``org_id``). **@mentions are the single cross-org source** —
  DECISIONS.md 2026-06-19 (E4-a) makes cross-org notifications labelled +
  switch-on-select — and they are read through the audited ``app_user_mentions()``
  ``SECURITY DEFINER`` function (migration 0049), which binds to the caller's
  ``app.current_user_id`` GUC and to *active* memberships. A cross-org row
  carries its org's identity so the UI can label it and route the org switch; no
  other data from that org is read.
* **No money crosses the wire.** Quote value enters the score as a *band* only
  (:func:`app.urgency.value_band`), so the queue never hands the client a
  monetary amount — the tier-1 minor-units rule has nothing to violate.

Vendor-RFQ rows are the fifth source; their entities land in **M6.2**, so the
source is gated behind the per-org ``vendor_rfq_queue_enabled`` flag (default
off) and returns nothing until then — as the block's scope explicitly directs.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, delete, func, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .dashboard_settings import get_or_create_row, load_dashboard_settings
from .deps import get_session
from .errors import AppError
from .models import (
    Account,
    ComponentQuantity,
    MembershipRole,
    Order,
    OrderLine,
    Part,
    Quote,
    QuoteItem,
    QuoteStatus,
    QuoteStatusEvent,
    RecentView,
    ReviewItem,
    Task,
    TaskStatus,
)
from .quote_filters import ACTIVE_QUOTE_STATUSES as _OPEN_STATUSES
from .quote_filters import owned_by
from .urgency import UrgencyInputs, UrgencyWeights, score_urgency

work_queue_router = APIRouter(prefix="/api/work-queue", tags=["dashboard"])

#: Statuses where the ball is in *our* court. A ``sent`` quote is waiting on the
#: customer, a won/lost/cancelled one on nobody — neither is "my action".
_MY_ACTION_STATUSES = (QuoteStatus.draft, QuoteStatus.on_hold)
#: Statuses that still count as live pipeline for the manager KPI row. Shared
#: with the "workflows" system view (app.quote_filters) so the glance row and the
#: table it links to cannot disagree about what "open" means.
#: The Recently-opened strip's length (spec ``#newscope``: "last 8 quotes/parts").
_RECENTS_LIMIT = 8
#: How many entries are retained per user. A small multiple of the strip length:
#: enough that a deleted quote doesn't shorten the strip, far from a history log.
_RECENTS_KEEP = 24
_QUEUE_LIMIT_DEFAULT = 50
_QUEUE_LIMIT_MAX = 200
#: Per-source fetch ceiling before scoring/merging (see get_work_queue). Well
#: above _QUEUE_LIMIT_MAX so the ranking still sees more than it can show.
_SOURCE_FETCH_MAX = 500
#: Roles the KPI glance row is for (spec ``#newscope``: "for managers").
_MANAGER_ROLES = frozenset({MembershipRole.admin, MembershipRole.manager})

SourceKind = Literal["quote_action", "task", "review_item", "vendor_rfq", "mention"]


# --------------------------------------------------------------------------- #
# Wire schemas
# --------------------------------------------------------------------------- #
class ReasonChip(BaseModel):
    """Why this row surfaced — an **i18n key plus params**, never rendered prose,
    so the German-first UI owns the wording (CLAUDE.md §5)."""

    key: str
    params: dict[str, Any] = Field(default_factory=dict)


class FactorOut(BaseModel):
    """One term of the urgency score, as the hover panel shows it."""

    key: str
    raw: str
    normalized: Decimal
    weight: Decimal
    contribution: Decimal


class QueueRow(BaseModel):
    """One item of work. ``id`` is the *source entity's* id (quote, task, review
    item, notification) — the row's identity for dedup and deep-linking."""

    source: SourceKind
    id: uuid.UUID
    quote_id: uuid.UUID | None
    label: str
    reason_chips: list[ReasonChip]
    urgency: Decimal
    factors: list[FactorOut]
    deep_link: str
    org_id: uuid.UUID
    org_name: str
    org_slug: str
    #: True when the row belongs to another org the caller is a member of — the
    #: UI labels it and switches active org on select (DECISIONS E4-a).
    cross_org: bool


class WeightsOut(BaseModel):
    """The org's urgency weights + queue-source flags."""

    weight_due: Decimal
    weight_value: Decimal
    weight_unresolved: Decimal
    weight_flags: Decimal
    vendor_rfq_queue_enabled: bool


#: Upper bound on a weight: the column is ``numeric(6,4)``, so anything at or
#: above 100 overflows. Rejecting it at the edge (422) beats a mid-flush
#: NumericValueOutOfRange surfacing as a 500 for input the contract called legal.
_WEIGHT_MAX = Decimal("99.9999")


class WeightsPatch(BaseModel):
    """A partial settings write — omitted fields keep their stored value."""

    model_config = ConfigDict(extra="forbid")

    weight_due: Decimal | None = Field(default=None, ge=0, le=_WEIGHT_MAX)
    weight_value: Decimal | None = Field(default=None, ge=0, le=_WEIGHT_MAX)
    weight_unresolved: Decimal | None = Field(default=None, ge=0, le=_WEIGHT_MAX)
    weight_flags: Decimal | None = Field(default=None, ge=0, le=_WEIGHT_MAX)
    vendor_rfq_queue_enabled: bool | None = None


class WorkQueueOut(BaseModel):
    """The queue plus the weights it was scored with (so the client can explain a
    row without a second call) and the date the due-dates were measured against."""

    rows: list[QueueRow]
    weights: WeightsOut
    generated_on: date


class RecentRow(BaseModel):
    """One *Recently opened* entry. ``deep_link`` is built server-side because it
    depends on the entity type — the strip must not assume every row is a quote."""

    entity_type: str
    entity_id: uuid.UUID
    label: str
    status: str | None
    deep_link: str
    opened_at: datetime


class RecentsOut(BaseModel):
    rows: list[RecentRow]


class RecentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["quote", "part"]
    entity_id: uuid.UUID


class KpiOut(BaseModel):
    """The manager glance row (spec ``#newscope``: open quotes, due this week,
    win rate 30d). ``win_rate_30d_pct`` is ``None`` when nothing closed in the
    window — an empty window has no rate, and 0% would read as "we lost
    everything"."""

    open_quotes: int
    due_this_week: int
    win_rate_30d_pct: Decimal | None


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #
@dataclasses.dataclass(frozen=True, slots=True)
class _QuoteSignals:
    """Everything the score needs about one quote, fetched once per request."""

    number: str
    status: QuoteStatus
    due_date: datetime | None
    value_minor: int | None
    unresolved_count: int
    expedite: bool
    vip: bool
    export_controlled: bool
    created_at: datetime


def _days_to_due(due: datetime | None, today: date) -> int | None:
    """Whole days from *today* to the due date — day granularity, so a re-render
    an hour later cannot change the ordering."""
    if due is None:
        return None
    return (due.astimezone(UTC).date() - today).days


#: Why the expedite flag is sourced from an **accepted** checkout selection
#: (``order_line.expedite_option_id``, M5.2) and *not* from ``quote.expedite_tiers``:
#: that column is the top-of-quote editor's staging state — ``app.addons``
#: writes the whole payload on "apply to all", and new orgs are seeded with two
#: default tiers — so a non-empty ``tiers`` list means expedite options were
#: **offered**, which is true of nearly every quote and says nothing about
#: urgency. Scoring on it would rank ordinary jobs as rush jobs *and* tell the
#: user so on the chip. A queue row is by definition draft/on-hold (not yet
#: ordered), so this reads false today; it lights up by itself for a
#: reopened/requoted job that carries a prior acceptance. See DECISIONS.md
#: 2026-07-19 (M6.1 urgency-score contract).


async def _quote_signals(
    session: AsyncSession, quote_ids: set[uuid.UUID]
) -> dict[uuid.UUID, _QuoteSignals]:
    """Fetch the scoring signals for a set of quotes in the caller's org.

    Four small aggregate queries rather than one wide join: each aggregate has a
    different grain (quantities per component, review items per quote, items per
    quote), and joining them in one statement multiplies rows before the SUMs."""
    if not quote_ids:
        return {}

    base = (
        select(
            Quote.id,
            Quote.number,
            Quote.status,
            Quote.due_date,
            Quote.created_at,
            func.coalesce(Account.is_vip, False).label("vip"),
        )
        .outerjoin(Account, Account.id == Quote.account_id)
        .where(Quote.id.in_(quote_ids))
    )

    # Value proxy: per line item the *largest* quantity break's total (the biggest
    # version of the job on the table), summed across the quote's items. Bands —
    # not amounts — are all that reaches the score, so this only has to be
    # monotonic, not accounting-exact.
    max_per_item = (
        select(
            QuoteItem.quote_id.label("quote_id"),
            func.max(ComponentQuantity.total_price).label("item_total"),
        )
        .join(ComponentQuantity, ComponentQuantity.component_id == QuoteItem.root_component_id)
        .where(QuoteItem.quote_id.in_(quote_ids))
        .group_by(QuoteItem.quote_id, QuoteItem.id)
        .subquery()
    )
    value_stmt = select(max_per_item.c.quote_id, func.sum(max_per_item.c.item_total)).group_by(
        max_per_item.c.quote_id
    )

    unresolved_stmt = (
        select(ReviewItem.quote_id, func.count())
        .where(ReviewItem.quote_id.in_(quote_ids), ReviewItem.status == "open")
        .group_by(ReviewItem.quote_id)
    )
    export_stmt = (
        select(QuoteItem.quote_id)
        .where(QuoteItem.quote_id.in_(quote_ids), QuoteItem.export_controlled.is_(True))
        .group_by(QuoteItem.quote_id)
    )
    # An *accepted* expedite — a checkout selection, not the offered menu (see
    # the note above the signal dataclass).
    expedite_stmt = (
        select(Order.quote_id)
        .join(OrderLine, OrderLine.order_id == Order.id)
        .where(Order.quote_id.in_(quote_ids), OrderLine.expedite_option_id.isnot(None))
        .group_by(Order.quote_id)
    )

    values = {row[0]: row[1] for row in await session.execute(value_stmt)}
    unresolved = {row[0]: row[1] for row in await session.execute(unresolved_stmt)}
    export_flagged = {row[0] for row in await session.execute(export_stmt)}
    expedited = {row[0] for row in await session.execute(expedite_stmt)}

    out: dict[uuid.UUID, _QuoteSignals] = {}
    for row in await session.execute(base):
        total = values.get(row.id)
        out[row.id] = _QuoteSignals(
            number=row.number,
            status=row.status,
            due_date=row.due_date,
            # Numeric major units -> integer minor units at the boundary.
            value_minor=None if total is None else int(Decimal(total) * 100),
            unresolved_count=unresolved.get(row.id, 0),
            expedite=row.id in expedited,
            vip=bool(row.vip),
            export_controlled=row.id in export_flagged,
            created_at=row.created_at,
        )
    return out


def _score(
    signals: _QuoteSignals | None,
    *,
    weights: UrgencyWeights,
    today: date,
    due_override: date | None = None,
) -> tuple[Decimal, list[FactorOut], int | None]:
    """Score one row from its parent quote's signals (``None`` for a row with no
    quote — a standalone task or a cross-org mention), letting the row's own due
    date win when it has one."""
    days = _days_to_due(signals.due_date, today) if signals else None
    if due_override is not None:
        days = (due_override - today).days
    scored = score_urgency(
        UrgencyInputs(
            days_to_due=days,
            value_minor=signals.value_minor if signals else None,
            unresolved_count=signals.unresolved_count if signals else 0,
            expedite=signals.expedite if signals else False,
            vip=signals.vip if signals else False,
            export_controlled=signals.export_controlled if signals else False,
        ),
        weights,
    )
    factors = [
        FactorOut(
            key=f.key,
            raw=f.raw,
            normalized=f.normalized,
            weight=f.weight,
            contribution=f.contribution,
        )
        for f in scored.factors
    ]
    return scored.score, factors, days


def _due_chips(days: int | None) -> list[ReasonChip]:
    if days is None:
        return []
    if days < 0:
        # ``count`` (not ``days``) — it is i18next's plural selector, so German
        # renders "seit 1 Tag" vs "seit 3 Tagen" rather than always the plural.
        return [ReasonChip(key="work_queue.chip.overdue", params={"count": -days})]
    if days == 0:
        return [ReasonChip(key="work_queue.chip.due_today")]
    return [ReasonChip(key="work_queue.chip.due_in", params={"count": days})]


def _signal_chips(signals: _QuoteSignals | None) -> list[ReasonChip]:
    if signals is None:
        return []
    chips: list[ReasonChip] = []
    if signals.unresolved_count:
        chips.append(
            ReasonChip(key="work_queue.chip.unresolved", params={"count": signals.unresolved_count})
        )
    if signals.expedite:
        chips.append(ReasonChip(key="work_queue.chip.expedite"))
    if signals.vip:
        chips.append(ReasonChip(key="work_queue.chip.vip"))
    if signals.export_controlled:
        chips.append(ReasonChip(key="work_queue.chip.export_controlled"))
    return chips


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
def _my_action_quotes_stmt(user_id: uuid.UUID) -> Select[Any]:
    """Quotes where the ball is in my court — mine, open, not trashed.

    Ownership comes from :func:`app.quote_filters.owned_by`, the same predicate
    the ``my-quotes`` system view uses, so "mine" is defined once and the queue
    cannot drift from the list."""
    return select(Quote.id).where(
        Quote.status.in_(_MY_ACTION_STATUSES),
        Quote.deleted_at.is_(None),
        owned_by(user_id),
    )


async def _org_identity(session: AsyncSession, org_id: uuid.UUID) -> tuple[str, str]:
    row = (
        await session.execute(
            text("SELECT name, slug FROM organization WHERE id = :id"), {"id": str(org_id)}
        )
    ).one()
    return str(row.name), str(row.slug)


async def _cross_org_mentions(session: AsyncSession) -> list[dict[str, Any]]:
    """The caller's unread @mentions across every org they actively belong to.

    Goes through the audited ``app_user_mentions()`` SECURITY DEFINER function
    (migration 0049) because the request's session is RLS-pinned to the active
    org. The function takes no user argument — it binds to the ``app.current_user_id``
    GUC — so a caller can only ever read their own mentions."""
    raw = (await session.execute(text("SELECT app_user_mentions(50)"))).scalar_one()
    rows = json.loads(raw) if isinstance(raw, str) else raw
    return list(rows or [])


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@work_queue_router.get("")
async def get_work_queue(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
    limit: Annotated[int, Query(ge=1, le=_QUEUE_LIMIT_MAX)] = _QUEUE_LIMIT_DEFAULT,
) -> WorkQueueOut:
    """The merged, prioritised work queue for the signed-in user."""
    org_id = principal.active_org_id
    user_id = principal.user_id
    today = datetime.now(UTC).date()
    settings = await load_dashboard_settings(session, org_id)
    weights = settings.weights
    org_name, org_slug = await _org_identity(session, org_id)

    my_action_ids = set(
        await session.scalars(_my_action_quotes_stmt(user_id).limit(_SOURCE_FETCH_MAX))
    )
    quote_ids = set(my_action_ids)
    # Each source is bounded before the merge: an estimator with thousands of open
    # review items must not make the dashboard fan out over thousands of parent
    # quotes to then show 50 rows. Newest-first with an id tiebreaker keeps the
    # truncation itself deterministic.
    tasks = list(
        await session.scalars(
            select(Task)
            .where(Task.assignee_id == user_id, Task.status != TaskStatus.resolved)
            .order_by(Task.created_at.desc(), Task.id.desc())
            .limit(_SOURCE_FETCH_MAX)
        )
    )
    review_items = list(
        await session.scalars(
            select(ReviewItem)
            .where(ReviewItem.assignee_id == user_id, ReviewItem.status == "open")
            .order_by(ReviewItem.created_at.desc(), ReviewItem.id.desc())
            .limit(_SOURCE_FETCH_MAX)
        )
    )
    mentions = await _cross_org_mentions(session)

    quote_ids |= {t.quote_id for t in tasks if t.quote_id}
    quote_ids |= {r.quote_id for r in review_items if r.quote_id}
    quote_ids |= {
        uuid.UUID(m["payload"]["quote_id"])
        for m in mentions
        if m["org_id"] == str(org_id)
        and isinstance(m.get("payload"), dict)
        # A mention's payload is written by whatever raised it — treat every
        # field as untrusted and skip anything that isn't a quote id we can use.
        and _maybe_uuid(m["payload"].get("quote_id")) is not None
    }
    signals = await _quote_signals(session, quote_ids)

    rows: list[tuple[tuple[Any, ...], QueueRow]] = []

    def _emit(
        *,
        source: SourceKind,
        entity_id: uuid.UUID,
        quote_id: uuid.UUID | None,
        label: str,
        chips: list[ReasonChip],
        deep_link: str,
        created_at: datetime,
        due_override: date | None = None,
        row_org: tuple[uuid.UUID, str, str] | None = None,
    ) -> None:
        sig = signals.get(quote_id) if quote_id else None
        score, factors, days = _score(sig, weights=weights, today=today, due_override=due_override)
        row_org_id, row_org_name, row_org_slug = row_org or (org_id, org_name, org_slug)
        rows.append(
            (
                # Sort key: score desc, soonest due first (undated last), newest
                # first, then id — fully specified, so the order is reproducible.
                (
                    -score,
                    0 if days is not None else 1,
                    days if days is not None else 0,
                    -created_at.timestamp(),
                    str(entity_id),
                ),
                QueueRow(
                    source=source,
                    id=entity_id,
                    quote_id=quote_id,
                    label=label,
                    reason_chips=[*_due_chips(days), *chips],
                    urgency=score,
                    factors=factors,
                    deep_link=deep_link,
                    org_id=row_org_id,
                    org_name=row_org_name,
                    org_slug=row_org_slug,
                    cross_org=row_org_id != org_id,
                ),
            )
        )

    # Only quotes that are *mine and open* become rows; the rest were fetched
    # solely as the parent of a task / review item / mention.
    for quote_id in sorted(my_action_ids & set(signals), key=str):
        sig = signals[quote_id]
        _emit(
            source="quote_action",
            entity_id=quote_id,
            quote_id=quote_id,
            label=sig.number,
            chips=_signal_chips(sig),
            deep_link=f"/quotes/{quote_id}",
            created_at=sig.created_at,
        )

    for task in tasks:
        _emit(
            source="task",
            entity_id=task.id,
            quote_id=task.quote_id,
            label=task.message or "",
            chips=[ReasonChip(key="work_queue.chip.task_assigned")],
            deep_link=(f"/quotes/{task.quote_id}" if task.quote_id else f"/parts/{task.part_id}"),
            created_at=task.created_at,
            due_override=task.due_date,
        )

    for item in review_items:
        _emit(
            source="review_item",
            entity_id=item.id,
            quote_id=item.quote_id,
            label=item.resolution_label or "",
            chips=[ReasonChip(key="work_queue.chip.review_item_assigned")],
            deep_link=f"/quotes/{item.quote_id}?panel=review",
            created_at=item.created_at,
        )

    for mention in mentions:
        mention_org = uuid.UUID(mention["org_id"])
        payload = mention.get("payload") if isinstance(mention.get("payload"), dict) else {}
        mention_quote = _maybe_uuid((payload or {}).get("quote_id"))
        # Another org's quote is unreadable from here (RLS) — the row still
        # surfaces, labelled with its org, and selecting it switches org.
        same_org = mention_org == org_id
        _emit(
            source="mention",
            entity_id=uuid.UUID(mention["id"]),
            quote_id=mention_quote if same_org else None,
            label=mention.get("org_name", ""),
            chips=[ReasonChip(key="work_queue.chip.mentioned")],
            deep_link=f"/quotes/{mention_quote}" if mention_quote else "/",
            created_at=datetime.fromisoformat(mention["created_at"]),
            row_org=(mention_org, mention["org_name"], mention["org_slug"]),
        )

    if settings.vendor_rfq_queue_enabled:
        # Fifth source (spec ``#newscope`` §4): vendor RFQs awaiting send/ingest.
        # Its entities are built in M6.2 — until then the flag is inert by
        # design, not by oversight (block scope: "gate that source behind a
        # feature flag until M6.2 lands").
        pass

    rows.sort(key=lambda pair: pair[0])
    return WorkQueueOut(
        rows=[row for _, row in rows[:limit]],
        weights=_weights_out(settings.weights, settings.vendor_rfq_queue_enabled),
        generated_on=today,
    )


def _maybe_uuid(value: object) -> uuid.UUID | None:
    """Parse an id out of untrusted JSON, or ``None``."""
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _weights_out(weights: UrgencyWeights, vendor_rfq_enabled: bool) -> WeightsOut:
    return WeightsOut(
        weight_due=weights.due,
        weight_value=weights.value,
        weight_unresolved=weights.unresolved,
        weight_flags=weights.flags,
        vendor_rfq_queue_enabled=vendor_rfq_enabled,
    )


@work_queue_router.get("/settings")
async def get_work_queue_settings(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> WeightsOut:
    """The org's urgency weights — readable by anyone who sees the queue, since
    the queue explains itself with them."""
    settings = await load_dashboard_settings(session, principal.active_org_id)
    return _weights_out(settings.weights, settings.vendor_rfq_queue_enabled)


@work_queue_router.put("/settings")
async def put_work_queue_settings(
    payload: WeightsPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.settings_edit))],
) -> WeightsOut:
    """Re-weight the queue. Weights are org-wide config, so this needs
    ``settings_edit``; the read above deliberately does not."""
    row = await get_or_create_row(session, principal.active_org_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    await session.flush()
    # Re-validate through the scoring type: it is the one place that decides what
    # a legal weight set is (e.g. no negatives), and it must agree with the DB.
    weights = UrgencyWeights(
        due=row.weight_due,
        value=row.weight_value,
        unresolved=row.weight_unresolved,
        flags=row.weight_flags,
    )
    return _weights_out(weights, row.vendor_rfq_queue_enabled)


@work_queue_router.get("/recents")
async def get_recents(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> RecentsOut:
    """The caller's *Recently opened* strip — their last 8, most recent first."""
    recents = list(
        await session.scalars(
            select(RecentView)
            .where(RecentView.user_id == principal.user_id)
            .order_by(RecentView.opened_at.desc(), RecentView.entity_id.desc())
            .limit(_RECENTS_LIMIT)
        )
    )
    quote_ids = [r.entity_id for r in recents if r.entity_type == "quote"]
    part_ids = [r.entity_id for r in recents if r.entity_type == "part"]
    labels: dict[uuid.UUID, tuple[str, str | None]] = {}
    if quote_ids:
        for quote_row in await session.execute(
            select(Quote.id, Quote.number, Quote.status).where(Quote.id.in_(quote_ids))
        ):
            labels[quote_row.id] = (quote_row.number, quote_row.status.value)
    if part_ids:
        for part_row in await session.execute(
            select(Part.id, Part.part_number, Part.name).where(Part.id.in_(part_ids))
        ):
            labels[part_row.id] = (part_row.part_number or part_row.name or "", None)
    out: list[RecentRow] = []
    for recent in recents:
        resolved = labels.get(recent.entity_id)
        if resolved is None:
            # Deleted (or never existed) — a strip entry linking to a 404 is worse
            # than a shorter strip.
            continue
        label, quote_status = resolved
        section = "quotes" if recent.entity_type == "quote" else "parts"
        out.append(
            RecentRow(
                entity_type=recent.entity_type,
                entity_id=recent.entity_id,
                label=label,
                status=quote_status,
                deep_link=f"/{section}/{recent.entity_id}",
                opened_at=recent.opened_at,
            )
        )
    return RecentsOut(rows=out)


@work_queue_router.post("/recents", status_code=status.HTTP_204_NO_CONTENT)
async def record_recent(
    payload: RecentIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Response:
    """Record that the caller opened something.

    Upsert on (org, user, entity) so re-opening refreshes the timestamp rather
    than appending, then prune to :data:`_RECENTS_KEEP`. Both matter: this is a
    *resume affordance*, not an access log — an unpruned one would become a
    per-user browsing history with a retention duty under the GDPR pack, for
    rows nobody ever reads (only the newest :data:`_RECENTS_LIMIT` are shown).

    The entity is verified through the caller's org-scoped session first, so a
    client cannot plant arbitrary ids (or another org's) into its own strip."""
    exists_stmt = (
        select(Quote.id).where(Quote.id == payload.entity_id, Quote.deleted_at.is_(None))
        if payload.entity_type == "quote"
        else select(Part.id).where(Part.id == payload.entity_id)
    )
    if (await session.scalars(exists_stmt)).one_or_none() is None:
        raise AppError(
            "not_found",
            "Unknown entity.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    now = datetime.now(UTC)
    stmt = pg_insert(RecentView).values(
        org_id=principal.active_org_id,
        user_id=principal.user_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        opened_at=now,
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[
                RecentView.org_id,
                RecentView.user_id,
                RecentView.entity_type,
                RecentView.entity_id,
            ],
            set_={"opened_at": now},
        )
    )
    # Keep the tail bounded (see the docstring). Deletes by primary key from a
    # window over this user's own rows — RLS still pins the org.
    keep = (
        select(RecentView.entity_type, RecentView.entity_id)
        .where(RecentView.user_id == principal.user_id)
        .order_by(RecentView.opened_at.desc(), RecentView.entity_id.desc())
        .limit(_RECENTS_KEEP)
        .subquery()
    )
    await session.execute(
        delete(RecentView).where(
            RecentView.user_id == principal.user_id,
            tuple_(RecentView.entity_type, RecentView.entity_id).notin_(select(keep)),
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@work_queue_router.get("/kpis")
async def get_kpis(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> KpiOut:
    """The manager glance row. Gated on the manager/admin roles rather than a new
    permission — the spec scopes it by audience ("for managers"), and the M0.3
    matrix stays the single source of truth for capabilities."""
    if not _MANAGER_ROLES.intersection(principal.roles):
        raise AppError(
            "forbidden",
            "The KPI row is available to managers.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    now = datetime.now(UTC)
    open_stmt = select(func.count()).where(
        Quote.status.in_(_OPEN_STATUSES), Quote.deleted_at.is_(None)
    )
    # "Due this week" includes what is already overdue — it is due, and hiding it
    # here would make the glance row disagree with the queue above it.
    due_stmt = open_stmt.where(Quote.due_date.isnot(None), Quote.due_date < now + timedelta(days=7))
    # One quote, one outcome: a quote won then reopened and lost inside the window
    # would otherwise land in *both* buckets and report a 50% win rate off a single
    # loss. Take each quote's LAST closing event in the window, then tally.
    ranked = (
        select(
            QuoteStatusEvent.quote_id,
            QuoteStatusEvent.to_status,
            func.row_number()
            .over(
                partition_by=QuoteStatusEvent.quote_id,
                order_by=(QuoteStatusEvent.created_at.desc(), QuoteStatusEvent.id.desc()),
            )
            .label("rn"),
        )
        .where(
            QuoteStatusEvent.to_status.in_((QuoteStatus.won, QuoteStatus.lost)),
            QuoteStatusEvent.created_at >= now - timedelta(days=30),
        )
        .subquery()
    )
    won_lost_stmt = (
        select(ranked.c.to_status, func.count())
        .where(ranked.c.rn == 1)
        .group_by(ranked.c.to_status)
    )
    closed = {row[0]: row[1] for row in await session.execute(won_lost_stmt)}
    won = closed.get(QuoteStatus.won, 0)
    lost = closed.get(QuoteStatus.lost, 0)
    win_rate = (
        None
        if won + lost == 0
        else (Decimal(won) * 100 / Decimal(won + lost)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
    )
    return KpiOut(
        open_quotes=(await session.execute(open_stmt)).scalar_one(),
        due_this_week=(await session.execute(due_stmt)).scalar_one(),
        win_rate_30d_pct=win_rate,
    )
