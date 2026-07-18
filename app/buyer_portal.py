"""Digital Quote buyer portal — the public, unauthenticated read endpoint (M5.1).

Spec ``#digitalquote``: a buyer opens ``/q/:token`` with no login and sees the
white-label, read-only quote. This module serves the data the React portal renders.

Two invariants shape it:

* **No auth, but still org-scoped.** The endpoint bypasses ``get_principal`` /
  ``get_session`` (there is no Clerk session) yet must not escape tenancy — it opens
  an :func:`~app.db.org_scoped_session` for the *token's* org (the signed ``org``
  claim), so Postgres RLS is in force exactly as for an authenticated request.
* **Field-gating is an allowlist, not a denylist.** The buyer payload is built by
  copying *only* the buyer-visible fields out of the internal
  :func:`~app.pricing._pricing_summary` — internal cost/margin (``costing``,
  ``pricing_items``, ``total_markup*``, ``total_profit``, ``profit_margin_pct``,
  ``unit_cost``, discount internals) can never leak, even if a future field is added
  upstream. Toggled-off Display-Settings fields are *absent from the payload*, not
  merely CSS-hidden (spec AC).

Money is emitted as **exact decimal strings** (the frontend's `string` money type;
never a bare float — CLAUDE.md §5). VAT is **not** applied here — the buyer grid is
net; tax is M5.3, checkout/order money is M5.2.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import org_scoped_session
from .errors import AppError
from .models import (
    Component,
    Material,
    Organization,
    Part,
    PartGeometry,
    Process,
    QiWorkflowStatus,
    Quote,
    QuoteItem,
    QuoteToken,
    QuoteTokenAccess,
    QuoteTokenScope,
)
from .pricing import _pricing_summary
from .quote_tokens import InvalidToken, decode_jwt

buyer_router = APIRouter(prefix="/api/public/quotes", tags=["buyer-portal"])


# --------------------------------------------------------------------------- #
# Display Settings — the buyer-visibility toggles (persistence lands in M5.8).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DisplaySettings:
    """Which line-item fields the digital quote exposes to the buyer.

    Persistence + the Settings UI are M5.8 (build-plan: "Quote Display Settings
    persistence (the toggles M5.4/M5.1 read)"); M5.1 owns the *read* side — this
    value object + defaults + the gating projection. Defaults mirror the spec's
    line-item card (identity + process/material on; dimensions/DFM opt-in)."""

    show_part_number: bool = True
    show_revision: bool = True
    show_description: bool = True
    show_process: bool = True
    show_material: bool = True
    show_dimensions: bool = False
    show_dfm: bool = False
    show_3d: bool = True


DEFAULT_DISPLAY_SETTINGS = DisplaySettings()


async def load_display_settings(session: AsyncSession, org_id: uuid.UUID) -> DisplaySettings:
    """The org's Display Settings. M5.1 returns defaults; M5.8 backs this with a
    persisted row (the seam is here so callers never re-encode the toggle set)."""
    return DEFAULT_DISPLAY_SETTINGS


def _money(value: Decimal | None) -> str | None:
    """Exact decimal string (already 4-dp-quantized upstream), or None."""
    return None if value is None else str(value)


# --------------------------------------------------------------------------- #
# Projection — internal pricing summary → buyer-visible line item (allowlist).
# --------------------------------------------------------------------------- #
@dataclass
class _ItemRow:
    """One line item's joined source data for the projection."""

    quote_item: QuoteItem
    part: Part
    process: Process | None
    material: Material | None
    geometry: PartGeometry | None


def build_line_item(
    row: _ItemRow, pricing: dict[str, Any], settings: DisplaySettings
) -> dict[str, Any]:
    """Build the buyer-visible card for one line item — copying ONLY allowed fields."""
    qi = row.quote_item
    is_no_quote = qi.workflow_status is QiWorkflowStatus.no_quote
    card: dict[str, Any] = {
        "quote_item_id": str(qi.id),
        "position": qi.position,
        "is_no_quote": is_no_quote,
        "has_model": row.part.primary_file_id is not None,
    }
    if settings.show_part_number and row.part.part_number:
        card["part_number"] = row.part.part_number
    if settings.show_revision and row.part.revision:
        card["revision"] = row.part.revision
    if settings.show_description and row.part.description:
        card["description"] = row.part.description
    if settings.show_process and row.process is not None:
        card["process"] = row.process.external_name or row.process.name
    if settings.show_material and row.material is not None:
        card["material"] = row.material.display_name
        card["werkstoffnummer"] = row.material.werkstoffnummer
    if settings.show_dimensions and row.geometry is not None:
        card["dimensions"] = {
            "x": _money(row.geometry.size_x),
            "y": _money(row.geometry.size_y),
            "z": _money(row.geometry.size_z),
        }
    if settings.show_dfm:
        # Toggle honoured now; DFM warning *content* on the portal is wired with the
        # PDF/display work (M5.4) — the field is present-but-empty, never fabricated.
        card["dfm_warnings"] = []

    if is_no_quote:
        return card  # No-Quote line — no pricing grid (spec #digitalquote)

    lead_by_qty = {lt["quantity"]: lt for lt in pricing["lead_times"]}
    breaks = []
    for total in pricing["totals"]:
        qty = total["quantity"]
        lead = lead_by_qty.get(qty, {})
        base_unit = total["unit_price"]
        expedites = []
        for ex in lead.get("expedites", []):
            ex_unit = ex["unit_price"]
            # "+ €60,00 / ea" — the per-unit surcharge over the standard price.
            surcharge = (
                ex_unit - base_unit if ex_unit is not None and base_unit is not None else None
            )
            expedites.append(
                {
                    "id": ex["id"],
                    "days_faster": ex["days_faster"],
                    "lead_time_days": ex["lead_time_days"],
                    "unit_price": _money(ex_unit),
                    "total_price": _money(ex["total_price"]),
                    "unit_surcharge": _money(surcharge),
                }
            )
        breaks.append(
            {
                "quantity": qty,
                "unit_price": _money(base_unit),
                "total_price": _money(total["total_price"]),
                "lead_time_days": lead.get("lead_time_days"),
                "expedites": expedites,
            }
        )
    card["breaks"] = breaks

    # Add-ons: required ones auto-include (price shown); optional ones are the
    # buyer's checkout choice (M5.2). Internal calc/manual split is NOT exposed.
    add_ons = []
    for add_on in pricing["add_ons"]:
        add_ons.append(
            {
                "id": add_on["id"],
                "display_name": add_on["display_name"],
                "is_required": add_on["is_required"],
                "prices": [
                    {"quantity": cell["quantity"], "price": _money(cell["price"])}
                    for cell in add_on["cells"]
                ],
            }
        )
    card["add_ons"] = add_ons
    return card


def _price_range(line_items: list[dict[str, Any]]) -> dict[str, str] | None:
    """AVAILABLE FROM the min to the max unit price across every break (range chip)."""
    units = [
        Decimal(brk["unit_price"])
        for item in line_items
        for brk in item.get("breaks", [])
        if brk.get("unit_price") is not None
    ]
    if not units:
        return None
    return {"min_unit": str(min(units)), "max_unit": str(max(units))}


async def _load_item_rows(session: AsyncSession, quote: Quote) -> list[_ItemRow]:
    rows = (
        await session.execute(
            select(QuoteItem, Part, Process, Material)
            .join(
                Component,
                (Component.id == QuoteItem.root_component_id)
                & (Component.org_id == QuoteItem.org_id),
            )
            .join(Part, (Part.id == Component.part_id) & (Part.org_id == Component.org_id))
            .outerjoin(
                Process, (Process.id == Component.process_id) & (Process.org_id == Component.org_id)
            )
            .outerjoin(
                Material,
                (Material.id == Component.material_id) & (Material.org_id == Component.org_id),
            )
            .where(QuoteItem.quote_id == quote.id)
            .order_by(QuoteItem.position)
        )
    ).all()
    part_ids = [part.id for _, part, _, _ in rows]
    geoms = (
        {
            g.part_id: g
            for g in (
                await session.execute(
                    select(PartGeometry).where(PartGeometry.part_id.in_(part_ids))
                )
            )
            .scalars()
            .all()
        }
        if part_ids
        else {}
    )
    return [
        _ItemRow(quote_item=qi, part=part, process=proc, material=mat, geometry=geoms.get(part.id))
        for qi, part, proc, mat in rows
    ]


async def build_buyer_payload(
    session: AsyncSession,
    org: Organization,
    quote: Quote,
    settings: DisplaySettings,
    now: datetime,
) -> dict[str, Any]:
    """Assemble the full buyer-portal payload for ``quote`` (field-gated, net)."""
    item_rows = await _load_item_rows(session, quote)
    line_items = []
    for row in item_rows:
        component = await session.get(Component, row.quote_item.root_component_id)
        pricing = await _pricing_summary(session, component) if component is not None else {}
        line_items.append(build_line_item(row, pricing, settings))

    is_expired = quote.expiration_date is not None and quote.expiration_date <= now
    return {
        "quote_number": quote.number,
        "rfq_number": quote.rfq_number,
        "currency": quote.currency,
        "expiration_date": (
            quote.expiration_date.isoformat() if quote.expiration_date is not None else None
        ),
        # Soft expiry: the portal stays reachable and selectable; only checkout is
        # blocked (M5.2). Divergence from the reference is intentional (DECISIONS).
        "is_expired": is_expired,
        # M5.8 wires the real Requotes toggle; default off (button hidden) until then.
        "requotes_enabled": False,
        "shop": {
            "name": org.name,
            "slug": org.slug,
            "country": org.country.value,
            "currency": org.currency,
            "locale": org.locale,
        },
        "price_range": _price_range(line_items),
        "line_items": line_items,
    }


# --------------------------------------------------------------------------- #
# The public endpoint.
# --------------------------------------------------------------------------- #
def _rejected() -> AppError:
    """A single, non-enumerating rejection for every bad-token path (no oracle)."""
    return AppError("invalid_token", "This quote link is not valid.", status_code=401)


@buyer_router.get("/{token}")
async def get_buyer_quote(token: str, request: Request) -> dict[str, Any]:
    """Return the field-gated buyer view of a quote for a valid ``buyer_portal`` token.

    401 on a malformed/forged/revoked/wrong-scope token; 404 on a missing/trashed
    quote. A successful load is recorded in the access log (export-control audit)."""
    settings = request.app.state.settings
    secret = settings.resolve_quote_token_secret()
    try:
        claims = decode_jwt(secret, token)
    except InvalidToken as exc:
        raise _rejected() from exc
    if claims.scope is not QuoteTokenScope.buyer_portal:
        raise _rejected()

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
        org = await session.get(Organization, quote.org_id)
        if org is None:  # RLS breakage — never invent shop identity
            raise _rejected()

        display = await load_display_settings(session, quote.org_id)
        payload = await build_buyer_payload(session, org, quote, display, now)

        session.add(
            QuoteTokenAccess(
                org_id=quote.org_id,
                quote_token_id=token_row.id,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
    return payload
