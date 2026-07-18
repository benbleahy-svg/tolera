"""VAT / reverse-charge / VIES tax service (M5.3).

The DACH tax engine that resolves a net figure to net / VAT / gross for the
buyer's region and tax profile — **at the quote/order boundary, never in Kalk**
(``PRICING-ENGINE-SPEC §1``, ``DACH-DELTA-LAYER §3``). It generalises M1.11's
domestic-only path (``app.tax``) with the three M5 additions:

* **Reverse charge (§13b UStG)** — intra-EU B2B: an EU shop selling to a
  VAT-registered business in *another* EU member state charges no VAT; the
  invoice carries the note *"Steuerschuldnerschaft des Leistungsempfängers"*
  and both VAT-IDs. Requires a VIES-validated buyer USt-IdNr.
* **VIES validation** — the buyer's USt-IdNr is checked against the EU VIES
  service; the result + timestamp are stored. Fail-safe: an invalid, absent, or
  unreachable VIES result **falls back to charging VAT** (charging is never
  under-collection; wrongly granting reverse charge would be).
* **Kleinunternehmer (§19 UStG)** — a per-org flag that suppresses VAT lines.

Switzerland is non-EU: §13b / VIES never apply, so a CH shop always bills
domestic MWST (DECISIONS.md 2026-07-18 M5.2+M5.3).

Money invariant: ``net`` in is a 2-dp ``Decimal``; ``*_minor`` out are integer
minor units (cents/Rappen), rounded ROUND_HALF_UP at the cent (kaufmännische
Rundung) — the same primitives as ``app.tax`` so the M1.11 ``/totals`` goldens
stay green.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from .models import OrgCountry
from .tax import VAT_PROFILES, to_minor_units, vat_amount

# §13b UStG note rendered on a reverse-charge invoice/quote (DACH-DELTA §3, verbatim).
REVERSE_CHARGE_NOTE = "Steuerschuldnerschaft des Leistungsempfängers"
# §19 UStG small-business suppression note (German; Fechner-reviewed before go-live).
KLEINUNTERNEHMER_NOTE = (
    "Gemäß §19 UStG wird keine Umsatzsteuer berechnet (Kleinunternehmerregelung)."
)

# The 27 EU member-state VAT country prefixes. Greece uses ``EL`` (not ``GR``);
# CH/NO/GB and every other prefix are non-EU → no intra-EU acquisition.
EU_VAT_COUNTRIES: frozenset[str] = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "EL",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
    }
)


@dataclass(frozen=True)
class ViesResult:
    """A VIES validation verdict for a USt-IdNr, with the check timestamp
    (stored on the order for the audit trail / §14 evidence)."""

    valid: bool
    checked_at: datetime
    name: str | None = None


class VIESClient(Protocol):
    """The EU VIES validation seam — a live REST client in prod, a double in
    tests. Never raises to the caller of ``resolve_order_tax`` (the resolver
    treats any error as *not validated* → charge VAT)."""

    async def check(self, ust_id_nr: str) -> ViesResult: ...


@dataclass(frozen=True)
class RateLine:
    """One VAT-rate band for the §14-UStG breakdown (net + VAT per rate)."""

    rate_pct: Decimal
    net_minor: int
    vat_minor: int


@dataclass(frozen=True)
class TaxBreakdown:
    """The resolved tax posture for an order total — everything the checkout
    summary and the M5.4 §14 PDF need, in integer minor units."""

    currency: str
    net_minor: int
    vat_minor: int
    gross_minor: int
    vat_rate_pct: Decimal
    vat_label: str
    reverse_charge: bool
    kleinunternehmer: bool
    note: str | None
    supplier_ust_id_nr: str | None
    customer_ust_id_nr: str | None
    rate_lines: list[RateLine] = field(default_factory=list)


def parse_vat_country(ust_id_nr: str | None) -> str | None:
    """The country prefix of a USt-IdNr (first two letters, uppercased), or
    ``None`` if the value has no alphabetic prefix. Spaces are ignored so
    ``"de 123 456"`` → ``"DE"``. VIES treats this prefix as authoritative for
    the member state (``EL`` = Greece)."""
    if not ust_id_nr:
        return None
    compact = ust_id_nr.replace(" ", "")
    if len(compact) < 2 or not compact[:2].isalpha():
        return None
    return compact[:2].upper()


def _domestic_breakdown(
    net: Decimal,
    shop_country: OrgCountry,
    currency: str,
    *,
    customer_ust_id_nr: str | None,
) -> TaxBreakdown:
    """Standard-rate domestic VAT (DE 19% · AT 20% · CH 8.1%)."""
    profile = VAT_PROFILES[shop_country]
    vat = vat_amount(net, profile.standard_pct)
    net_minor = to_minor_units(net)
    vat_minor = to_minor_units(vat)
    return TaxBreakdown(
        currency=currency,
        net_minor=net_minor,
        vat_minor=vat_minor,
        gross_minor=net_minor + vat_minor,
        vat_rate_pct=profile.standard_pct,
        vat_label=profile.label,
        reverse_charge=False,
        kleinunternehmer=False,
        note=None,
        supplier_ust_id_nr=None,
        customer_ust_id_nr=customer_ust_id_nr,
        rate_lines=[RateLine(profile.standard_pct, net_minor, vat_minor)],
    )


def _reverse_charge_breakdown(
    net: Decimal,
    shop_country: OrgCountry,
    currency: str,
    *,
    supplier_ust_id_nr: str | None,
    customer_ust_id_nr: str | None,
) -> TaxBreakdown:
    """§13b intra-EU B2B: no VAT; the note + both VAT-IDs carry to the invoice."""
    net_minor = to_minor_units(net)
    return TaxBreakdown(
        currency=currency,
        net_minor=net_minor,
        vat_minor=0,
        gross_minor=net_minor,
        vat_rate_pct=Decimal("0"),
        vat_label=VAT_PROFILES[shop_country].label,
        reverse_charge=True,
        kleinunternehmer=False,
        note=REVERSE_CHARGE_NOTE,
        supplier_ust_id_nr=supplier_ust_id_nr,
        customer_ust_id_nr=customer_ust_id_nr,
        rate_lines=[RateLine(Decimal("0"), net_minor, 0)],
    )


def _kleinunternehmer_breakdown(
    net: Decimal, currency: str, *, customer_ust_id_nr: str | None
) -> TaxBreakdown:
    """§19: no VAT line at all; the suppression note is shown instead."""
    net_minor = to_minor_units(net)
    return TaxBreakdown(
        currency=currency,
        net_minor=net_minor,
        vat_minor=0,
        gross_minor=net_minor,
        vat_rate_pct=Decimal("0"),
        vat_label="",
        reverse_charge=False,
        kleinunternehmer=True,
        note=KLEINUNTERNEHMER_NOTE,
        supplier_ust_id_nr=None,
        customer_ust_id_nr=customer_ust_id_nr,
        rate_lines=[RateLine(Decimal("0"), net_minor, 0)],
    )


def _is_intra_eu_b2b(shop_country: OrgCountry, buyer_country: str | None) -> bool:
    """Reverse charge applies only for an EU shop selling to a business in a
    *different* EU member state. CH (non-EU) shops never qualify."""
    return (
        shop_country.value in EU_VAT_COUNTRIES
        and buyer_country is not None
        and buyer_country in EU_VAT_COUNTRIES
        and buyer_country != shop_country.value
    )


async def resolve_order_tax(
    *,
    net: Decimal,
    shop_country: OrgCountry,
    currency: str,
    is_kleinunternehmer: bool,
    buyer_ust_id_nr: str | None,
    supplier_ust_id_nr: str | None,
    vies: VIESClient,
) -> tuple[TaxBreakdown, ViesResult | None]:
    """Resolve ``net`` to a full :class:`TaxBreakdown` for the shop's region and
    the buyer's tax profile. Returns the breakdown plus the :class:`ViesResult`
    when a VIES check was actually performed (else ``None``).

    Precedence: **§19 Kleinunternehmer** (never charges VAT, never reverse
    charge) → **§13b reverse charge** (intra-EU B2B with a VIES-valid USt-IdNr)
    → **domestic standard VAT** (the fallback, including every VIES failure)."""
    customer_id = buyer_ust_id_nr or None

    if is_kleinunternehmer:
        return _kleinunternehmer_breakdown(net, currency, customer_ust_id_nr=customer_id), None

    buyer_country = parse_vat_country(buyer_ust_id_nr)
    if not _is_intra_eu_b2b(shop_country, buyer_country):
        # Domestic (incl. same-country VAT-IDs, CH shops, non-EU buyers): no
        # cross-border reverse-charge question → VIES is never consulted.
        return _domestic_breakdown(
            net, shop_country, currency, customer_ust_id_nr=customer_id
        ), None

    # Intra-EU B2B candidate — validate against VIES, failing safe to VAT.
    assert buyer_ust_id_nr is not None  # guaranteed by _is_intra_eu_b2b
    try:
        vies_result: ViesResult = await vies.check(buyer_ust_id_nr)
    except Exception:  # any VIES failure ⇒ not validated ⇒ charge VAT (fail-safe)
        vies_result = ViesResult(valid=False, checked_at=datetime.now(UTC))

    if vies_result.valid:
        breakdown = _reverse_charge_breakdown(
            net,
            shop_country,
            currency,
            supplier_ust_id_nr=supplier_ust_id_nr,
            customer_ust_id_nr=customer_id,
        )
    else:
        breakdown = _domestic_breakdown(net, shop_country, currency, customer_ust_id_nr=customer_id)
    return breakdown, vies_result


class LiveVIESClient:
    """Production VIES client — the EU REST endpoint
    ``/ms/{country}/vat/{number}`` (``ViesResult.valid`` from the JSON
    ``valid`` field). Any HTTP/parse error propagates so the resolver's
    fail-safe charges VAT rather than granting reverse charge on a bad check."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def check(self, ust_id_nr: str) -> ViesResult:
        import httpx

        compact = ust_id_nr.replace(" ", "").upper()
        country, number = compact[:2], compact[2:]
        url = f"{self._base_url}/ms/{country}/vat/{number}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.json()
        return ViesResult(
            valid=bool(body.get("valid")),
            checked_at=datetime.now(UTC),
            name=body.get("name") or None,
        )


def get_vies_client() -> VIESClient:
    """The default VIES client from settings (overridable in tests / via DI)."""
    from .config import get_settings

    settings = get_settings()
    return LiveVIESClient(settings.vies_base_url, timeout_seconds=settings.vies_timeout_seconds)


def _group(digits: str, sep: str) -> str:
    """Group an integer string in thousands with ``sep``."""
    parts: list[str] = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return sep.join(parts)


def format_money(minor: int, currency: str, locale: str) -> str:
    """Format integer minor units for display in the DACH locales
    (``DACH-DELTA §1``): DE/AT EUR → ``1.234,56 €``; CH CHF → ``CHF 1'234.56``.
    ``locale`` is accepted for future per-locale variants; formatting today is
    driven by ``currency``."""
    negative = minor < 0
    major, cents = divmod(abs(minor), 100)
    if currency == "CHF":
        body = f"CHF {_group(str(major), chr(0x27))}.{cents:02d}"
    else:  # EUR — de-DE / de-AT
        body = f"{_group(str(major), '.')},{cents:02d} €"
    return f"-{body}" if negative else body
