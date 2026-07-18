"""Finalized Quote Settings admin API (M5.8) — the Settings surface that persists
the org's :class:`~app.models.OrgQuoteSettings` row.

Spec ``#digital-quote-settings`` + ``#company-settings-detail``. Reads are
``view_all`` (any member may see how quotes are configured); writes are
``settings_edit`` (admin/manager — the same gate as Email Templates). Org
isolation is enforced by RLS on ``org_quote_settings``; the row is get-or-created
on first write, so a never-configured org reads all-defaults without a row.

The write is a **partial** update (only supplied fields change). The three
display radios and the shipping-method list are validated against their enums by
Pydantic; ``default_tax_rate_pct`` is bounded and is **informational only** — it
never enters the VAT engine (§14-UStG resolution is legally computed, not a
preference; CLAUDE.md §5)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .buyer_portal import NotesPlacement, PreparerDisplay, TotalDisplay
from .deps import get_session
from .models import OrderShippingMethod
from .quote_settings import get_or_create_row, load_quote_settings

quote_settings_router = APIRouter(prefix="/api/settings/quote", tags=["settings"])

#: The recipient keys the Email-Notification matrix accepts (spec Email
#: Notification Settings). Unknown keys are rejected; a key may be null (unset).
_NOTIFICATION_KEYS = frozenset(
    {
        "quote_send_bcc",
        "order_confirmation",
        "requote_request",
        "smartrfq_received",
        "email_fwd_received",
    }
)

#: Update fields whose column is NOT NULL — a supplied explicit ``null`` is a 422
#: (module-level so it is not mistaken for a Pydantic private attribute).
_NON_NULLABLE_FIELDS = (
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
    "total_display",
    "preparer",
    "notes_placement",
    "require_terms_acceptance",
    "requotes_enabled",
    "allow_local_pickup",
    "send_order_confirmation_emails",
    "disabled_shipping_methods",
    "lead_time_business_days",
    "notification_recipients",
)


class QuoteSettingsOut(BaseModel):
    """The org's Finalized Quote Settings (current row, or all-defaults)."""

    model_config = ConfigDict(from_attributes=True)

    # Display Settings — show_* toggles.
    show_part_number: bool
    show_revision: bool
    show_description: bool
    show_process: bool
    show_material: bool
    show_dimensions: bool
    show_dfm: bool
    show_3d: bool
    show_part_file_name: bool
    show_thumbnail: bool
    show_quote_number: bool
    show_rfq_number: bool
    show_facility_phone: bool
    show_facility_website: bool
    show_digital_quote_link: bool
    total_display: TotalDisplay
    preparer: PreparerDisplay
    notes_placement: NotesPlacement
    # Quote merge content.
    terms: str | None
    manufacturers_notes: str | None
    quote_notes: str | None
    require_terms_acceptance: bool
    # Requotes + Checkout Settings.
    requotes_enabled: bool
    allow_local_pickup: bool
    send_order_confirmation_emails: bool
    disabled_shipping_methods: list[OrderShippingMethod]
    # Lead-Time + notifications + accounting.
    lead_time_business_days: bool
    notification_recipients: dict[str, Any]
    default_tax_rate_pct: Decimal | None


class QuoteSettingsUpdate(BaseModel):
    """Partial edit — only supplied fields change. ``| None`` models *omission*;
    fields whose column is NOT NULL reject an explicit ``null`` (a 422, not a
    NULL write) while the genuinely-nullable text/rate fields accept it."""

    model_config = ConfigDict(extra="forbid")

    show_part_number: bool | None = None
    show_revision: bool | None = None
    show_description: bool | None = None
    show_process: bool | None = None
    show_material: bool | None = None
    show_dimensions: bool | None = None
    show_dfm: bool | None = None
    show_3d: bool | None = None
    show_part_file_name: bool | None = None
    show_thumbnail: bool | None = None
    show_quote_number: bool | None = None
    show_rfq_number: bool | None = None
    show_facility_phone: bool | None = None
    show_facility_website: bool | None = None
    show_digital_quote_link: bool | None = None
    total_display: TotalDisplay | None = None
    preparer: PreparerDisplay | None = None
    notes_placement: NotesPlacement | None = None
    # Nullable text content (explicit null clears it).
    terms: str | None = Field(default=None, max_length=100_000)
    manufacturers_notes: str | None = Field(default=None, max_length=100_000)
    quote_notes: str | None = Field(default=None, max_length=100_000)
    require_terms_acceptance: bool | None = None
    requotes_enabled: bool | None = None
    allow_local_pickup: bool | None = None
    send_order_confirmation_emails: bool | None = None
    disabled_shipping_methods: list[OrderShippingMethod] | None = None
    lead_time_business_days: bool | None = None
    notification_recipients: dict[str, str | None] | None = None
    # Nullable, informational (explicit null clears it); a plausible VAT bound.
    default_tax_rate_pct: Decimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            nulled = [k for k in _NON_NULLABLE_FIELDS if data.get(k, ...) is None]
            if nulled:
                raise ValueError(f"Fields may not be null: {', '.join(sorted(nulled))}")
        return data

    @model_validator(mode="after")
    def _validate_notification_keys(self) -> QuoteSettingsUpdate:
        if self.notification_recipients is not None:
            unknown = set(self.notification_recipients) - _NOTIFICATION_KEYS
            if unknown:
                raise ValueError(f"Unknown notification keys: {', '.join(sorted(unknown))}")
        return self


def _serialise(qs: Any) -> QuoteSettingsOut:
    """Build the response from the resolved dataclass snapshot."""
    payload = {
        name: getattr(qs, name)
        for name in QuoteSettingsOut.model_fields
        if name != "disabled_shipping_methods"
    }
    payload["disabled_shipping_methods"] = list(qs.disabled_shipping_methods)
    return QuoteSettingsOut(**payload)


@quote_settings_router.get("")
async def get_quote_settings(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> QuoteSettingsOut:
    """The org's Finalized Quote Settings (all-defaults when never configured)."""
    org_id = _principal.active_org_id
    return _serialise(await load_quote_settings(session, org_id))


@quote_settings_router.put("")
async def update_quote_settings(
    body: QuoteSettingsUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.settings_edit))],
) -> QuoteSettingsOut:
    """Persist a partial edit to the org's Finalized Quote Settings. The row is
    created on first write; RLS pins it to the caller's org."""
    row = await get_or_create_row(session, principal.active_org_id)
    for name, value in body.model_dump(exclude_unset=True).items():
        if name == "disabled_shipping_methods" and value is not None:
            # Persist the enum values (JSONB list of strings), de-duplicated.
            value = sorted({OrderShippingMethod(v).value for v in value})
        setattr(row, name, value)
    await session.flush()
    return _serialise(await load_quote_settings(session, principal.active_org_id))
