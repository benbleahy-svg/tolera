"""Tax/Region service — VAT at the quote-total boundary (M1.11).

Placement per PRICING-ENGINE-SPEC §1 and DACH-DELTA §3: **tax is never in
Kalk** and never stored on cells; it is computed at quote/order level from
the org's country. Rates are the spec ``#dach-tax`` table (standard rate
applies to machined parts; the reduced rates ride along for later config,
their "(verify)" flags included). Money crosses to **integer minor units +
explicit currency** exactly here (DECISIONS.md 2026-07-08: ``numeric(14,4)``
internals, minor units only at the quote-total boundary), with 2-dp
ROUND_HALF_UP (kaufmännische Rundung).

Out of scope until M5 (block Scope (out)): reverse charge §13b UStG + VIES
validation, Kleinunternehmer §19 suppression, e-invoice field assembly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .models import OrgCountry

_CENT = Decimal("0.01")
_MINOR_PER_UNIT = 100


@dataclass(frozen=True)
class VatProfile:
    """One country's VAT posture (spec ``#dach-tax`` table)."""

    standard_pct: Decimal
    reduced_pcts: tuple[Decimal, ...]
    label: str  # the tax term shown on the quote's VAT line


VAT_PROFILES: dict[OrgCountry, VatProfile] = {
    OrgCountry.DE: VatProfile(Decimal("19"), (Decimal("7"),), "MwSt."),
    OrgCountry.AT: VatProfile(Decimal("20"), (Decimal("13"), Decimal("10")), "USt."),
    OrgCountry.CH: VatProfile(Decimal("8.1"), (Decimal("2.6"), Decimal("3.8")), "MWST"),
}


def round_money(amount: Decimal) -> Decimal:
    """2-dp kaufmännische Rundung — the display/total boundary."""
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def vat_amount(net: Decimal, rate_pct: Decimal) -> Decimal:
    """VAT on a 2-dp net, rounded half-up at the cent."""
    return round_money(net * rate_pct / Decimal(100))


def to_minor_units(amount: Decimal) -> int:
    """A 2-dp money amount → exact integer minor units (cents/Rappen)."""
    minor = (amount * _MINOR_PER_UNIT).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)
