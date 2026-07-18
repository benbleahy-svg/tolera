"""Quotes list — the read side of the quotes screen (M1.3, spec ``#quoteslist``).

One endpoint: ``POST /api/quotes/search``. It is a **read** (no side effects) but
takes a structured, persistable filter/sort body, so a POST is the right tool — and
crucially the body shape is **identical** to a saved view's stored ``filters``/``sort``
(DECISIONS.md 2026-06-25 "M1.3 build path"), so applying a saved view is just POSTing
its stored clauses back. The list is **read-only** in M1.3: quotes are created by the
seeder/owner (for this list) and by M1.4's create flow thereafter — the app role has
SELECT-only on ``quote``.

Results are org-scoped by RLS via ``get_session``; a request either selects a computed
``system_view`` (All Quotes / My Quotes / Drafts / Outstanding / Overdue) **or** an
ad-hoc ``filters``/``sort`` set — never both.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal, get_principal
from .authz import Permission, has_permission, require
from .config_completeness import quote_items_missing_rates
from .costing import recalculate_component
from .deps import get_session
from .errors import AppError
from .models import (
    Account,
    AccountType,
    Component,
    Contact,
    MembershipStatus,
    Organization,
    QiWorkflowStatus,
    Quote,
    QuoteItem,
    QuoteStatus,
    QuoteStatusEvent,
    ReviewItem,
    UserOrgMembership,
)
from .parts import create_root_part
from .quantities import (
    ChangeQuantitiesRequest,
    QuantityCellOut,
    create_default_break,
    load_grids,
    set_quantity_breaks,
)
from .quote_filters import (
    QUOTE_MAX_PRIORITY,
    FilterClause,
    SortClause,
    apply_filters,
    apply_sort,
    apply_system_view,
    is_system_view,
)
from .quote_lifecycle import INITIAL_STATUS, allowed_targets, required_permission, transition

# Line-item workflow_status values that count as "done" for the quote's outstanding-
# work rollup (spec: a no-quoted item counts as complete but is unselectable).
_DONE_LINE_ITEM_STATUSES = (QiWorkflowStatus.completed, QiWorkflowStatus.no_quote)

quotes_router = APIRouter(prefix="/api/quotes", tags=["quotes"])

_PAGE_SIZE_DEFAULT = 20  # spec footer "1-20 of N"
_PAGE_SIZE_MAX = 200


class QuoteRow(BaseModel):
    """One quote as rendered in the grid (the M1.3 column subset)."""

    id: uuid.UUID
    number: str
    status: QuoteStatus
    account_id: uuid.UUID | None
    salesperson_id: uuid.UUID | None
    estimator_id: uuid.UUID | None
    rfq_number: str | None
    due_date: datetime | None
    created_at: datetime
    #: M5.0 #partview — derived MAX(line-item priority); NULL when the quote has no
    #: prioritised line (rendered "—" in the grid).
    priority: int | None


class QuoteSearchRequest(BaseModel):
    """Either a computed ``system_view`` key, or an ad-hoc ``filters``/``sort`` set
    (the same shape stored on a saved view) — plus offset pagination."""

    model_config = ConfigDict(extra="forbid")

    system_view: str | None = None
    filters: list[FilterClause] = Field(default_factory=list)
    sort: list[SortClause] = Field(default_factory=list)
    limit: int = Field(default=_PAGE_SIZE_DEFAULT, ge=1, le=_PAGE_SIZE_MAX)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _exclusive(self) -> QuoteSearchRequest:
        if self.system_view is not None and (self.filters or self.sort):
            raise ValueError("system_view cannot be combined with filters/sort")
        return self


class QuoteSearchResponse(BaseModel):
    rows: list[QuoteRow]
    total: int
    limit: int
    offset: int


def _quote_row(q: Quote, priority: int | None) -> QuoteRow:
    return QuoteRow(
        id=q.id,
        number=q.number,
        status=q.status,
        account_id=q.account_id,
        salesperson_id=q.salesperson_id,
        estimator_id=q.estimator_id,
        rfq_number=q.rfq_number,
        due_date=q.due_date,
        created_at=q.created_at,
        priority=priority,
    )


@quotes_router.post("/search")
async def search_quotes(
    req: QuoteSearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> QuoteSearchResponse:
    """Filter/sort/paginate the active org's quotes (RLS-scoped)."""
    # Trashed quotes (M1.4 soft-delete) never surface in the list; a dedicated Trash
    # view can opt them back in later (spec ``#quoteslist``).
    stmt = select(Quote).where(Quote.deleted_at.is_(None))
    if req.system_view is not None:
        if not is_system_view(req.system_view):
            raise AppError(
                "unknown_system_view",
                f"Unknown system view: {req.system_view}",
                status_code=422,
            )
        stmt = apply_system_view(stmt, req.system_view, user_id=principal.user_id)
    else:
        stmt = apply_filters(stmt, req.filters)
        stmt = apply_sort(stmt, req.sort)

    # Total over the filtered set, independent of ordering/pagination (the footer
    # "1-20 of N"). Strip ORDER BY for the count subquery.
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    # Carry the derived MAX(line-item priority) alongside each row (M5.0). Added only
    # to the page query — the filter/sort/count above already reference the same
    # correlated subquery where needed.
    page = (
        stmt.add_columns(QUOTE_MAX_PRIORITY.label("priority")).limit(req.limit).offset(req.offset)
    )
    rows = (await session.execute(page)).all()
    return QuoteSearchResponse(
        rows=[_quote_row(q, priority) for q, priority in rows],
        total=total or 0,
        limit=req.limit,
        offset=req.offset,
    )


# --------------------------------------------------------------------------- #
# M1.4 — create, detail, lifecycle transitions, line items, trash
# --------------------------------------------------------------------------- #
class QuoteCreate(BaseModel):
    """Open a Draft quote by direct-create (email ingest is M3). Every reference is
    optional at create — a contact is only mandatory at the Draft→Sent step."""

    model_config = ConfigDict(extra="forbid")

    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    salesperson_id: uuid.UUID | None = None
    estimator_id: uuid.UUID | None = None
    rfq_number: str | None = Field(default=None, max_length=200)
    due_date: datetime | None = None
    expiration_date: datetime | None = None


class QuoteUpdate(BaseModel):
    """Partial edit of a Draft quote's General/People fields. Only fields present in
    the body change. Editing is locked once a quote is Sent (Create Revision is M5)."""

    model_config = ConfigDict(extra="forbid")

    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    salesperson_id: uuid.UUID | None = None
    estimator_id: uuid.UUID | None = None
    rfq_number: str | None = Field(default=None, max_length=200)
    due_date: datetime | None = None
    expiration_date: datetime | None = None
    private_notes: str | None = None


class QuoteTransitionRequest(BaseModel):
    """Request a lifecycle status change. ``note`` carries e.g. the Lost reason."""

    model_config = ConfigDict(extra="forbid")

    to_status: QuoteStatus
    note: str | None = Field(default=None, max_length=2000)


class QuoteItemOut(BaseModel):
    """A line item (root component) on a quote, with its per-quantity-break grid (M1.6 —
    the columns every downstream cost/price renders into; ascending by quantity)."""

    id: uuid.UUID
    position: int
    root_component_id: uuid.UUID
    part_id: uuid.UUID
    workflow_status: QiWorkflowStatus
    was_won: bool
    export_controlled: bool
    #: M5.0 #partview — line-item priority (nullable numeric, higher = more urgent).
    priority: int | None
    quantities: list[QuantityCellOut]


class QuoteItemUpdate(BaseModel):
    """Editable line-item fields from the estimating sidebar (M5.0). ``priority`` is
    nullable numeric (higher = more urgent); the quote grid derives MAX over it."""

    model_config = ConfigDict(extra="forbid")

    priority: int | None = Field(default=None, ge=1, le=10)


class WorkflowTracker(BaseModel):
    """The 4-stage Draft-phase progress tracker — derived from the quote's timestamps
    + the live count of incomplete line items (spec ``#quotelifecycle``), not stored."""

    rfq_received_at: datetime | None
    quote_started_at: datetime | None
    incomplete_item_count: int
    #: M3.8 — open Requirements-Review items across the quote's parts. Spec
    #: #rules: the unresolved count drives "Outstanding Work".
    unresolved_review_item_count: int = 0
    quote_sent_at: datetime | None


class QuoteDetail(BaseModel):
    """The quote-detail skeleton: header + lifecycle + the workflow tracker + items.
    ``allowed_transitions`` is what the ACTIONS menu may legally offer next."""

    id: uuid.UUID
    number: str
    revision: int
    status: QuoteStatus
    currency: str
    account_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    salesperson_id: uuid.UUID | None
    estimator_id: uuid.UUID | None
    rfq_number: str | None
    private_notes: str | None
    due_date: datetime | None
    expiration_date: datetime | None
    expired_at: datetime | None
    sent_at: datetime | None
    config_frozen_at: datetime | None
    trashed: bool
    # M1.14 #missing-rates-warning: how many line items use an operation whose
    # rate resolves to nothing — non-blocking banner, reappears until rates set
    missing_rates_item_count: int
    # the top-of-quote dynamic-lead-time editor staging (M1.11 #addons)
    expedite_tiers: dict[str, Any] | None
    allowed_transitions: list[QuoteStatus]
    workflow: WorkflowTracker
    items: list[QuoteItemOut]
    created_at: datetime
    updated_at: datetime


def _is_editable(quote: Quote) -> bool:
    """A quote is editable in its Draft phase only: while ``draft``, or while
    ``on_hold`` *from* a draft (spec: On-Hold is editable only if it came from Draft).
    Sent and closed quotes are read-only — changes go through a revision (M5). A
    **trashed** quote is never editable (it must be restored first), mirroring the
    transition/list paths (CodeRabbit 2026-06-26)."""
    if quote.deleted_at is not None:
        return False
    if quote.status is QuoteStatus.draft:
        return True
    return quote.status is QuoteStatus.on_hold and quote.status_before_hold is QuoteStatus.draft


async def _next_quote_number(session: AsyncSession, org_id: uuid.UUID) -> str:
    """Atomically allocate this org's next sequential quote number (DECISIONS.md
    2026-06-26). The upsert row-locks the counter, so concurrent creates serialise;
    ``last_number`` is the last assigned value (0 ⇒ first quote is 1)."""
    result = await session.execute(
        text(
            "INSERT INTO quote_counter AS qc (org_id, last_number) VALUES (:org, 1) "
            "ON CONFLICT (org_id) DO UPDATE SET last_number = qc.last_number + 1 "
            "RETURNING last_number"
        ),
        {"org": str(org_id)},
    )
    return str(result.scalar_one())


async def _validate_account(session: AsyncSession, account_id: uuid.UUID | None) -> None:
    """A quote's account must be a live, non-``vendor`` account in this org (the same-org
    part is also a DB invariant via the composite FK; this adds the vendor/archived rule
    + a clean 422 instead of a 500)."""
    if account_id is None:
        return
    account = await session.get(Account, account_id)
    if account is None or account.deleted_at is not None:
        raise AppError(
            "invalid_account", "Account not found in this organization.", status_code=422
        )
    if account.type is AccountType.vendor:
        raise AppError(
            "invalid_account",
            "A vendor account cannot be assigned to a quote.",
            status_code=422,
        )


async def _validate_contact(session: AsyncSession, contact_id: uuid.UUID | None) -> None:
    if contact_id is None:
        return
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise AppError(
            "invalid_contact", "Contact not found in this organization.", status_code=422
        )


async def _validate_member(session: AsyncSession, user_id: uuid.UUID | None, *, field: str) -> None:
    """Reject a salesperson/estimator who isn't an **active member of the active org**
    (the M1.1 salesperson guard; the org-scoped session makes the lookup org-local)."""
    if user_id is None:
        return
    member = await session.scalar(
        select(UserOrgMembership.id).where(
            UserOrgMembership.user_id == user_id,
            UserOrgMembership.status == MembershipStatus.active,
        )
    )
    if member is None:
        raise AppError(
            f"invalid_{field}",
            f"{field.capitalize()} must be an active member of this organization.",
            status_code=422,
        )


async def _get_quote_or_404(session: AsyncSession, quote_id: uuid.UUID) -> Quote:
    """Fetch a quote in the active org (trashed included, so detail/restore work)."""
    quote = await session.get(Quote, quote_id)
    if quote is None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    return quote


async def _load_detail(session: AsyncSession, quote: Quote) -> QuoteDetail:
    """Assemble the detail response: items (joined to their part) + the derived tracker."""
    rows = (
        await session.execute(
            select(QuoteItem, Component.part_id)
            .join(
                Component,
                (Component.id == QuoteItem.root_component_id)
                & (Component.org_id == QuoteItem.org_id),
            )
            .where(QuoteItem.quote_id == quote.id)
            .order_by(QuoteItem.position)
        )
    ).all()
    # One query for every line item's quantity-break grid (avoids an N+1 over items).
    grids = await load_grids(session, quote.org_id, [qi.root_component_id for qi, _ in rows])
    items = [
        QuoteItemOut(
            id=qi.id,
            position=qi.position,
            root_component_id=qi.root_component_id,
            part_id=part_id,
            workflow_status=qi.workflow_status,
            was_won=qi.was_won,
            export_controlled=qi.export_controlled,
            priority=qi.priority,
            quantities=grids.get(qi.root_component_id, []),
        )
        for qi, part_id in rows
    ]
    incomplete = sum(1 for qi, _ in rows if qi.workflow_status not in _DONE_LINE_ITEM_STATUSES)
    # M3.8, spec #rules: "The unresolved count drives the quote's Outstanding
    # Work / Incomplete Quote Items" — a quote with an open review item still
    # has work on it, whatever its line-item statuses say.
    unresolved_review_items = await session.scalar(
        select(func.count())
        .select_from(ReviewItem)
        .where(
            ReviewItem.org_id == quote.org_id,
            ReviewItem.quote_id == quote.id,
            ReviewItem.status == "open",
        )
    )
    tracker = WorkflowTracker(
        rfq_received_at=quote.rfq_received_date,
        quote_started_at=quote.started_at,
        incomplete_item_count=incomplete,
        unresolved_review_item_count=unresolved_review_items or 0,
        quote_sent_at=quote.sent_at,
    )
    return QuoteDetail(
        id=quote.id,
        number=quote.number,
        revision=quote.revision,
        status=quote.status,
        currency=quote.currency,
        account_id=quote.account_id,
        contact_id=quote.contact_id,
        salesperson_id=quote.salesperson_id,
        estimator_id=quote.estimator_id,
        rfq_number=quote.rfq_number,
        private_notes=quote.private_notes,
        due_date=quote.due_date,
        expiration_date=quote.expiration_date,
        expired_at=quote.expired_at,
        sent_at=quote.sent_at,
        config_frozen_at=quote.config_frozen_at,
        trashed=quote.deleted_at is not None,
        missing_rates_item_count=await quote_items_missing_rates(session, quote.id),
        expedite_tiers=quote.expedite_tiers,
        allowed_transitions=sorted(allowed_targets(quote.status, quote.status_before_hold)),
        workflow=tracker,
        items=items,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


@quotes_router.post("", status_code=status.HTTP_201_CREATED)
async def create_quote(
    payload: QuoteCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> QuoteDetail:
    """Create a Draft quote against an account, with an auto-allocated number. The
    quote opens the golden thread; line items are added via ``POST /{id}/items``."""
    await _validate_account(session, payload.account_id)
    await _validate_contact(session, payload.contact_id)
    await _validate_member(session, payload.salesperson_id, field="salesperson")
    await _validate_member(session, payload.estimator_id, field="estimator")

    now = datetime.now(UTC)
    number = await _next_quote_number(session, principal.active_org_id)
    # The quote inherits the org's currency (EUR for DE/AT, CHF for CH) — never the
    # bare model default, so a CHF org's monetary context is correct from creation
    # (DACH money convention; CodeRabbit 2026-06-26).
    org = await session.get(Organization, principal.active_org_id)
    if org is None:
        # A valid principal always has its active org visible under RLS; a miss means
        # tenancy/RLS breakage — fail loud rather than invent a currency (CodeRabbit
        # 2026-06-26: never invent a value that wasn't on the source).
        raise AppError(
            "invalid_org",
            "Active organization is not available.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    currency = org.currency
    quote = Quote(
        org_id=principal.active_org_id,
        number=number,
        status=INITIAL_STATUS,
        currency=currency,
        account_id=payload.account_id,
        contact_id=payload.contact_id,
        salesperson_id=payload.salesperson_id,
        estimator_id=payload.estimator_id,
        rfq_number=payload.rfq_number,
        due_date=payload.due_date,
        expiration_date=payload.expiration_date,
        rfq_received_date=now,  # tracker stage 1 — set when the quote is created
        salesperson_assigned_at=now if payload.salesperson_id is not None else None,
        estimator_assigned_at=now if payload.estimator_id is not None else None,
    )
    session.add(quote)
    await session.flush()
    # Open the audit trail (no prior status → draft).
    session.add(
        QuoteStatusEvent(
            org_id=quote.org_id,
            quote_id=quote.id,
            from_status=None,
            to_status=INITIAL_STATUS,
            actor_id=principal.user_id,
        )
    )
    await session.flush()
    return await _load_detail(session, quote)


@quotes_router.get("/{quote_id}")
async def get_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> QuoteDetail:
    """Fetch the quote-detail skeleton (trashed quotes included, for the restore UI)."""
    return await _load_detail(session, await _get_quote_or_404(session, quote_id))


@quotes_router.get("/{quote_id}/triage-brief")
async def get_triage_brief(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> dict[str, Any]:
    """The cached RFQ Triage Brief for the dashboard card + header chip (M3.9,
    spec #ai-triage). Returns the ``triage_brief`` JSONB, or a ``pending`` shell
    when the brief hasn't been generated yet (a manually-created quote, or one
    still being processed) — never a silent 404 for a real quote."""
    quote = await _get_quote_or_404(session, quote_id)
    if quote.triage_brief is None:
        return {"brief": None, "ai": {"enabled": False, "reason": "pending"}}
    return {"brief": quote.triage_brief}


@quotes_router.patch("/{quote_id}")
async def update_quote(
    quote_id: uuid.UUID,
    payload: QuoteUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> QuoteDetail:
    """Edit a Draft quote's General/People fields. Rejected once the quote is locked."""
    quote = await _get_quote_or_404(session, quote_id)
    if not _is_editable(quote):
        raise AppError(
            "quote_locked",
            "This quote is no longer a draft; changes require a revision.",
            status_code=409,
        )
    changes = payload.model_dump(exclude_unset=True)
    if "account_id" in changes:
        await _validate_account(session, changes["account_id"])
    if "contact_id" in changes:
        await _validate_contact(session, changes["contact_id"])
    if "salesperson_id" in changes:
        await _validate_member(session, changes["salesperson_id"], field="salesperson")
    if "estimator_id" in changes:
        await _validate_member(session, changes["estimator_id"], field="estimator")
    # Keep ``*_assigned_at`` coherent with its FK: stamp when the assignee changes,
    # and clear it on unassign so a NULL assignee never carries a stale timestamp
    # (CodeRabbit 2026-06-26). Evaluated before the setattr loop, while the old
    # value is still on the row.
    now = datetime.now(UTC)
    if "salesperson_id" in changes and changes["salesperson_id"] != quote.salesperson_id:
        quote.salesperson_assigned_at = now if changes["salesperson_id"] is not None else None
    if "estimator_id" in changes and changes["estimator_id"] != quote.estimator_id:
        quote.estimator_assigned_at = now if changes["estimator_id"] is not None else None
    for field_name, value in changes.items():
        setattr(quote, field_name, value)
    await session.flush()
    return await _load_detail(session, quote)


@quotes_router.post("/{quote_id}/items", status_code=status.HTTP_201_CREATED)
async def add_quote_item(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> QuoteDetail:
    """Add a root line item: a fresh Part → root Component → QuoteItem at the next
    position (the 4-layer model; M1.5 fills in the part/component detail). Setting the
    first item marks the quote's ``started_at`` (estimator work has begun)."""
    # Lock the quote row FIRST (refreshing its in-session state), then gate on
    # editability — so a concurrent transition/trash can't change status/deleted_at
    # in a TOCTOU window between the check and the lock. The lock also serialises the
    # max(position)+1 allocation; UNIQUE (quote_id, position) is the DB backstop
    # (CodeRabbit 2026-06-26).
    quote = await session.scalar(
        select(Quote)
        .where(Quote.id == quote_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if quote is None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    if not _is_editable(quote):
        raise AppError(
            "quote_locked",
            "Line items can only be added while the quote is a draft.",
            status_code=409,
        )
    # The 4-layer model: a fresh Part (with its root Node) → root Component → QuoteItem.
    part = await create_root_part(session, quote.org_id)
    component = Component(org_id=quote.org_id, part_id=part.id, is_root_component=True)
    session.add(component)
    await session.flush()
    # Every line item opens with a single qty=1 break — the grid the rest of M1 fills.
    await create_default_break(session, quote.org_id, component.id)
    # M1.10: snapshot the org's pricing-item/discount defs onto the new line
    # (E4-d attach-time copy; later def edits never touch this draft).
    from .pricing import attach_default_pricing

    await attach_default_pricing(session, quote.org_id, component.id)
    max_position = await session.scalar(
        select(func.max(QuoteItem.position)).where(QuoteItem.quote_id == quote.id)
    )
    next_position = (max_position or 0) + 1
    session.add(
        QuoteItem(
            org_id=quote.org_id,
            quote_id=quote.id,
            root_component_id=component.id,
            position=next_position,
        )
    )
    if quote.started_at is None:
        quote.started_at = datetime.now(UTC)
    await session.flush()
    return await _load_detail(session, quote)


@quotes_router.patch("/{quote_id}/items/{item_id}")
async def update_quote_item(
    quote_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: QuoteItemUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> QuoteDetail:
    """Edit a line item's estimating-sidebar fields (M5.0 #partview). v1 carries
    ``priority`` — nullable numeric, higher = more urgent; the quotes grid derives
    MAX(priority) per quote. Draft-only, like every other line-item mutation."""
    quote = await _get_quote_or_404(session, quote_id)
    if not _is_editable(quote):
        raise AppError(
            "quote_locked",
            "Line items can only be edited while the quote is a draft.",
            status_code=409,
        )
    item = await session.get(QuoteItem, item_id)
    if item is None or item.quote_id != quote.id:
        raise AppError("not_found", "Line item not found.", status_code=status.HTTP_404_NOT_FOUND)
    changes = payload.model_dump(exclude_unset=True)
    for field_name, value in changes.items():
        setattr(item, field_name, value)
    await session.flush()
    return await _load_detail(session, quote)


@quotes_router.put("/{quote_id}/items/{item_id}/quantities")
async def change_quantities(
    quote_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ChangeQuantitiesRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> QuoteDetail:
    """ "Change quantities" — reshape a line item's quantity breaks to the requested set
    (spec ``#partview`` Pricing & Quantities). Draft-only; the response carries the
    reshaped per-qty grid. The break set must be non-empty, positive, and unique (M1.6)."""
    # Lock the quote first (same TOCTOU reasoning as add-item): gate editability against a
    # concurrent transition/trash, and serialise concurrent quantity edits on this quote.
    quote = await session.scalar(
        select(Quote)
        .where(Quote.id == quote_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if quote is None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    if not _is_editable(quote):
        raise AppError(
            "quote_locked",
            "Quantities can only be changed while the quote is a draft.",
            status_code=409,
        )
    # RLS scopes the lookup to the active org; the quote_id check rejects an item that
    # belongs to a different (same-org) quote.
    item = await session.get(QuoteItem, item_id)
    if item is None or item.quote_id != quote_id:
        raise AppError(
            "not_found",
            "Line item not found on this quote.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    # M4.3: make quantities are locked while the component is in a nest — the
    # shared costing would silently drift (spec #nesting dialog warning).
    from .nesting import ensure_component_not_nested

    await ensure_component_not_nested(session, item.root_component_id)
    await set_quantity_breaks(session, quote.org_id, item.root_component_id, payload.quantities)
    # New breaks need their per-op cost cells materialised (removed breaks cascaded
    # theirs away); recalc writes calc_cost only — overrides are untouched (M1.7).
    await recalculate_component(session, quote.org_id, item.root_component_id)
    return await _load_detail(session, quote)


@quotes_router.post("/{quote_id}/transition")
async def transition_quote(
    quote_id: uuid.UUID,
    payload: QuoteTransitionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> QuoteDetail:
    """Move a quote through its lifecycle. The required capability is target-aware
    (finalize→``quote_finalize``, cancel→``quote_delete``, else ``quote_edit``); the
    state machine rejects illegal transitions server-side."""
    quote = await _get_quote_or_404(session, quote_id)
    if quote.deleted_at is not None:
        raise AppError(
            "quote_trashed",
            "A trashed quote cannot change status; restore it first.",
            status_code=409,
        )
    needed = required_permission(quote.status, payload.to_status)
    if not has_permission(principal.roles, needed):
        raise AppError(
            "forbidden",
            "You do not have permission to perform this transition",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    await transition(
        session, quote, payload.to_status, actor_id=principal.user_id, note=payload.note
    )
    return await _load_detail(session, quote)


@quotes_router.post("/{quote_id}/trash")
async def trash_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_delete))],
) -> QuoteDetail:
    """Soft-delete (Trash) a quote from any status. Recoverable via restore. Idempotent."""
    quote = await _get_quote_or_404(session, quote_id)
    if quote.deleted_at is None:
        quote.deleted_at = datetime.now(UTC)
        await session.flush()
    return await _load_detail(session, quote)


@quotes_router.post("/{quote_id}/restore")
async def restore_quote(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_delete))],
) -> QuoteDetail:
    """Un-trash a quote (clear ``deleted_at``); its lifecycle status is unchanged.
    Idempotent."""
    quote = await _get_quote_or_404(session, quote_id)
    if quote.deleted_at is not None:
        quote.deleted_at = None
        await session.flush()
    return await _load_detail(session, quote)
