"""Send-from-user + the quote communications timeline (M3.5).

Spec ``#email-connectivity``: "Quotes are sent from the estimator's own email
address" — ``POST /quotes/{id}/emails`` sends via the caller's PRIMARY
connection, captures the minted Message-ID + provider thread id onto
``quote_email_thread`` (first send creates the row), and stores the outbound
``email_message``. Follow-ups carry RFC 2822 ``In-Reply-To``/``References`` so
the customer's mail client threads them too.

``GET /quotes/{id}/emails`` is the unified communications timeline — every
message on the quote's thread, both directions, in order.

The full send-quote composer (templates, quote PDF, platform-address fallback
banner) is M5 (build-plan M3.5 scope-out); this is the minimal vertical slice
the reply-sync round-trip needs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .accounts import _normalize_email
from .auth import Principal
from .authz import Permission, require
from .config import Settings
from .deps import get_app_settings, get_session
from .email_crypto import decrypt_credentials
from .email_providers import OutboundEmail, get_provider
from .errors import AppError
from .models import (
    EmailDirection,
    EmailMessage,
    Quote,
    QuoteEmailThread,
    UserEmailConnection,
)

router = APIRouter(prefix="/quotes/{quote_id}/emails", tags=["email-threads"])


class EmailMessageOut(BaseModel):
    """One communications-timeline entry."""

    id: uuid.UUID
    direction: EmailDirection
    from_address: str
    to_addresses: list[str]
    subject: str | None
    body_text: str | None
    body_html: str | None
    attachments: list[dict[str, Any]]
    sent_at: datetime | None
    created_at: datetime


class SendEmailIn(BaseModel):
    """The minimal send-on-quote payload (composer/templates → M5)."""

    to: list[str] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=500)
    body_text: str = Field(min_length=1, max_length=100_000)

    @field_validator("to")
    @classmethod
    def _norm_recipients(cls, value: list[str]) -> list[str]:
        return [_normalize_email(addr) for addr in value]


def _out(row: EmailMessage) -> EmailMessageOut:
    return EmailMessageOut(
        id=row.id,
        direction=row.direction,
        from_address=row.from_address,
        to_addresses=row.to_addresses,
        subject=row.subject,
        body_text=row.body_text,
        body_html=row.body_html,
        # Metadata only — the payload lives in Object Storage.
        attachments=row.attachments,
        sent_at=row.sent_at,
        created_at=row.created_at,
    )


async def _quote_or_404(session: AsyncSession, quote_id: uuid.UUID) -> Quote:
    quote = await session.get(Quote, quote_id)
    if quote is None:
        raise AppError(
            "quote_not_found",
            "Angebot nicht gefunden.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return quote


@router.get("")
async def timeline(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[EmailMessageOut]:
    """The quote's communications timeline, oldest first."""
    await _quote_or_404(session, quote_id)
    thread_id = await session.scalar(
        select(QuoteEmailThread.id).where(QuoteEmailThread.quote_id == quote_id)
    )
    if thread_id is None:
        return []
    rows = await session.scalars(
        select(EmailMessage)
        .where(EmailMessage.thread_id == thread_id)
        .order_by(EmailMessage.created_at, EmailMessage.id)
    )
    return [_out(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def send_email(
    quote_id: uuid.UUID,
    payload: SendEmailIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> EmailMessageOut:
    """Send from the caller's own address (primary connection) and record the
    outbound message on the quote's thread."""
    await _quote_or_404(session, quote_id)
    connection = await session.scalar(
        select(UserEmailConnection).where(
            UserEmailConnection.user_id == principal.user_id,
            UserEmailConnection.is_primary,
        )
    )
    if connection is None:
        # The M5 composer adds the platform-address fallback banner; until
        # then the API states the requirement plainly.
        raise AppError(
            "no_email_connection",
            "Kein E-Mail-Konto verbunden. Verbinden Sie Ihr E-Mail-Konto, "
            "um vom eigenen Absender zu versenden.",
            status_code=status.HTTP_409_CONFLICT,
        )

    thread = await session.scalar(
        select(QuoteEmailThread).where(QuoteEmailThread.quote_id == quote_id)
    )
    in_reply_to: str | None = None
    references: list[str] = []
    if thread is not None:
        # Thread the follow-up under the first outbound (RFC 2822).
        references = [thread.sent_message_id]
        last_id = await session.scalar(
            select(EmailMessage.rfc_message_id)
            .where(EmailMessage.thread_id == thread.id, EmailMessage.rfc_message_id.is_not(None))
            .order_by(EmailMessage.created_at.desc(), EmailMessage.id.desc())
            .limit(1)
        )
        in_reply_to = last_id or thread.sent_message_id

    credentials = decrypt_credentials(
        settings.email_credentials_key, connection.encrypted_credentials
    )
    result = await get_provider(connection.connection_type).send(
        credentials,
        from_address=connection.from_address,
        from_name=connection.from_name,
        message=OutboundEmail(
            to=payload.to,
            subject=payload.subject,
            body_text=payload.body_text,
            in_reply_to=in_reply_to,
            references=references,
        ),
    )

    if thread is None:
        thread = QuoteEmailThread(
            org_id=principal.active_org_id,
            quote_id=quote_id,
            sent_message_id=result.message_id,
            provider_thread_id=result.provider_thread_id,
        )
        session.add(thread)
        await session.flush()
    elif thread.provider_thread_id is None and result.provider_thread_id:
        thread.provider_thread_id = result.provider_thread_id

    message = EmailMessage(
        org_id=principal.active_org_id,
        thread_id=thread.id,
        connection_id=connection.id,
        direction=EmailDirection.outbound,
        rfc_message_id=result.message_id,
        in_reply_to=in_reply_to,
        from_address=connection.from_address,
        to_addresses=payload.to,
        subject=payload.subject,
        body_text=payload.body_text,
        sent_at=datetime.now(UTC),
    )
    session.add(message)
    await session.flush()
    return _out(message)
