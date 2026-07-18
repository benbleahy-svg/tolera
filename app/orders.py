"""Orders tab — the read side of the orders screen (M5.6, spec ``#orderslist``).

Orders are **created** by the buyer-portal checkout (M5.2, ``source=buyer_portal``)
or internal facilitation (M5.7, ``source=facilitated``) — there is **no create-order
affordance here** and no status lifecycle (status is ERP-owned; the only shipment
state is nullable ``Order.shipped_at``). This module is the list + detail read surface:

* ``POST /api/orders/search`` — filter / free-text search / sort / paginate, reusing
  the M1.3 grid engine (:mod:`app.order_filters`). Rows carry the spec columns:
  Order #, Quote #, Account, Contact, PO Number, Date Placed, Parts, Order Total
  (**net**, excl. VAT — a direct read of the persisted ``net_minor``), Source and
  Expected Ship Date (earliest line ``ships_on``).
* ``GET /api/orders/{id}`` — the order detail view: header + persisted §14 tax
  breakdown + the ordered lines.
* ``POST /api/orders/{id}/push-to-erp`` — the ERP push **stub** (no adapter is wired
  in v1; the real adapter is M6). Returns ``not_configured`` so the affordance is
  honest without pretending to push.

Everything is org-scoped by RLS via ``get_session``. The **Edit order** affordance is
gated (spec ``#orderslist``) on ``organization.facilitate_order_updates`` AND the order
having no shipment (``shipped_at IS NULL``) — surfaced as ``can_edit`` per row so the
frontend renders the ⋮ action only when allowed. The editing drawer itself is M5.7.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import (
    Account,
    Component,
    Contact,
    Order,
    OrderLine,
    OrderShippingMethod,
    OrderSource,
    Organization,
    Part,
    Quote,
    QuoteItem,
)
from .order_filters import (
    ORDER_EARLIEST_SHIP,
    ORDER_PARTS_COUNT,
    OrderFilterClause,
    OrderSortClause,
    apply_filters,
    apply_sort,
    apply_system_view,
    is_system_view,
)
from .order_filters import (
    SYSTEM_ORDER_VIEWS as _SYSTEM_ORDER_VIEWS,
)
from .quote_filters import SystemView

orders_router = APIRouter(prefix="/api/orders", tags=["orders"])

_PAGE_SIZE_DEFAULT = 20  # spec footer "1-20 of N", mirrors quotes
_PAGE_SIZE_MAX = 200


def _contact_name(first: str | None, last: str | None, email: str | None) -> str | None:
    """The person who placed the order — "First Last", falling back to the email
    (spec ``#orderslist`` Contact column). NULL when the order has no contact."""
    full = " ".join(p for p in (first, last) if p).strip()
    return full or email or None


def _part_label(
    part_number: str | None, revision: str | None, name: str | None, description: str | None
) -> str | None:
    """A human label for an ordered line's part so several lines are distinguishable
    (spec ``#orderslist`` order detail). Prefer the part number (+ revision), then
    the part name, then the description; NULL when the part carries none (the
    frontend falls back to the line position)."""
    if part_number:
        return f"{part_number} Rev {revision}" if revision else part_number
    return name or description or None


# --------------------------------------------------------------------------- #
# List
# --------------------------------------------------------------------------- #
class OrderRow(BaseModel):
    """One order as rendered in the grid (the spec ``#orderslist`` column set)."""

    id: uuid.UUID
    number: str
    quote_id: uuid.UUID
    quote_number: str | None
    account_id: uuid.UUID | None
    account_name: str | None
    contact_name: str | None
    po_number: str | None
    #: "Date Placed".
    created_at: datetime
    #: "Parts" — count of order lines.
    parts_count: int
    #: "Order Total" — **net, excl. VAT** (persisted ``net_minor``); integer minor
    #: units + explicit ``currency`` (never a float).
    net_minor: int
    currency: str
    source: OrderSource
    #: "Expected Ship Date" — earliest line ``ships_on``; NULL when none set.
    expected_ship_date: date | None
    #: Nullable shipment timestamp — the only shipment state in v1 (no lifecycle).
    shipped_at: datetime | None
    #: Whether the Edit-order ⋮ action is offered: Facilitate Order Updates enabled
    #: AND no shipment yet (spec ``#orderslist``). The drawer is M5.7.
    can_edit: bool


class OrderSearchRequest(BaseModel):
    """Either a computed ``system_view`` key, or an ad-hoc ``filters``/``sort`` set,
    plus an optional free-text ``search`` (order # / quote # / PO / account) and
    offset pagination. ``system_view`` and ``filters``/``sort`` are mutually
    exclusive (matching the quotes engine); ``search`` composes with either."""

    model_config = ConfigDict(extra="forbid")

    system_view: str | None = None
    filters: list[OrderFilterClause] = Field(default_factory=list)
    sort: list[OrderSortClause] = Field(default_factory=list)
    search: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=_PAGE_SIZE_DEFAULT, ge=1, le=_PAGE_SIZE_MAX)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _exclusive(self) -> OrderSearchRequest:
        if self.system_view is not None and (self.filters or self.sort):
            raise ValueError("system_view cannot be combined with filters/sort")
        return self


class OrderSearchResponse(BaseModel):
    rows: list[OrderRow]
    total: int
    limit: int
    offset: int
    #: The computed system views (sidebar/tabs) — derived, never stored.
    views: list[SystemView]


def _base_stmt() -> Select[Any]:
    """``select(Order)`` LEFT-JOINed to quote / account / contact for the display
    columns and free-text search. Outer joins (each reference is 1:1 or nullable),
    so they never change the order row count. All joins are org-scoped (composite
    same-org keys) so RLS + the join predicate agree."""
    return (
        select(Order)
        .outerjoin(Quote, and_(Quote.org_id == Order.org_id, Quote.id == Order.quote_id))
        .outerjoin(Account, and_(Account.org_id == Order.org_id, Account.id == Order.account_id))
        .outerjoin(Contact, and_(Contact.org_id == Order.org_id, Contact.id == Order.contact_id))
    )


def _apply_search(stmt: Select[Any], search: str | None) -> Select[Any]:
    """Free-text search across Order # / Quote # / PO Number / Account name
    (spec ``#orderslist`` toolbar). Case-insensitive substring; empty/blank is a
    no-op. ``company_name`` (the checkout-captured name) is included so a
    portal order without a linked Account is still findable by company."""
    if not search or not search.strip():
        return stmt
    like = f"%{search.strip()}%"
    return stmt.where(
        or_(
            Order.number.ilike(like),
            Quote.number.ilike(like),
            Order.po_number.ilike(like),
            Account.name.ilike(like),
            Order.company_name.ilike(like),
        )
    )


@orders_router.post("/search")
async def search_orders(
    req: OrderSearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> OrderSearchResponse:
    """Filter/search/sort/paginate the active org's orders (RLS-scoped)."""
    org = await session.get(Organization, principal.active_org_id)
    can_edit_orders = bool(org and org.facilitate_order_updates)

    stmt = _apply_search(_base_stmt(), req.search)
    if req.system_view is not None:
        if not is_system_view(req.system_view):
            raise AppError(
                "unknown_system_view",
                f"Unknown system view: {req.system_view}",
                status_code=422,
            )
        stmt = apply_system_view(stmt, req.system_view)
    else:
        stmt = apply_filters(stmt, req.filters)
        stmt = apply_sort(stmt, req.sort)

    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))

    page = (
        stmt.add_columns(
            Quote.number.label("quote_number"),
            Account.name.label("account_name"),
            Contact.first_name.label("contact_first"),
            Contact.last_name.label("contact_last"),
            Contact.email.label("contact_email"),
            ORDER_PARTS_COUNT.label("parts_count"),
            ORDER_EARLIEST_SHIP.label("expected_ship_date"),
        )
        .limit(req.limit)
        .offset(req.offset)
    )
    result = (await session.execute(page)).all()
    rows = [
        OrderRow(
            id=o.id,
            number=o.number,
            quote_id=o.quote_id,
            quote_number=quote_number,
            account_id=o.account_id,
            account_name=account_name,
            contact_name=_contact_name(contact_first, contact_last, contact_email),
            po_number=o.po_number,
            created_at=o.created_at,
            parts_count=parts_count or 0,
            net_minor=o.net_minor,
            currency=o.currency,
            source=o.source,
            expected_ship_date=expected_ship_date,
            shipped_at=o.shipped_at,
            can_edit=can_edit_orders and o.shipped_at is None,
        )
        for (
            o,
            quote_number,
            account_name,
            contact_first,
            contact_last,
            contact_email,
            parts_count,
            expected_ship_date,
        ) in result
    ]
    return OrderSearchResponse(
        rows=rows,
        total=total or 0,
        limit=req.limit,
        offset=req.offset,
        views=list(_SYSTEM_ORDER_VIEWS),
    )


# --------------------------------------------------------------------------- #
# Detail
# --------------------------------------------------------------------------- #
class OrderLineOut(BaseModel):
    """One ordered line in the detail view (spec ``#orderslist`` → order detail)."""

    id: uuid.UUID
    quote_item_id: uuid.UUID
    #: 1-based line number on the source quote (natural line order + identity).
    position: int
    #: Human label for the ordered part — part number (+ rev) / name / description,
    #: so several lines are distinguishable. NULL when the part carries none of them
    #: (the frontend then falls back to the position). Read from the quote's part.
    part_label: str | None
    quantity: int
    unit_price_minor: int
    total_price_minor: int
    expedites_fee_minor: int
    lead_time_days: int | None
    ships_on: date | None
    add_ons: list[Any] | None


class OrderTaxRateLine(BaseModel):
    rate_pct: float
    net_minor: int
    vat_minor: int


class OrderDetail(BaseModel):
    """The order detail view — header, persisted §14-UStG tax breakdown, and lines.

    The tax figures are a **read of the persisted Order** (never a recompute — the
    tier-1 money invariant); the M5.4 PDF renders from the same stored values."""

    id: uuid.UUID
    number: str
    source: OrderSource
    quote_id: uuid.UUID
    quote_number: str | None
    account_id: uuid.UUID | None
    account_name: str | None
    contact_id: uuid.UUID | None
    contact_name: str | None
    po_number: str | None
    company_name: str | None
    billing_address: str | None
    shipping_method: OrderShippingMethod | None
    notes: str | None
    created_at: datetime
    shipped_at: datetime | None
    # --- Money (integer minor units + explicit currency) ---
    currency: str
    net_minor: int
    vat_minor: int
    gross_minor: int
    # --- §14-UStG tax posture (persisted) ---
    vat_rate_pct: float
    vat_label: str | None
    reverse_charge: bool
    kleinunternehmer: bool
    tax_note: str | None
    supplier_ust_id_nr: str | None
    buyer_ust_id_nr: str | None
    tax_rate_lines: list[OrderTaxRateLine] | None
    expected_ship_date: date | None
    #: Edit-order affordance (Facilitate Order Updates enabled AND no shipment).
    can_edit: bool
    lines: list[OrderLineOut]


@orders_router.get("/{order_id}")
async def get_order(
    order_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> OrderDetail:
    """The order detail view (RLS-scoped; a cross-org id is invisible → 404)."""
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError("not_found", "Order not found.", status_code=status.HTTP_404_NOT_FOUND)

    quote = await session.get(Quote, order.quote_id)
    account = await session.get(Account, order.account_id) if order.account_id is not None else None
    contact = await session.get(Contact, order.contact_id) if order.contact_id is not None else None

    # Join each ordered line to its quote line item → root component → part for the
    # line position + a human part label. All joins are org-scoped (composite
    # same-org keys) so RLS and the join agree; ordered by the quote line position.
    line_rows = (
        await session.execute(
            select(
                OrderLine,
                QuoteItem.position.label("position"),
                Part.part_number.label("part_number"),
                Part.revision.label("revision"),
                Part.name.label("part_name"),
                Part.description.label("description"),
            )
            .outerjoin(
                QuoteItem,
                and_(
                    QuoteItem.org_id == OrderLine.org_id,
                    QuoteItem.id == OrderLine.quote_item_id,
                ),
            )
            .outerjoin(
                Component,
                and_(
                    Component.org_id == QuoteItem.org_id,
                    Component.id == QuoteItem.root_component_id,
                ),
            )
            .outerjoin(Part, and_(Part.org_id == Component.org_id, Part.id == Component.part_id))
            .where(OrderLine.order_id == order.id)
            .order_by(QuoteItem.position.asc(), OrderLine.created_at.asc(), OrderLine.id.asc())
        )
    ).all()
    expected_ship = min(
        (r.OrderLine.ships_on for r in line_rows if r.OrderLine.ships_on is not None),
        default=None,
    )

    org = await session.get(Organization, principal.active_org_id)
    can_edit = bool(org and org.facilitate_order_updates) and order.shipped_at is None

    tax_rate_lines = None
    if order.tax_rate_lines is not None:
        tax_rate_lines = [
            OrderTaxRateLine(
                rate_pct=float(row["rate_pct"]),
                net_minor=int(row["net_minor"]),
                vat_minor=int(row["vat_minor"]),
            )
            for row in order.tax_rate_lines
        ]

    return OrderDetail(
        id=order.id,
        number=order.number,
        source=order.source,
        quote_id=order.quote_id,
        quote_number=quote.number if quote else None,
        account_id=order.account_id,
        account_name=account.name if account else None,
        contact_id=order.contact_id,
        contact_name=(
            _contact_name(contact.first_name, contact.last_name, contact.email) if contact else None
        ),
        po_number=order.po_number,
        company_name=order.company_name,
        billing_address=order.billing_address,
        shipping_method=order.shipping_method,
        notes=order.notes,
        created_at=order.created_at,
        shipped_at=order.shipped_at,
        currency=order.currency,
        net_minor=order.net_minor,
        vat_minor=order.vat_minor,
        gross_minor=order.gross_minor,
        vat_rate_pct=float(order.vat_rate_pct),
        vat_label=order.vat_label,
        reverse_charge=order.reverse_charge,
        kleinunternehmer=order.kleinunternehmer,
        tax_note=order.tax_note,
        supplier_ust_id_nr=order.supplier_ust_id_nr,
        buyer_ust_id_nr=order.buyer_ust_id_nr,
        tax_rate_lines=tax_rate_lines,
        expected_ship_date=expected_ship,
        can_edit=can_edit,
        lines=[
            OrderLineOut(
                id=r.OrderLine.id,
                quote_item_id=r.OrderLine.quote_item_id,
                position=r.position,
                part_label=_part_label(r.part_number, r.revision, r.part_name, r.description),
                quantity=r.OrderLine.quantity,
                unit_price_minor=r.OrderLine.unit_price_minor,
                total_price_minor=r.OrderLine.total_price_minor,
                expedites_fee_minor=r.OrderLine.expedites_fee_minor,
                lead_time_days=r.OrderLine.lead_time_days,
                ships_on=r.OrderLine.ships_on,
                add_ons=r.OrderLine.add_ons,
            )
            for r in line_rows
        ],
    )


# --------------------------------------------------------------------------- #
# ERP push — stub (spec #orderslist "Push to ERP — if ERP adapter configured")
# --------------------------------------------------------------------------- #
class ErpPushResponse(BaseModel):
    order_id: uuid.UUID
    #: ``not_configured`` in v1 — no ERP adapter is wired (the real adapter is M6).
    status: str


@orders_router.post("/{order_id}/push-to-erp")
async def push_order_to_erp(
    order_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ErpPushResponse:
    """Re-push the order payload to the shop's ERP (spec ``#orderslist``).

    **Stub for v1** — no ERP adapter is configured yet (real adapter → M6). We
    still resolve the order (so a bad/cross-org id 404s honestly) and then report
    ``not_configured`` rather than pretending to push. The frontend only offers the
    action when an adapter exists, so this is the defensive backstop."""
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError("not_found", "Order not found.", status_code=status.HTTP_404_NOT_FOUND)
    return ErpPushResponse(order_id=order.id, status="not_configured")
