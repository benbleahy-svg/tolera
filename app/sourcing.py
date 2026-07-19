"""In-context supplier sourcing — "Tolera Source" (M6.7).

Spec ``#collab`` ("Supplier sourcing integrations" → Tolera Source: BOM-driven
fastener availability + pricing, SEND RFQ) and ``#integrations`` /
``#dach-connectors-tbl`` (Würth replaces Online Metals/MSC in the DACH stack).
The supplier lane itself lives in :mod:`app.services.suppliers.wuerth`; this
module is only the org-scoped HTTP surface over it.

Two invariants shape every handler here:

**Nothing is repriced.** A supplier price is a *suggestion* — it is displayed
next to a purchased component and never written to ``purchased_component.
piece_price`` or into costing. Applying an outside price stays the M6.6
Vendor-Quotes Apply path, so there is exactly one price-application code path
and one audit trail (spec ``#sourcing-adapters`` → E4-d freeze).

**A supplier outage is not an error.** Every lookup answers 200 with
``degraded: true`` and no prices when the supplier cannot be reached, so the
estimator sees a badge instead of a broken page and costing continues
(spec ``#sourcing-adapters``: "never blocks costing").
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .events import emit_event
from .models import Organization, PurchasedComponent
from .services.suppliers.base import (
    AvailabilityItem,
    SourcingRfqLine,
    SourcingRfqRequest,
    SupplierUnavailable,
)
from .services.suppliers.wuerth import (
    WuerthMaterialPricingAdapter,
    get_sourcing_adapter,
)

sourcing_router = APIRouter(prefix="/api/sourcing", tags=["sourcing"])

#: How many quantity breaks one lookup may ask for — the reference product shows
#: a handful of make-quantity columns, and an unbounded list is a cheap way to
#: hammer the supplier.
MAX_QUANTITIES = 10
#: How many components one RFQ may cover ("Request for Quote (Entire BOM)").
MAX_RFQ_COMPONENTS = 200

Adapter = Annotated[WuerthMaterialPricingAdapter, Depends(get_sourcing_adapter)]


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class QuantityQuoteOut(BaseModel):
    quantity: int
    #: Minor units of ``AvailabilityItemOut.currency`` (CLAUDE.md §5) — never a float.
    #: ``null`` = the supplier carries the part but quotes no price at this quantity.
    unit_price_minor: int | None
    extended_price_minor: int | None
    #: ``available`` | ``at_risk`` | ``insufficient`` | ``unknown`` — the inventory dot.
    status: str


class AvailabilityItemOut(BaseModel):
    oem_part_number: str
    found: bool
    currency: str
    description: str | None = None
    brand: str | None = None
    quantity_available: int | None = None
    lead_time_days: int | None = None
    quotes: list[QuantityQuoteOut] = Field(default_factory=list)


class AvailabilityOut(BaseModel):
    """One component's supplier answer.

    ``degraded`` is the stale/unavailable badge: true means the supplier could
    not be reached and ``item`` carries no prices — never an error status, so a
    costing page that embeds this keeps rendering.
    """

    supplier: str
    degraded: bool
    item: AvailabilityItemOut


class SourcingRfqIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchased_component_ids: Annotated[
        list[uuid.UUID], Field(min_length=1, max_length=MAX_RFQ_COMPONENTS)
    ]
    quantities: Annotated[list[int], Field(min_length=1, max_length=MAX_QUANTITIES)]
    message: Annotated[str | None, Field(max_length=2000)] = None
    #: The shop's own purchasing address for the reply; never a customer address.
    reply_to: Annotated[str | None, Field(max_length=320)] = None


class SourcingRfqOut(BaseModel):
    supplier: str
    reference: str
    accepted: bool
    supplier_reference: str | None = None
    estimated_response_hours: int | None = None
    #: ``fixture`` while procurement is pending, ``live`` once credentials land.
    #: The UI labels a fixture send so nobody believes the supplier has it.
    mode: str = "fixture"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _parse_quantities(raw: str) -> list[int]:
    """``"1,100,500"`` → ``[1, 100, 500]``; a malformed list is a 400, not a 500."""
    values: list[int] = []
    for chunk in raw.split(","):
        text = chunk.strip()
        if not text:
            continue
        try:
            value = int(text)
        except ValueError:
            raise AppError(
                "invalid_quantities",
                "quantities muss eine Liste ganzer Zahlen sein (z. B. 1,100,500).",
            ) from None
        if value <= 0:
            raise AppError("invalid_quantities", "Mengen müssen größer als 0 sein.")
        values.append(value)
    return _check_quantities(values)


def _check_quantities(values: list[int]) -> list[int]:
    """Validate, de-duplicate and sort — the list is forwarded to the supplier,
    so ``[1] * 50000`` must not become a 50 000-element outbound payload."""
    if not values:
        raise AppError("invalid_quantities", "Mindestens eine Menge ist erforderlich.")
    if any(value <= 0 for value in values):
        raise AppError("invalid_quantities", "Mengen müssen größer als 0 sein.")
    unique = sorted(set(values))
    if len(unique) > MAX_QUANTITIES:
        raise AppError(
            "too_many_quantities",
            f"Höchstens {MAX_QUANTITIES} Mengenstufen pro Abfrage.",
        )
    return unique


async def _load_components(
    session: AsyncSession, org_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[PurchasedComponent]:
    """Load the org's components, or 404 — a foreign id is indistinguishable
    from a missing one (the cross-org convention: never confirm existence)."""
    rows = (
        (
            await session.execute(
                select(PurchasedComponent).where(
                    PurchasedComponent.org_id == org_id,
                    PurchasedComponent.id.in_(ids),
                    PurchasedComponent.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {row.id: row for row in rows}
    missing = [str(pc_id) for pc_id in ids if pc_id not in by_id]
    if missing:
        raise AppError(
            "purchased_component_not_found",
            "Artikel nicht gefunden.",
            status_code=404,
            details={"ids": missing},
        )
    return [by_id[pc_id] for pc_id in ids]


def _item_out(item: AvailabilityItem) -> AvailabilityItemOut:
    return AvailabilityItemOut(
        oem_part_number=item.oem_part_number,
        found=item.found,
        currency=item.currency,
        description=item.description,
        brand=item.brand,
        quantity_available=item.quantity_available,
        lead_time_days=item.lead_time_days,
        quotes=[
            QuantityQuoteOut(
                quantity=quote.quantity,
                unit_price_minor=quote.unit_price_minor,
                extended_price_minor=quote.extended_price_minor,
                status=quote.status.value,
            )
            for quote in item.quotes
        ],
    )


def _degraded(supplier: str, oem_part_number: str) -> AvailabilityOut:
    """The stale badge: answered, but with nothing to price against."""
    return AvailabilityOut(
        supplier=supplier,
        degraded=True,
        item=AvailabilityItemOut(
            oem_part_number=oem_part_number,
            found=False,
            # The supplier's currency is unknown while it is unreachable; the org
            # currency would be a lie about a price we do not have.
            currency="",
        ),
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@sourcing_router.get("/purchased-components/{pc_id}/availability")
async def component_availability(
    pc_id: uuid.UUID,
    adapter: Adapter,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
    quantities: Annotated[str, Query(description="Comma-separated, e.g. 1,100,500")] = "1",
) -> AvailabilityOut:
    """Supplier stock + price-by-quantity for one purchased component.

    Read-only in every sense: it neither persists the answer nor touches the
    library row it was asked about.
    """
    wanted = _parse_quantities(quantities)
    component = (await _load_components(session, principal.active_org_id, [pc_id]))[0]

    try:
        result = await adapter.availability([component.oem_part_number], quantities=wanted)
    except SupplierUnavailable:
        return _degraded(adapter.supplier, component.oem_part_number)

    return AvailabilityOut(
        supplier=result.supplier,
        degraded=False,
        item=_item_out(result.items[0]),
    )


@sourcing_router.post("/rfq")
async def send_sourcing_rfq(
    payload: SourcingRfqIn,
    adapter: Adapter,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> SourcingRfqOut:
    """Issue a sourcing RFQ to the supplier for a set of purchased components.

    Part numbers and quantities only — **no files leave the tenant**, which is
    why the M6.7c external-send gate (per-send confirmation + redacted variant +
    export-control screening) does not apply to this lane. The send is recorded
    on the org's event outbox so the disclosure is auditable (M6.9).
    """
    wanted = _check_quantities(payload.quantities)
    components = await _load_components(
        session, principal.active_org_id, payload.purchased_component_ids
    )
    org_name = await session.scalar(
        select(Organization.name).where(Organization.id == principal.active_org_id)
    )

    reference = f"TS-RFQ-{uuid.uuid4()}"
    request = SourcingRfqRequest(
        reference=reference,
        requested_by=org_name or "",
        reply_to=payload.reply_to,
        message=payload.message,
        lines=[
            SourcingRfqLine(
                oem_part_number=component.oem_part_number,
                description=component.description,
                quantities=wanted,
            )
            for component in components
        ],
    )

    try:
        result = await adapter.send_rfq(request)
    except SupplierUnavailable:
        # Unlike a lookup, a send that did not happen must say so — there is no
        # sensible "degraded" send, and the estimator has to be able to retry.
        raise AppError(
            "supplier_unavailable",
            "Der Lieferant ist derzeit nicht erreichbar. Bitte später erneut senden.",
            status_code=503,
        ) from None

    await emit_event(
        session,
        principal.active_org_id,
        "sourcing.rfq_sent",
        {
            "supplier": adapter.supplier,
            # fixture vs live is part of the audit record: a mock send must never
            # read, later, as evidence that the supplier was contacted.
            "mode": result.mode,
            "reference": result.reference,
            "supplier_reference": result.supplier_reference,
            "purchased_component_ids": [str(component.id) for component in components],
            "quantities": wanted,
            "sent_by": str(principal.user_id),
        },
    )

    return SourcingRfqOut(
        supplier=adapter.supplier,
        reference=result.reference,
        accepted=result.accepted,
        supplier_reference=result.supplier_reference,
        estimated_response_hours=result.estimated_response_hours,
        mode=result.mode,
    )
