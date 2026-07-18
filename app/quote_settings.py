"""Per-org **Finalized Quote Settings** accessor (spec ``#digital-quote-settings``;
M5.8) — the single read/write seam over :class:`~app.models.OrgQuoteSettings`.

Mirrors :mod:`app.ai_settings`: a **direct DB read** (no cache), and an **absent
row is treated as all-defaults** so an org provisioned before the default-row
insert never silently changes behaviour. This one row backs the Display Settings
+ quote merge content that the buyer portal (M5.1) and PDF (M5.4) already read
through their own seams (``load_display_settings`` / ``load_quote_content``),
plus the Requotes / Checkout / Lead-Time / notification toggles M5.8 adds.

The dataclass carries the persisted values *flat*; the enum-typed display radios
are kept as their string values here and mapped to the ``DisplaySettings`` enums
at the buyer-portal boundary (keeps this module free of a buyer_portal import,
so there is no cycle).
"""

from __future__ import annotations

import dataclasses
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import OrderShippingMethod, OrgQuoteSettings

#: The show_* Display-Settings toggles (mirror app.buyer_portal.DisplaySettings).
SHOW_FLAGS: tuple[str, ...] = (
    "show_part_number",
    "show_revision",
    "show_description",
    "show_process",
    "show_material",
    "show_dimensions",
    "show_dfm",
    "show_3d",
    "show_part_file_name",
    "show_thumbnail",
    "show_quote_number",
    "show_rfq_number",
    "show_facility_phone",
    "show_facility_website",
    "show_digital_quote_link",
)


@dataclasses.dataclass(frozen=True, slots=True)
class QuoteSettings:
    """A resolved snapshot of an org's Finalized Quote Settings (all defaults)."""

    # Display Settings — show_* toggles.
    show_part_number: bool = True
    show_revision: bool = True
    show_description: bool = True
    show_process: bool = True
    show_material: bool = True
    show_dimensions: bool = False
    show_dfm: bool = False
    show_3d: bool = True
    show_part_file_name: bool = False
    show_thumbnail: bool = False
    show_quote_number: bool = True
    show_rfq_number: bool = True
    show_facility_phone: bool = True
    show_facility_website: bool = True
    show_digital_quote_link: bool = True
    # Display Settings — radios (enum values; validated on write).
    total_display: str = "price_range"
    preparer: str = "salesperson"
    notes_placement: str = "above"

    # Quote merge content.
    terms: str | None = None
    manufacturers_notes: str | None = None
    quote_notes: str | None = None
    require_terms_acceptance: bool = False

    # Requotes (gates the M5.1 expired-state request button).
    requotes_enabled: bool = True

    # Checkout Settings (enforced server-side by app.checkout).
    allow_local_pickup: bool = True
    send_order_confirmation_emails: bool = True
    disabled_shipping_methods: tuple[str, ...] = ()

    # Lead-Time preference (v1 order math stays calendar days).
    lead_time_business_days: bool = True

    # Email Notification recipient matrix (consumed by M5.5/M5.2).
    notification_recipients: dict[str, Any] = dataclasses.field(default_factory=dict)

    # Accounting — informational only (never fed into the VAT engine).
    default_tax_rate_pct: Decimal | None = None


#: Reference all-defaults snapshot. NOTE: ``load_quote_settings`` returns a
#: *fresh* instance for a missing row, never this shared object — ``frozen=True``
#: does not freeze the nested ``notification_recipients`` dict, so sharing one
#: instance across orgs would let a mutation leak between tenants.
DEFAULT_QUOTE_SETTINGS = QuoteSettings()

#: Scalar fields copied straight from the ORM row (JSONB handled separately).
_SCALAR_FIELDS: tuple[str, ...] = (
    *SHOW_FLAGS,
    "total_display",
    "preparer",
    "notes_placement",
    "terms",
    "manufacturers_notes",
    "quote_notes",
    "require_terms_acceptance",
    "requotes_enabled",
    "allow_local_pickup",
    "send_order_confirmation_emails",
    "lead_time_business_days",
    "default_tax_rate_pct",
)


def _from_row(row: OrgQuoteSettings) -> QuoteSettings:
    values: dict[str, Any] = {name: getattr(row, name) for name in _SCALAR_FIELDS}
    # JSONB list → tuple (frozen dataclass); guard against a malformed value.
    disabled = row.disabled_shipping_methods or []
    values["disabled_shipping_methods"] = tuple(disabled) if isinstance(disabled, list) else ()
    recipients = row.notification_recipients or {}
    values["notification_recipients"] = dict(recipients) if isinstance(recipients, dict) else {}
    return QuoteSettings(**values)


async def load_quote_settings(session: AsyncSession, org_id: uuid.UUID) -> QuoteSettings:
    """The org's Finalized Quote Settings, or all-defaults when no row exists.

    Reads within the caller's org-scoped session (RLS already pins ``org_id``)."""
    row = (
        await session.scalars(select(OrgQuoteSettings).where(OrgQuoteSettings.org_id == org_id))
    ).one_or_none()
    if row is None:
        # A *fresh* snapshot — never the shared singleton, whose nested
        # notification_recipients dict is mutable (see DEFAULT_QUOTE_SETTINGS).
        return QuoteSettings()
    return _from_row(row)


async def get_or_create_row(session: AsyncSession, org_id: uuid.UUID) -> OrgQuoteSettings:
    """The org's ``org_quote_settings`` row, inserting an all-default one if absent.

    Used by the settings write endpoint (M5.8) — the accessor above still treats a
    never-written org as defaults, so this is only materialised on first save.

    The insert is an atomic ``ON CONFLICT DO NOTHING`` so two concurrent first
    saves for the same org cannot race on the primary key (one would otherwise
    raise on flush); the row is then loaded whether we or the other txn wrote it.
    RLS's ``WITH CHECK`` still pins ``org_id`` to the caller."""
    await session.execute(
        pg_insert(OrgQuoteSettings)
        .values(org_id=org_id)
        .on_conflict_do_nothing(index_elements=[OrgQuoteSettings.org_id])
    )
    row = (
        await session.scalars(select(OrgQuoteSettings).where(OrgQuoteSettings.org_id == org_id))
    ).one()
    return row


def offered_shipping_methods(qs: QuoteSettings) -> list[str]:
    """The checkout fulfilment options this org offers, in enum order — the full
    :class:`~app.models.OrderShippingMethod` set minus the ones disabled in
    Checkout Settings, and ``local_pickup`` only when "Allow Local Pickup" is on.

    This is the single source the buyer portal renders and the checkout endpoint
    enforces against, so a disabled option cannot be submitted (the client list is
    display; the server re-checks — CLAUDE.md §5)."""
    disabled = set(qs.disabled_shipping_methods)
    out: list[str] = []
    for method in OrderShippingMethod:
        if method.value in disabled:
            continue
        if method is OrderShippingMethod.local_pickup and not qs.allow_local_pickup:
            continue
        out.append(method.value)
    return out
