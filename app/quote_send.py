"""Send-quote composer (M5.5) — the real draft→Sent send.

Spec ``#settings`` (send-quote composer) + ``#email-connectivity``. The estimator
composes To/CC/BCC, picks a (merge-filled) template, optionally attaches the quote
PDF, and ``SEND QUOTE`` dispatches ONE email from their **connected identity** (or
the Mailgun-EU platform fallback), carrying the secure ``/q/:token`` link. On send
this:

* mints a per-recipient :class:`~app.models.QuoteToken` (the primary To recipient's
  token backs the shared ``%%QUOTE_LINK%%``),
* runs the ``%%FIELD%%`` merge **server-side** on the final subject/body (so the
  link is authentic and never client-forged),
* snapshots the quote PDF when "Include quote PDF" is on (mirrors M5.4),
* records the outbound message on the quote's thread (M3.5),
* flips the quote to **Sent** (replacing the golden-thread's sent-flag mock), and
* emits ``quote.sent`` onto the domain-event outbox.

The M3.5 module's note named this composer as the place that "rebuilds this flow
(templates, PDF, fallback)". Follow-up replies still go through the M3.5 timeline
endpoint — this is the one-time finalise/send.
"""

from __future__ import annotations

import html as _htmllib
import io
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .accounts import _normalize_email
from .auth import Principal
from .authz import Permission, require
from .buyer_portal import load_display_settings
from .config import Settings
from .deps import get_app_settings, get_session, get_storage
from .email_crypto import decrypt_credentials
from .email_providers import (
    OutboundAttachment,
    OutboundEmail,
    get_platform_sender,
    get_provider,
)
from .errors import AppError
from .events import emit_event
from .merge_fields import build_merge_values, render_merge
from .models import (
    EmailDirection,
    EmailMessage,
    Organization,
    Quote,
    QuoteEmailThread,
    QuoteStatus,
    QuoteToken,
    UserEmailConnection,
)
from .pdf import (
    assemble_quote_context,
    html_to_pdf,
    load_quote_content,
    render_document_html,
    weasyprint_available,
)
from .quote_lifecycle import is_legal_transition, transition
from .quote_tokens import create_buyer_token
from .storage import ObjectStorage

quote_send_router = APIRouter(prefix="/api/quotes/{quote_id}", tags=["quote-send"])

_MAX_RECIPIENTS = 50


class SendQuoteIn(BaseModel):
    """The send-quote composer payload ("Who will get this quote?")."""

    model_config = ConfigDict(extra="forbid")

    to: list[str] = Field(min_length=1, max_length=_MAX_RECIPIENTS)
    cc: list[str] = Field(default_factory=list, max_length=_MAX_RECIPIENTS)
    bcc: list[str] = Field(default_factory=list, max_length=_MAX_RECIPIENTS)
    template_id: uuid.UUID | None = None
    subject: str = Field(min_length=1, max_length=500)
    body_html: str = Field(min_length=1, max_length=200_000)
    include_pdf: bool = False

    @field_validator("to", "cc", "bcc")
    @classmethod
    def _norm(cls, value: list[str]) -> list[str]:
        return [_normalize_email(addr) for addr in value]


class SendQuoteOut(BaseModel):
    quote_id: uuid.UUID
    status: QuoteStatus
    recipients: list[str]
    pdf_attached: bool


class PreviewOut(BaseModel):
    subject: str
    body_html: str


_TAG = re.compile(r"<[^>]+>")
_BLOCK_BREAK = re.compile(r"(?i)</(p|div|h[1-6]|li|tr)>|<br\s*/?>")


def _html_to_text(html: str) -> str:
    """A minimal HTML→text projection for the plain-text MIME alternative:
    block-closes become newlines, tags are stripped, entities unescaped."""
    text = _BLOCK_BREAK.sub("\n", html)
    text = _TAG.sub("", text)
    text = _htmllib.unescape(text)
    # Collapse 3+ blank lines and trim trailing space per line.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _portal_link(base_url: str, token_jwt: str) -> str:
    return f"{base_url.rstrip('/')}/q/{token_jwt}"


def _dedupe(addrs: list[str]) -> list[str]:
    """Every recipient once, in first-seen order (To then Cc then Bcc)."""
    seen: dict[str, None] = {}
    for addr in addrs:
        seen.setdefault(addr, None)
    return list(seen)


async def _load_quote(session: AsyncSession, quote_id: uuid.UUID) -> Quote:
    quote = await session.get(Quote, quote_id, with_for_update=True)
    if quote is None or quote.deleted_at is not None:
        raise AppError("quote_not_found", "Angebot nicht gefunden.", status_code=404)
    return quote


async def _load_org(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await session.get(Organization, org_id)
    if org is None:
        raise AppError("org_not_found", "Organisation nicht gefunden.", status_code=404)
    return org


async def _render_pdf_snapshot(
    session: AsyncSession,
    org: Organization,
    quote: Quote,
    storage: ObjectStorage,
    *,
    link: str,
) -> bytes:
    """Render + persist the send-time quote PDF snapshot (mirrors M5.4's
    ``download_order_pdf``): the bytes are stored under a tenant key and the key is
    stamped on the quote."""
    if not weasyprint_available():
        raise AppError(
            "pdf_unavailable", "PDF-Erstellung ist derzeit nicht verfügbar.", status_code=503
        )
    settings = await load_display_settings(session, org.id)
    content = await load_quote_content(session, org.id)
    ctx = await assemble_quote_context(
        session, org, quote, settings, content, storage, datetime.now(UTC), digital_quote_link=link
    )
    pdf = html_to_pdf(render_document_html(ctx))
    key = f"org/{org.id}/quote/{quote.id}/quote.pdf"
    await storage.put(key, io.BytesIO(pdf), content_type="application/pdf")
    quote.pdf_object_key = key
    return pdf


async def _resolve_content(
    session: AsyncSession,
    org: Organization,
    quote: Quote,
    payload: SendQuoteIn,
    *,
    link: str,
) -> tuple[str, str]:
    """Server-side merge of the (edited) subject + HTML body against the authentic
    context — ``%%QUOTE_LINK%%`` becomes the real minted ``link``. Values merged into
    the HTML body are HTML-escaped (a customer-supplied part/RFQ value must not be a
    script sink); the plain-text subject merges unescaped."""
    values = await build_merge_values(session, org, quote, quote_link=link)
    subject = render_merge(payload.subject, values)
    body_html = render_merge(payload.body_html, values, escape_html=True)
    return subject, body_html


@quote_send_router.post("/send/preview")
async def preview_quote_send(
    quote_id: uuid.UUID,
    payload: SendQuoteIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> PreviewOut:
    """Resolve the merge fields for display — no send, no token mint, no transition.

    ``%%QUOTE_LINK%%`` shows the most-recent existing portal token for the quote if
    one exists, else an illustrative link (the real per-recipient token is minted
    only on send)."""
    quote = await session.get(Quote, quote_id)
    if quote is None or quote.deleted_at is not None:
        raise AppError("quote_not_found", "Angebot nicht gefunden.", status_code=404)
    org = await _load_org(session, quote.org_id)
    existing = await session.scalar(
        select(QuoteToken.token)
        .where(QuoteToken.quote_id == quote_id, QuoteToken.revoked_at.is_(None))
        .order_by(QuoteToken.created_at.desc())
        .limit(1)
    )
    link = (
        _portal_link(settings.app_base_url, existing)
        if existing
        else f"{settings.app_base_url.rstrip('/')}/q/…"
    )
    subject, body_html = await _resolve_content(session, org, quote, payload, link=link)
    return PreviewOut(subject=subject, body_html=body_html)


@quote_send_router.post("/send")
async def send_quote(
    quote_id: uuid.UUID,
    payload: SendQuoteIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_finalize))],
    settings: Annotated[Settings, Depends(get_app_settings)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
) -> SendQuoteOut:
    """Compose + send the quote from the estimator's identity (or the platform
    fallback), mint the portal token(s), snapshot the PDF if asked, record the
    thread message, flip to Sent, and emit ``quote.sent``."""
    quote = await _load_quote(session, quote_id)

    # Preconditions BEFORE any side effect: the send must legally reach Sent and the
    # quote must have an assigned contact (the lifecycle's send precondition).
    if not is_legal_transition(quote.status, QuoteStatus.sent, quote.status_before_hold):
        raise AppError(
            "invalid_state",
            f"Ein Angebot im Status '{quote.status.value}' kann nicht gesendet werden.",
            status_code=status.HTTP_409_CONFLICT,
        )
    if quote.contact_id is None:
        raise AppError(
            "missing_contact",
            "Dem Angebot muss ein Kontakt zugewiesen sein, bevor es gesendet werden kann.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    org = await _load_org(session, quote.org_id)

    # Resolve the sender: the caller's primary connection, else the platform
    # fallback, else the "connect your email" prompt.
    connection = await session.scalar(
        select(UserEmailConnection).where(
            UserEmailConnection.user_id == principal.user_id,
            UserEmailConnection.is_primary,
        )
    )
    if connection is not None:
        provider = get_provider(connection.connection_type)
        credentials = decrypt_credentials(
            settings.email_credentials_key, connection.encrypted_credentials
        )
        from_address, from_name = connection.from_address, connection.from_name
        connection_id: uuid.UUID | None = connection.id
    else:
        platform = get_platform_sender(settings)
        if platform is None:
            raise AppError(
                "no_email_connection",
                "Kein E-Mail-Konto verbunden. Verbinden Sie Ihr E-Mail-Konto, "
                "um Angebote vom eigenen Absender zu versenden.",
                status_code=status.HTTP_409_CONFLICT,
            )
        provider = platform.provider
        credentials = {}
        from_address, from_name = platform.from_address, platform.from_name
        connection_id = None

    # Mint a token per unique recipient (attribution/revocation); the primary To
    # recipient's token backs the shared %%QUOTE_LINK%%.
    secret = settings.resolve_quote_token_secret()
    all_recipients = _dedupe([*payload.to, *payload.cc, *payload.bcc])
    primary_link = ""
    for addr in all_recipients:
        _, token_jwt = await create_buyer_token(session, secret, quote, recipient_email=addr)
        if addr == payload.to[0]:
            primary_link = _portal_link(settings.app_base_url, token_jwt)

    subject, body_html = await _resolve_content(session, org, quote, payload, link=primary_link)
    body_text = _html_to_text(body_html)

    attachments: list[OutboundAttachment] = []
    if payload.include_pdf:
        pdf = await _render_pdf_snapshot(session, org, quote, storage, link=primary_link)
        attachments.append(
            OutboundAttachment(f"Angebot-{quote.number}.pdf", "application/pdf", pdf)
        )

    message = OutboundEmail(
        to=payload.to,
        cc=payload.cc,
        bcc=payload.bcc,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
    )
    # KNOWN LIMITATION (accepted, DECISIONS 2026-07-18; inherited from M3.5): the
    # provider send runs mid-transaction, so a failure/commit-error after it leaves
    # the email sent while the token mint + Sent transition roll back. Closing it
    # needs the durable email-send outbox (send from a worker AFTER commit) — a
    # larger deferred feature. The frontend disables submit in-flight (no double-send).
    result = await provider.send(
        credentials, from_address=from_address, from_name=from_name, message=message
    )

    # Record the outbound on the quote's thread (first send creates the thread row).
    thread = QuoteEmailThread(
        org_id=org.id,
        quote_id=quote.id,
        sent_message_id=result.message_id,
        provider_thread_id=result.provider_thread_id,
    )
    session.add(thread)
    await session.flush()
    session.add(
        EmailMessage(
            org_id=org.id,
            thread_id=thread.id,
            connection_id=connection_id,
            direction=EmailDirection.outbound,
            rfc_message_id=result.message_id,
            from_address=from_address,
            to_addresses=payload.to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachments=[
                {"filename": a.filename, "content_type": a.content_type} for a in attachments
            ],
            sent_at=datetime.now(UTC),
        )
    )

    # Flip to Sent (stamps sent_at + audit) and emit the integration event.
    await transition(session, quote, QuoteStatus.sent, actor_id=principal.user_id)
    await emit_event(
        session,
        org.id,
        "quote.sent",
        {
            "quote_id": str(quote.id),
            "quote_number": quote.number,
            "recipient_count": len(all_recipients),
            "pdf_attached": bool(attachments),
        },
    )

    return SendQuoteOut(
        quote_id=quote.id,
        status=quote.status,
        recipients=all_recipients,
        pdf_attached=bool(attachments),
    )
