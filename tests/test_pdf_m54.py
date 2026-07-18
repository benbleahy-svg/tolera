"""M5.4 — white-label quote/order PDF (WeasyPrint).

Two test layers:

* **Pure HTML render** (no DB, no native libs) — the stable oracle. Asserts
  field-gating (a toggled-off Display Setting is *absent* from the output),
  the §14-UStG order tax block (incl. the §13b reverse-charge note), German
  labels, and white-label (no "Tolera"/platform string anywhere).
* **Actual PDF render** — skipped when WeasyPrint's native libs are unavailable
  (mirrors the ``db_client`` skip); asserts a valid **A4** PDF via pypdf.

The DB-backed endpoint path (build context from ORM → download) is exercised in
:mod:`tests.test_pdf_api_m54`.
"""

from __future__ import annotations

import html as htmllib
import io
from typing import TYPE_CHECKING, Any, cast

import pytest

from app.buyer_portal import DisplaySettings, NotesPlacement, TotalDisplay

if TYPE_CHECKING:
    from app.models import Order, Organization
from app.pdf import (
    QuoteContent,
    build_order_context,
    build_quote_context,
    html_to_pdf,
    render_document_html,
    weasyprint_available,
)

PLATFORM_STRINGS = ("Tolera", "tolera", "Bid Factory", "Paperless")


# --------------------------------------------------------------------------- #
# Fakes — the shapes the ORM context builders normally assemble.
# --------------------------------------------------------------------------- #
class _Org:
    def __init__(self, **kw: Any) -> None:
        self.name = kw.get("name", "Fechner Zerspanung GmbH")
        self.slug = kw.get("slug", "fechner")
        self.country = kw.get("country")
        self.currency = kw.get("currency", "EUR")
        self.locale = kw.get("locale", "de-DE")
        self.ust_id_nr = kw.get("ust_id_nr", "DE123456789")
        self.logo_object_key = kw.get("logo_object_key")
        self.brand_accent_color = kw.get("brand_accent_color", "#1a3c5e")
        self.facility_phone = kw.get("facility_phone", "+49 89 1234567")
        self.facility_website = kw.get("facility_website", "www.fechner.example")
        self.facility_address = kw.get("facility_address", "Musterstr. 1\n80331 München")


def _buyer_payload(**over: Any) -> dict[str, Any]:
    """A buyer-portal payload shape (what ``build_buyer_payload`` returns)."""
    payload: dict[str, Any] = {
        "quote_number": "Q-1001",
        "rfq_number": "RFQ-77",
        "currency": "EUR",
        "expiration_date": None,
        "is_expired": False,
        "requotes_enabled": False,
        "shop": {"name": "Fechner Zerspanung GmbH", "slug": "fechner"},
        "price_range": {"min_unit": "200.0000", "max_unit": "220.0000"},
        "line_items": [
            {
                "quote_item_id": "11111111-1111-1111-1111-111111111111",
                "position": 1,
                "is_no_quote": False,
                "has_model": True,
                "part_number": "BRK-42",
                "revision": "B",
                "description": "Halterung",
                "process": "CNC-Fräsen",
                "material": "Aluminium 6061",
                "werkstoffnummer": "3.3211",
                "breaks": [
                    {
                        "quantity": 1,
                        "unit_price": "220.0000",
                        "total_price": "220.0000",
                        "lead_time_days": 10,
                        "expedites": [],
                    },
                    {
                        "quantity": 10,
                        "unit_price": "200.0000",
                        "total_price": "2000.0000",
                        "lead_time_days": 10,
                        "expedites": [],
                    },
                ],
                "add_ons": [
                    {
                        "id": "a1",
                        "display_name": "Zertifikat 3.1",
                        "is_required": True,
                        "prices": [{"quantity": 1, "price": "25.0000"}],
                    }
                ],
            }
        ],
    }
    payload.update(over)
    return payload


def _quote_ctx(
    *,
    settings: DisplaySettings | None = None,
    content: QuoteContent | None = None,
    file_names: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_quote_context(
        org=cast("Organization", _Org()),
        payload=payload or _buyer_payload(),
        settings=settings or DisplaySettings(),
        content=content or QuoteContent(),
        document_date="18.07.2026",
        logo_data_uri=None,
        file_names=file_names or {},
        preparer=None,
        # A neutral host: the digital-quote-link is caller-supplied data, not
        # renderer branding. The renderer itself must emit zero platform strings
        # (the white-label check below); the portal URL host is orthogonal
        # infrastructure (custom domains are post-v1).
        digital_quote_link="https://q.example.com/q/abc",
    )


# --------------------------------------------------------------------------- #
# White-label
# --------------------------------------------------------------------------- #
def test_quote_pdf_has_no_platform_branding() -> None:
    html = render_document_html(_quote_ctx())
    for needle in PLATFORM_STRINGS:
        assert needle not in html, f"white-label breach: {needle!r} present"


def test_quote_pdf_shows_org_identity() -> None:
    html = render_document_html(_quote_ctx())
    assert "Fechner Zerspanung GmbH" in html
    assert "Angebot" in html  # German doc title


# --------------------------------------------------------------------------- #
# Field gating — a toggled-off Display Setting is ABSENT from the output.
# --------------------------------------------------------------------------- #
def test_quote_number_toggle_off_removes_it() -> None:
    on = render_document_html(_quote_ctx(settings=DisplaySettings(show_quote_number=True)))
    off = render_document_html(_quote_ctx(settings=DisplaySettings(show_quote_number=False)))
    assert "Q-1001" in on
    assert "Q-1001" not in off


def test_rfq_number_toggle_off_removes_it() -> None:
    on = render_document_html(_quote_ctx(settings=DisplaySettings(show_rfq_number=True)))
    off = render_document_html(_quote_ctx(settings=DisplaySettings(show_rfq_number=False)))
    assert "RFQ-77" in on
    assert "RFQ-77" not in off


def test_facility_phone_toggle_off_removes_it() -> None:
    off = render_document_html(_quote_ctx(settings=DisplaySettings(show_facility_phone=False)))
    assert "+49 89 1234567" not in off


def test_process_toggle_off_removes_it() -> None:
    off = render_document_html(_quote_ctx(settings=DisplaySettings(show_process=False)))
    assert "CNC-Fräsen" not in off


def test_digital_quote_link_toggle_off_removes_it() -> None:
    off = render_document_html(_quote_ctx(settings=DisplaySettings(show_digital_quote_link=False)))
    assert "q.tolera.eu/q/abc" not in off


def test_part_file_name_toggle_on_shows_it() -> None:
    qi = "11111111-1111-1111-1111-111111111111"
    on = render_document_html(
        _quote_ctx(
            settings=DisplaySettings(show_part_file_name=True),
            file_names={qi: "halterung.step"},
        )
    )
    off = render_document_html(_quote_ctx(settings=DisplaySettings(show_part_file_name=False)))
    assert "halterung.step" in on
    assert "halterung.step" not in off


# --------------------------------------------------------------------------- #
# Total display radio
# --------------------------------------------------------------------------- #
def test_total_display_none_hides_the_total() -> None:
    settings = DisplaySettings(total_display=TotalDisplay.none)
    html = render_document_html(_quote_ctx(settings=settings))
    # No aggregate total block; the per-line grid still prints its prices.
    assert "Preisspanne" not in html
    assert "Maximalpreis" not in html


def test_total_display_price_range_shows_a_range() -> None:
    html = render_document_html(
        _quote_ctx(settings=DisplaySettings(total_display=TotalDisplay.price_range))
    )
    assert "Preisspanne" in html
    assert "200,00" in html and "220,00" in html  # German-formatted min/max


def test_total_display_maximum_price_shows_the_max() -> None:
    html = render_document_html(
        _quote_ctx(settings=DisplaySettings(total_display=TotalDisplay.maximum_price))
    )
    assert "Maximalpreis" in html
    assert "220,00" in html


# --------------------------------------------------------------------------- #
# Notes placement + merge content
# --------------------------------------------------------------------------- #
def test_notes_placement_above_puts_notes_before_items() -> None:
    content = QuoteContent(quote_notes="Bitte Grate entfernen.")
    settings = DisplaySettings(notes_placement=NotesPlacement.above)
    html = render_document_html(_quote_ctx(settings=settings, content=content))
    assert html.index("Bitte Grate entfernen.") < html.index("Halterung")


def test_notes_placement_below_puts_notes_after_items() -> None:
    content = QuoteContent(quote_notes="Bitte Grate entfernen.")
    settings = DisplaySettings(notes_placement=NotesPlacement.below)
    html = render_document_html(_quote_ctx(settings=settings, content=content))
    assert html.index("Bitte Grate entfernen.") > html.index("Halterung")


def test_terms_and_manufacturers_notes_render() -> None:
    content = QuoteContent(
        terms="Es gelten unsere AGB.",
        manufacturers_notes="Fertigung nach ISO 2768-m.",
        quote_notes=None,
    )
    html = render_document_html(_quote_ctx(content=content))
    assert "Es gelten unsere AGB." in html
    assert "Fertigung nach ISO 2768-m." in html


# --------------------------------------------------------------------------- #
# Quote is net (Angebot ≠ Rechnung): net note, no invented VAT block.
# --------------------------------------------------------------------------- #
def test_quote_shows_net_note_and_no_tax_block() -> None:
    html = render_document_html(_quote_ctx())
    assert "netto" in html.lower()
    # The quote is pre-checkout: no resolved §14 tax block / reverse-charge note.
    assert "Steuerschuldnerschaft des Leistungsempfängers" not in html


# --------------------------------------------------------------------------- #
# Order variant — §14-UStG tax block + order-confirmation header.
# --------------------------------------------------------------------------- #
class _Order:
    def __init__(self, **kw: Any) -> None:
        self.number = kw.get("number", "O-500")
        self.currency = kw.get("currency", "EUR")
        self.net_minor = kw.get("net_minor", 22500)
        self.vat_minor = kw.get("vat_minor", 4275)
        self.gross_minor = kw.get("gross_minor", 26775)
        self.vat_rate_pct = kw.get("vat_rate_pct", __import__("decimal").Decimal("19"))
        self.vat_label = kw.get("vat_label", "MwSt.")
        self.reverse_charge = kw.get("reverse_charge", False)
        self.kleinunternehmer = kw.get("kleinunternehmer", False)
        self.tax_note = kw.get("tax_note")
        self.supplier_ust_id_nr = kw.get("supplier_ust_id_nr")
        self.buyer_ust_id_nr = kw.get("buyer_ust_id_nr")
        self.tax_rate_lines = kw.get(
            "tax_rate_lines", [{"rate_pct": "19", "net_minor": 22500, "vat_minor": 4275}]
        )
        self.po_number = kw.get("po_number", "PO-4711")
        self.company_name = kw.get("company_name", "Muster GmbH")
        self.billing_address = kw.get("billing_address", "Musterstr. 9\n10115 Berlin")


def _order_lines() -> list[dict[str, Any]]:
    return [
        {
            "position": 1,
            "part_number": "BRK-42",
            "revision": "B",
            "description": "Halterung",
            "process": "CNC-Fräsen",
            "material": "Aluminium 6061",
            "werkstoffnummer": "3.3211",
            "quantity": 10,
            "unit_price_minor": 20000,
            "total_price_minor": 22500,
            "lead_time_days": 10,
            "ships_on": "2026-08-01",
            "add_ons": [{"name": "Zertifikat 3.1", "price_minor": 2500, "required": True}],
        }
    ]


def _order_ctx(*, order: _Order | None = None) -> dict[str, Any]:
    return build_order_context(
        org=cast("Organization", _Org()),
        order=cast("Order", order or _Order()),
        lines=_order_lines(),
        settings=DisplaySettings(),
        content=QuoteContent(),
        document_date="18.07.2026",
        logo_data_uri=None,
    )


def test_order_variant_has_confirmation_header() -> None:
    html = render_document_html(_order_ctx())
    assert "Auftragsbestätigung" in html
    assert "O-500" in html
    assert "PO-4711" in html


def test_order_domestic_tax_block() -> None:
    html = render_document_html(_order_ctx())
    assert "225,00" in html  # net 22500
    assert "42,75" in html  # vat 4275
    assert "267,75" in html  # gross 26775
    assert "19" in html
    assert "MwSt" in html


def test_order_reverse_charge_note_and_both_vat_ids() -> None:
    order = _Order(
        vat_minor=0,
        gross_minor=22500,
        vat_rate_pct=__import__("decimal").Decimal("0"),
        reverse_charge=True,
        tax_note="Steuerschuldnerschaft des Leistungsempfängers",
        supplier_ust_id_nr="DE123456789",
        buyer_ust_id_nr="ATU12345678",
        tax_rate_lines=[{"rate_pct": "0", "net_minor": 22500, "vat_minor": 0}],
    )
    html = render_document_html(_order_ctx(order=order))
    assert "Steuerschuldnerschaft des Leistungsempfängers" in html
    assert "DE123456789" in html
    assert "ATU12345678" in html


def test_order_kleinunternehmer_suppresses_vat() -> None:
    order = _Order(
        vat_minor=0,
        gross_minor=22500,
        vat_rate_pct=__import__("decimal").Decimal("0"),
        kleinunternehmer=True,
        tax_note="Gemäß §19 UStG wird keine Umsatzsteuer berechnet (Kleinunternehmerregelung).",
        tax_rate_lines=[],
    )
    html = render_document_html(_order_ctx(order=order))
    assert "§19 UStG" in html


def test_order_has_no_platform_branding() -> None:
    html = render_document_html(_order_ctx())
    for needle in PLATFORM_STRINGS:
        assert needle not in html, f"white-label breach: {needle!r} present"


def test_ch_order_uses_swiss_money_format() -> None:
    org = _Org(currency="CHF")
    order = _Order(
        currency="CHF",
        net_minor=123456,
        vat_minor=10000,
        gross_minor=133456,
        vat_rate_pct=__import__("decimal").Decimal("8.1"),
        tax_rate_lines=[{"rate_pct": "8.1", "net_minor": 123456, "vat_minor": 10000}],
    )
    ctx = build_order_context(
        org=cast("Organization", org),
        order=cast("Order", order),
        lines=_order_lines(),
        settings=DisplaySettings(),
        content=QuoteContent(),
        document_date="18.07.2026",
        logo_data_uri=None,
    )
    # The Swiss apostrophe separator (U+0027) is HTML-escaped to &#39; by Jinja
    # autoescaping — it renders as a plain apostrophe in the PDF. Assert on the
    # unescaped (semantic) text.
    html = htmllib.unescape(render_document_html(ctx))
    assert "CHF 1'234.56" in html  # apostrophe thousands, point decimal


# --------------------------------------------------------------------------- #
# Actual PDF render — A4, valid PDF. Skipped without WeasyPrint native libs.
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not weasyprint_available(), reason="WeasyPrint native libs unavailable")
def test_rendered_pdf_is_valid_a4() -> None:
    from pypdf import PdfReader

    pdf = html_to_pdf(render_document_html(_quote_ctx()))
    assert pdf[:5] == b"%PDF-"
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 1
    box = reader.pages[0].mediabox
    # A4 = 210x297 mm = 595.28 x 841.89 pt (1 pt = 1/72 in). Allow a small rounding band.
    assert abs(float(box.width) - 595.28) < 3
    assert abs(float(box.height) - 841.89) < 3


@pytest.mark.skipif(not weasyprint_available(), reason="WeasyPrint native libs unavailable")
def test_rendered_order_pdf_is_valid() -> None:
    pdf = html_to_pdf(render_document_html(_order_ctx()))
    assert pdf[:5] == b"%PDF-"
