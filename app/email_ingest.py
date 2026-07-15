"""Email ingest → auto-quote (M3.3 — spec ``#wingman`` pipeline 1, ``#email-connectivity``).

An inbound RFQ to ``{org-slug}@rfq.tolera.eu`` (Mailgun EU) becomes a draft
Quote: the webhook authenticates the POST (Mailgun HMAC signature), resolves
the org from the recipient, stores the raw ``.eml`` as the quote's **ORIGINAL
RFQ**, and inserts the ``request_for_quote`` row — the Message-Id idempotency
gate — then hands off to Celery (long work never blocks a request, CLAUDE.md
§5). The ``app.rfq_ingest`` task does the rest under the org's RLS scope:
sender→Contact(+Account) match (else an **account-less** contact — the
held-for-review intake state, DECISIONS.md 2026-06-25), draft Quote with
``email_thread_id`` (M3.5 threads replies onto it), attachments — **ZIPs
recursed** (spec: "recurse ZIPs; size cap 200 MB/file") — filed via the M2.12
part pipeline with RFQ provenance, Lens extraction queued per PDF/TIFF print,
and the dashboard notification fanned out to the org's active members.

Interrogation queueing is deliberately absent: the GeometryService lands in M4
(build-plan M3.7 gating note) — the enqueue seam is `_enqueue_lens_extract`'s
sibling when it arrives.

Security posture: the endpoint is unauthenticated-by-Clerk (Mailgun is a
machine caller), so it FAILS CLOSED without a signing key, verifies the HMAC
before touching anything, and never logs sender addresses or message content
(CLAUDE.md §5 — ids and counts only).
"""

from __future__ import annotations

import email
import hashlib
import hmac
import io
import logging
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from typing import Annotated, Any, cast

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.datastructures import Headers

from .celery_app import celery_app
from .config import get_settings
from .db import make_engine, make_sessionmaker, org_scoped_session
from .deps import get_app_settings, get_storage
from .errors import AppError
from .file_types import MAGIC_SNIFF_BYTES, classify, sniff_matches_extension
from .lens_extract import _run_on_own_loop, lens_extract_task
from .models import (
    Contact,
    MembershipStatus,
    Notification,
    Organization,
    Quote,
    RequestForQuote,
    UserOrgMembership,
)
from .part_index import normalize_filename
from .parts import _safe_filename, _store_files_on_part, _validate_upload_batch, create_root_part
from .quotes import _next_quote_number
from .services.org_service import RFQ_INGEST_DOMAIN
from .storage import ObjectStorage
from .task_resources import resolve as resolve_task_resources
from .tasks import BaseTask

logger = logging.getLogger("app.email_ingest")

ingest_router = APIRouter(tags=["email-ingest"])

#: Display name for the stored raw message (the quote Files panel's "RFQ (1)").
RFQ_EML_FILENAME = "original-rfq.eml"
#: Mailgun signs timestamp+token; older posts are replays (defence in depth —
#: the Message-Id dedupe is the durable idempotency gate behind it).
SIGNATURE_MAX_AGE_SECONDS = 900
#: ZIP recursion guards: total extracted members per email, nesting depth
#: (outer zip = 0; "recurse ZIPs" needs 1; deeper is hostile), the spec's
#: per-file cap ("size cap 200 MB/file" — #email-connectivity), and an
#: AGGREGATE decompressed-bytes budget per email — without it a small zip
#: deflating to 200 MB x N members would be held in memory all at once
#: (zip-bomb → worker OOM; fresh-eyes review 🔴1).
MAX_ATTACHMENT_MEMBERS = 200
MAX_ZIP_DEPTH = 1
DEFAULT_MAX_MEMBER_BYTES = 200 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 500 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Pure helpers — webhook auth + recipient routing
# --------------------------------------------------------------------------- #
def slug_from_recipient(recipient: str) -> str | None:
    """Extract the org slug from ``{slug}@rfq.tolera.eu`` (derived, never stored
    — DECISIONS.md 2026-06-24). Foreign domains → ``None`` (permanent reject)."""
    _, address = parseaddr(recipient or "")
    local, sep, domain = address.partition("@")
    if not sep or domain.lower() != RFQ_INGEST_DOMAIN:
        return None
    return local.lower() or None


def verify_mailgun_signature(
    signing_key: str, *, timestamp: str, token: str, signature: str
) -> bool:
    """Mailgun webhook auth: ``HMAC-SHA256(key, timestamp + token) == signature``,
    with a freshness window against replays."""
    try:
        age = abs(time.time() - float(timestamp))
    except (TypeError, ValueError):
        return False
    if age > SIGNATURE_MAX_AGE_SECONDS:
        return False
    expected = hmac.new(
        signing_key.encode(), (timestamp + token).encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


class _TokenReplayCache:
    """Single-use enforcement for Mailgun tokens (fresh-eyes review 🟡4):
    the HMAC covers only ``timestamp + token`` — it does NOT bind the payload
    — so a captured signature could be re-posted with a crafted body within
    the freshness window. Mailgun's guidance is to cache seen tokens and
    reject repeats. In-process cache: sufficient for the single-API-container
    pilot deploy; a multi-instance deploy needs a shared (Redis) cache —
    noted as a follow-up in the PR."""

    def __init__(self, ttl_seconds: float = SIGNATURE_MAX_AGE_SECONDS * 2) -> None:
        self._ttl = ttl_seconds
        self._seen: dict[str, float] = {}

    def seen_before(self, token: str) -> bool:
        now = time.time()
        if len(self._seen) > 10_000:  # bound memory; expired entries dominate
            self._seen = {t: exp for t, exp in self._seen.items() if exp > now}
        if self._seen.get(token, 0) > now:
            return True
        self._seen[token] = now + self._ttl
        return False


_token_replay_cache = _TokenReplayCache()


# --------------------------------------------------------------------------- #
# Pure helpers — .eml parsing (stdlib email) + ZIP recursion
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ParsedAttachment:
    """One ingestable file from the message; ``origin`` names the ZIP container
    a recursed member came from (``None`` for direct attachments)."""

    filename: str
    content_type: str | None
    payload: bytes
    origin: str | None = None


@dataclass(frozen=True)
class ParsedEmail:
    """The ingest-relevant projection of an RFC 5322 message."""

    message_id: str
    sender_email: str
    sender_name: str | None
    subject: str
    sent_at: datetime | None
    body_text: str
    attachments: list[ParsedAttachment] = field(default_factory=list)


def _surrogate_message_id(raw: bytes) -> str:
    """Deterministic stand-in when Message-Id is absent, so the idempotency
    gate still holds for a resent identical payload."""
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


#: RFC 5322 caps a header line at 998 chars; anything longer is hostile and
#: would also blow Postgres's btree index-row limit on the unique index
#: (fresh-eyes review 🟡6) — fall back to the content-hash surrogate instead.
MAX_MESSAGE_ID_CHARS = 512


def message_id_of(raw: bytes, msg: Message) -> str:
    header = (msg.get("Message-Id") or "").strip()
    if not header or len(header) > MAX_MESSAGE_ID_CHARS:
        return _surrogate_message_id(raw)
    return header


def _acceptable(name: str, payload: bytes, max_member_bytes: int) -> bool:
    """The parse-level allow-list gate (same criteria the filing pipeline
    re-checks): supported extension, matching magic bytes, size cap."""
    if classify(name) is None:
        return False
    if len(payload) > max_member_bytes:
        return False
    return sniff_matches_extension(name, payload[:MAGIC_SNIFF_BYTES])


def _remaining_budget(out: list[ParsedAttachment]) -> int:
    """The aggregate decompressed-bytes budget left for this email (🔴1:
    per-member caps alone let N members hold N x 200 MB in memory at once)."""
    return MAX_TOTAL_ATTACHMENT_BYTES - sum(len(a.payload) for a in out)


#: Refuse to even PARSE archives declaring more entries than this:
#: ``ZipFile()`` materialises the whole central directory eagerly, so a
#: million-entry archive would allocate gigabytes before any member loop
#: (CodeRabbit major). Generous vs MAX_ATTACHMENT_MEMBERS — dirs count too.
MAX_ZIP_ENTRIES = 2000
_EOCD_SIG = b"PK\x05\x06"


def _zip_entry_count(payload: bytes) -> int | None:
    """Entry count from the end-of-central-directory record, WITHOUT letting
    ``ZipFile`` parse the central directory. EOCD sits in the last 22 bytes
    plus up to a 64 KiB comment; ``None`` = record not found (corrupt)."""
    tail = payload[-(65536 + 22) :]
    pos = tail.rfind(_EOCD_SIG)
    if pos < 0 or pos + 12 > len(tail):
        return None
    return int.from_bytes(tail[pos + 10 : pos + 12], "little")


def _collect_zip_members(
    container_name: str,
    payload: bytes,
    out: list[ParsedAttachment],
    *,
    depth: int,
    max_member_bytes: int,
) -> bool:
    """Recurse a ZIP attachment into ``out``. Returns False when the archive
    could not be unpacked (caller keeps the container opaque so nothing is
    lost). Zip-bomb guards: container size + declared-entry caps checked
    BEFORE the (eager) central-directory parse, member count cap, per-member
    size cap enforced on the ACTUAL decompressed bytes (headers can lie),
    aggregate budget bounding what a single decompress may even READ,
    nesting depth cap."""
    if len(payload) > max_member_bytes:
        return False  # container over the per-file cap — don't even parse it
    entries = _zip_entry_count(payload)
    if entries is None or entries > MAX_ZIP_ENTRIES:
        logger.warning(
            "zip_unpack_refused",
            extra={"reason": "entry_count", "entries": entries, "container_depth": depth},
        )
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if len(out) >= MAX_ATTACHMENT_MEMBERS:
                    logger.warning(
                        "zip_members_capped",
                        extra={"cap": MAX_ATTACHMENT_MEMBERS, "container_depth": depth},
                    )
                    break
                # Never read past the smaller of the per-member cap and what's
                # left of the aggregate budget (+1 so the over-limit case is
                # detectable and the member is dropped, not truncated).
                read_cap = min(max_member_bytes, _remaining_budget(out))
                if read_cap <= 0:
                    logger.warning(
                        "zip_budget_exhausted",
                        extra={"budget": MAX_TOTAL_ATTACHMENT_BYTES, "container_depth": depth},
                    )
                    break
                member_name = _safe_filename(info.filename)
                with zf.open(info) as fh:
                    data = fh.read(read_cap + 1)
                if len(data) > read_cap:
                    logger.info(
                        "attachment_skipped", extra={"reason": "member_too_large", "depth": depth}
                    )
                    continue
                _collect_attachment(
                    member_name,
                    None,
                    data,
                    out,
                    depth=depth + 1,
                    origin=container_name,
                    max_member_bytes=max_member_bytes,
                )
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, OSError):
        return False
    return True


def _collect_attachment(
    filename: str,
    content_type: str | None,
    payload: bytes,
    out: list[ParsedAttachment],
    *,
    depth: int,
    origin: str | None,
    max_member_bytes: int,
) -> None:
    """File one attachment (or recurse it, for ZIPs) into ``out``; anything
    off the allow-list is skipped with a log line, never a hard failure — a
    bad attachment must not lose the RFQ."""
    name = _safe_filename(filename)
    if len(out) >= MAX_ATTACHMENT_MEMBERS:
        return
    if classify(name) is not None and name.lower().endswith(".zip"):
        if depth < MAX_ZIP_DEPTH + 1 and _collect_zip_members(
            name, payload, out, depth=depth, max_member_bytes=max_member_bytes
        ):
            return  # members filed; the container itself is not
        # Unpack failed (or nested too deep): keep the archive opaque.
        if _acceptable(name, payload, max_member_bytes) and len(payload) <= _remaining_budget(out):
            out.append(ParsedAttachment(name, content_type, payload, origin))
        return
    if not _acceptable(name, payload, max_member_bytes) or len(payload) > _remaining_budget(out):
        logger.info("attachment_skipped", extra={"reason": "not_acceptable", "depth": depth})
        return
    out.append(ParsedAttachment(name, content_type, payload, origin))


def parse_rfq_email(raw: bytes, *, max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES) -> ParsedEmail:
    """Project a raw RFC 5322 message into the ingest contract."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    sender_name, sender_email = parseaddr(str(msg.get("From", "")))
    sent_at: datetime | None = None
    if msg.get("Date"):
        try:
            sent_at = parsedate_to_datetime(str(msg["Date"]))
        except ValueError:
            sent_at = None
    body = msg.get_body(preferencelist=("plain",))
    body_text = str(body.get_content()) if body is not None else ""

    attachments: list[ParsedAttachment] = []
    for part in msg.iter_attachments():
        filename = part.get_filename()
        if not filename:
            continue  # unnamed inline part (signature image etc.) — not a file
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        _collect_attachment(
            filename,
            part.get_content_type(),
            payload,
            attachments,
            depth=0,
            origin=None,
            max_member_bytes=max_member_bytes,
        )
    return ParsedEmail(
        message_id=message_id_of(raw, msg),
        sender_email=sender_email.lower(),
        sender_name=sender_name or None,
        subject=str(msg.get("Subject", "")),
        sent_at=sent_at,
        body_text=body_text,
        attachments=attachments,
    )


# --------------------------------------------------------------------------- #
# Storage key for the ORIGINAL RFQ (.eml is quote-level, not a part's file)
# --------------------------------------------------------------------------- #
def rfq_object_key(org_id: uuid.UUID, rfq_id: uuid.UUID) -> str:
    """Tenant-scoped key mirroring ``storage.object_key``'s layout."""
    return f"org/{org_id}/rfq/{rfq_id}/{RFQ_EML_FILENAME}"


# --------------------------------------------------------------------------- #
# The webhook — verify, resolve org, persist the gate row, hand off
# --------------------------------------------------------------------------- #
async def _resolve_org_id(sessionmaker: async_sessionmaker[Any], slug: str) -> uuid.UUID | None:
    """Slug → org id via the SECURITY DEFINER lookup (migration 0022): the
    restricted role cannot read ``organization`` before an org GUC is set."""
    async with sessionmaker() as session:
        org_id = await session.scalar(text("SELECT resolve_org_id_by_slug(:slug)"), {"slug": slug})
        return cast("uuid.UUID | None", org_id)


@ingest_router.post("/webhooks/mailgun")
async def mailgun_inbound(
    request: Request,
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    timestamp: Annotated[str, Form()] = "",
    token: Annotated[str, Form()] = "",
    signature: Annotated[str, Form()] = "",
    recipient: Annotated[str, Form()] = "",
    body_mime: Annotated[str, Form(alias="body-mime")] = "",
) -> dict[str, Any]:
    """Mailgun EU inbound route (raw-MIME variant — the post carries the full
    message as ``body-mime``, which is exactly the ``.eml`` we must store).

    Response codes follow Mailgun's route semantics: 200 = delivered (also for
    an idempotent duplicate), 401 = bad signature (Mailgun retries), 406 =
    permanent reject (unknown recipient — Mailgun stops retrying)."""
    settings = get_app_settings(request)
    if not settings.mailgun_webhook_signing_key:
        # Fail closed: an unauthenticated ingest endpoint must never accept
        # unsigned posts because a key was forgotten (config.py rationale).
        raise AppError(
            "ingest_not_configured",
            "E-Mail-Eingang ist nicht konfiguriert.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if not verify_mailgun_signature(
        settings.mailgun_webhook_signing_key,
        timestamp=timestamp,
        token=token,
        signature=signature,
    ):
        raise AppError(
            "invalid_signature",
            "Signaturprüfung fehlgeschlagen.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if _token_replay_cache.seen_before(token):
        # The signature doesn't bind the payload — reject token reuse so a
        # captured (timestamp, token, signature) can't be re-posted with a
        # crafted body inside the freshness window (🟡4).
        raise AppError(
            "replayed_token",
            "Signatur-Token wurde bereits verwendet.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    slug = slug_from_recipient(recipient)
    sessionmaker: async_sessionmaker[Any] = request.app.state.sessionmaker
    org_id = await _resolve_org_id(sessionmaker, slug) if slug else None
    if org_id is None:
        # 406 = permanent: retrying an unroutable recipient can never succeed.
        raise AppError(
            "unknown_recipient",
            "Empfängeradresse ist keinem Mandanten zugeordnet.",
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
        )

    # MIME is 7-bit/base64 text on the wire; utf-8 round-trips it. (The parser
    # decoded the form field as utf-8 already — bytes beyond that are gone
    # regardless of what we do here.)
    raw = body_mime.encode("utf-8")
    headers_msg = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    message_id = message_id_of(raw, headers_msg)
    _, sender_email = parseaddr(str(headers_msg.get("From", "")))

    duplicate = await _existing_rfq(sessionmaker, org_id, message_id)
    if duplicate is None:
        try:
            rfq_id = await _create_rfq_row(
                sessionmaker,
                storage,
                org_id=org_id,
                message_id=message_id,
                sender_email=sender_email.lower() or None,
                subject=str(headers_msg.get("Subject", "")) or None,
                raw=raw,
            )
        except IntegrityError:
            # Concurrent retry lost the unique-index race — converge on the
            # winner's row (same answer as the pre-check path).
            duplicate = await _existing_rfq(sessionmaker, org_id, message_id)
            if duplicate is None:  # pragma: no cover — the index just fired
                raise
    if duplicate is not None:
        logger.info(
            "rfq_ingest_duplicate",
            extra={"org_id": str(org_id), "rfq_id": str(duplicate[0])},
        )
        return {
            "status": "duplicate",
            "rfq_id": str(duplicate[0]),
            "quote_id": str(duplicate[1]) if duplicate[1] else None,
        }

    rfq_ingest_task.delay(str(org_id), str(rfq_id))
    logger.info("rfq_ingest_accepted", extra={"org_id": str(org_id), "rfq_id": str(rfq_id)})
    # Eager test mode runs the task inline on .delay — surface the quote id it
    # minted (production returns null here; the quote arrives asynchronously).
    converted = await _existing_rfq(sessionmaker, org_id, message_id)
    return {
        "status": "created",
        "rfq_id": str(rfq_id),
        "quote_id": str(converted[1]) if converted and converted[1] else None,
    }


async def _existing_rfq(
    sessionmaker: async_sessionmaker[Any], org_id: uuid.UUID, message_id: str
) -> tuple[uuid.UUID, uuid.UUID | None] | None:
    async with org_scoped_session(sessionmaker, org_id) as session:
        row = await session.scalar(
            select(RequestForQuote).where(RequestForQuote.email_message_id == message_id)
        )
        if row is None:
            return None
        return (row.id, row.quote_id)


async def _create_rfq_row(
    sessionmaker: async_sessionmaker[Any],
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    message_id: str,
    sender_email: str | None,
    subject: str | None,
    raw: bytes,
) -> uuid.UUID:
    """Store the raw ``.eml`` and insert the gate row (one transaction; the
    blob is discarded if the insert loses the idempotency race)."""
    rfq_id = uuid.uuid4()
    key = rfq_object_key(org_id, rfq_id)
    size = await storage.put(key, io.BytesIO(raw), content_type="message/rfc822")
    try:
        async with org_scoped_session(sessionmaker, org_id) as session:
            session.add(
                RequestForQuote(
                    id=rfq_id,
                    org_id=org_id,
                    email=sender_email,
                    email_message_id=message_id,
                    subject=subject,
                    eml_storage_key=key,
                    eml_filename=RFQ_EML_FILENAME,
                    eml_size_bytes=size,
                )
            )
            await session.flush()
    except Exception:
        await storage.delete(key)  # don't orphan the blob on a lost race
        raise
    return rfq_id


# --------------------------------------------------------------------------- #
# The ingest task — contact match, draft quote, files, extraction, notify
# --------------------------------------------------------------------------- #
def _enqueue_lens_extract(org_id: uuid.UUID, part_id: uuid.UUID, file_id: uuid.UUID) -> None:
    """Post-commit Lens enqueue (PDF/TIFF prints only — AI-LENS §Scope). Never
    raises: the ingest already committed; a broker outage must not fail it.
    Tests monkeypatch this seam to assert "extraction queued"."""
    try:
        lens_extract_task.delay(str(org_id), str(part_id), str(file_id))
    except Exception:  # pragma: no cover — broker outage
        logger.exception(
            "lens_enqueue_failed", extra={"org_id": str(org_id), "file_id": str(file_id)}
        )


def _split_sender_name(sender_name: str | None) -> tuple[str | None, str | None]:
    """Display name → (first, last) — a best-effort prefill the estimator can
    correct; German RFQs often carry a department or company here."""
    if not sender_name:
        return None, None
    first, _, rest = sender_name.strip().partition(" ")
    return first or None, rest or None


_PRINT_EXTENSIONS = (".pdf", ".tif", ".tiff")


def _as_upload(att: ParsedAttachment) -> UploadFile:
    """Wrap parsed bytes as an UploadFile so the M2.12 filing pipeline
    (validate → store → index → PRIMARY) is reused verbatim."""
    headers = Headers({"content-type": att.content_type or "application/octet-stream"})
    return UploadFile(
        file=io.BytesIO(att.payload),
        size=len(att.payload),
        filename=att.filename,
        headers=headers,
    )


async def _file_attachments(
    session: Any,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    rfq_id: uuid.UUID,
    attachments: list[ParsedAttachment],
    stored_keys: list[str],
) -> tuple[int, list[tuple[uuid.UUID, uuid.UUID]]]:
    """File attachments as Parts via the M2.12 pipeline (stem auto-bundling:
    ``Bracket.stp`` + ``Bracket.pdf`` → ONE part, CAD primary), stamping RFQ
    provenance on every row. Returns (part_count, [(part_id, file_id)] of
    PDF/TIFF prints to extract)."""
    settings = get_settings()  # only max_upload_bytes is read here
    groups: dict[str, list[ParsedAttachment]] = {}
    for att in attachments:
        key = normalize_filename(att.filename) or f"\x00{id(att)}"
        groups.setdefault(key, []).append(att)

    part_count = 0
    to_extract: list[tuple[uuid.UUID, uuid.UUID]] = []
    for batch in groups.values():
        try:
            validated = await _validate_upload_batch([_as_upload(a) for a in batch], settings)
        except AppError as exc:
            # Parse-level filtering already applied the same criteria; a miss
            # here is unexpected but must not lose the rest of the RFQ.
            logger.warning("ingest_bundle_skipped", extra={"code": exc.code})
            continue
        part = await create_root_part(session, org_id)
        rows = await _store_files_on_part(
            session,
            storage,
            org_id=org_id,
            part=part,
            validated=validated,
            stored_keys=stored_keys,
        )
        for row in rows:
            row.rfq_id = rfq_id
            if row.filename.lower().endswith(_PRINT_EXTENSIONS):
                to_extract.append((part.id, row.id))
        primary = next((r for r in rows if r.role == "primary"), rows[0])
        stem, _, _ = primary.filename.rpartition(".")
        part.name = stem or primary.filename
        part_count += 1
    await session.flush()
    return part_count, to_extract


async def _read_blob(storage: ObjectStorage, key: str) -> bytes:
    return b"".join([chunk async for chunk in storage.stream(key)])


async def run_rfq_ingest(
    db_url: str, storage: ObjectStorage, *, org_id: uuid.UUID, rfq_id: uuid.UUID
) -> dict[str, Any]:
    """The task core: everything after the webhook's gate row, in ONE
    org-scoped transaction (a retry that failed mid-way starts clean —
    ``processed_on``/``quote_id`` only exist once everything else does)."""
    engine = make_engine(db_url)
    to_extract: list[tuple[uuid.UUID, uuid.UUID]] = []
    stored_keys: list[str] = []
    try:
        sessionmaker = make_sessionmaker(engine)
        try:
            async with org_scoped_session(sessionmaker, org_id) as session:
                # Row-lock the gate row: two concurrent deliveries (visibility-
                # timeout expiry, manual requeue) would otherwise both see
                # processed_on IS NULL and mint two quotes (🟡2). The second
                # worker blocks here, then sees the winner's processed_on.
                rfq = await session.get(RequestForQuote, rfq_id, with_for_update=True)
                if rfq is None:
                    return {"failed": True, "error_code": "rfq_gone"}
                if rfq.processed_on is not None and rfq.quote_id is not None:
                    # Redelivered after commit — idempotent no-op (§5).
                    return {"already_processed": True, "quote_id": str(rfq.quote_id)}
                if not rfq.eml_storage_key:  # pragma: no cover — webhook always sets it
                    return {"failed": True, "error_code": "eml_missing"}

                parsed = parse_rfq_email(await _read_blob(storage, rfq.eml_storage_key))

                contact: Contact | None = None
                if parsed.sender_email:
                    # Deterministic pick if duplicate live emails ever exist (🟢7).
                    contact = await session.scalar(
                        select(Contact)
                        .where(Contact.email == parsed.sender_email, Contact.deleted_at.is_(None))
                        .order_by(Contact.created_at)
                        .limit(1)
                    )
                    if contact is None:
                        first, last = _split_sender_name(parsed.sender_name)
                        # Account-less = the held-for-review intake state
                        # (DECISIONS.md 2026-06-25) — no Account is invented.
                        contact = Contact(
                            org_id=org_id,
                            account_id=None,
                            email=parsed.sender_email,
                            first_name=first,
                            last_name=last,
                        )
                        session.add(contact)
                        await session.flush()

                org = await session.get(Organization, org_id)
                if org is None:  # pragma: no cover — GUC guarantees visibility
                    return {"failed": True, "error_code": "org_gone"}
                quote = Quote(
                    org_id=org_id,
                    number=await _next_quote_number(session, org_id),
                    currency=org.currency,
                    contact_id=contact.id if contact else None,
                    account_id=contact.account_id if contact else None,
                    rfq_received_date=parsed.sent_at or datetime.now(UTC),
                    email_thread_id=parsed.message_id,
                )
                session.add(quote)
                await session.flush()

                rfq.quote_id = quote.id
                rfq.processed_on = datetime.now(UTC)
                rfq.description = parsed.body_text or None
                first, last = _split_sender_name(parsed.sender_name)
                rfq.first_name, rfq.last_name = first, last
                if parsed.sender_email and not rfq.email:
                    rfq.email = parsed.sender_email

                part_count, to_extract = await _file_attachments(
                    session,
                    storage,
                    org_id=org_id,
                    rfq_id=rfq_id,
                    attachments=parsed.attachments,
                    stored_keys=stored_keys,
                )

                member_ids = (
                    await session.scalars(
                        select(UserOrgMembership.user_id).where(
                            UserOrgMembership.org_id == org_id,
                            UserOrgMembership.status == MembershipStatus.active,
                        )
                    )
                ).all()
                for user_id in member_ids:
                    # Spec #wingman: "New Quote created from Email Forwarding:
                    # Created Quote #N" — rendered German-first client-side; the
                    # M3.9 Triage card replaces this plain notification later.
                    session.add(
                        Notification(
                            org_id=org_id,
                            user_id=user_id,
                            kind="quote_email_ingested",
                            payload={
                                "quote_id": str(quote.id),
                                "quote_number": quote.number,
                                "rfq_id": str(rfq_id),
                            },
                        )
                    )
                await session.flush()
                quote_id, quote_number = quote.id, quote.number
        except Exception:
            # Rows roll back with the session (including a failed COMMIT);
            # discard every blob written this attempt so a Celery retry
            # starts clean instead of compounding orphans (🟡3).
            for key in stored_keys:
                await storage.delete(key)
            raise
        # Transaction committed — only now queue extraction on committed rows.
        for part_id, file_id in to_extract:
            _enqueue_lens_extract(org_id, part_id, file_id)
        return {
            "quote_id": str(quote_id),
            "quote_number": quote_number,
            "part_count": part_count,
            "extraction_queued": len(to_extract),
            "notified": len(member_ids),
        }
    finally:
        await engine.dispose()


@celery_app.task(
    base=BaseTask, name="app.rfq_ingest", bind=True, soft_time_limit=540, time_limit=600
)
def rfq_ingest_task(self: Any, org_id: str, rfq_id: str) -> dict[str, Any]:
    """Celery wrapper around :func:`run_rfq_ingest` (idempotent, §5)."""
    binding = {"org_id": org_id, "rfq_id": rfq_id}
    task_id = self.request.id
    # Redelivery guard (M3.1 precedent): a worker dying after commit but
    # before ack redelivers — return the stored SUCCESS, don't re-ingest.
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    result = _run_on_own_loop(
        run_rfq_ingest(
            *resolve_task_resources(), org_id=uuid.UUID(org_id), rfq_id=uuid.UUID(rfq_id)
        )
    )
    out = cast("dict[str, Any]", result)
    # Ids + counts only — the message carries customer PII (§5 logging).
    logger.info(
        "rfq_ingest_completed",
        extra={
            "task_id": task_id,
            "part_count": out.get("part_count"),
            "extraction_queued": out.get("extraction_queued"),
            "failed": out.get("failed", False),
            **binding,
        },
    )
    return {**out, **binding}
