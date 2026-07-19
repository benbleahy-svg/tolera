"""M6.5 — a vendor's email reply, matched to its RFQ and filed (spec ``#vendor-rfq``).

The spec treats a vendor who replies to the RFQ email as equally valid as one who uses
the M6.2 portal. This module is the return leg of :mod:`app.vendor_rfq_email`: it hangs
off the existing M3 Mailgun-EU webhook, so a vendor reply reaches it through exactly the
same signed, replay-checked, org-resolved front door as a customer RFQ — nothing new is
exposed to the internet.

What it decides:

* **Matching.** By ``RFQ-n`` reference (:mod:`app.vendor_reply`) **in the subject**, or
  by the reply threading onto the ``Message-ID`` we sent that vendor. Scoped to the org
  the recipient slug already resolved. Sender address is never consulted — because M6.4
  mints one batch per vendor, the reference alone names the vendor, which is what lets a
  vendor answer from a shared inbox (the spec's own reason).

  The *body* is deliberately **not** searched: a customer writing "unsere Anfrage RFQ 12"
  in prose would otherwise be swallowed as a vendor reply and never become the draft
  quote they were owed. Our outbound email puts the reference in the subject and asks the
  vendor to leave it there, so the subject is where it legitimately lives.
* **What it will not overwrite.** A response already **applied** to costing is immutable,
  and a **portal** response — a human typing their own numbers — is never clobbered by an
  AI extraction. In both cases the reply's body and PDF are still filed, so nothing the
  vendor sent is lost; only the numbers stand aside.
* **The PDF is a Quote File.** There is no ``QuoteFile`` table in this build — a quote's
  files *are* its parts' files — so the vendor's attachment is written as a
  ``supporting`` :class:`PartFile` on the first line's part, which is what makes it show
  up where the AC says it must. The row is written directly rather than through the parts
  upload pipeline on purpose: a vendor's commercial quote must never be promoted to a
  part's PRIMARY drawing or trigger geometry interrogation.
* **Extraction is asynchronous.** The webhook only files what arrived; Lens runs on
  Celery afterwards (M3's post-commit enqueue pattern), so a slow or failing model can
  never cost us the reply itself.

The response lands ``ai_extracted=True, verified=False`` — "AI extracted — verify".
Nothing here reaches costing; M6.6 owns the estimator's confirmation and Apply.
"""

from __future__ import annotations

import io
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db import org_scoped_session, run_after_commit
from .email_ingest import ParsedEmail
from .file_types import classify
from .models import (
    Component,
    FileRole,
    Part,
    PartFile,
    QuoteItem,
    VendorRfq,
    VendorRfqLine,
    VendorRfqRecipient,
    VendorRfqResponse,
    VendorRfqStatus,
)
from .part_index import file_sha256, normalize_filename
from .storage import ObjectStorage, object_key
from .vendor_reply import find_rfq_reference

logger = logging.getLogger("app.vendor_reply_ingest")

#: Content types we will file from a vendor reply. A quote arrives as a PDF; anything
#: else (a vCard, a tracking pixel, an unsolicited executable) is not filed.
FILED_CONTENT_TYPES = ("application/pdf",)

#: A vendor quote PDF beyond this is not a quote (the portal channel's own cap, M6.2).
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class VendorReplyResult:
    """Outcome of filing one reply — what the webhook reports back."""

    def __init__(
        self,
        *,
        matched: bool,
        rfq_id: uuid.UUID | None = None,
        response_id: uuid.UUID | None = None,
        duplicate: bool = False,
        numbers_skipped: str | None = None,
    ) -> None:
        self.matched = matched
        self.rfq_id = rfq_id
        self.response_id = response_id
        self.duplicate = duplicate
        #: Set when the reply was filed but its numbers were not allowed to land.
        self.numbers_skipped = numbers_skipped


async def find_open_rfq(
    session: Any, org_id: uuid.UUID, reference: str
) -> tuple[VendorRfq, VendorRfqRecipient] | None:
    """The batch this reference names, with its (single) recipient.

    Org-scoped by the session's RLS *and* explicitly here: a reference number from one
    org can never address another's batch. A **closed** batch still matches: a late
    reply belongs in RFQ history, whereas falling through would file a supplier's price
    sheet into the customer intake queue as a new draft quote. Only a *cancelled* batch
    is unreachable."""
    rfq = (
        await session.execute(
            select(VendorRfq).where(
                VendorRfq.org_id == org_id,
                VendorRfq.number == reference,
                VendorRfq.status != VendorRfqStatus.cancelled,
            )
        )
    ).scalar_one_or_none()
    if rfq is None:
        return None
    recipient = (
        (
            await session.execute(
                select(VendorRfqRecipient)
                .where(VendorRfqRecipient.rfq_id == rfq.id)
                .order_by(VendorRfqRecipient.created_at)
            )
        )
        .scalars()
        .first()
    )
    if recipient is None:  # pragma: no cover — M6.4 always creates one
        return None
    return rfq, recipient


async def find_by_thread(
    session: Any, org_id: uuid.UUID, references: Sequence[str]
) -> tuple[VendorRfq, VendorRfqRecipient] | None:
    """The batch whose outbound copy this reply threads onto.

    Corroboration for the case the subject lost the reference (a vendor's client
    rewriting it, or a fresh compose): ``sent_message_id`` is a value only we minted, so
    a reply carrying it in ``In-Reply-To``/``References`` is unambiguously a vendor's."""
    if not references:
        return None
    recipient = (
        (
            await session.execute(
                select(VendorRfqRecipient).where(
                    VendorRfqRecipient.org_id == org_id,
                    VendorRfqRecipient.sent_message_id.in_(list(references)),
                )
            )
        )
        .scalars()
        .first()
    )
    if recipient is None:
        return None
    rfq = await session.get(VendorRfq, recipient.rfq_id)
    if rfq is None or rfq.status == VendorRfqStatus.cancelled:
        return None
    return rfq, recipient


async def _first_line_part(session: Any, rfq_id: uuid.UUID) -> Part | None:
    """The part the vendor's PDF is filed against — the batch's first line.

    One copy, not one per line: the attachment is a single commercial document
    covering the whole RFQ, and duplicating it across parts would make the estimator
    delete it N times."""
    part: Part | None = (
        (
            await session.execute(
                select(Part)
                .join(Component, Component.part_id == Part.id)
                .join(QuoteItem, QuoteItem.root_component_id == Component.id)
                .join(VendorRfqLine, VendorRfqLine.quote_item_id == QuoteItem.id)
                .where(VendorRfqLine.rfq_id == rfq_id)
                .order_by(VendorRfqLine.position)
            )
        )
        .scalars()
        .first()
    )
    return part


async def _file_vendor_pdf(
    session: Any,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    part: Part,
    filename: str,
    payload: bytes,
) -> PartFile | None:
    """Write the vendor's quote PDF as a supporting Quote File.

    Deliberately not via ``parts._store_files_on_part``: that pipeline may promote an
    upload to the part's PRIMARY and enqueue geometry work, neither of which is right
    for a supplier's price sheet."""
    category = classify(filename)
    if category is None:
        return None
    file_id = uuid.uuid4()
    key = object_key(org_id, part.id, file_id, filename)
    size = await storage.put(key, io.BytesIO(payload), content_type="application/pdf")
    row = PartFile(
        id=file_id,
        org_id=org_id,
        part_id=part.id,
        storage_key=key,
        filename=filename,
        file_type=category.value,
        content_type="application/pdf",
        size_bytes=size,
        role=FileRole.supporting,
        file_hash=file_sha256(payload),
        filename_normalized=normalize_filename(filename),
    )
    session.add(row)
    await session.flush()
    return row


def _pick_attachment(parsed: ParsedEmail) -> tuple[str, bytes] | None:
    """The vendor's quote document, if the reply carried one."""
    for att in parsed.attachments:
        if (att.content_type or "").lower() not in FILED_CONTENT_TYPES or not att.payload:
            continue
        if len(att.payload) > MAX_ATTACHMENT_BYTES:
            # Size only — a filename can carry a part number (CLAUDE.md §5: no customer
            # content in logs).
            logger.info("vendor_reply_attachment_too_large", extra={"bytes": len(att.payload)})
            continue
        # The declared content type is the *sender's* claim; the bytes are not. Without
        # this a `quote.step` announced as application/pdf would be filed as a PDF (the
        # upload path sniffs for the same reason, ``file_types.sniff_matches_extension``).
        if not att.payload.startswith(b"%PDF-"):
            logger.info("vendor_reply_attachment_not_a_pdf", extra={"bytes": len(att.payload)})
            continue
        return att.filename, att.payload
    return None


async def handle_vendor_reply(
    sessionmaker: async_sessionmaker[Any],
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    message_id: str,
    subject: str | None,
    parsed: ParsedEmail,
    references: Sequence[str] = (),
) -> VendorReplyResult:
    """File a vendor's reply against its RFQ. Returns ``matched=False`` to fall through.

    Falling through matters: a *customer* may well write "RFQ-12" in an email, and that
    message must still become a normal inbound RFQ rather than vanishing into a vendor
    batch that does not exist."""
    # Subject only — never the body. See the module doc: a customer writing the
    # reference in prose must still get their draft quote.
    reference = find_rfq_reference(subject)

    async with org_scoped_session(sessionmaker, org_id) as session:
        match = await find_open_rfq(session, org_id, reference) if reference else None
        if match is None:
            match = await find_by_thread(session, org_id, references)
        if match is None:
            return VendorReplyResult(matched=False)
        rfq, recipient = match

        existing = (
            await session.execute(
                select(VendorRfqResponse).where(VendorRfqResponse.recipient_id == recipient.id)
            )
        ).scalar_one_or_none()

        # Idempotency: Mailgun retries every non-2xx, so the same reply may arrive twice.
        if existing is not None and existing.email_message_id == message_id:
            return VendorReplyResult(
                matched=True, rfq_id=rfq.id, response_id=existing.id, duplicate=True
            )

        attachment = _pick_attachment(parsed)
        part = await _first_line_part(session, rfq.id)
        stored: PartFile | None = None
        if attachment is not None and part is not None:
            stored = await _file_vendor_pdf(
                session,
                storage,
                org_id=org_id,
                part=part,
                filename=attachment[0],
                payload=attachment[1],
            )

        # What may not be overwritten — see the module doc.
        blocked: str | None = None
        if existing is not None:
            if existing.applied_at is not None:
                blocked = "already_applied"
            elif existing.source == "portal":
                blocked = "portal_response_exists"
        if existing is not None and blocked is not None:
            logger.info(
                "vendor_reply_numbers_skipped",
                extra={"rfq_id": str(rfq.id), "reason": blocked},
            )
            return VendorReplyResult(
                matched=True, rfq_id=rfq.id, response_id=existing.id, numbers_skipped=blocked
            )

        now = datetime.now(UTC)
        response = existing or VendorRfqResponse(
            org_id=org_id, recipient_id=recipient.id, source="email"
        )
        response.source = "email"
        response.ai_extracted = True
        # The whole point: an extracted reply is a suggestion until a human says so.
        response.verified = False
        response.email_message_id = message_id
        response.email_body_text = parsed.body_text
        response.is_late = rfq.need_by_date is not None and rfq.need_by_date < now.date()
        response.submitted_at = now
        if stored is not None:
            response.attachment_object_key = stored.storage_key
            response.attachment_filename = stored.filename
            response.attachment_size_bytes = stored.size_bytes
            response.attachment_content_type = stored.content_type
        elif existing is not None:
            # A later reply without an attachment must not keep advertising the
            # superseded one — the file stays a Quote File, but this response no longer
            # claims it as *its* quote document.
            response.attachment_object_key = None
            response.attachment_filename = None
            response.attachment_size_bytes = None
            response.attachment_content_type = None
        if existing is None:
            session.add(response)
        try:
            await session.flush()
        except IntegrityError:
            # Lost the idempotency race with a concurrent retry — the winner's row is
            # the same reply, so converge on it rather than 500ing Mailgun into more
            # retries. The rollback is required, not tidiness: a failed flush leaves the
            # transaction deactivated, and the session's own commit on exit would then
            # raise PendingRollbackError — a 500, which Mailgun would retry forever.
            logger.info("vendor_reply_duplicate_race", extra={"rfq_id": str(rfq.id)})
            await session.rollback()
            if stored is not None:
                # The blob was written before the flush; nothing references it now.
                await storage.delete(stored.storage_key)
            return VendorReplyResult(matched=True, rfq_id=rfq.id, duplicate=True)

        response_id = response.id
        pdf_file_id = stored.id if stored is not None else None
        run_after_commit(
            session,
            lambda: _enqueue_vendor_reply_extract(org_id, response_id, pdf_file_id),
        )
        return VendorReplyResult(matched=True, rfq_id=rfq.id, response_id=response_id)


def _enqueue_vendor_reply_extract(
    org_id: uuid.UUID, response_id: uuid.UUID, pdf_file_id: uuid.UUID | None
) -> None:
    """Post-commit Lens enqueue, mirroring ``email_ingest._enqueue_lens_extract``.

    Never raises: the reply is already filed and visible to the estimator; a broker
    outage costs the *suggestions*, not the response. Tests monkeypatch this seam."""
    from .vendor_reply_lens import vendor_reply_extract_task

    try:
        vendor_reply_extract_task.delay(
            str(org_id), str(response_id), str(pdf_file_id) if pdf_file_id else None
        )
    except Exception:
        logger.warning(
            "vendor_reply_extract_enqueue_failed",
            extra={"org_id": str(org_id), "response_id": str(response_id)},
            exc_info=True,
        )
