"""The shared ``SupplierAdapter`` interface (M6.7).

One interface, several capabilities — the family ``DECISIONS.md`` names across
M6.7 / M6.7b / M6.7c:

``availability_pricing``
    stock + price-by-quantity for a catalogue part (Würth here; thyssenkrupp
    materials4me at M6.7b as the raw-material ``MaterialPricingFeed``).
``sourcing_rfq``
    issue a quote request to the supplier for a set of parts + quantity breaks.
``part_quoting``
    instant quotes for an outsourced *part* from a STEP file (M6.7c) — declared
    here so the capability vocabulary is one list, implemented there. That lane
    alone carries the mandatory external-send gate (per-send confirmation +
    redacted variant + export-control screening), because customer CAD leaves
    the tenant; the two capabilities above never send a file.

**Money.** Every price crossing this boundary is an integer in **minor units**
plus an explicit ISO-4217 ``currency`` (CLAUDE.md §5) — never a float. No FX
conversion happens: a supplier's quoted currency is reported verbatim, so a CHF
shop sees an EUR-quoted supplier price labelled EUR.

**Suggestion-only.** Nothing here writes to costing. A supplier price is
displayed and may be applied by a human through the existing Apply path; it
never silently reprices a draft (spec ``#sourcing-adapters`` → E4-d freeze).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class SupplierCapability(enum.StrEnum):
    """What an adapter can do — see the module docstring."""

    availability_pricing = "availability_pricing"
    sourcing_rfq = "sourcing_rfq"
    part_quoting = "part_quoting"


class AvailabilityStatus(enum.StrEnum):
    """The inventory dot for one requested quantity (spec ``#collab`` →
    "Real-time purchased-component pricing & availability").

    The reference product's rule: green when the distributor holds **≥ 200 %** of
    the required quantity for that make-quantity break, amber ("stock is at
    risk") when it holds enough but less than that, red below the requirement.
    """

    available = "available"
    at_risk = "at_risk"
    insufficient = "insufficient"
    unknown = "unknown"


#: The "comfortable stock" multiplier behind :attr:`AvailabilityStatus.available`.
STOCK_COMFORT_FACTOR = 2


def classify_stock(quantity_available: int | None, required: int) -> AvailabilityStatus:
    """Map stock-on-hand against one required quantity onto an inventory dot."""
    if quantity_available is None:
        return AvailabilityStatus.unknown
    if quantity_available >= required * STOCK_COMFORT_FACTOR:
        return AvailabilityStatus.available
    if quantity_available >= required:
        return AvailabilityStatus.at_risk
    return AvailabilityStatus.insufficient


@dataclass(frozen=True, slots=True)
class QuantityQuote:
    """The supplier's answer for one requested quantity.

    ``unit_price_minor`` is ``None`` when the supplier carries the part but
    quotes no price at that quantity (e.g. its cheapest break starts at 5 and
    the line asks for 1). The row is still returned: dropping it would leave one
    of the estimator's make-quantities silently missing from the table.
    """

    quantity: int
    #: Unit price in minor units of :attr:`AvailabilityItem.currency` (int, never float).
    unit_price_minor: int | None
    status: AvailabilityStatus

    @property
    def extended_price_minor(self) -> int | None:
        """Unit price times quantity, still in minor units."""
        if self.unit_price_minor is None:
            return None
        return self.unit_price_minor * self.quantity


@dataclass(frozen=True, slots=True)
class AvailabilityItem:
    """One requested part number, answered.

    ``found=False`` is a normal answer, not an error: the supplier simply does
    not carry that part number.
    """

    oem_part_number: str
    found: bool
    currency: str
    description: str | None = None
    brand: str | None = None
    quantity_available: int | None = None
    lead_time_days: int | None = None
    quotes: tuple[QuantityQuote, ...] = ()


@dataclass(frozen=True, slots=True)
class AvailabilityResult:
    """One answer per requested part number, in request order."""

    supplier: str
    items: tuple[AvailabilityItem, ...]


@dataclass(frozen=True, slots=True)
class SourcingRfqLine:
    """One line of a sourcing RFQ — a part number and the quantity breaks."""

    oem_part_number: str
    quantities: tuple[int, ...] | list[int]
    description: str | None = None


@dataclass(frozen=True, slots=True)
class SourcingRfqRequest:
    """A quote request to the supplier.

    Carries part numbers, quantities and an optional free-text message only —
    **never a file**. ``requested_by`` is the org's display name; ``reply_to`` is
    the shop's own purchasing address when it wants the answer by mail.
    """

    reference: str
    requested_by: str
    lines: list[SourcingRfqLine] = field(default_factory=list)
    reply_to: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class SourcingRfqResult:
    """The supplier's acknowledgement of a sourcing RFQ.

    ``mode`` says whether this went to the real supplier (``live``) or to the
    recorded fixture (``fixture``). It is carried all the way to the UI and the
    audit event on purpose: while procurement is pending, an estimator must not
    read "Anfrage gesendet" as "Würth has it".
    """

    reference: str
    accepted: bool
    supplier_reference: str | None = None
    estimated_response_hours: int | None = None
    mode: str = "fixture"


class SupplierUnavailable(Exception):
    """The supplier could not be reached, or answered unusably.

    Callers degrade — a stale/unavailable badge — and **never** fail costing on
    it (spec ``#sourcing-adapters``: "timeout/error → last-known price + stale
    badge; never blocks costing"). The underlying client error is logged, not
    re-raised, so no endpoint URL or credential can leak into an API response.
    """

    def __init__(self, supplier: str, message: str = "Lieferant nicht erreichbar") -> None:
        super().__init__(message)
        self.supplier = supplier


@runtime_checkable
class SupplierAdapter(Protocol):
    """What every supplier connector exposes.

    Implementations declare :attr:`capabilities`; a caller checks membership
    before invoking the matching method rather than catching ``AttributeError``.
    """

    supplier: str
    capabilities: frozenset[SupplierCapability]

    async def availability(
        self, oem_part_numbers: list[str], *, quantities: list[int]
    ) -> AvailabilityResult:
        """Stock + price-by-quantity for each part number.

        Raises :class:`SupplierUnavailable` on any transport/parse failure.
        """
        ...

    async def send_rfq(self, request: SourcingRfqRequest) -> SourcingRfqResult:
        """Issue a sourcing RFQ. Raises :class:`SupplierUnavailable` on failure."""
        ...
