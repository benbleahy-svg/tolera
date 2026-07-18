"""Email Template CRUD (M5.5).

Spec ``#settings`` Email Templates (DemoH 08): per-type templates —
``quote_send`` / ``order_shipment`` / ``order_refund`` — each with a display
``name`` and an optional DEFAULT flag. At most one default per type + locale (a
partial unique index); promoting a template to default unseats the previous one,
and the current default is protected from deletion (the greyed trash in DemoH 08).

Reads are ``view_all`` (the send composer's template picker is available to every
estimator); mutations are ``settings_edit`` (an admin/settings action). Org
isolation is enforced at the DB by RLS — a foreign-org id simply 404s.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import EmailTemplate, EmailTemplateType

email_templates_router = APIRouter(prefix="/api/email-templates", tags=["email-templates"])

_DEFAULT_LOCALE = "de-DE"


class EmailTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_type: EmailTemplateType
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=100_000)
    is_default: bool = False
    locale: str = Field(default=_DEFAULT_LOCALE, min_length=2, max_length=20)


class EmailTemplateUpdate(BaseModel):
    """Partial edit — only the fields present change.

    Fields are ``| None`` to model *omission* (partial update), NOT to accept an
    explicit ``null``: every target column is NOT NULL, so a supplied ``null`` must
    be a 422, never a NULL write via ``exclude_unset``."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, max_length=100_000)
    is_default: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            fields = ("name", "subject", "body", "is_default")
            nulled = [k for k in fields if data.get(k, ...) is None]
            if nulled:
                raise ValueError(f"Fields may not be null: {', '.join(sorted(nulled))}")
        return data


class EmailTemplateOut(BaseModel):
    id: uuid.UUID
    template_type: EmailTemplateType
    name: str
    subject: str
    body: str
    is_default: bool
    locale: str
    #: The editor's email (DemoH 08 "Last edited by") — resolved from the id via
    #: the org-scoped ``app_org_members()`` view; NULL for seeded rows or a user no
    #: longer in the org.
    last_edited_by: str | None
    updated_at: datetime


async def _editor_emails(session: AsyncSession) -> dict[str, str]:
    """user-id → email for the active org's members (the RLS-safe ``app_org_members()``
    view — the restricted role cannot read ``app_user`` directly)."""
    raw = (await session.execute(text("SELECT app_org_members()"))).scalar_one()
    members = json.loads(raw) if isinstance(raw, str) else raw
    return {str(m["id"]): m["email"] for m in (members or []) if m.get("email")}


def _out(row: EmailTemplate, editor_emails: dict[str, str]) -> EmailTemplateOut:
    return EmailTemplateOut(
        id=row.id,
        template_type=row.template_type,
        name=row.name,
        subject=row.subject,
        body=row.body,
        is_default=row.is_default,
        locale=row.locale,
        last_edited_by=(
            editor_emails.get(str(row.last_edited_by)) if row.last_edited_by is not None else None
        ),
        updated_at=row.updated_at,
    )


async def _get_or_404(session: AsyncSession, template_id: uuid.UUID) -> EmailTemplate:
    row = await session.get(EmailTemplate, template_id)
    if row is None:
        raise AppError("template_not_found", "E-Mail-Vorlage nicht gefunden.", status_code=404)
    return row


async def _clear_defaults(
    session: AsyncSession,
    org_id: uuid.UUID,
    template_type: EmailTemplateType,
    locale: str,
    *,
    keep_id: uuid.UUID | None = None,
) -> None:
    """Unset the current default of this (type, locale) — run BEFORE the new
    default is flushed, so the partial unique index (one default per type) is
    never momentarily violated. ``keep_id`` spares an already-persisted row."""
    stmt = update(EmailTemplate).where(
        EmailTemplate.org_id == org_id,
        EmailTemplate.template_type == template_type,
        EmailTemplate.locale == locale,
        EmailTemplate.is_default.is_(True),
    )
    if keep_id is not None:
        stmt = stmt.where(EmailTemplate.id != keep_id)
    # synchronize_session=False: this is a blind bulk flag-flip; the ORM identity
    # map is not consulted (avoids a sync-time lazy load), and the row we keep is
    # written by its own ORM flush right after.
    await session.execute(
        stmt.values(is_default=False).execution_options(synchronize_session=False)
    )
    await session.flush()


@email_templates_router.get("")
async def list_templates(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    template_type: Annotated[EmailTemplateType | None, Query()] = None,
) -> list[EmailTemplateOut]:
    """List the org's templates (optionally one type), grouped by type then
    default-first then name — the order the settings page + composer render."""
    stmt = select(EmailTemplate)
    if template_type is not None:
        stmt = stmt.where(EmailTemplate.template_type == template_type)
    stmt = stmt.order_by(
        EmailTemplate.template_type,
        EmailTemplate.is_default.desc(),
        EmailTemplate.name,
    )
    rows = list((await session.execute(stmt)).scalars())
    emails = await _editor_emails(session)
    return [_out(row, emails) for row in rows]


@email_templates_router.post("", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: EmailTemplateCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.settings_edit))],
) -> EmailTemplateOut:
    # Clear the current default FIRST — the new row is flushed as default next, and
    # the partial unique index (one default per type) must never be double-occupied.
    if payload.is_default:
        await _clear_defaults(
            session, principal.active_org_id, payload.template_type, payload.locale
        )
    row = EmailTemplate(
        org_id=principal.active_org_id,
        template_type=payload.template_type,
        name=payload.name,
        subject=payload.subject,
        body=payload.body,
        is_default=payload.is_default,
        locale=payload.locale,
        last_edited_by=principal.user_id,
    )
    session.add(row)
    await session.flush()
    return _out(row, await _editor_emails(session))


@email_templates_router.get("/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> EmailTemplateOut:
    row = await _get_or_404(session, template_id)
    return _out(row, await _editor_emails(session))


@email_templates_router.patch("/{template_id}")
async def update_template(
    template_id: uuid.UUID,
    payload: EmailTemplateUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.settings_edit))],
) -> EmailTemplateOut:
    row = await _get_or_404(session, template_id)
    changes = payload.model_dump(exclude_unset=True)
    # Promote-to-default: unseat the current default (other than this row) BEFORE
    # this row's is_default=true is flushed, so the partial unique index holds.
    if changes.get("is_default"):
        await _clear_defaults(session, row.org_id, row.template_type, row.locale, keep_id=row.id)
    for field, value in changes.items():
        setattr(row, field, value)
    row.last_edited_by = principal.user_id
    await session.flush()
    # The default-clearing bulk UPDATE expired the identity map; refresh so the
    # response reads server-set columns (updated_at) without a sync lazy-load.
    await session.refresh(row)
    return _out(row, await _editor_emails(session))


@email_templates_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.settings_edit))],
) -> Response:
    row = await _get_or_404(session, template_id)
    if row.is_default:
        # The default's trash is greyed in DemoH 08 — promote another first.
        raise AppError(
            "default_template_protected",
            "Die Standardvorlage kann nicht gelöscht werden. "
            "Legen Sie zuerst eine andere Vorlage als Standard fest.",
            status_code=status.HTTP_409_CONFLICT,
        )
    await session.delete(row)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
