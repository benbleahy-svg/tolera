"""Facilitate Order (M5.7) — the internal Build-Order drawer + pre-ship editing.

Spec ``#order`` ("Build Order" / "Facilitate Order" — two-step flow) +
``#shipping-options`` (facilitated-order options). Unlike the buyer-portal
checkout (:mod:`app.checkout`, token-authed), facilitation is **internal**: an
estimator (Clerk session, ``Permission.quote_edit``) converts an accepted quote
into an Order (``source=facilitated``), picking one quantity break per line plus
per-line **Discounts** (Percent) and **Additional Charges** (Price), and may edit
the order **before shipment** with a recorded **history trail**.

Three endpoints:

* ``POST /api/quotes/{quote_id}/facilitate-order`` — build the Order + OrderLines
  + adjustments; writes a ``created`` history event.
* ``PATCH /api/orders/{order_id}`` — a pre-ship edit (PO / addresses / shipping /
  add-remove lines), gated on ``facilitate_order_updates AND shipped_at IS NULL``
  (KB ``post-order-changes-and-limitations``: no edits once shipped / on CC
  orders — CC is hidden in v1). Writes an ``edited`` history event.
* ``GET /api/orders/{order_id}/history`` — the chronological trail.

Money invariants (CLAUDE.md §5): prices are **re-derived server-side** from
:func:`app.checkout._resolve_line` (the request carries only IDs + quantities for
the priced portion — a tampered client cannot change what a break costs);
shop-entered discounts/charges are the only client-supplied money and are
validated + persisted as integer minor units + currency. VAT is resolved by
:mod:`app.vat_service` (never in Kalk); the §14-UStG breakdown is persisted so
the M5.4 PDF renders stored figures.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .checkout import CheckoutLineSelection, _next_order_number, _resolve_line, _ResolvedLine
from .deps import get_session
from .errors import AppError
from .models import (
    Order,
    OrderHistoryEvent,
    OrderHistoryEventKind,
    OrderLine,
    OrderLineAdjustment,
    OrderLineAdjustmentKind,
    OrderShippingMethod,
    OrderSource,
    Organization,
    Quote,
)
from .tax import round_money, to_minor_units
from .vat_service import VIESClient, get_vies_client, resolve_order_tax

facilitate_router = APIRouter(prefix="/api", tags=["facilitate"])


# --------------------------------------------------------------------------- #
# Request schemas
# --------------------------------------------------------------------------- #
class DiscountInput(BaseModel):
    """A per-line **Discount** (Build Order drawer — Percent). Percentages **sum,
    they don't compound** (mirrors :class:`~app.models.Discount`)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)
    percent: Decimal = Field(ge=0, le=100)


class AdditionalChargeInput(BaseModel):
    """A per-line **Additional Charge** (Build Order drawer — Price). A fixed
    money amount (e.g. "Tooling (Required) — €500.00")."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(ge=0)


class FacilitateLineSelection(CheckoutLineSelection):
    """One line item's build: the same priced break (quote item + quantity +
    optional expedite / add-ons) the checkout resolves, plus an optional per-line
    ``ships_on`` override and the per-line Discounts / Additional Charges. Extends
    :class:`~app.checkout.CheckoutLineSelection` so the shared
    :func:`~app.checkout._resolve_line` re-derives the priced portion identically."""

    #: Manual Ships-On override (spec ``#shipping-options`` — adjustable per line);
    #: absent → placement date + the break's lead time (calendar days, v1).
    ships_on: date | None = None
    discounts: list[DiscountInput] = Field(default_factory=list)
    additional_charges: list[AdditionalChargeInput] = Field(default_factory=list)


class FacilitateOrderRequest(BaseModel):
    """The Build-Order submission (drawer Step 1 selections + Step 2 shipping &
    payment). PO is **optional** for a facilitated order (Payment = Not Provided
    leaves it blank; Purchase Order sets it)."""

    model_config = ConfigDict(extra="forbid")

    selections: list[FacilitateLineSelection] = Field(min_length=1)
    po_number: str | None = Field(default=None, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    billing_address: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    buyer_ust_id_nr: str | None = Field(default=None, max_length=32)
    #: None (NULL) is a valid facilitated option ("None" in the shipping table).
    shipping_method: OrderShippingMethod | None = None


class OrderEditRequest(BaseModel):
    """A pre-ship order edit (spec ``#order`` order-editing note): change PO /
    company / billing address / shipping method / notes, and add or remove lines.
    Every field is optional — only what is present changes. ``notify_buyer``
    records the "Notify customer of update to order" intent on the history event."""

    model_config = ConfigDict(extra="forbid")

    po_number: str | None = Field(default=None, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    billing_address: str | None = Field(default=None, max_length=2000)
    shipping_method: OrderShippingMethod | None = None
    #: Present + ``true`` clears the shipping method (distinguish "set to None"
    #: from "leave unchanged", which a bare NULL cannot).
    clear_shipping_method: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    add_lines: list[FacilitateLineSelection] = Field(default_factory=list)
    remove_line_ids: list[uuid.UUID] = Field(default_factory=list)
    notify_buyer: bool = False


def _invalid(msg: str) -> AppError:
    return AppError("invalid_selection", msg, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


# --------------------------------------------------------------------------- #
# Per-line adjustment resolution (the money the shop enters)
# --------------------------------------------------------------------------- #
class _ResolvedAdjustment:
    """A priced adjustment row ready to persist: its money ``effect`` on the line
    net (negative for a discount, positive for a charge) plus the raw inputs."""

    def __init__(
        self,
        *,
        kind: OrderLineAdjustmentKind,
        label: str,
        percent: Decimal | None,
        amount_minor: int | None,
        effect: Decimal,
    ) -> None:
        self.kind = kind
        self.label = label
        self.percent = percent
        self.amount_minor = amount_minor
        self.effect = effect  # signed money (Decimal, rounded)


def _resolve_adjustments(
    line: FacilitateLineSelection, base_net: Decimal
) -> tuple[list[_ResolvedAdjustment], Decimal]:
    """Resolve a line's discounts + charges against its pre-adjustment ``base_net``.

    Each discount effect = ``round(base_net · percent/100)`` (individually rounded
    so every persisted row reconciles the line total exactly); charges add a fixed
    rounded amount. Returns the resolved rows and the **adjusted line net**, which
    must not go negative (over-100% stacked discounts are rejected)."""
    resolved: list[_ResolvedAdjustment] = []
    net = base_net
    for d in line.discounts:
        effect = round_money(base_net * d.percent / Decimal(100))
        net -= effect
        resolved.append(
            _ResolvedAdjustment(
                kind=OrderLineAdjustmentKind.discount,
                label=d.label,
                percent=d.percent,
                amount_minor=None,
                effect=-effect,
            )
        )
    for c in line.additional_charges:
        amount = round_money(c.amount)
        net += amount
        resolved.append(
            _ResolvedAdjustment(
                kind=OrderLineAdjustmentKind.additional_charge,
                label=c.label,
                percent=None,
                amount_minor=to_minor_units(amount),
                effect=amount,
            )
        )
    net = round_money(net)
    if net < 0:
        raise _invalid("Line discounts exceed the line total.")
    return resolved, net


# --------------------------------------------------------------------------- #
# Building an OrderLine (+ adjustments) from a resolved selection
# --------------------------------------------------------------------------- #
async def _build_line(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    org_id: uuid.UUID,
    quote_id: uuid.UUID,
    sel: FacilitateLineSelection,
    placed_on: date,
) -> Decimal:
    """Resolve a selection, persist the OrderLine + its adjustments, and return the
    **adjusted line net** (Decimal) for the order total roll-up."""
    resolved: _ResolvedLine = await _resolve_line(session, quote_id, sel)
    adjustments, line_net = _resolve_adjustments(sel, resolved.line_net)

    ships_on = sel.ships_on
    if ships_on is None and resolved.lead_time_days is not None:
        ships_on = placed_on + timedelta(days=resolved.lead_time_days)

    order_line = OrderLine(
        org_id=org_id,
        order_id=order_id,
        quote_item_id=resolved.quote_item_id,
        component_id=resolved.component_id,
        quantity=resolved.quantity,
        unit_price_minor=to_minor_units(resolved.unit_price),
        total_price_minor=to_minor_units(line_net),
        expedite_option_id=resolved.expedite_option_id,
        expedites_fee_minor=to_minor_units(resolved.expedites_fee),
        lead_time_days=resolved.lead_time_days,
        ships_on=ships_on,
        add_ons=resolved.add_ons,
    )
    session.add(order_line)
    await session.flush()
    for pos, adj in enumerate(adjustments):
        session.add(
            OrderLineAdjustment(
                org_id=org_id,
                order_line_id=order_line.id,
                kind=adj.kind,
                label=adj.label,
                percent=adj.percent,
                amount_minor=adj.amount_minor,
                effect_minor=to_minor_units(adj.effect),
                position=pos,
            )
        )
    return line_net


async def _apply_tax(
    order: Order,
    *,
    org: Organization,
    net: Decimal,
    buyer_ust_id_nr: str | None,
    vies: VIESClient,
) -> None:
    """Resolve ``net`` to the §14-UStG breakdown for the shop/buyer and stamp it
    onto ``order`` (the persisted tax posture the M5.4 PDF renders)."""
    breakdown, vies_result = await resolve_order_tax(
        net=net,
        shop_country=org.country,
        currency=org.currency,
        is_kleinunternehmer=org.is_kleinunternehmer,
        buyer_ust_id_nr=buyer_ust_id_nr,
        supplier_ust_id_nr=org.ust_id_nr,
        vies=vies,
    )
    order.currency = breakdown.currency
    order.net_minor = breakdown.net_minor
    order.vat_minor = breakdown.vat_minor
    order.gross_minor = breakdown.gross_minor
    order.vat_rate_pct = breakdown.vat_rate_pct
    order.vat_label = breakdown.vat_label or None
    order.reverse_charge = breakdown.reverse_charge
    order.kleinunternehmer = breakdown.kleinunternehmer
    order.tax_note = breakdown.note
    order.supplier_ust_id_nr = breakdown.supplier_ust_id_nr
    order.buyer_ust_id_nr = breakdown.customer_ust_id_nr
    order.tax_rate_lines = [
        {"rate_pct": str(rl.rate_pct), "net_minor": rl.net_minor, "vat_minor": rl.vat_minor}
        for rl in breakdown.rate_lines
    ]
    order.vies_valid = vies_result.valid if vies_result is not None else None
    order.vies_checked_at = vies_result.checked_at if vies_result is not None else None


# --------------------------------------------------------------------------- #
# Build Order (create)
# --------------------------------------------------------------------------- #
@facilitate_router.post("/quotes/{quote_id}/facilitate-order", status_code=status.HTTP_201_CREATED)
async def facilitate_order(
    quote_id: uuid.UUID,
    payload: FacilitateOrderRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    vies: Annotated[VIESClient, Depends(get_vies_client)],
) -> dict[str, Any]:
    """Build an Order from ``quote_id`` internally (``source=facilitated``).

    404 on a missing/trashed quote (RLS-scoped — a cross-org id is invisible); 422
    on an invalid selection. Does **not** change the quote's status (matching the
    M5.2 buyer-portal path); the quote → Order link is the ``quote_id`` FK."""
    if len({s.quote_item_id for s in payload.selections}) != len(payload.selections):
        raise _invalid("Each line item may be selected only once.")

    quote = await session.get(Quote, quote_id)
    if quote is None or quote.deleted_at is not None:
        raise AppError("quote_not_found", "Quote not found.", status_code=404)
    org = await session.get(Organization, principal.active_org_id)
    if org is None:  # RLS breakage
        raise AppError("not_found", "Organization not found.", status_code=404)

    placed_on = datetime.now(UTC).date()
    order = Order(
        org_id=quote.org_id,
        number=await _next_order_number(session, quote.org_id),
        source=OrderSource.facilitated,
        quote_id=quote.id,
        account_id=quote.account_id,
        contact_id=quote.contact_id,
        po_number=payload.po_number,
        company_name=payload.company_name,
        billing_address=payload.billing_address,
        notes=payload.notes,
        shipping_method=payload.shipping_method,
        # Placeholder tax fields (NOT NULL) — overwritten by _apply_tax below.
        currency=org.currency,
        net_minor=0,
        vat_minor=0,
        gross_minor=0,
        vat_rate_pct=Decimal("0"),
    )
    session.add(order)
    await session.flush()

    order_net = Decimal("0")
    for sel in payload.selections:
        order_net += await _build_line(
            session,
            order_id=order.id,
            org_id=quote.org_id,
            quote_id=quote.id,
            sel=sel,
            placed_on=placed_on,
        )
    order_net = round_money(order_net)

    await _apply_tax(
        order, org=org, net=order_net, buyer_ust_id_nr=payload.buyer_ust_id_nr, vies=vies
    )
    session.add(
        OrderHistoryEvent(
            org_id=quote.org_id,
            order_id=order.id,
            kind=OrderHistoryEventKind.created,
            actor_user_id=principal.user_id,
            changes={"lines": len(payload.selections)},
        )
    )
    await session.flush()

    return {
        "order_id": str(order.id),
        "order_number": order.number,
        "source": order.source.value,
        "currency": order.currency,
        "net_minor": order.net_minor,
        "vat_minor": order.vat_minor,
        "gross_minor": order.gross_minor,
        "reverse_charge": order.reverse_charge,
        "kleinunternehmer": order.kleinunternehmer,
        "po_number": order.po_number,
        "shipping_method": order.shipping_method.value if order.shipping_method else None,
    }


# --------------------------------------------------------------------------- #
# Pre-ship edit
# --------------------------------------------------------------------------- #
async def _order_net(session: AsyncSession, order_id: uuid.UUID) -> Decimal:
    """Current net of an order = Σ its persisted line totals (minor units → money)."""
    rows = (
        (
            await session.execute(
                select(OrderLine.total_price_minor).where(OrderLine.order_id == order_id)
            )
        )
        .scalars()
        .all()
    )
    return round_money(Decimal(sum(rows)) / Decimal(100))


@facilitate_router.patch("/orders/{order_id}")
async def edit_order(
    order_id: uuid.UUID,
    payload: OrderEditRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    vies: Annotated[VIESClient, Depends(get_vies_client)],
) -> dict[str, Any]:
    """Edit an order **before shipment** and record the change (spec ``#order``).

    404 on a missing/cross-org order; **409 (``order_not_editable``)** when the
    shop has not enabled Facilitate Order Updates, or the order already shipped
    (KB: no edits on shipped / credit-card orders — CC is hidden in v1)."""
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError("not_found", "Order not found.", status_code=status.HTTP_404_NOT_FOUND)

    org = await session.get(Organization, principal.active_org_id)
    if org is None or not org.facilitate_order_updates:
        raise AppError(
            "order_not_editable",
            "Order editing is not enabled for this shop.",
            status_code=status.HTTP_409_CONFLICT,
        )
    if order.shipped_at is not None:
        raise AppError(
            "order_not_editable",
            "A shipped order can no longer be edited.",
            status_code=status.HTTP_409_CONFLICT,
        )

    changes: dict[str, Any] = {}
    for field_name in ("po_number", "company_name", "billing_address", "notes"):
        new = getattr(payload, field_name)
        if new is not None and new != getattr(order, field_name):
            changes[field_name] = [getattr(order, field_name), new]
            setattr(order, field_name, new)
    if payload.clear_shipping_method:
        if order.shipping_method is not None:
            changes["shipping_method"] = [order.shipping_method.value, None]
            order.shipping_method = None
    elif payload.shipping_method is not None and payload.shipping_method != order.shipping_method:
        changes["shipping_method"] = [
            order.shipping_method.value if order.shipping_method else None,
            payload.shipping_method.value,
        ]
        order.shipping_method = payload.shipping_method

    # Remove requested lines (only lines actually on this order; cascades adjustments).
    if payload.remove_line_ids:
        existing = set(
            (
                await session.execute(select(OrderLine.id).where(OrderLine.order_id == order.id))
            ).scalars()
        )
        to_remove = [lid for lid in payload.remove_line_ids if lid in existing]
        if len(to_remove) != len(set(payload.remove_line_ids)):
            raise _invalid("A line to remove does not belong to this order.")
        if to_remove:
            await session.execute(delete(OrderLine).where(OrderLine.id.in_(to_remove)))
            changes["lines_removed"] = len(to_remove)

    # Add new lines.
    if payload.add_lines:
        placed_on = order.created_at.date()
        for sel in payload.add_lines:
            await _build_line(
                session,
                order_id=order.id,
                org_id=order.org_id,
                quote_id=order.quote_id,
                sel=sel,
                placed_on=placed_on,
            )
        changes["lines_added"] = len(payload.add_lines)

    # An empty order is not a valid edit outcome (must keep ≥1 line).
    remaining = await session.scalar(
        select(OrderLine.id).where(OrderLine.order_id == order.id).limit(1)
    )
    if remaining is None:
        raise _invalid("An order must keep at least one line.")

    # Recompute the tax posture whenever the line set changed.
    if "lines_removed" in changes or "lines_added" in changes:
        await _apply_tax(
            order,
            org=org,
            net=await _order_net(session, order.id),
            buyer_ust_id_nr=order.buyer_ust_id_nr,
            vies=vies,
        )

    event = OrderHistoryEvent(
        org_id=order.org_id,
        order_id=order.id,
        kind=OrderHistoryEventKind.edited,
        actor_user_id=principal.user_id,
        changes=changes,
        buyer_notified=payload.notify_buyer,
    )
    session.add(event)
    await session.flush()

    return {
        "order_id": str(order.id),
        "changes": changes,
        "buyer_notified": event.buyer_notified,
        "net_minor": order.net_minor,
        "vat_minor": order.vat_minor,
        "gross_minor": order.gross_minor,
    }


# --------------------------------------------------------------------------- #
# History trail
# --------------------------------------------------------------------------- #
class OrderHistoryOut(BaseModel):
    id: uuid.UUID
    kind: OrderHistoryEventKind
    actor_user_id: uuid.UUID | None
    changes: dict[str, Any]
    buyer_notified: bool
    created_at: datetime


@facilitate_router.get("/orders/{order_id}/history")
async def order_history(
    order_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[OrderHistoryOut]:
    """The order's history trail, oldest first (spec ``#order`` — the hover-icon
    edit log). 404 on a missing/cross-org order (RLS-scoped)."""
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError("not_found", "Order not found.", status_code=status.HTTP_404_NOT_FOUND)
    events = (
        (
            await session.execute(
                select(OrderHistoryEvent)
                .where(OrderHistoryEvent.order_id == order.id)
                .order_by(OrderHistoryEvent.created_at.asc(), OrderHistoryEvent.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        OrderHistoryOut(
            id=e.id,
            kind=e.kind,
            actor_user_id=e.actor_user_id,
            changes=e.changes,
            buyer_notified=e.buyer_notified,
            created_at=e.created_at,
        )
        for e in events
    ]
