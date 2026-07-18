"""White-label quote / order-confirmation PDF (M5.4).

Renders the shop's **fully white-label** A4 document with WeasyPrint (spec :603;
DECISIONS.md 2026-06-14 — design folded into M5, no Tolera branding). Two layers:

* **Pure** ``build_quote_context`` / ``build_order_context`` → a plain dict, and
  ``render_document_html`` (Jinja2, autoescaped) → HTML. No DB, no native libs —
  the stable, snapshot-friendly oracle.
* **``html_to_pdf``** (WeasyPrint, lazy-imported) → A4 PDF bytes, plus the async
  ORM ``assemble_*`` helpers that pull a quote/order out of the DB.

Field-gating happens **here** (in the context builders), driven by the single
``DisplaySettings`` entity (:mod:`app.buyer_portal`): a toggled-off field is
*absent* from the context, so the template can stay a dumb renderer and the AC
"toggling a Display Setting off removes that field" holds structurally.

Money is never recomputed: the quote grid formats the buyer payload's net
figures, the order block formats the persisted §14-UStG breakdown — both via
:func:`app.vat_service.format_money` (DE/AT ``1.234,56 €`` · CH ``CHF 1'234.56``).
The quote is an *Angebot* (net, pre-checkout) → net note, no invented VAT; the
order is an *Auftragsbestätigung* → the full §14 block from stored data.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .buyer_portal import (
    DisplaySettings,
    PreparerDisplay,
    TotalDisplay,
    build_buyer_payload,
)
from .quote_settings import load_quote_settings
from .tax import to_minor_units
from .vat_service import format_money

if TYPE_CHECKING:  # avoid heavy/ORM imports at module load
    from sqlalchemy.ext.asyncio import AsyncSession

    from .models import Order, Organization, Quote
    from .storage import ObjectStorage

# Neutral fallback accent when the org has set no brand colour — deliberately
# NOT a Tolera colour (white-label; the document must carry no platform identity).
DEFAULT_ACCENT = "#1f2937"

# The accent colour is interpolated into a CSS ``<style>`` context, where Jinja's
# HTML autoescaping does NOT protect (it escapes ``<>&'"`` but not ``{ } ; :``).
# So it is validated to a strict hex literal here rather than trusted — anything
# else (incl. a CSS-injection payload) falls back to the neutral default. The
# M5.8 write path will validate on save too; this is defence at render time.
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _safe_accent(value: str | None) -> str:
    """A `#rgb`/`#rrggbb` accent, or the neutral default for anything else."""
    return value if value is not None and _HEX_COLOR.match(value) else DEFAULT_ACCENT


# Angebot ≠ Rechnung: a quote is a net, pre-checkout offer. The buyer's tax
# posture (reverse-charge / VIES) is unknown until checkout, so no §14 block is
# rendered on the quote — only this net notice (CLAUDE.md §6.4 never invent).
NET_NOTE = "Alle Preise verstehen sich netto zzgl. gesetzlicher MwSt."


@dataclass(frozen=True)
class QuoteContent:
    """The merge-content text blocks that print on the digital quote + PDF (spec
    :4197-4199). **Persistence is M5.8**; M5.4 renders them via
    :func:`load_quote_content`, whose defaults are empty (nothing invented)."""

    terms: str | None = None
    manufacturers_notes: str | None = None
    quote_notes: str | None = None


async def load_quote_content(session: AsyncSession, org_id: uuid.UUID) -> QuoteContent:
    """The org's quote merge content (T&Cs / Manufacturer's Notes / Quote Notes),
    backed by the persisted ``org_quote_settings`` row (M5.8) — an absent row
    resolves to empty defaults (nothing invented). Mirrors ``load_display_settings``."""
    qs = await load_quote_settings(session, org_id)
    return QuoteContent(
        terms=qs.terms,
        manufacturers_notes=qs.manufacturers_notes,
        quote_notes=qs.quote_notes,
    )


# --------------------------------------------------------------------------- #
# Jinja2 environment (autoescaped — quote/customer text is untrusted).
# --------------------------------------------------------------------------- #
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_document_html(ctx: dict[str, Any]) -> str:
    """Render a quote/order context dict to white-label HTML."""
    return _env.get_template("document.html").render(**ctx)


def weasyprint_available() -> bool:
    """True when WeasyPrint's native libs (pango/cairo) can be imported — the
    actual-PDF tests skip otherwise (mirrors the ``db_client`` DB-absent skip)."""
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def html_to_pdf(html: str) -> bytes:
    """Render HTML to A4 PDF bytes (WeasyPrint, lazy-imported)."""
    import weasyprint

    pdf: bytes = weasyprint.HTML(string=html).write_pdf()
    return pdf


# --------------------------------------------------------------------------- #
# Money / format helpers
# --------------------------------------------------------------------------- #
def _fmt_minor(minor: int | None, currency: str, locale: str) -> str | None:
    return None if minor is None else format_money(minor, currency, locale)


def _fmt_decimal(value: str | Decimal | None, currency: str, locale: str) -> str | None:
    """Format a decimal-string net amount (buyer payload money) in the locale."""
    if value is None:
        return None
    return format_money(to_minor_units(Decimal(str(value))), currency, locale)


def _fmt_pct(value: str | Decimal) -> str:
    """A VAT rate without trailing zeros or exponent notation: ``19`` / ``8.1``."""
    return format(Decimal(str(value)).normalize(), "f")


def _format_date(when: datetime) -> str:
    """German date TT.MM.JJJJ (DACH-DELTA §1)."""
    return when.strftime("%d.%m.%Y")


# --------------------------------------------------------------------------- #
# Shop / customer blocks
# --------------------------------------------------------------------------- #
def _shop_block(
    org: Organization, settings: DisplaySettings, logo_data_uri: str | None
) -> dict[str, Any]:
    return {
        "name": org.name,
        "address": org.facility_address,
        "phone": org.facility_phone if settings.show_facility_phone else None,
        "website": org.facility_website if settings.show_facility_website else None,
        "ust_id_nr": org.ust_id_nr,
        "accent_color": _safe_accent(org.brand_accent_color),
        "logo_data_uri": logo_data_uri,
    }


def _content_block(content: QuoteContent) -> dict[str, Any]:
    return {
        "terms": content.terms,
        "manufacturers_notes": content.manufacturers_notes,
        "quote_notes": content.quote_notes,
    }


def _gated_identity(item: dict[str, Any], settings: DisplaySettings, out: dict[str, Any]) -> None:
    """Copy the display-gated identity/spec fields common to quote + order lines.

    Gating is applied here (not trusted from the payload) so the builder is robust
    whether or not the caller pre-gated — production ``build_buyer_payload`` gates
    with the same settings, so this is idempotent."""
    if settings.show_part_number and item.get("part_number"):
        out["part_number"] = item["part_number"]
    if settings.show_revision and item.get("revision"):
        out["revision"] = item["revision"]
    if settings.show_description and item.get("description"):
        out["description"] = item["description"]
    if settings.show_process and item.get("process"):
        out["process"] = item["process"]
    if settings.show_material and item.get("material"):
        out["material"] = item["material"]
        out["werkstoffnummer"] = item.get("werkstoffnummer")
    if settings.show_dimensions and item.get("dimensions"):
        out["dimensions"] = item["dimensions"]
    if settings.show_dfm and item.get("dfm_warnings"):
        out["dfm_warnings"] = item["dfm_warnings"]


# --------------------------------------------------------------------------- #
# Quote context
# --------------------------------------------------------------------------- #
def _quote_line(
    li: dict[str, Any],
    currency: str,
    locale: str,
    settings: DisplaySettings,
    file_names: dict[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "position": li["position"],
        "is_no_quote": bool(li.get("is_no_quote")),
    }
    _gated_identity(li, settings, out)
    if settings.show_part_file_name:
        fn = file_names.get(str(li.get("quote_item_id")))
        if fn:
            out["file_name"] = fn
    out["breaks"] = [
        {
            "quantity": b["quantity"],
            "unit_price": _fmt_decimal(b.get("unit_price"), currency, locale),
            "total_price": _fmt_decimal(b.get("total_price"), currency, locale),
            "lead_time_days": b.get("lead_time_days"),
        }
        for b in li.get("breaks", [])
    ]
    add_ons: list[dict[str, Any]] = []
    for a in li.get("add_ons", []):
        prices = a.get("prices") or []
        price = prices[0].get("price") if prices else None
        add_ons.append(
            {
                "display_name": a["display_name"],
                "is_required": bool(a.get("is_required")),
                "price": _fmt_decimal(price, currency, locale),
            }
        )
    out["add_ons"] = add_ons
    return out


def _quote_total(
    price_range: dict[str, str] | None,
    mode: TotalDisplay,
    currency: str,
    locale: str,
) -> dict[str, Any]:
    """The document total per the total-display radio. Reuses the buyer portal's
    min/max **unit** range (never a recompute); ``none`` prints nothing."""
    if mode is TotalDisplay.none or not price_range:
        return {"mode": "none"}
    min_u = _fmt_decimal(price_range.get("min_unit"), currency, locale)
    max_u = _fmt_decimal(price_range.get("max_unit"), currency, locale)
    if mode is TotalDisplay.maximum_price:
        return {"mode": "maximum_price", "value": max_u}
    return {"mode": "price_range", "min": min_u, "max": max_u}


def build_quote_context(
    *,
    org: Organization,
    payload: dict[str, Any],
    settings: DisplaySettings,
    content: QuoteContent,
    document_date: str,
    logo_data_uri: str | None,
    file_names: dict[str, str],
    preparers: list[dict[str, Any]] | None,
    digital_quote_link: str | None,
) -> dict[str, Any]:
    """Assemble the render context for a **quote** (Angebot) from a buyer payload."""
    currency = payload.get("currency") or org.currency
    locale = org.locale
    line_items = [
        _quote_line(li, currency, locale, settings, file_names)
        for li in payload.get("line_items", [])
    ]
    return {
        "kind": "quote",
        "doc_title": "Angebot",
        "number_label": "Angebotsnummer",
        "document_number": (payload.get("quote_number") if settings.show_quote_number else None),
        "document_date": document_date,
        "rfq_number": (payload.get("rfq_number") if settings.show_rfq_number else None),
        "po_number": None,
        "shop": _shop_block(org, settings, logo_data_uri),
        "customer": None,
        "line_items": line_items,
        "total": _quote_total(payload.get("price_range"), settings.total_display, currency, locale),
        "preparers": preparers or [],
        "notes_placement": settings.notes_placement.value,
        "content": _content_block(content),
        "net_note": NET_NOTE,
        "tax": None,
        "digital_quote_link": (digital_quote_link if settings.show_digital_quote_link else None),
        "currency": currency,
    }


# --------------------------------------------------------------------------- #
# Order context
# --------------------------------------------------------------------------- #
def _order_line(
    line: dict[str, Any],
    currency: str,
    locale: str,
    settings: DisplaySettings,
) -> dict[str, Any]:
    out: dict[str, Any] = {"position": line["position"], "is_no_quote": False}
    _gated_identity(line, settings, out)
    if settings.show_part_file_name and line.get("file_name"):
        out["file_name"] = line["file_name"]
    out["breaks"] = [
        {
            "quantity": line["quantity"],
            "unit_price": _fmt_minor(line.get("unit_price_minor"), currency, locale),
            "total_price": _fmt_minor(line.get("total_price_minor"), currency, locale),
            "lead_time_days": line.get("lead_time_days"),
        }
    ]
    out["add_ons"] = [
        {
            "display_name": a["name"],
            "is_required": bool(a.get("required")),
            "price": _fmt_minor(a.get("price_minor"), currency, locale),
        }
        for a in line.get("add_ons", [])
    ]
    return out


def _order_tax(order: Order, currency: str, locale: str) -> dict[str, Any]:
    rate_lines = [
        {
            "rate_pct": _fmt_pct(rl["rate_pct"]),
            "net": _fmt_minor(rl["net_minor"], currency, locale),
            "vat": _fmt_minor(rl["vat_minor"], currency, locale),
        }
        for rl in (order.tax_rate_lines or [])
    ]
    return {
        "net": _fmt_minor(order.net_minor, currency, locale),
        "vat": _fmt_minor(order.vat_minor, currency, locale),
        "gross": _fmt_minor(order.gross_minor, currency, locale),
        "vat_rate_pct": _fmt_pct(order.vat_rate_pct),
        "vat_label": order.vat_label or "MwSt.",
        "reverse_charge": order.reverse_charge,
        "kleinunternehmer": order.kleinunternehmer,
        "note": order.tax_note,
        "supplier_ust_id_nr": order.supplier_ust_id_nr,
        "buyer_ust_id_nr": order.buyer_ust_id_nr,
        "rate_lines": rate_lines,
    }


def _order_customer(order: Order) -> dict[str, Any] | None:
    if not order.company_name and not order.billing_address:
        return None
    return {"name": order.company_name, "address": order.billing_address}


def build_order_context(
    *,
    org: Organization,
    order: Order,
    lines: list[dict[str, Any]],
    settings: DisplaySettings,
    content: QuoteContent,
    document_date: str,
    logo_data_uri: str | None,
    preparers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the render context for an **order confirmation** (Auftragsbestätigung)
    — the §14-UStG document, rendered from the Order's persisted tax breakdown."""
    currency = order.currency
    locale = org.locale
    return {
        "kind": "order",
        "doc_title": "Auftragsbestätigung",
        "number_label": "Auftragsnummer",
        "document_number": order.number,
        "document_date": document_date,
        "rfq_number": None,
        "po_number": order.po_number,
        "shop": _shop_block(org, settings, logo_data_uri),
        "customer": _order_customer(order),
        "line_items": [_order_line(line, currency, locale, settings) for line in lines],
        "total": {"mode": "none"},
        "preparers": preparers or [],
        "notes_placement": settings.notes_placement.value,
        "content": _content_block(content),
        "net_note": None,
        "tax": _order_tax(order, currency, locale),
        "digital_quote_link": None,
        "currency": currency,
    }


# --------------------------------------------------------------------------- #
# Logo → inline data-URI (no external asset; spec :603 CSP-clean)
# --------------------------------------------------------------------------- #
async def logo_data_uri(storage: ObjectStorage, key: str | None) -> str | None:
    """Fetch the org logo from object storage and inline it as a ``data:`` URI.

    Returns ``None`` if there is no key or the blob can't be read (a missing logo
    must never break the render — the document falls back to the shop name)."""
    if not key:
        return None
    try:
        chunks = [chunk async for chunk in storage.stream(key)]
    except Exception:
        return None
    data = b"".join(chunks)
    if not data:
        return None
    mime = mimetypes.guess_type(key)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


# --------------------------------------------------------------------------- #
# ORM assembly — DB → context (used by the download endpoints)
# --------------------------------------------------------------------------- #
async def _quote_file_names(session: AsyncSession, quote: Quote) -> dict[str, str]:
    """Map each line item's ``quote_item_id`` → its part's primary file name (for
    the Part-File-Name toggle). Only the primary file; supporting files are not
    named on the customer document."""
    from sqlalchemy import select

    from .models import Component, Part, PartFile, QuoteItem

    rows = (
        await session.execute(
            select(QuoteItem.id, PartFile.filename)
            .join(
                Component,
                (Component.id == QuoteItem.root_component_id)
                & (Component.org_id == QuoteItem.org_id),
            )
            .join(Part, (Part.id == Component.part_id) & (Part.org_id == Component.org_id))
            .join(
                PartFile,
                (PartFile.id == Part.primary_file_id) & (PartFile.org_id == Part.org_id),
            )
            # RLS already scopes the session; the explicit org predicate is
            # defence-in-depth (the codebase's double-scoping convention).
            .where(QuoteItem.quote_id == quote.id, QuoteItem.org_id == quote.org_id)
        )
    ).all()
    return {str(qi_id): filename for qi_id, filename in rows}


async def _order_lines(session: AsyncSession, order: Order) -> list[dict[str, Any]]:
    """Load the order's lines with part identity for the confirmation document,
    ordered by the underlying quote-item position."""
    from sqlalchemy import select

    from .models import (
        Component,
        Material,
        OrderLine,
        Part,
        Process,
        QuoteItem,
    )

    rows = (
        await session.execute(
            select(OrderLine, QuoteItem, Part, Process, Material)
            .join(
                QuoteItem,
                (QuoteItem.id == OrderLine.quote_item_id) & (QuoteItem.org_id == OrderLine.org_id),
            )
            .join(
                Component,
                (Component.id == OrderLine.component_id) & (Component.org_id == OrderLine.org_id),
            )
            .join(Part, (Part.id == Component.part_id) & (Part.org_id == Component.org_id))
            .outerjoin(
                Process, (Process.id == Component.process_id) & (Process.org_id == Component.org_id)
            )
            .outerjoin(
                Material,
                (Material.id == Component.material_id) & (Material.org_id == Component.org_id),
            )
            # Explicit org predicate = defence-in-depth alongside RLS.
            .where(OrderLine.order_id == order.id, OrderLine.org_id == order.org_id)
            .order_by(QuoteItem.position)
        )
    ).all()
    lines: list[dict[str, Any]] = []
    for position, (ol, _qi, part, proc, mat) in enumerate(rows, start=1):
        lines.append(
            {
                "position": position,
                "part_number": part.part_number,
                "revision": part.revision,
                "description": part.description,
                "process": (proc.external_name or proc.name) if proc is not None else None,
                "material": mat.display_name if mat is not None else None,
                "werkstoffnummer": mat.werkstoffnummer if mat is not None else None,
                "quantity": ol.quantity,
                "unit_price_minor": ol.unit_price_minor,
                "total_price_minor": ol.total_price_minor,
                "lead_time_days": ol.lead_time_days,
                "ships_on": ol.ships_on.isoformat() if ol.ships_on is not None else None,
                "add_ons": ol.add_ons or [],
            }
        )
    return lines


async def _resolve_preparers(
    session: AsyncSession, quote: Quote, settings: DisplaySettings
) -> list[dict[str, Any]]:
    """The quote's preparer contact block(s) per the Preparer & Contact radio
    (Salesperson / Estimator / Both). Identities come through ``app_org_members()``
    — the scoped ``SECURITY DEFINER`` view (M0.2) the restricted role must use for
    ``app_user`` (a direct read is ``permission denied``); a person who is both
    salesperson and estimator is shown once."""
    wants_sales = settings.preparer in (PreparerDisplay.salesperson, PreparerDisplay.both)
    wants_est = settings.preparer in (PreparerDisplay.estimator, PreparerDisplay.both)
    entries: list[tuple[str, uuid.UUID]] = []
    if wants_sales and quote.salesperson_id is not None:
        entries.append(("Vertrieb", quote.salesperson_id))
    if wants_est and quote.estimator_id is not None:
        entries.append(("Kalkulation", quote.estimator_id))
    if not entries:
        return []

    from sqlalchemy import text

    raw = (await session.execute(text("SELECT app_org_members()"))).scalar_one()
    members = json.loads(raw) if isinstance(raw, str) else raw
    by_id = {str(m["id"]): m for m in (members or [])}

    out: list[dict[str, Any]] = []
    seen: set[uuid.UUID] = set()
    for label, user_id in entries:
        if user_id in seen:
            continue
        seen.add(user_id)
        member = by_id.get(str(user_id))
        if member is None:
            continue
        name = f"{member.get('first_name') or ''} {member.get('last_name') or ''}".strip() or None
        out.append({"label": label, "name": name, "email": member.get("email"), "phone": None})
    return out


async def assemble_quote_context(
    session: AsyncSession,
    org: Organization,
    quote: Quote,
    settings: DisplaySettings,
    content: QuoteContent,
    storage: ObjectStorage,
    now: datetime,
    *,
    digital_quote_link: str | None = None,
) -> dict[str, Any]:
    """Build the quote render context straight from the DB (buyer projection +
    branding + optional file names + resolved preparer)."""
    quote_settings = await load_quote_settings(session, org.id)
    payload = await build_buyer_payload(session, org, quote, settings, quote_settings, now)
    file_names = await _quote_file_names(session, quote) if settings.show_part_file_name else {}
    logo = await logo_data_uri(storage, org.logo_object_key)
    preparers = await _resolve_preparers(session, quote, settings)
    return build_quote_context(
        org=org,
        payload=payload,
        settings=settings,
        content=content,
        document_date=_format_date(now),
        logo_data_uri=logo,
        file_names=file_names,
        preparers=preparers,
        digital_quote_link=digital_quote_link,
    )


async def assemble_order_context(
    session: AsyncSession,
    org: Organization,
    order: Order,
    settings: DisplaySettings,
    content: QuoteContent,
    storage: ObjectStorage,
) -> dict[str, Any]:
    """Build the order-confirmation render context from the persisted Order (the
    preparer contact is resolved from the order's originating quote)."""
    from .models import Quote as QuoteModel

    lines = await _order_lines(session, order)
    logo = await logo_data_uri(storage, org.logo_object_key)
    quote = await session.get(QuoteModel, order.quote_id)
    preparers = await _resolve_preparers(session, quote, settings) if quote is not None else []
    return build_order_context(
        org=org,
        order=order,
        lines=lines,
        settings=settings,
        content=content,
        document_date=_format_date(order.created_at),
        logo_data_uri=logo,
        preparers=preparers,
    )
