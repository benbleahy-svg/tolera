"""Add-Ons / Lead Times / Expedite + quote VAT totals — the M1.11 API.

Spec ``#addons`` (per-line add-ons with the Required toggle + the
admin-configurable AddOnType list behind ADD ADD-ON; per-qty lead times; the
quote-level expedite editor whose APPLY TO ALL pushes tiers to every line)
and ``#dach-tax`` (VAT computed at quote level by the Tax service — never in
Kalk). Engine math lives in ``app.pricing``; this module is CRUD + the
minor-units totals boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import (
    AddOn,
    AddOnDef,
    ComponentQuantity,
    ExpediteOption,
    Organization,
    QuoteItem,
)
from .pricing import (
    _get_component_or_404,
    _lock_editable,
    _pricing_summary,
    _validate_pricing_formula,
    reprice_component,
)
from .quotes import _get_quote_or_404
from .tax import VAT_PROFILES, round_money, to_minor_units, vat_amount

addons_router = APIRouter(prefix="/api", tags=["addons"])

_ZERO = Decimal(0)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class AddOnDefPayload(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_price: Annotated[Decimal | None, Field(ge=0)] = None
    default_is_required: bool = False
    position: int = 0


class AddOnDefUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_price: Annotated[Decimal | None, Field(ge=0)] = None
    default_is_required: bool | None = None
    position: int | None = None


class AddOnPayload(BaseModel):
    """Attach an add-on: from a def (snapshot) or ad hoc (a Manual Add-On)."""

    source_def_id: uuid.UUID | None = None
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_price: Annotated[Decimal | None, Field(ge=0)] = None
    is_required: bool | None = None


class AddOnUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_price: Annotated[Decimal | None, Field(ge=0)] = None
    manual_is_required: bool | None = None
    position: int | None = None


class AddOnCellUpdate(BaseModel):
    manual_price: Annotated[Decimal | None, Field(ge=0)] = None


class ExpediteTier(BaseModel):
    days_faster: Annotated[int, Field(gt=0)]
    markup_pct: Annotated[Decimal, Field(ge=0, le=Decimal("9999.999"))]


class ExpediteOptionsPayload(BaseModel):
    options: list[ExpediteTier]


class LeadTimeUpdate(BaseModel):
    manual_lead_time_days: Annotated[int | None, Field(ge=0)] = None


class ApplyToAllPayload(BaseModel):
    """The top-of-quote editor: standard lead time (optional — leave blank to
    push expedites only, KB dynamic-lead-times-guide) + the expedite tiers."""

    standard_lead_time_days: Annotated[int | None, Field(ge=0)] = None
    tiers: list[ExpediteTier] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _def_out(add_on_def: AddOnDef) -> dict[str, Any]:
    return {
        "id": str(add_on_def.id),
        "name": add_on_def.name,
        "formula": add_on_def.formula,
        "default_price": add_on_def.default_price,
        "default_is_required": add_on_def.default_is_required,
        "position": add_on_def.position,
    }


async def _add_on_out(session: AsyncSession, add_on: AddOn) -> dict[str, Any]:
    component = await _get_component_or_404(session, add_on.component_id)
    summary = await _pricing_summary(session, component)
    rows: list[dict[str, Any]] = summary["add_ons"]
    for row in rows:
        if row["id"] == str(add_on.id):
            return row
    raise AppError(  # pragma: no cover — the row was just persisted
        "not_found", "Add-on not found.", status_code=status.HTTP_404_NOT_FOUND
    )


async def _get_add_on_or_404(session: AsyncSession, add_on_id: uuid.UUID) -> AddOn:
    add_on = await session.get(AddOn, add_on_id)
    if add_on is None:
        raise AppError("not_found", "Add-on not found.", status_code=status.HTTP_404_NOT_FOUND)
    return add_on


def _validate_tiers(tiers: list[ExpediteTier]) -> None:
    days = [tier.days_faster for tier in tiers]
    if len(days) != len(set(days)):
        raise AppError(
            "duplicate_expedite_tier",
            "Each expedite tier needs a distinct days-faster value.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


async def _replace_expedite_options(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID, tiers: list[ExpediteTier]
) -> None:
    existing = (
        await session.scalars(
            select(ExpediteOption).where(ExpediteOption.component_id == component_id)
        )
    ).all()
    for option in existing:
        await session.delete(option)
    await session.flush()
    for position, tier in enumerate(sorted(tiers, key=lambda t: t.days_faster)):
        session.add(
            ExpediteOption(
                org_id=org_id,
                component_id=component_id,
                days_faster=tier.days_faster,
                markup_pct=tier.markup_pct,
                position=position,
            )
        )
    await session.flush()


# --------------------------------------------------------------------------- #
# Configure → Add-On types (the AddOnType dropdown; def/snapshot per E4-d)
# --------------------------------------------------------------------------- #
@addons_router.get("/add-on-defs")
async def list_add_on_defs(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Any:
    defs = (
        await session.scalars(
            select(AddOnDef)
            .where(AddOnDef.deleted_at.is_(None))
            .order_by(AddOnDef.position, AddOnDef.name)
        )
    ).all()
    return [_def_out(d) for d in defs]


@addons_router.post("/add-on-defs", status_code=status.HTTP_201_CREATED)
async def create_add_on_def(
    payload: AddOnDefPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> Any:
    _validate_pricing_formula(payload.formula, "add_on")
    add_on_def = AddOnDef(org_id=principal.active_org_id, **payload.model_dump())
    session.add(add_on_def)
    await session.flush()
    return _def_out(add_on_def)


@addons_router.patch("/add-on-defs/{def_id}")
async def update_add_on_def(
    def_id: uuid.UUID,
    payload: AddOnDefUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> Any:
    add_on_def = await session.get(AddOnDef, def_id)
    if add_on_def is None or add_on_def.deleted_at is not None:
        raise AppError("not_found", "Add-on type not found.", status_code=status.HTTP_404_NOT_FOUND)
    updates = payload.model_dump(exclude_unset=True)
    if "formula" in updates:
        _validate_pricing_formula(updates["formula"], "add_on")
    for key, value in updates.items():
        setattr(add_on_def, key, value)
    await session.flush()
    return _def_out(add_on_def)


@addons_router.delete("/add-on-defs/{def_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_add_on_def(
    def_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> None:
    add_on_def = await session.get(AddOnDef, def_id)
    if add_on_def is None or add_on_def.deleted_at is not None:
        raise AppError("not_found", "Add-on type not found.", status_code=status.HTTP_404_NOT_FOUND)
    add_on_def.deleted_at = datetime.now(UTC)  # soft delete: snapshots keep working
    await session.flush()


# --------------------------------------------------------------------------- #
# Line-item add-ons
# --------------------------------------------------------------------------- #
@addons_router.post("/components/{component_id}/add-ons", status_code=status.HTTP_201_CREATED)
async def add_add_on(
    component_id: uuid.UUID,
    payload: AddOnPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable(session, component)

    name = payload.name
    formula = payload.formula
    default_price = payload.default_price
    default_is_required = payload.is_required if payload.is_required is not None else False
    if payload.source_def_id is not None:
        add_on_def = await session.get(AddOnDef, payload.source_def_id)
        if add_on_def is None:
            raise AppError(
                "not_found", "Add-on type not found.", status_code=status.HTTP_404_NOT_FOUND
            )
        # snapshot-on-attach (E4-d) — explicit payload fields win over the def
        name = name or add_on_def.name
        formula = formula if formula is not None else add_on_def.formula
        default_price = default_price if default_price is not None else add_on_def.default_price
        if payload.is_required is None:
            default_is_required = add_on_def.default_is_required
    if not name:
        raise AppError(
            "name_required",
            "An add-on needs a name (or an add-on type to copy one from).",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    _validate_pricing_formula(formula, "add_on")

    position = len(
        (await session.scalars(select(AddOn.id).where(AddOn.component_id == component_id))).all()
    )
    add_on = AddOn(
        org_id=principal.active_org_id,
        component_id=component_id,
        source_def_id=payload.source_def_id,
        name=name,
        formula=formula,
        default_price=default_price,
        default_is_required=default_is_required,
        position=position,
    )
    session.add(add_on)
    await session.flush()
    await reprice_component(session, principal.active_org_id, component_id)
    return await _add_on_out(session, add_on)


@addons_router.patch("/add-ons/{add_on_id}")
async def update_add_on(
    add_on_id: uuid.UUID,
    payload: AddOnUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    add_on = await _get_add_on_or_404(session, add_on_id)
    component = await _get_component_or_404(session, add_on.component_id)
    await _lock_editable(session, component)
    updates = payload.model_dump(exclude_unset=True)
    if "formula" in updates:
        _validate_pricing_formula(updates["formula"], "add_on")
    for key, value in updates.items():
        setattr(add_on, key, value)
    await session.flush()
    await reprice_component(session, principal.active_org_id, add_on.component_id)
    return await _add_on_out(session, add_on)


@addons_router.delete("/add-ons/{add_on_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_add_on(
    add_on_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> None:
    add_on = await _get_add_on_or_404(session, add_on_id)
    component = await _get_component_or_404(session, add_on.component_id)
    await _lock_editable(session, component)
    component_id = add_on.component_id
    await session.delete(add_on)
    await session.flush()
    # later add-ons may read this one via get_price_value — recompute the chain
    await reprice_component(session, principal.active_org_id, component_id)


@addons_router.patch("/add-ons/{add_on_id}/cells/{quantity}")
async def set_add_on_cell_override(
    add_on_id: uuid.UUID,
    quantity: int,
    payload: AddOnCellUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    from .models import AddOnCell

    add_on = await _get_add_on_or_404(session, add_on_id)
    component = await _get_component_or_404(session, add_on.component_id)
    await _lock_editable(session, component)
    cell = await session.scalar(
        select(AddOnCell).where(AddOnCell.add_on_id == add_on_id, AddOnCell.quantity == quantity)
    )
    if cell is None:
        raise AppError(
            "not_found",
            "No such quantity break on this add-on.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    cell.manual_price = payload.manual_price
    await session.flush()
    await reprice_component(session, principal.active_org_id, add_on.component_id)
    return {
        "quantity": quantity,
        "calc_price": cell.calc_price,
        "manual_price": cell.manual_price,
    }


# --------------------------------------------------------------------------- #
# Lead times + expedite
# --------------------------------------------------------------------------- #
@addons_router.patch("/components/{component_id}/lead-time/{quantity}")
async def set_lead_time_override(
    component_id: uuid.UUID,
    quantity: int,
    payload: LeadTimeUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable(session, component)
    brk = await session.scalar(
        select(ComponentQuantity).where(
            ComponentQuantity.component_id == component_id,
            ComponentQuantity.quantity == quantity,
        )
    )
    if brk is None:
        raise AppError(
            "not_found",
            "No such quantity break on this line item.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    brk.manual_lead_time_days = payload.manual_lead_time_days
    await session.flush()
    await reprice_component(session, principal.active_org_id, component_id)
    summary = await _pricing_summary(session, component)
    return {"lead_times": summary["lead_times"]}


@addons_router.put("/components/{component_id}/expedite-options")
async def set_expedite_options(
    component_id: uuid.UUID,
    payload: ExpediteOptionsPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable(session, component)
    _validate_tiers(payload.options)
    await _replace_expedite_options(session, principal.active_org_id, component_id, payload.options)
    summary = await _pricing_summary(session, component)
    return {"lead_times": summary["lead_times"]}


@addons_router.post("/quotes/{quote_id}/lead-times/apply-to-all")
async def apply_lead_times_to_all(
    quote_id: uuid.UUID,
    payload: ApplyToAllPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    """APPLY TO ALL (spec #addons): push the quote-level tiers — and, when
    given, the standard lead time — to every line item and quantity."""
    quote = await _get_quote_or_404(session, quote_id)
    _validate_tiers(payload.tiers)
    items = (
        await session.scalars(
            select(QuoteItem).where(QuoteItem.quote_id == quote_id).order_by(QuoteItem.created_at)
        )
    ).all()
    for item in items:
        component = await _get_component_or_404(session, item.root_component_id)
        await _lock_editable(session, component)
    for item in items:
        await _replace_expedite_options(
            session, principal.active_org_id, item.root_component_id, payload.tiers
        )
        if payload.standard_lead_time_days is not None:
            breaks = (
                await session.scalars(
                    select(ComponentQuantity).where(
                        ComponentQuantity.component_id == item.root_component_id
                    )
                )
            ).all()
            for brk in breaks:
                brk.manual_lead_time_days = payload.standard_lead_time_days
        await session.flush()
        await reprice_component(session, principal.active_org_id, item.root_component_id)
    quote.expedite_tiers = payload.model_dump(mode="json")  # the editor's staging state
    await session.flush()
    return {"applied_to": len(items), "expedite_tiers": quote.expedite_tiers}


# --------------------------------------------------------------------------- #
# Quote totals — net + VAT line + gross (integer minor units + currency)
# --------------------------------------------------------------------------- #
@addons_router.get("/quotes/{quote_id}/totals")
async def quote_totals(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    item: Annotated[list[str], Query()] = [],  # noqa: B006 — FastAPI query default
) -> Any:
    """Net + MwSt/USt/MWST + gross for a DACH quote (spec #dach-tax; the
    2026-07-08 minor-units boundary). Line = resolved total price at the
    selected break + its REQUIRED add-ons; optional add-ons and expedites are
    the buyer's checkout choice (M5). Selection: ``?item=<quote_item_id>:<qty>``
    per line; unselected items use their lowest break."""
    from .models import AddOnCell

    quote = await _get_quote_or_404(session, quote_id)
    org = await session.get(Organization, quote.org_id)
    assert org is not None  # RLS guarantees the active org is visible
    profile = VAT_PROFILES[org.country]

    selections: dict[uuid.UUID, int] = {}
    for raw in item:
        item_id, sep, qty = raw.partition(":")
        try:
            selections[uuid.UUID(item_id)] = int(qty)
        except ValueError:
            sep = ""
        if not sep:
            raise AppError(
                "invalid_selection",
                "Selections take the form item=<quote_item_id>:<quantity>.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    items = (
        await session.scalars(
            select(QuoteItem).where(QuoteItem.quote_id == quote_id).order_by(QuoteItem.created_at)
        )
    ).all()

    net = _ZERO
    lines: list[dict[str, Any]] = []
    for quote_item in items:
        breaks = sorted(
            (
                await session.scalars(
                    select(ComponentQuantity).where(
                        ComponentQuantity.component_id == quote_item.root_component_id
                    )
                )
            ).all(),
            key=lambda b: b.quantity,
        )
        if not breaks:
            continue
        chosen_qty = selections.get(quote_item.id, breaks[0].quantity)
        brk = next((b for b in breaks if b.quantity == chosen_qty), None)
        if brk is None:
            raise AppError(
                "invalid_selection",
                f"Quantity {chosen_qty} is not a break on this line item.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        add_ons = (
            await session.scalars(
                select(AddOn).where(AddOn.component_id == quote_item.root_component_id)
            )
        ).all()
        required_total = _ZERO
        for add_on in add_ons:
            if not add_on.is_required:
                continue
            cell = await session.scalar(
                select(AddOnCell).where(
                    AddOnCell.add_on_id == add_on.id, AddOnCell.quantity == brk.quantity
                )
            )
            if cell is None:
                continue
            price = cell.manual_price if cell.manual_price is not None else cell.calc_price
            if price is not None:
                required_total += price
        line_net = round_money((brk.total_price or _ZERO) + required_total)
        net += line_net
        lines.append(
            {
                "quote_item_id": str(quote_item.id),
                "component_id": str(quote_item.root_component_id),
                "quantity": brk.quantity,
                "net_minor": to_minor_units(line_net),
            }
        )

    vat = vat_amount(net, profile.standard_pct)
    return {
        "currency": quote.currency,
        "country": org.country.value,
        "vat_label": profile.label,
        "vat_rate_pct": str(profile.standard_pct),
        "items": lines,
        "net_minor": to_minor_units(net),
        "vat_minor": to_minor_units(vat),
        "gross_minor": to_minor_units(net + vat),
    }
