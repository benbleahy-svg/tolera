"""Inbound email sync — the 5-minute poll + reply matching (M3.5).

Spec ``#email-connectivity`` threading mechanism: every 5 minutes per
connected user, fetch new messages since the stored cursor
(``historyId`` / delta link / IMAP UNSEEN), and for each one check whether
``In-Reply-To``/``References`` matches a stored ``sent_message_id`` — or the
provider ``threadId``/``conversationId`` matches a stored thread. M3.3's
hand-off adds one more key: ``quote.email_thread_id`` (the ingested RFQ's
Message-Id), so a customer reply that references the original RFQ threads onto
its quote even if no outbound was ever sent from the platform.

On match: create the ``email_message`` row, save attachments to Object
Storage, notify the estimator. **No match → not stored** — the sync must never
ingest the user's unrelated mail (GDPR data minimisation; spec: "On match:
create an email_message row").

Fan-out: ``app.email_sync_all`` (beat) enumerates (org, connection) pairs via
the narrow SECURITY DEFINER ``list_email_sync_targets()`` (ids only — RLS
correctly hides rows before an org GUC is set), then queues one org-scoped
``app.email_sync_connection`` per pair on the ``email`` queue (spec build note:
capped concurrency so N users don't flood the provider APIs).

Idempotency (§5): the partial unique index on (org, ``rfc_message_id``) makes
re-polls and redeliveries no-ops; provider errors land on
``last_sync_error`` instead of crash-looping the beat.
"""

from __future__ import annotations

import hashlib
import io
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .celery_app import celery_app
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker, org_scoped_session
from .email_crypto import decrypt_credentials
from .email_ingest import _acceptable
from .email_providers import (
    InboundEmail,
    ProviderError,
    SyncResult,
    get_provider,
)
from .errors import AppError
from .lens_extract import _run_on_own_loop
from .models import (
    EmailConnectionType,
    EmailDirection,
    EmailMessage,
    Notification,
    Quote,
    QuoteEmailThread,
    UserEmailConnection,
)
from .parts import _safe_filename
from .storage import ObjectStorage
from .task_resources import resolve as resolve_task_resources
from .tasks import BaseTask

logger = logging.getLogger("app.email_sync")

#: Reply attachments obey the same per-file cap as ingest attachments
#: (spec #email-connectivity: "size cap 200 MB/file").
MAX_ATTACHMENT_BYTES = 200 * 1024 * 1024


def _task_settings() -> Settings:
    """Settings seam for the worker context (tests inject their own)."""
    return get_settings()


def attachment_key(org_id: uuid.UUID, message_id: uuid.UUID, filename: str) -> str:
    """Tenant-scoped storage key, mirroring ``rfq_object_key``'s layout."""
    return f"org/{org_id}/email/{message_id}/{filename}"


def _effective_message_id(msg: InboundEmail) -> str:
    """The Message-Id, or a deterministic content-hash surrogate when the
    header is absent (legal, rare) — otherwise an UNSEEN IMAP message with no
    Message-Id would re-store on every poll (the M3.3 surrogate precedent)."""
    if msg.message_id:
        return msg.message_id
    digest = hashlib.sha256(
        "\x00".join([msg.from_address, msg.subject, msg.body_text, str(msg.sent_at or "")]).encode()
    ).hexdigest()
    return f"sha256:{digest}"


# --------------------------------------------------------------------------- #
# Reply matching (spec threading mechanism + the M3.3 email_thread_id key)
# --------------------------------------------------------------------------- #
async def _match_thread(
    session: AsyncSession, org_id: uuid.UUID, msg: InboundEmail
) -> QuoteEmailThread | None:
    """The thread an inbound message belongs to, or ``None`` (→ not stored).

    Keys, in order: provider thread id; ``In-Reply-To``/``References`` against
    the threads' ``sent_message_id``; against any stored OUTBOUND message id
    (follow-ups); against ``quote.email_thread_id`` (ingested RFQ) — which
    creates the quote's thread row anchored on the RFQ's Message-Id."""
    if msg.provider_thread_id:
        thread = await session.scalar(
            select(QuoteEmailThread).where(
                QuoteEmailThread.provider_thread_id == msg.provider_thread_id
            )
        )
        if thread is not None:
            return thread

    candidates = [ref for ref in ([msg.in_reply_to, *msg.references]) if ref]
    if not candidates:
        return None

    thread = cast(
        "QuoteEmailThread | None",
        await session.scalar(
            select(QuoteEmailThread).where(QuoteEmailThread.sent_message_id.in_(candidates))
        ),
    )
    if thread is not None:
        return thread

    thread_id = await session.scalar(
        select(EmailMessage.thread_id).where(
            EmailMessage.direction == EmailDirection.outbound,
            EmailMessage.rfc_message_id.in_(candidates),
        )
    )
    if thread_id is not None:
        return await session.get(QuoteEmailThread, thread_id)

    quote = await session.scalar(select(Quote).where(Quote.email_thread_id.in_(candidates)))
    if quote is not None:
        thread = QuoteEmailThread(
            org_id=org_id,
            quote_id=quote.id,
            # Anchored on the ingested RFQ's Message-Id — no outbound exists yet;
            # the first platform send keeps this anchor (References still match).
            sent_message_id=cast("str", quote.email_thread_id),
        )
        session.add(thread)
        await session.flush()
        return thread
    return None


async def _store_inbound(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    connection: UserEmailConnection,
    thread: QuoteEmailThread,
    msg: InboundEmail,
    stored_keys: list[str],
) -> EmailMessage:
    message_id = uuid.uuid4()
    attachments: list[dict[str, Any]] = []
    for att in msg.attachments:
        try:
            name = _safe_filename(att.filename)
        except AppError:
            # A hostile/broken filename must skip THIS attachment, never fail
            # the sync transaction — that would pin the cursor and refetch the
            # same message forever (fresh-eyes review 🔴3).
            logger.info("email_attachment_skipped", extra={"reason": "bad_filename"})
            continue
        # Same allow-list gate as ingest (extension + magic bytes + cap) — a
        # reply attachment is as untrusted as an RFQ attachment.
        if not _acceptable(name, att.payload, MAX_ATTACHMENT_BYTES):
            logger.info("email_attachment_skipped", extra={"reason": "not_acceptable"})
            continue
        key = attachment_key(org_id, message_id, name)
        size = await storage.put(key, io.BytesIO(att.payload), content_type=att.content_type)
        stored_keys.append(key)
        attachments.append(
            {
                "filename": name,
                "storage_key": key,
                "size_bytes": size,
                "content_type": att.content_type,
            }
        )
    row = EmailMessage(
        id=message_id,
        org_id=org_id,
        thread_id=thread.id,
        connection_id=connection.id,
        direction=EmailDirection.inbound,
        rfc_message_id=_effective_message_id(msg),
        in_reply_to=msg.in_reply_to,
        from_address=msg.from_address or "unbekannt@invalid",
        to_addresses=msg.to_addresses,
        subject=msg.subject or None,
        body_text=msg.body_text or None,
        body_html=msg.body_html,
        attachments=attachments,
        sent_at=msg.sent_at,
    )
    session.add(row)
    await session.flush()
    return row


async def run_email_sync_connection(
    db_url: str, storage: ObjectStorage, *, org_id: uuid.UUID, connection_id: uuid.UUID
) -> dict[str, Any]:
    """Sync one connection: fetch since cursor, match, store, notify, advance
    the cursor. One org-scoped transaction; blobs are rolled back on failure."""
    settings = _task_settings()
    engine = make_engine(db_url)
    stored_keys: list[str] = []
    try:
        sessionmaker = make_sessionmaker(engine)
        try:
            async with org_scoped_session(sessionmaker, org_id) as session:
                connection = await session.get(
                    UserEmailConnection, connection_id, with_for_update=True
                )
                if connection is None:
                    return {"failed": True, "error_code": "connection_gone"}
                credentials = decrypt_credentials(
                    settings.email_credentials_key, connection.encrypted_credentials
                )
                cursor = (
                    connection.gmail_history_id
                    if connection.connection_type is EmailConnectionType.gmail
                    else connection.outlook_delta_link
                    if connection.connection_type is EmailConnectionType.outlook
                    else None
                )
                try:
                    result: SyncResult = await get_provider(connection.connection_type).fetch_new(
                        credentials, cursor=cursor
                    )
                except ProviderError as exc:
                    # Status surfaces on the settings page; next beat retries.
                    connection.last_sync_error = exc.code
                    await session.flush()
                    return {"failed": True, "error_code": exc.code}

                matched = 0
                for msg in result.messages:
                    effective_id = _effective_message_id(msg)
                    exists = await session.scalar(
                        select(EmailMessage.id).where(EmailMessage.rfc_message_id == effective_id)
                    )
                    if exists is not None:
                        continue  # idempotent re-poll (IMAP UNSEEN, redelivery)
                    thread = await _match_thread(session, org_id, msg)
                    if thread is None:
                        continue  # no match → NOT stored (data minimisation)
                    row = await _store_inbound(
                        session,
                        storage,
                        org_id=org_id,
                        connection=connection,
                        thread=thread,
                        msg=msg,
                        stored_keys=stored_keys,
                    )
                    session.add(
                        Notification(
                            org_id=org_id,
                            user_id=connection.user_id,
                            kind="quote_email_reply",
                            payload={
                                "quote_id": str(thread.quote_id),
                                "thread_id": str(thread.id),
                                "message_id": str(row.id),
                            },
                        )
                    )
                    matched += 1

                if connection.connection_type is EmailConnectionType.gmail:
                    connection.gmail_history_id = result.cursor or connection.gmail_history_id
                elif connection.connection_type is EmailConnectionType.outlook:
                    connection.outlook_delta_link = result.cursor or connection.outlook_delta_link
                connection.last_synced_at = datetime.now(UTC)
                connection.last_sync_error = None
                await session.flush()
        except Exception:
            for key in stored_keys:
                await storage.delete(key)  # blobs roll back with the transaction
            raise
        # Ids + counts only — message contents are customer PII (§5 logging).
        logger.info(
            "email_sync_completed",
            extra={
                "org_id": str(org_id),
                "connection_id": str(connection_id),
                "fetched": len(result.messages),
                "matched": matched,
            },
        )
        return {"fetched": len(result.messages), "matched": matched}
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# Celery tasks — beat fan-out + per-connection sync
# --------------------------------------------------------------------------- #
@celery_app.task(
    base=BaseTask, name="app.email_sync_connection", bind=True, soft_time_limit=240, time_limit=270
)
def email_sync_connection_task(self: Any, org_id: str, connection_id: str) -> dict[str, Any]:
    result = _run_on_own_loop(
        run_email_sync_connection(
            *resolve_task_resources(),
            org_id=uuid.UUID(org_id),
            connection_id=uuid.UUID(connection_id),
        )
    )
    return cast("dict[str, Any]", result)


async def _list_sync_targets(db_url: str) -> list[tuple[uuid.UUID, uuid.UUID]]:
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        async with sessionmaker() as session:
            rows = await session.execute(
                text("SELECT org_id, connection_id FROM list_email_sync_targets()")
            )
            return [(row[0], row[1]) for row in rows]
    finally:
        await engine.dispose()


@celery_app.task(
    base=BaseTask, name="app.email_sync_all", bind=True, soft_time_limit=60, time_limit=90
)
def email_sync_all_task(self: Any) -> dict[str, Any]:
    """The beat entry point: one sync task per connection, org-scoped."""
    db_url, _storage = resolve_task_resources()
    targets = _run_on_own_loop(_list_sync_targets(db_url))
    for org_id, connection_id in targets:
        email_sync_connection_task.delay(str(org_id), str(connection_id))
    logger.info("email_sync_fanout", extra={"connections": len(targets)})
    return {"connections": len(targets)}
