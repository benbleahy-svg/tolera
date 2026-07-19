"""Legal Impressum footer for customer-facing PDFs + quote emails (M5.9).

``DACH-DELTA §Email/§37`` requires every customer-facing document to carry a legal
Impressum: the shop's legal name, address, commercial-register entry
(Handelsregister — DE HRB / AT Firmenbuch / CH HR) and USt-IdNr. The DE
Impressumspflicht lives in **§5 DDG** (Digitale-Dienste-Gesetz — successor to the
TMG since 2024-05-14); the USt-IdNr is additionally a §14 UStG invoice field.

de-DE labels only — de-CH/de-AT *language* variants are post-pilot
(``DACH-DELTA §8.6``); the register is stored free-text so a single label stays
DACH-generic. Every line renders **only when its source field is present** — an
absent register or VAT-ID is omitted, never invented (CLAUDE.md §5 "never
hallucinate"). The footer as a whole is suppressed unless a commercial register
**or** a USt-IdNr is set, so a bare org renders nothing (no empty Impressum).
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Protocol, TypedDict

#: de-DE footer labels. Kept here (not the i18n catalog) because the Impressum is
#: assembled server-side for the PDF/email footer, always in the pilot's de-DE.
HEADING = "Impressum"
REGISTER_LABEL = "Handelsregister"
UST_ID_LABEL = "USt-IdNr."


class OrgIdentity(Protocol):
    """The subset of ``Organization`` the Impressum reads. Read-only properties so
    the protocol is covariant — a concrete ``Organization.name: str`` satisfies the
    ``str | None`` here (a mutable attribute would be invariant and reject it)."""

    @property
    def name(self) -> str | None: ...
    @property
    def facility_address(self) -> str | None: ...
    @property
    def commercial_register(self) -> str | None: ...
    @property
    def ust_id_nr(self) -> str | None: ...


@dataclass(frozen=True)
class ImpressumLine:
    """One footer line. ``label`` is ``None`` for the plain name/address lines and
    the de-DE label (``Handelsregister``/``USt-IdNr.``) for the register/VAT-ID."""

    value: str
    label: str | None = None


def impressum_lines(org: OrgIdentity) -> list[ImpressumLine]:
    """The Impressum footer lines in render order.

    Empty when neither a commercial register nor a USt-IdNr is set — a name +
    address alone is not a legal Impressum, so no heading is emitted."""
    name = getattr(org, "name", None)
    address = getattr(org, "facility_address", None)
    register = getattr(org, "commercial_register", None)
    ust_id = getattr(org, "ust_id_nr", None)
    if not (register or ust_id):
        return []
    lines: list[ImpressumLine] = []
    if name:
        lines.append(ImpressumLine(name))
    if address:
        lines.append(ImpressumLine(address))
    if register:
        lines.append(ImpressumLine(register, REGISTER_LABEL))
    if ust_id:
        lines.append(ImpressumLine(ust_id, UST_ID_LABEL))
    return lines


def impressum_footer_html(org: OrgIdentity) -> str:
    """Trusted HTML Impressum block for the quote-email footer; ``''`` when
    suppressed. Values are HTML-escaped and newlines become ``<br>`` — the footer
    is a non-injection sink regardless of the (org-config) source."""
    lines = impressum_lines(org)
    if not lines:
        return ""
    parts = [f'<p style="margin:0 0 4px;font-weight:bold;">{escape(HEADING)}</p>']
    for line in lines:
        text = escape(line.value).replace("\n", "<br>")
        if line.label:
            parts.append(f'<p style="margin:0;">{escape(line.label)}: {text}</p>')
        else:
            parts.append(f'<p style="margin:0;">{text}</p>')
    body = "".join(parts)
    return (
        '<hr style="border:none;border-top:1px solid #ccc;margin:16px 0 8px;">'
        f'<div style="color:#666;font-size:11px;line-height:1.4;">{body}</div>'
    )


class ImpressumLineOut(TypedDict):
    label: str | None
    value: str


class LegalBlock(TypedDict):
    """The legal footer's JSON shape, typed so portal callers and tests get real
    field types instead of ``object``."""

    heading: str
    impressum: list[ImpressumLineOut]
    privacy_policy_url: str | None


def legal_block(org: OrgIdentity) -> LegalBlock:
    """The legal footer as **structured data** for an API payload (M6.9).

    DACH-DELTA §5 requires Impressum + Datenschutzerklärung on all customer- and
    vendor-facing surfaces. M5.9 covered the server-rendered ones (quote PDF,
    quote email) via :func:`impressum_footer_html`; the buyer and vendor portals
    are React, so they need the same facts as JSON rather than trusted HTML.

    Both parts render only when present — an org with no commercial register gets
    an empty ``impressum``, and one that has published no privacy policy gets a
    null ``privacy_policy_url``. Neither is ever invented (CLAUDE.md §6.4).
    """
    return {
        "heading": HEADING,
        "impressum": [{"label": line.label, "value": line.value} for line in impressum_lines(org)],
        "privacy_policy_url": getattr(org, "privacy_policy_url", None),
    }
