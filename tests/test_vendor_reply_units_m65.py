"""M6.5 — pure units of the vendor email channel.

Three things here are worth pinning without a database, because getting any of them
wrong is silent and expensive:

* the **RFQ reference** round-trip — ``vendor_rfq.number`` is a bare integer, so the
  wire form (``RFQ-12``) and the regex that finds it again are the only thing keeping
  a reply from matching on a stray digit in a vendor's signature;
* **German money parsing** — ``1.234,56 €`` and ``1,234.56`` mean the same amount and
  ``1.234`` means one *thousand* two hundred thirty-four in a DACH quote. We parse the
  vendor's verbatim text ourselves rather than trusting a model's normalisation
  (CLAUDE.md §5: money is never a float, and never an AI's arithmetic);
* the **never-hallucinate guard** — a price the model reports that is not verbatim in
  the reply is dropped, mirroring ``parts_list_guard`` (M3.4).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.vendor_reply import (
    RawVendorPrice,
    RawVendorQuoteLine,
    find_rfq_reference,
    parse_money,
    parse_price,
    rfq_reference,
    vendor_reply_guard,
)


# --------------------------------------------------------------------------- #
# Reference round-trip
# --------------------------------------------------------------------------- #
def test_reference_is_the_bare_number_made_greppable() -> None:
    assert rfq_reference("12") == "RFQ-12"


@pytest.mark.parametrize(
    "text",
    [
        "Betreff: RFQ-12 — Anfrage Eloxieren",
        "AW: RFQ 12 Anfrage",
        "Re: RFQ #12",
        "unsere Antwort zu RFQ-0012 folgt",
        "rfq-12 (Kleinschreibung)",
        "Ihre Anfrage RFQ:12 vom 19.07.",
    ],
)
def test_reference_is_found_in_every_shape_a_mail_client_mangles_it_into(text: str) -> None:
    assert find_rfq_reference(text) == "12"


@pytest.mark.parametrize(
    "text",
    [
        "Angebot 12 vom 19.07.2026",  # a bare number is never a reference
        "unsere Auftragsnummer 12345",
        "RFQ ohne Nummer",
        "Bestellung BST-12",
    ],
)
def test_a_bare_number_never_matches(text: str) -> None:
    assert find_rfq_reference(text) is None


def test_subject_wins_over_body_when_both_carry_a_reference() -> None:
    # A vendor quoting our own footer can drag an older reference into the body; the
    # subject is the thread's identity.
    assert find_rfq_reference("AW: RFQ-12", "... siehe auch RFQ-9 ...") == "12"


def test_body_is_used_when_the_subject_lost_the_reference() -> None:
    assert find_rfq_reference("Ihr Angebot", "Bezug: RFQ-9") == "9"


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12,50", Decimal("12.50")),  # German decimal comma
        ("12.50", Decimal("12.50")),  # English decimal point
        ("1.234,56", Decimal("1234.56")),  # German grouped
        ("1,234.56", Decimal("1234.56")),  # English grouped
        ("1.234", Decimal("1234")),  # German thousands, no decimals
        # A lone comma is ALWAYS the decimal separator in a DACH quote — reading
        # "2,750" as two thousand seven hundred fifty would be a 1000x error on a
        # price the vendor meant as 2,75 €, and nothing downstream would catch it.
        ("0,500", Decimal("0.500")),
        ("2,750 EUR", Decimal("2.750")),
        ("12,500", Decimal("12.5")),
        # A lone dot with a leading zero is a decimal point, not a group.
        ("0.500", Decimal("0.5")),
        ("1.234.567", Decimal("1234567")),
        ("1234", Decimal("1234")),
        ("0,45", Decimal("0.45")),
        ("12,50 €", Decimal("12.50")),
        ("EUR 12,50", Decimal("12.50")),
        ("€ 1.234,56", Decimal("1234.56")),
        ("CHF 89.90", Decimal("89.90")),
        ("  12,50  ", Decimal("12.50")),
        ("12,5", Decimal("12.5")),
    ],
)
def test_parse_money_reads_both_locales(raw: str, expected: Decimal) -> None:
    assert parse_money(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "auf Anfrage",
        "-12,50",  # a negative vendor price is never meaningful
        "12,50,60",
        "1.2.3,4.5",
        "abc",
        "12,50%",  # a percentage is not a price
        "1e5",
    ],
)
def test_parse_money_refuses_what_it_cannot_read_rather_than_guessing(raw: str) -> None:
    assert parse_money(raw) is None


def test_parse_money_keeps_exact_decimal_never_float() -> None:
    value = parse_money("0,10")
    assert value == Decimal("0.10")
    # The classic float trap: 0.1 * 3 != 0.3. Decimal must not fall into it.
    assert value is not None and value * 3 == Decimal("0.30")


def test_parse_money_rejects_more_precision_than_the_column_holds() -> None:
    # vendor_rfq_response_price.unit_price is numeric(14,4).
    assert parse_money("12,12345") is None
    assert parse_money("12,1234") == Decimal("12.1234")


# --------------------------------------------------------------------------- #
# Never-hallucinate guard
# --------------------------------------------------------------------------- #
def _line(
    *, price_raw: str = "12,50", lead_raw: str | None = "10 Arbeitstage"
) -> RawVendorQuoteLine:
    return RawVendorQuoteLine(
        part_number="P-1",
        cannot_quote=False,
        notes=None,
        prices=[
            RawVendorPrice(
                quantity=10,
                unit_price_raw=price_raw,
                lead_time_days=10,
                lead_time_raw=lead_raw,
            )
        ],
    )


def test_guard_keeps_a_price_quoted_verbatim_in_the_body() -> None:
    body = "Fuer 10 Stueck: 12,50 EUR/Stueck, Lieferzeit 10 Arbeitstage."
    kept, dropped = vendor_reply_guard([_line()], body)
    assert dropped == 0
    assert kept[0].prices[0].unit_price == Decimal("12.50")
    assert kept[0].prices[0].lead_time_days == 10


def test_guard_drops_a_price_that_appears_nowhere_in_the_reply() -> None:
    body = "Fuer 10 Stueck: 12,50 EUR/Stueck."
    kept, dropped = vendor_reply_guard([_line(price_raw="99,00", lead_raw=None)], body)
    assert dropped == 1
    # Nothing verifiable is left, so the line carries no information and goes too.
    assert kept == []


def test_guard_drops_only_the_lead_time_when_only_the_lead_time_is_invented() -> None:
    body = "Fuer 10 Stueck: 12,50 EUR/Stueck."
    kept, dropped = vendor_reply_guard([_line(lead_raw="10 Arbeitstage")], body)
    assert dropped == 1
    # The price survives — a hallucinated neighbour must not cost us a real number.
    assert kept[0].prices[0].unit_price == Decimal("12.50")
    assert kept[0].prices[0].lead_time_days is None


def test_guard_searches_the_attached_pdf_text_too() -> None:
    body = "Unser Angebot finden Sie im Anhang."
    pdf = "Position 1 — 10 Stueck zu 12,50 EUR"
    kept, dropped = vendor_reply_guard([_line(lead_raw=None)], body, pdf)
    assert dropped == 0
    assert kept[0].prices[0].unit_price == Decimal("12.50")


def test_guard_is_insensitive_to_whitespace_and_nbsp_the_way_mail_clients_mangle_it() -> None:
    body = "Preis: 1.234,56\u00a0€ pro Stueck"
    kept, dropped = vendor_reply_guard([_line(price_raw="1.234,56 €", lead_raw=None)], body)
    assert dropped == 0
    assert kept[0].prices[0].unit_price == Decimal("1234.56")


def test_guard_keeps_a_cannot_quote_line_which_carries_no_numbers_to_verify() -> None:
    line = RawVendorQuoteLine(
        part_number="P-1", cannot_quote=True, notes="Kein Titan im Haus", prices=[]
    )
    kept, dropped = vendor_reply_guard([line], "Kein Titan im Haus, tut uns leid.")
    assert dropped == 0
    assert kept[0].cannot_quote is True
    assert kept[0].notes == "Kein Titan im Haus"


def test_guard_drops_a_note_the_model_invented() -> None:
    # Notes are shown to the estimator as the vendor's words — they must be the
    # vendor's words.
    line = RawVendorQuoteLine(
        part_number="P-1", cannot_quote=True, notes="Wir liefern ab Werk Stuttgart", prices=[]
    )
    kept, _ = vendor_reply_guard([line], "Titan koennen wir leider nicht.")
    assert kept[0].notes is None


# --------------------------------------------------------------------------- #
# Currency — a CHF quote must never be stored as EUR
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12,50 €", "EUR"),
        ("EUR 12,50", "EUR"),
        ("CHF 89.90", "CHF"),
        ("89.90 CHF", "CHF"),
        ("12,50", None),  # unmarked — the response's own currency stands
    ],
)
def test_parse_price_reports_the_currency_the_vendor_wrote(raw: str, expected: str | None) -> None:
    parsed = parse_price(raw)
    assert parsed is not None
    assert parsed[1] == expected


def test_guard_drops_a_price_quoted_in_a_currency_the_rfq_is_not_in() -> None:
    """A Swiss supplier answering a EUR RFQ in CHF would otherwise be stored as EUR —
    a ~6% silent error on a cost the estimator is about to apply."""
    body = "Fuer 10 Stueck: CHF 89.90 pro Stueck."
    kept, dropped = vendor_reply_guard(
        [_line(price_raw="CHF 89.90", lead_raw=None)], body, currency="EUR"
    )
    assert dropped == 1
    assert kept == []


def test_guard_keeps_a_price_in_the_rfqs_own_currency() -> None:
    body = "Fuer 10 Stueck: 89,90 EUR pro Stueck."
    kept, dropped = vendor_reply_guard(
        [_line(price_raw="89,90 EUR", lead_raw=None)], body, currency="EUR"
    )
    assert dropped == 0
    assert kept[0].prices[0].unit_price == Decimal("89.90")


def test_guard_drops_a_quantity_break_the_rfq_never_asked_about() -> None:
    """The quantity is not a citation the guard can check, so it is checked against
    the batch instead — otherwise a real price lands on an invented break."""
    body = "Fuer 10 Stueck: 12,50 EUR/Stueck."
    kept, dropped = vendor_reply_guard([_line(lead_raw=None)], body, allowed_quantities={5, 100})
    assert dropped == 1
    assert kept == []


def test_guard_keeps_a_quantity_break_the_rfq_did_ask_about() -> None:
    body = "Fuer 10 Stueck: 12,50 EUR/Stueck."
    kept, dropped = vendor_reply_guard([_line(lead_raw=None)], body, allowed_quantities={10, 50})
    assert dropped == 0
    assert kept[0].prices[0].quantity == 10


def test_an_uncited_lead_time_is_absent_but_not_counted_as_a_drop() -> None:
    """Nothing was invented — the model simply declined to cite — so the drop counter,
    which the estimator reads as "facts we refused", must not inflate."""
    body = "Fuer 10 Stueck: 12,50 EUR/Stueck."
    kept, dropped = vendor_reply_guard([_line(lead_raw=None)], body)
    assert dropped == 0
    assert kept[0].prices[0].lead_time_days is None
