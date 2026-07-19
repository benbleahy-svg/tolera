"""M6.5 — Lens over a filed vendor reply, writing flagged (unverified) suggestions.

:mod:`app.vendor_reply_ingest` files the reply synchronously; this is the asynchronous
half that reads it. It runs on Celery for the reason CLAUDE.md §5 gives — a model call
must never sit inside a webhook — and because a failed extraction should cost the
*suggestions*, not the response, which the estimator can still open and read.

The rows it writes are the portal's own ``VendorRfqResponseLine`` /
``VendorRfqResponsePrice`` tables, so M6.6's Vendor Quotes panel and its one-click Apply
have a single code path regardless of how the vendor answered. What separates the two
channels is not the shape of the data but ``ai_extracted``/``verified`` on the parent
response: everything written here stays ``verified = False`` — "AI extracted — verify" —
and never reaches costing until a human says so.

Never-hallucinate is enforced *outside* the model, in :func:`app.vendor_reply.
vendor_reply_guard`: every price and lead time must be quoted verbatim from the reply
body or the attached PDF's text layer, and the money itself is parsed from that verbatim
citation rather than from any number the model computed.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, cast

from celery.result import AsyncResult
from sqlalchemy import delete, select

from .celery_app import celery_app
from .db import make_engine, make_sessionmaker, org_scoped_session
from .events import emit_event
from .export_control import record_ai_skip
from .lens_extract import _run_on_own_loop
from .lens_provider import LensProviderError
from .lens_provider import resolve as resolve_lens_provider
from .models import (
    Component,
    ComponentQuantity,
    ExportControlSubject,
    Part,
    PartFile,
    QuoteItem,
    VendorRfq,
    VendorRfqLine,
    VendorRfqRecipient,
    VendorRfqResponse,
    VendorRfqResponseLine,
    VendorRfqResponsePrice,
)
from .part_index import extract_pdf_text
from .storage import ObjectStorage
from .tasks import BaseTask
from .vendor_reply import RawVendorQuoteLine, vendor_reply_guard

logger = logging.getLogger("app.vendor_reply_lens")


class VendorReplyProvider(Protocol):
    """The vendor-reply slice of the Lens provider seam.

    Separate from :class:`app.lens.LensProvider` for the same reason M3.4's
    parts-list slice is: the M3.1 document-extraction fakes must keep type-checking
    without growing a method they never use."""

    async def parse_vendor_reply(
        self, body_text: str, part_numbers: list[str], pdf: bytes | None = None
    ) -> list[RawVendorQuoteLine]: ...


async def _read_blob(storage: ObjectStorage, key: str) -> bytes:
    return b"".join([chunk async for chunk in storage.stream(key)])


async def run_vendor_reply_extract(
    db_url: str,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    response_id: uuid.UUID,
    pdf_file_id: uuid.UUID | None,
) -> dict[str, Any]:
    """The task core: read the filed reply, ask Lens, guard, write suggestions.

    Idempotent — re-running replaces this response's extracted lines rather than
    appending, so a Celery redelivery cannot double a vendor's prices."""
    engine = make_engine(db_url)
    try:
        return await _extract(
            make_sessionmaker(engine),
            storage,
            org_id=org_id,
            response_id=response_id,
            pdf_file_id=pdf_file_id,
        )
    finally:
        await engine.dispose()


async def _extract(
    sessionmaker: Any,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    response_id: uuid.UUID,
    pdf_file_id: uuid.UUID | None,
) -> dict[str, Any]:
    """One org-scoped transaction: read the reply, ask Lens, guard, write."""
    async with org_scoped_session(sessionmaker, org_id) as session:
        response = await session.get(VendorRfqResponse, response_id)
        if response is None or not response.ai_extracted:
            # Either gone, or a human's portal submission superseded it while the task
            # was queued — in both cases there is nothing here to extract.
            return {"skipped": "no_extractable_response", "response_id": str(response_id)}
        if response.applied_at is not None:
            return {"skipped": "already_applied", "response_id": str(response_id)}

        recipient = await session.get(VendorRfqRecipient, response.recipient_id)
        if recipient is None:  # pragma: no cover — FK guarantees it
            return {"skipped": "no_recipient", "response_id": str(response_id)}
        rfq = await session.get(VendorRfq, recipient.rfq_id)
        if rfq is None:  # pragma: no cover
            return {"skipped": "no_rfq", "response_id": str(response_id)}

        lines = await _rfq_lines(session, rfq.id)
        if any(line.export_controlled for line in lines):
            # Defence in depth, mirroring ``lens_extract``: an export-flagged part's
            # documents never reach ANY provider (DECISIONS 2026-06-26), and a vendor's
            # reply routinely quotes the drawing back at us. The reply stays filed and
            # readable; only the model call is refused.
            logger.info(
                "vendor_reply_extract_skipped_export_controlled",
                extra={"response_id": str(response_id)},
            )
            # M6.9: the refusal is recorded, so the compliance log shows the
            # skips rather than asking an auditor to take them on trust.
            await record_ai_skip(
                session,
                org_id=org_id,
                subject_type=ExportControlSubject.vendor_rfq,
                subject_id=rfq.id,
                route="vendor_reply_lens.extract",
            )
            return {"skipped": "export_controlled", "response_id": str(response_id)}
        body_text = response.email_body_text or ""

        pdf_text: str | None = None
        pdf_bytes: bytes | None = None
        if pdf_file_id is not None:
            pdf_file = await session.get(PartFile, pdf_file_id)
            if pdf_file is not None:
                pdf_bytes = await _read_blob(storage, pdf_file.storage_key)
                # The guard's corpus: a price cited from the attachment must be
                # findable in the attachment's own text layer.
                pdf_text = extract_pdf_text(pdf_bytes)

        provider = cast("VendorReplyProvider", resolve_lens_provider())
        try:
            raw = await provider.parse_vendor_reply(
                body_text,
                [line.part_number for line in lines if line.part_number],
                pdf_bytes,
            )
        except LensProviderError as exc:
            # Deterministic model outcome — retrying burns an identical call.
            logger.warning(
                "vendor_reply_extract_provider_error",
                extra={"response_id": str(response_id), "code": exc.code},
            )
            return {"skipped": exc.code, "response_id": str(response_id)}

        kept, dropped = vendor_reply_guard(
            raw,
            body_text,
            pdf_text,
            currency=response.currency,
            allowed_quantities=await _offered_quantities(session, lines),
        )

        # Idempotency: this response's extracted answer is replaced wholesale. Prices
        # cascade from their line, so deleting the lines is enough.
        await session.execute(
            delete(VendorRfqResponseLine).where(VendorRfqResponseLine.response_id == response_id)
        )

        by_part = {
            (line.part_number or "").strip().casefold(): line.id
            for line in lines
            if line.part_number
        }
        written = 0
        unmatched = 0
        # One response line per RFQ line: the table is unique on (response, rfq_line),
        # and a model that splits one part's breaks across two objects (or two uncited
        # items falling back onto a single-line batch) would otherwise raise mid-write
        # and cost the estimator every suggestion in the reply.
        merged: dict[uuid.UUID, RawVendorQuoteLine] = {}
        for item in kept:
            key = (item.part_number or "").strip().casefold()
            rfq_line_id = by_part.get(key)
            if rfq_line_id is None:
                # A single-line RFQ needs no part number to be unambiguous; anything
                # else we refuse to guess at, rather than attach a price to the wrong
                # part (which M6.6 would then offer to apply to costing).
                if len(lines) == 1:
                    rfq_line_id = lines[0].id
                else:
                    unmatched += 1
                    continue
            prior = merged.get(rfq_line_id)
            if prior is None:
                merged[rfq_line_id] = item
            else:
                seen_breaks = {p.quantity for p in prior.prices}
                merged[rfq_line_id] = prior.model_copy(
                    update={
                        "cannot_quote": prior.cannot_quote or item.cannot_quote,
                        "notes": prior.notes or item.notes,
                        "prices": prior.prices
                        + [p for p in item.prices if p.quantity not in seen_breaks],
                    }
                )

        for rfq_line_id, item in merged.items():
            response_line = VendorRfqResponseLine(
                org_id=org_id,
                response_id=response_id,
                rfq_line_id=rfq_line_id,
                cannot_quote=item.cannot_quote,
                notes=item.notes,
            )
            session.add(response_line)
            await session.flush()
            for price in item.prices:
                session.add(
                    VendorRfqResponsePrice(
                        org_id=org_id,
                        response_line_id=response_line.id,
                        quantity=price.quantity,
                        unit_price=price.unit_price,
                        lead_time_days=price.lead_time_days,
                    )
                )
            written += 1

        # Belt and braces: extraction must never be what marks a response verified.
        response.verified = False
        await session.flush()

        await emit_event(
            session,
            org_id,
            "vendor_rfq.reply_extracted",
            {
                "rfq_id": str(rfq.id),
                "rfq_number": rfq.number,
                "recipient_id": str(recipient.id),
                "vendor_name": recipient.vendor_name,
                "response_id": str(response_id),
                "lines_extracted": written,
                "facts_dropped": dropped,
                # The estimator's cue, and the spec's own wording.
                "requires_verification": True,
            },
        )
        return {
            "response_id": str(response_id),
            "lines_extracted": written,
            "facts_dropped": dropped,
            "lines_unmatched": unmatched,
            "verified": False,
        }


@dataclass(frozen=True)
class RfqLine:
    """One line of the batch, as the extraction needs to see it."""

    id: uuid.UUID
    part_number: str | None
    component_id: uuid.UUID
    export_controlled: bool


async def _rfq_lines(session: Any, rfq_id: uuid.UUID) -> list[RfqLine]:
    """The batch's lines in order — how a model's answer is mapped back to the line the
    estimator will apply it to, plus the export flag that decides whether the reply may
    reach a model at all."""
    rows = (
        await session.execute(
            select(
                VendorRfqLine.id,
                Part.part_number,
                Component.id,
                QuoteItem.export_controlled,
            )
            .join(QuoteItem, QuoteItem.id == VendorRfqLine.quote_item_id)
            .join(Component, Component.id == QuoteItem.root_component_id)
            .join(Part, Part.id == Component.part_id)
            .where(VendorRfqLine.rfq_id == rfq_id)
            .order_by(VendorRfqLine.position)
        )
    ).all()
    return [
        RfqLine(
            id=line_id,
            part_number=part_number,
            component_id=component_id,
            export_controlled=bool(export_controlled),
        )
        for line_id, part_number, component_id, export_controlled in rows
    ]


async def _offered_quantities(session: Any, lines: list[RfqLine]) -> set[int]:
    """The quantity breaks the batch actually asked about.

    The guard checks prices against this: the quantity is the one field the model
    reports with no verbatim form of its own, so without it a correctly cited price
    could land on a break nobody asked for."""
    if not lines:
        return set()
    rows = (
        await session.execute(
            select(ComponentQuantity.quantity).where(
                ComponentQuantity.component_id.in_([line.component_id for line in lines])
            )
        )
    ).all()
    return {int(quantity) for (quantity,) in rows}


@celery_app.task(
    base=BaseTask,
    name="app.vendor_reply_extract",
    bind=True,
    soft_time_limit=180,
    time_limit=240,
)
def vendor_reply_extract_task(
    self: Any, org_id: str, response_id: str, pdf_file_id: str | None
) -> dict[str, Any]:
    """Celery wrapper around :func:`run_vendor_reply_extract` (idempotent, §5)."""
    task_id = self.request.id
    if task_id is not None:
        # Redelivery guard (M3.1 precedent): worker died after commit, before ack.
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    from .task_resources import resolve as resolve_task_resources

    db_url, storage = resolve_task_resources()
    result = _run_on_own_loop(
        run_vendor_reply_extract(
            db_url,
            storage,
            org_id=uuid.UUID(org_id),
            response_id=uuid.UUID(response_id),
            pdf_file_id=uuid.UUID(pdf_file_id) if pdf_file_id else None,
        )
    )
    return cast("dict[str, Any]", result)
