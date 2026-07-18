"""M5.3 — VAT / reverse-charge / VIES / Kleinunternehmer tax service.

Pure-logic tests for ``app.vat_service`` (no DB). The money invariant: net in
is a 2-dp ``Decimal``; net/vat/gross out are integer minor units. Reverse charge
(§13b UStG) and Kleinunternehmer (§19) suppress VAT. Rates verified 2026-07-18
against published 2026 values (DECISIONS.md 2026-07-18 M5.2+M5.3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models import OrgCountry
from app.vat_service import (
    ViesResult,
    format_money,
    parse_vat_country,
    resolve_order_tax,
)

_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


class _StubVies:
    """Injectable VIES double. ``valid`` fixes the verdict; ``raises`` simulates
    an unreachable service (the fail-safe path must fall back to charging VAT)."""

    def __init__(self, *, valid: bool = True, raises: bool = False) -> None:
        self._valid = valid
        self._raises = raises
        self.calls: list[str] = []

    async def check(self, ust_id_nr: str) -> ViesResult:
        self.calls.append(ust_id_nr)
        if self._raises:
            raise RuntimeError("VIES unreachable")
        return ViesResult(valid=self._valid, checked_at=_NOW, name="ACME GmbH")


# --------------------------------------------------------------------------- #
# parse_vat_country
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("ust_id", "expected"),
    [
        ("DE123456789", "DE"),
        ("de 123 456 789", "DE"),
        ("ATU12345678", "AT"),
        ("EL123456789", "EL"),  # Greece uses EL, not GR, for VAT
        ("FR12345678901", "FR"),
        ("", None),
        ("12345", None),
        (None, None),
    ],
)
def test_parse_vat_country(ust_id: str | None, expected: str | None) -> None:
    assert parse_vat_country(ust_id) == expected


# --------------------------------------------------------------------------- #
# Domestic VAT — standard rate, exact minor units
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_domestic_de_charges_19_pct() -> None:
    vies = _StubVies(valid=True)
    tb, vres = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr=None,
        supplier_ust_id_nr="DE999999999",
        vies=vies,
    )
    assert tb.reverse_charge is False
    assert tb.kleinunternehmer is False
    assert tb.vat_rate_pct == Decimal("19")
    assert tb.vat_label == "MwSt."
    assert tb.net_minor == 100000
    assert tb.vat_minor == 19000
    assert tb.gross_minor == 119000
    # gross = net + vat to the cent
    assert tb.gross_minor == tb.net_minor + tb.vat_minor
    # no buyer VAT-ID → VIES never called
    assert vies.calls == []
    assert vres is None


@pytest.mark.asyncio
async def test_domestic_at_charges_20_pct() -> None:
    tb, _ = await resolve_order_tax(
        net=Decimal("500.00"),
        shop_country=OrgCountry.AT,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr=None,
        supplier_ust_id_nr="ATU99999999",
        vies=_StubVies(),
    )
    assert tb.vat_rate_pct == Decimal("20")
    assert tb.vat_label == "USt."
    assert tb.net_minor == 50000
    assert tb.vat_minor == 10000
    assert tb.gross_minor == 60000


@pytest.mark.asyncio
async def test_domestic_ch_charges_8_1_pct_and_no_reverse_charge_even_with_vat_id() -> None:
    # Switzerland is non-EU: §13b/VIES never apply. A buyer VAT-ID does not
    # trigger reverse charge; CH is always domestic MWST.
    vies = _StubVies(valid=True)
    tb, vres = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.CH,
        currency="CHF",
        is_kleinunternehmer=False,
        buyer_ust_id_nr="DE123456789",
        supplier_ust_id_nr="CHE123456789",
        vies=vies,
    )
    assert tb.reverse_charge is False
    assert tb.vat_rate_pct == Decimal("8.1")
    assert tb.vat_label == "MWST"
    assert tb.vat_minor == 8100
    assert tb.gross_minor == 108100
    assert vies.calls == []  # CH shop never calls VIES
    assert vres is None


# --------------------------------------------------------------------------- #
# Reverse charge (§13b UStG) — intra-EU B2B with a VIES-valid USt-IdNr
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_eu_b2b_valid_vies_is_reverse_charge() -> None:
    vies = _StubVies(valid=True)
    tb, vres = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr="ATU12345678",  # Austrian buyer, different EU state
        supplier_ust_id_nr="DE999999999",
        vies=vies,
    )
    assert tb.reverse_charge is True
    assert tb.vat_rate_pct == Decimal("0")
    assert tb.vat_minor == 0
    assert tb.net_minor == 100000
    assert tb.gross_minor == 100000  # gross == net, no VAT
    assert tb.note == "Steuerschuldnerschaft des Leistungsempfängers"
    # both VAT-IDs carried for the §14 invoice
    assert tb.supplier_ust_id_nr == "DE999999999"
    assert tb.customer_ust_id_nr == "ATU12345678"
    assert vies.calls == ["ATU12345678"]
    assert vres is not None and vres.valid is True


@pytest.mark.asyncio
async def test_reverse_charge_needs_a_supplier_vat_id() -> None:
    # A shop with no USt-IdNr may not issue a §13b invoice (§14 UStG requires the
    # supplier VAT-ID) → fall back to domestic VAT, and never consult VIES.
    vies = _StubVies(valid=True)
    tb, vres = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr="ATU12345678",
        supplier_ust_id_nr=None,
        vies=vies,
    )
    assert tb.reverse_charge is False
    assert tb.vat_minor == 19000
    assert vies.calls == []
    assert vres is None


@pytest.mark.asyncio
async def test_same_country_eu_vat_id_is_domestic_not_reverse_charge() -> None:
    # A German buyer with a German VAT-ID buying from a German shop = domestic.
    vies = _StubVies(valid=True)
    tb, _ = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr="DE123456789",
        supplier_ust_id_nr="DE999999999",
        vies=vies,
    )
    assert tb.reverse_charge is False
    assert tb.vat_minor == 19000
    # domestic path must not consult VIES (no cross-border reverse-charge question)
    assert vies.calls == []


@pytest.mark.asyncio
async def test_eu_b2b_invalid_vies_falls_back_to_vat() -> None:
    vies = _StubVies(valid=False)
    tb, vres = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr="ATU12345678",
        supplier_ust_id_nr="DE999999999",
        vies=vies,
    )
    assert tb.reverse_charge is False
    assert tb.vat_minor == 19000
    assert tb.gross_minor == 119000
    assert vies.calls == ["ATU12345678"]
    assert vres is not None and vres.valid is False


@pytest.mark.asyncio
async def test_eu_b2b_vies_unreachable_fails_safe_to_vat() -> None:
    # Fail-safe: an unreachable VIES must charge VAT, never silently grant
    # reverse charge (that would under-collect tax).
    vies = _StubVies(raises=True)
    tb, vres = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr="ATU12345678",
        supplier_ust_id_nr="DE999999999",
        vies=vies,
    )
    assert tb.reverse_charge is False
    assert tb.vat_minor == 19000
    assert vres is not None and vres.valid is False


@pytest.mark.asyncio
async def test_non_eu_buyer_vat_id_is_not_reverse_charge() -> None:
    # A non-EU prefix (e.g. Norway NO) is not an intra-EU acquisition.
    vies = _StubVies(valid=True)
    tb, _ = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr="NO123456789",
        supplier_ust_id_nr="DE999999999",
        vies=vies,
    )
    assert tb.reverse_charge is False
    assert tb.vat_minor == 19000
    assert vies.calls == []  # not an EU state → no VIES check


# --------------------------------------------------------------------------- #
# Kleinunternehmer §19 — VAT lines suppressed
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_kleinunternehmer_suppresses_vat() -> None:
    tb, _ = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=True,
        buyer_ust_id_nr=None,
        supplier_ust_id_nr=None,
        vies=_StubVies(),
    )
    assert tb.kleinunternehmer is True
    assert tb.reverse_charge is False
    assert tb.vat_rate_pct == Decimal("0")
    assert tb.vat_minor == 0
    assert tb.net_minor == 100000
    assert tb.gross_minor == 100000
    assert tb.note is not None and "§19" in tb.note
    # §19 = no VAT line at all: no rate band a §14 PDF could render.
    assert tb.rate_lines == []


@pytest.mark.asyncio
async def test_kleinunternehmer_overrides_reverse_charge() -> None:
    # A Kleinunternehmer never charges VAT and never issues a reverse-charge
    # invoice — §19 wins over the §13b path.
    vies = _StubVies(valid=True)
    tb, _ = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=True,
        buyer_ust_id_nr="ATU12345678",
        supplier_ust_id_nr="DE999999999",
        vies=vies,
    )
    assert tb.kleinunternehmer is True
    assert tb.reverse_charge is False
    assert tb.vat_minor == 0
    assert vies.calls == []  # §19 short-circuits before any VIES call


# --------------------------------------------------------------------------- #
# Rounding — VAT computed on the rounded net, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_vat_rounds_half_up_to_the_cent() -> None:
    # 261.80 € net · 19% = 49.742 → 49.74 €; gross 311.54 €
    tb, _ = await resolve_order_tax(
        net=Decimal("261.80"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr=None,
        supplier_ust_id_nr=None,
        vies=_StubVies(),
    )
    assert tb.net_minor == 26180
    assert tb.vat_minor == 4974
    assert tb.gross_minor == 31154
    assert tb.gross_minor == tb.net_minor + tb.vat_minor


@pytest.mark.asyncio
async def test_vat_rounds_half_up_on_an_exact_tie() -> None:
    # An exact half-cent tie proves ROUND_HALF_UP (not half-even): 1,50 € · 19%
    # = 0,285 → 0,29 € (half-up); half-even would give 0,28 €.
    tb, _ = await resolve_order_tax(
        net=Decimal("1.50"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr=None,
        supplier_ust_id_nr=None,
        vies=_StubVies(),
    )
    assert tb.net_minor == 150
    assert tb.vat_minor == 29  # 0,285 → 0,29 (half-up), not 28 (half-even)


# --------------------------------------------------------------------------- #
# §14 rate-line breakdown
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_rate_lines_carry_the_single_standard_rate() -> None:
    tb, _ = await resolve_order_tax(
        net=Decimal("1000.00"),
        shop_country=OrgCountry.DE,
        currency="EUR",
        is_kleinunternehmer=False,
        buyer_ust_id_nr=None,
        supplier_ust_id_nr=None,
        vies=_StubVies(),
    )
    assert len(tb.rate_lines) == 1
    line = tb.rate_lines[0]
    assert line.rate_pct == Decimal("19")
    assert line.net_minor == 100000
    assert line.vat_minor == 19000


# --------------------------------------------------------------------------- #
# Locale formatting (spec AC: CH renders CHF 1'234.56; DE/AT 1.234,56 €)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("minor", "currency", "locale", "expected"),
    [
        (123456, "EUR", "de-DE", "1.234,56 €"),
        (123456, "EUR", "de-AT", "1.234,56 €"),
        (123456, "CHF", "de-CH", "CHF 1'234.56"),
        (100000, "EUR", "de-DE", "1.000,00 €"),
        (8100, "CHF", "de-CH", "CHF 81.00"),
    ],
)
def test_format_money(minor: int, currency: str, locale: str, expected: str) -> None:
    assert format_money(minor, currency, locale) == expected
