"""Quote Checkout → Order (M5.2) — the buyer completes a PO checkout at
``/q/:token`` and a real :class:`~app.models.Order` is created.

Spec ``#digitalquote`` (Checkout flow, **PO only in v1**) + ``#order``. Like the
M5.1 buyer portal this endpoint is **token-authenticated, not Clerk-authed**: it
opens an :func:`~app.db.org_scoped_session` for the token's org so RLS holds
without a session. Two invariants:

* **Prices are re-derived server-side.** The request carries only IDs +
  quantities (never money) — every price comes from
  :func:`~app.pricing._pricing_summary`, the same source the portal renders, so
  a tampered client cannot change what is charged (CLAUDE.md §5).
* **Money crosses to integer minor units + currency here** — the Order is the
  spine's terminal entity (the total boundary; M5.2 AC).

VAT / reverse-charge / Kleinunternehmer is resolved by :mod:`app.vat_service`
(never in Kalk) and the §14-UStG breakdown is persisted on the Order.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .buyer_portal import _rejected
from .db import org_scoped_session
from .errors import AppError
from .models import (
    Component,
    MembershipRole,
    MembershipStatus,
    Notification,
    Order,
    OrderLine,
    OrderShippingMethod,
    OrderSource,
    Organization,
    Quote,
    QuoteItem,
    QuoteToken,
    QuoteTokenScope,
    UserOrgMembership,
)
from .pricing import _pricing_summary
from .quote_tokens import InvalidToken, decode_jwt
from .tax import round_money, to_minor_units
from .vat_service import VIESClient, get_vies_client, resolve_order_tax

checkout_router = APIRouter(prefix="/api/public/quotes", tags=["checkout"])


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
class CheckoutLineSelection(BaseModel):
    """One line item's buyer selection — a chosen break, optional expedite tier
    and optional add-ons. Prices are looked up server-side from these IDs."""

    model_config = ConfigDict(extra="forbid")

    quote_item_id: uuid.UUID
    quantity: int = Field(gt=0)
    expedite_option_id: uuid.UUID | None = None
    add_on_ids: list[uuid.UUID] = Field(default_factory=list)


class CheckoutRequest(BaseModel):
    """The PO checkout submission (spec ``#digitalquote`` Company & PO + Shipping)."""

    model_config = ConfigDict(extra="forbid")

    selections: list[CheckoutLineSelection]
    po_number: str = Field(min_length=1, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    billing_address: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    buyer_ust_id_nr: str | None = Field(default=None, max_length=32)
    shipping_method: OrderShippingMethod


def _invalid(msg: str) -> AppError:
    return AppError("invalid_selection", msg, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


# --------------------------------------------------------------------------- #
# Per-line price re-derivation
# --------------------------------------------------------------------------- #
class _ResolvedLine:
    """A priced order line, re-derived from the internal pricing summary."""

    def __init__(
        self,
        *,
        quote_item_id: uuid.UUID,
        component_id: uuid.UUID,
        quantity: int,
        unit_price: Decimal,
        line_net: Decimal,
        expedite_option_id: uuid.UUID | None,
        expedites_fee: Decimal,
        lead_time_days: int | None,
        add_ons: list[dict[str, Any]],
    ) -> None:
        self.quote_item_id = quote_item_id
        self.component_id = component_id
        self.quantity = quantity
        self.unit_price = unit_price
        self.line_net = line_net
        self.expedite_option_id = expedite_option_id
        self.expedites_fee = expedites_fee
        self.lead_time_days = lead_time_days
        self.add_ons = add_ons


async def _resolve_line(
    session: AsyncSession, quote_id: uuid.UUID, sel: CheckoutLineSelection
) -> _ResolvedLine:
    quote_item = await session.get(QuoteItem, sel.quote_item_id)
    if quote_item is None or quote_item.quote_id != quote_id:
        raise _invalid("A selected line item does not belong to this quote.")

    component = await session.get(Component, quote_item.root_component_id)
    if component is None:
        raise _invalid("A selected line item has no priced component.")
    pricing = await _pricing_summary(session, component)
    total = next((t for t in pricing["totals"] if t["quantity"] == sel.quantity), None)
    if total is None:
        raise _invalid(f"Quantity {sel.quantity} is not a break on this line item.")
    if total.get("total_price") is None:
        raise _invalid("This line item is not fully priced and cannot be ordered.")

    base_unit: Decimal = total["unit_price"]
    line_before_add_ons: Decimal = total["total_price"]
    lead: dict[str, Any] = next(
        (lt for lt in pricing["lead_times"] if lt["quantity"] == sel.quantity), {}
    )
    lead_time_days = lead.get("lead_time_days")
    expedites_fee = Decimal("0")

    if sel.expedite_option_id is not None:
        ex = next(
            (e for e in lead.get("expedites", []) if str(e["id"]) == str(sel.expedite_option_id)),
            None,
        )
        if ex is None or ex.get("total_price") is None:
            raise _invalid("The chosen expedite option is not available for this line.")
        expedites_fee = ex["total_price"] - line_before_add_ons
        base_unit = ex["unit_price"]
        line_before_add_ons = ex["total_price"]
        lead_time_days = ex.get("lead_time_days")

    # Add-ons: required ones auto-include; optional ones only if the buyer chose
    # them. Every requested id must be a real add-on on this line.
    by_id = {str(a["id"]): a for a in pricing["add_ons"]}
    requested = {str(i) for i in sel.add_on_ids}
    unknown = requested - by_id.keys()
    if unknown:
        raise _invalid("A selected add-on does not exist on this line item.")

    add_on_total = Decimal("0")
    snapshot: list[dict[str, Any]] = []
    for add_on in pricing["add_ons"]:
        aid = str(add_on["id"])
        if not (add_on["is_required"] or aid in requested):
            continue
        cell = next((c for c in add_on["cells"] if c["quantity"] == sel.quantity), None)
        price = cell.get("price") if cell is not None else None
        if price is None:
            raise _invalid("A required or selected add-on is not priced at this quantity.")
        add_on_total += price
        snapshot.append(
            {
                "id": aid,
                "name": add_on["display_name"],
                "price_minor": to_minor_units(round_money(price)),
                "required": bool(add_on["is_required"]),
            }
        )

    line_net = round_money(line_before_add_ons + add_on_total)
    return _ResolvedLine(
        quote_item_id=sel.quote_item_id,
        component_id=quote_item.root_component_id,
        quantity=sel.quantity,
        unit_price=round_money(base_unit),
        line_net=line_net,
        expedite_option_id=sel.expedite_option_id,
        expedites_fee=round_money(expedites_fee),
        lead_time_days=lead_time_days,
        add_ons=snapshot,
    )


async def _next_order_number(session: AsyncSession, org_id: uuid.UUID) -> str:
    """Atomically allocate this org's next sequential order number (mirrors
    ``_next_quote_number`` — the upsert row-locks so concurrent checkouts serialise)."""
    result = await session.execute(
        text(
            "INSERT INTO order_counter AS oc (org_id, last_number) VALUES (:org, 1) "
            "ON CONFLICT (org_id) DO UPDATE SET last_number = oc.last_number + 1 "
            "RETURNING last_number"
        ),
        {"org": str(org_id)},
    )
    return str(result.scalar_one())


async def _notify_shop(session: AsyncSession, quote: Quote, order: Order) -> None:
    """Fire the dashboard notification to the shop (spec: PLACE ORDER notifies
    the shop). Recipients = the quote's estimator + salesperson, or — if neither
    is assigned — every active admin (so an order never lands silently). The
    Order Confirmation *email* is M5.5/M5.8."""
    recipients: set[uuid.UUID] = {
        uid for uid in (quote.estimator_id, quote.salesperson_id) if uid is not None
    }
    if not recipients:
        admins = (
            await session.execute(
                select(UserOrgMembership.user_id).where(
                    UserOrgMembership.org_id == quote.org_id,
                    UserOrgMembership.status == MembershipStatus.active,
                    UserOrgMembership.roles.contains([MembershipRole.admin]),
                )
            )
        ).scalars()
        recipients = set(admins)

    payload = {
        "order_id": str(order.id),
        "order_number": order.number,
        "quote_id": str(quote.id),
        "quote_number": quote.number,
    }
    for user_id in recipients:
        session.add(
            Notification(org_id=quote.org_id, user_id=user_id, kind="order_placed", payload=payload)
        )


# --------------------------------------------------------------------------- #
# The endpoint
# --------------------------------------------------------------------------- #
@checkout_router.post("/{token}/checkout", status_code=status.HTTP_201_CREATED)
async def checkout(
    token: str,
    payload: CheckoutRequest,
    request: Request,
    vies: Annotated[VIESClient, Depends(get_vies_client)],
) -> dict[str, Any]:
    """Complete the PO checkout for ``token``'s quote and create the Order.

    401 on a bad/revoked/wrong-scope token; 404 on a missing/trashed quote; 409
    on a soft-expired quote (portal reachable, checkout blocked — spec); 422 on
    an empty or invalid selection."""
    settings = request.app.state.settings
    secret = settings.resolve_quote_token_secret()
    try:
        claims = decode_jwt(secret, token)
    except InvalidToken as exc:
        raise _rejected() from exc
    if claims.scope is not QuoteTokenScope.buyer_portal:
        raise _rejected()

    # Token authenticated → now validate the submission (an invalid credential
    # must 401 before any business rule, so this check follows the token check).
    if not payload.selections:
        raise _invalid("Select at least one line item to place an order.")
    if len({s.quote_item_id for s in payload.selections}) != len(payload.selections):
        raise _invalid("Each line item may be selected only once.")

    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    now = datetime.now(UTC)
    async with org_scoped_session(sessionmaker, claims.org_id) as session:
        token_row = await session.get(QuoteToken, claims.token_id)
        if (
            token_row is None
            or token_row.is_revoked
            or token_row.scope is not QuoteTokenScope.buyer_portal
            or token_row.quote_id != claims.quote_id
        ):
            raise _rejected()

        quote = await session.get(Quote, claims.quote_id)
        if quote is None or quote.deleted_at is not None:
            raise AppError("quote_not_found", "This quote is no longer available.", status_code=404)
        if quote.expiration_date is not None and quote.expiration_date <= now:
            # Soft expiry: the portal stays readable but checkout is blocked
            # (spec #digitalquote expired state; M5.1 DECISIONS).
            raise AppError(
                "quote_expired",
                "This quote has expired — request an updated quote to order.",
                status_code=status.HTTP_409_CONFLICT,
            )
        org = await session.get(Organization, quote.org_id)
        if org is None:  # RLS breakage — never invent shop identity
            raise _rejected()

        resolved = [await _resolve_line(session, quote.id, sel) for sel in payload.selections]
        order_net = round_money(sum((line.line_net for line in resolved), Decimal("0")))

        breakdown, vies_result = await resolve_order_tax(
            net=order_net,
            shop_country=org.country,
            currency=org.currency,
            is_kleinunternehmer=org.is_kleinunternehmer,
            buyer_ust_id_nr=payload.buyer_ust_id_nr,
            supplier_ust_id_nr=org.ust_id_nr,
            vies=vies,
        )

        placed_on: date = now.date()
        order = Order(
            org_id=quote.org_id,
            number=await _next_order_number(session, quote.org_id),
            source=OrderSource.buyer_portal,
            quote_id=quote.id,
            account_id=quote.account_id,
            contact_id=quote.contact_id,
            po_number=payload.po_number,
            company_name=payload.company_name,
            billing_address=payload.billing_address,
            notes=payload.notes,
            shipping_method=payload.shipping_method,
            currency=breakdown.currency,
            net_minor=breakdown.net_minor,
            vat_minor=breakdown.vat_minor,
            gross_minor=breakdown.gross_minor,
            vat_rate_pct=breakdown.vat_rate_pct,
            vat_label=breakdown.vat_label or None,
            reverse_charge=breakdown.reverse_charge,
            kleinunternehmer=breakdown.kleinunternehmer,
            tax_note=breakdown.note,
            supplier_ust_id_nr=breakdown.supplier_ust_id_nr,
            buyer_ust_id_nr=breakdown.customer_ust_id_nr,
            tax_rate_lines=[
                {
                    "rate_pct": str(rl.rate_pct),
                    "net_minor": rl.net_minor,
                    "vat_minor": rl.vat_minor,
                }
                for rl in breakdown.rate_lines
            ],
            vies_valid=vies_result.valid if vies_result is not None else None,
            vies_checked_at=vies_result.checked_at if vies_result is not None else None,
        )
        session.add(order)
        await session.flush()

        lines_out: list[dict[str, Any]] = []
        for line in resolved:
            ships_on = (
                placed_on + timedelta(days=line.lead_time_days)
                if line.lead_time_days is not None
                else None
            )
            session.add(
                OrderLine(
                    org_id=quote.org_id,
                    order_id=order.id,
                    quote_item_id=line.quote_item_id,
                    component_id=line.component_id,
                    quantity=line.quantity,
                    unit_price_minor=to_minor_units(line.unit_price),
                    total_price_minor=to_minor_units(line.line_net),
                    expedite_option_id=line.expedite_option_id,
                    expedites_fee_minor=to_minor_units(line.expedites_fee),
                    lead_time_days=line.lead_time_days,
                    ships_on=ships_on,
                    add_ons=line.add_ons,
                )
            )
            lines_out.append(
                {
                    "quote_item_id": str(line.quote_item_id),
                    "quantity": line.quantity,
                    "unit_price_minor": to_minor_units(line.unit_price),
                    "total_price_minor": to_minor_units(line.line_net),
                    "expedites_fee_minor": to_minor_units(line.expedites_fee),
                    "lead_time_days": line.lead_time_days,
                    "ships_on": ships_on.isoformat() if ships_on is not None else None,
                    "add_ons": line.add_ons,
                }
            )

        await _notify_shop(session, quote, order)

        return {
            "order_id": str(order.id),
            "order_number": order.number,
            "currency": order.currency,
            "net_minor": order.net_minor,
            "vat_minor": order.vat_minor,
            "gross_minor": order.gross_minor,
            "vat_rate_pct": str(breakdown.vat_rate_pct),
            "vat_label": order.vat_label,
            "reverse_charge": order.reverse_charge,
            "kleinunternehmer": order.kleinunternehmer,
            "tax_note": order.tax_note,
            "po_number": order.po_number,
            "shipping_method": order.shipping_method.value if order.shipping_method else None,
            "lines": lines_out,
        }
