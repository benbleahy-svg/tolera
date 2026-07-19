"""M6.5 — the outbound vendor RFQ email (spec ``#vendor-rfq`` → "Outbound RFQ email").

M6.4 composes a batch, scopes its files and mints a per-vendor portal token, but
deliberately stops short of the wire ("M6.5 owns the transport"). This module is that
transport: it turns one ``VendorRfq`` + one ``VendorRfqRecipient`` into a German,
white-label email carrying the parts table, the vendor's own file links and the
"Angebot abgeben" button, and it sends it.

Three things here are decisions rather than mechanics:

**The email is system-generated, not an ``EmailTemplate``.** The spec says so
outright, and it is the right call for a reason worth writing down: this message's
content is the disclosure boundary — an editable body would let an estimator paste
customer prices or a second vendor's numbers into a mail we send to a competitor.

**Auto-fill reads only *accepted* Lens findings.** Accepting a finding is what writes
``part_number``/``revision``/``description`` onto the Part (``lens_findings``), so those
fields already *are* the accepted extraction. ``material`` has no home on the Part, so
it is read from the findings directly — and only where a human accepted it. Mailing a
merely *suggested* value to a third party would auto-feed an unreviewed AI guess into
an outward disclosure, which is precisely what the suggestion-only invariant forbids
(CLAUDE.md §5).

**``Reply-To`` points at the org's ingest address.** The vendor may answer by replying
instead of using the portal, and the inbound webhook only listens on
``{slug}@rfq.tolera.eu`` — so the reply path the spec promises exists only because of
that one header, plus the ``RFQ-n`` reference in the subject that
:mod:`app.vendor_reply` matches on.

**The send runs on Celery, after the batch commits.** Mailing from inside the request
transaction would put a portal token on the wire for rows that are not committed yet: a
later recipient's 422, or any commit failure, would roll back a batch a vendor has
already been told about, leaving a permanently dead "Angebot abgeben" link. It would
also hold the ``vendor_rfq_counter`` row lock across N provider round trips, serialising
every concurrent send in the org behind a mail server. So :func:`run_vendor_rfq_send`
re-reads committed rows — the M3 post-commit pattern — one task per vendor, and a
failure for one vendor costs only that vendor's mail: its ``sent_at`` stays NULL, which
is exactly the state M6.6's follow-up nudge reads.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from celery.result import AsyncResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .celery_app import celery_app
from .config import Settings, get_settings
from .email_crypto import decrypt_credentials
from .email_providers import EmailProvider, OutboundEmail, get_platform_sender, get_provider
from .events import emit_event
from .impressum import impressum_footer_html
from .lens_extract import _run_on_own_loop
from .models import (
    Component,
    ComponentQuantity,
    ExtractionFinding,
    FindingStatus,
    Organization,
    Part,
    PartFile,
    Process,
    QuoteItem,
    QuoteToken,
    UserEmailConnection,
    VendorContact,
    VendorRfq,
    VendorRfqLine,
    VendorRfqRecipient,
)
from .pdf import _env, _safe_accent, logo_data_uri
from .services.org_service import RFQ_INGEST_DOMAIN
from .storage import ObjectStorage
from .tasks import BaseTask
from .vendor_reply import rfq_reference

logger = logging.getLogger("app.vendor_rfq_email")

#: Finding types the email may auto-fill from. Kept tiny on purpose: these are the
#: requirement facts a vendor needs to price a part that have no column on ``Part``
#: (which already carries the accepted identity findings). Anything else stays out of
#: an outward-facing message.
AUTOFILL_TYPES = ("material",)

#: A finding only auto-fills once a human has said yes to it (or corrected it).
ACCEPTED_STATUSES = (FindingStatus.accepted, FindingStatus.edited)


@dataclass(frozen=True)
class EmailLine:
    """One row of the outbound parts table."""

    part_id: uuid.UUID
    part_number: str | None
    revision: str | None
    description: str | None
    process: str | None
    quantities: list[int]
    estimator_notes: str | None
    file_ids: list[uuid.UUID]


@dataclass(frozen=True)
class SentEmail:
    """What the batch endpoint reports back per recipient."""

    recipient_id: uuid.UUID
    sent: bool
    message_id: str | None = None
    error: str | None = None


def portal_url(base_url: str, token_jwt: str) -> str:
    """The vendor's "Angebot abgeben" destination — the M6.2 unauthenticated route."""
    return f"{base_url.rstrip('/')}/vendor-rfq/{token_jwt}"


def file_url(base_url: str, token_jwt: str, file_id: uuid.UUID) -> str:
    """A download link scoped by the vendor's own token.

    The link carries no file grant of its own: the portal re-checks the token's
    ``file_permissions`` allowlist at fetch time (M6.4), so a forwarded email cannot
    widen what this vendor may read."""
    return f"{base_url.rstrip('/')}/api/public/vendor-rfq/{token_jwt}/files/{file_id}"


def ingest_address(org: Organization) -> str:
    """Where this org's vendor replies must land to be parsed at all."""
    return f"{org.slug}@{RFQ_INGEST_DOMAIN}"


def format_de_date(value: date | None) -> str | None:
    """German date formatting (``19.07.2026``) — the UI's locale, not ISO."""
    return value.strftime("%d.%m.%Y") if value else None


async def accepted_autofill(
    session: AsyncSession, part_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, str]]:
    """Accepted Lens findings, per part, for the fields the parts table auto-fills.

    Suggested findings are excluded by the ``status`` filter — see the module doc for
    why that filter is the whole point rather than an optimisation. Findings reach a
    part through the file they were extracted from."""
    if not part_ids:
        return {}
    rows = (
        await session.execute(
            select(
                PartFile.part_id,
                ExtractionFinding.type,
                ExtractionFinding.normalized_value,
                ExtractionFinding.value,
                ExtractionFinding.created_at,
            )
            .join(ExtractionFinding, ExtractionFinding.source_file_id == PartFile.id)
            .where(
                PartFile.part_id.in_(part_ids),
                ExtractionFinding.type.in_(AUTOFILL_TYPES),
                ExtractionFinding.status.in_(ACCEPTED_STATUSES),
            )
            .order_by(ExtractionFinding.created_at)
        )
    ).all()

    out: dict[uuid.UUID, dict[str, str]] = {}
    for part_id, kind, normalized, raw, _created in rows:
        value = normalized or raw
        if value:
            # Last accepted wins — a later correction supersedes an earlier accept.
            out.setdefault(part_id, {})[kind] = value
    return out


async def build_email_context(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    org: Organization,
    rfq: VendorRfq,
    recipient: VendorRfqRecipient,
    lines: list[EmailLine],
    token_jwt: str,
    base_url: str,
    contact_name: str | None,
    estimator_name: str | None,
    estimator_email: str | None,
    filenames: dict[uuid.UUID, str],
) -> dict[str, Any]:
    """Assemble everything the template renders — nothing wider than the portal shows."""
    autofill = await accepted_autofill(session, [line.part_id for line in lines])
    return {
        "shop": {
            "name": org.name,
            "accent_color": _safe_accent(org.brand_accent_color),
            "logo_data_uri": await logo_data_uri(storage, org.logo_object_key),
        },
        "rfq": {
            "reference": rfq_reference(rfq.number),
            "number": rfq.number,
            "need_by_date": format_de_date(rfq.need_by_date),
            "message": rfq.message,
        },
        "vendor": {"name": recipient.vendor_name, "contact_name": contact_name},
        "portal_url": portal_url(base_url, token_jwt),
        "lines": [
            {
                "part_number": line.part_number,
                "revision": line.revision,
                "description": line.description,
                "process": line.process,
                "material": autofill.get(line.part_id, {}).get("material"),
                "quantities": line.quantities,
                "estimator_notes": line.estimator_notes,
                "files": [
                    {
                        "filename": filenames.get(fid, str(fid)),
                        "url": file_url(base_url, token_jwt, fid),
                    }
                    for fid in line.file_ids
                ],
            }
            for line in lines
        ],
        "estimator": {"name": estimator_name, "email": estimator_email},
        # Trusted markup — `app.impressum` escapes its own values (M5.9 / DACH).
        "impressum_html": impressum_footer_html(org),
    }


def render_email_html(ctx: dict[str, Any]) -> str:
    """Render the outbound RFQ email body."""
    return _env.get_template("vendor_rfq_email.html").render(**ctx)


def render_email_text(ctx: dict[str, Any]) -> str:
    """The plain-text alternative.

    Written from the context rather than by stripping tags out of the HTML: the link a
    vendor must be able to click has to survive in a text-only client, and a stripped
    ``<a>`` loses its href."""
    rfq = ctx["rfq"]
    out = [f"Anfrage {rfq['reference']}", ""]
    if rfq["need_by_date"]:
        out.append(f"Angebot erbeten bis: {rfq['need_by_date']}")
    out.append(f"Empfänger: {ctx['vendor']['name']}")
    if rfq["message"]:
        out += ["", rfq["message"]]
    out += ["", "Positionen:"]
    for line in ctx["lines"]:
        parts = [line["part_number"] or "—"]
        if line["revision"]:
            parts.append(f"Rev. {line['revision']}")
        if line["description"]:
            parts.append(line["description"])
        out.append("  - " + " | ".join(parts))
        if line["material"]:
            out.append(f"      Werkstoff: {line['material']}")
        if line["process"]:
            out.append(f"      Verfahren: {line['process']}")
        if line["quantities"]:
            out.append("      Stückzahlen: " + " / ".join(str(q) for q in line["quantities"]))
        if line["estimator_notes"]:
            out.append(f"      Hinweis: {line['estimator_notes']}")
        for file in line["files"]:
            out.append(f"      Datei: {file['filename']} — {file['url']}")
    out += [
        "",
        f"Angebot abgeben: {ctx['portal_url']}",
        "",
        "Oder antworten Sie auf diese E-Mail — bitte lassen Sie "
        f"„{rfq['reference']}“ im Betreff stehen.",
    ]
    return "\n".join(out)


def build_subject(org: Organization, rfq: VendorRfq) -> str:
    """The subject line — the reference is what a reply is matched on, so it leads."""
    return f"{rfq_reference(rfq.number)} — Anfrage von {org.name}"


async def resolve_sender(
    session: AsyncSession, settings: Settings, *, user_id: uuid.UUID | None
) -> tuple[EmailProvider, dict[str, Any], str, str | None] | None:
    """The estimator's own mailbox if they have one, else the platform sender.

    Same ladder as ``quote_send`` — a vendor should see the shop's real address where
    one is connected. ``None`` when neither is available; the caller reports that per
    recipient rather than failing the batch."""
    if user_id is not None:
        connection = (
            await session.execute(
                select(UserEmailConnection).where(
                    UserEmailConnection.user_id == user_id,
                    UserEmailConnection.is_primary.is_(True),
                )
            )
        ).scalar_one_or_none()
        if connection is not None:
            return (
                get_provider(connection.connection_type),
                decrypt_credentials(
                    settings.email_credentials_key, connection.encrypted_credentials
                ),
                connection.from_address,
                connection.from_name,
            )

    platform = get_platform_sender(settings)
    if platform is None:
        return None
    return platform.provider, {}, platform.from_address, platform.from_name


async def send_to_recipient(
    session: AsyncSession,
    settings: Settings,
    storage: ObjectStorage,
    *,
    org: Organization,
    rfq: VendorRfq,
    recipient: VendorRfqRecipient,
    lines: list[EmailLine],
    token_jwt: str,
    contact_name: str | None,
    estimator_name: str | None,
    estimator_email: str | None,
    filenames: dict[uuid.UUID, str],
    sender: tuple[EmailProvider, dict[str, Any], str, str | None] | None,
) -> SentEmail:
    """Mail one vendor its copy, stamping ``sent_at``/``sent_message_id`` on success.

    Never raises: a provider outage for one vendor must not lose the other vendors'
    batches, which are already committed rows with valid tokens."""
    if not recipient.contact_email:
        return SentEmail(recipient.id, sent=False, error="no_contact_email")
    if sender is None:
        return SentEmail(recipient.id, sent=False, error="no_email_connection")

    provider, credentials, from_address, from_name = sender
    ctx = await build_email_context(
        session,
        storage,
        org=org,
        rfq=rfq,
        recipient=recipient,
        lines=lines,
        token_jwt=token_jwt,
        base_url=settings.app_base_url,
        contact_name=contact_name,
        estimator_name=estimator_name,
        estimator_email=estimator_email,
        filenames=filenames,
    )
    message = OutboundEmail(
        to=[recipient.contact_email],
        subject=build_subject(org, rfq),
        body_text=render_email_text(ctx),
        body_html=render_email_html(ctx),
        # The whole email channel hangs off this header — see the module doc.
        reply_to=ingest_address(org),
    )
    try:
        result = await provider.send(
            credentials, from_address=from_address, from_name=from_name, message=message
        )
    except Exception as exc:
        logger.warning(
            "vendor_rfq_email_failed",
            extra={"rfq_id": str(rfq.id), "recipient_id": str(recipient.id)},
            exc_info=exc,
        )
        return SentEmail(recipient.id, sent=False, error="send_failed")

    now = datetime.now(UTC)
    recipient.sent_at = now
    recipient.sent_message_id = result.message_id
    if rfq.sent_at is None:
        rfq.sent_at = now
    return SentEmail(recipient.id, sent=True, message_id=result.message_id)


# --------------------------------------------------------------------------- #
# The Celery send — re-reads committed rows (see the module doc)
# --------------------------------------------------------------------------- #
async def _send_batch_lines(
    session: AsyncSession, rfq_id: uuid.UUID, allowed: list[uuid.UUID]
) -> tuple[list[EmailLine], dict[uuid.UUID, str]]:
    """Rebuild this batch's parts table from committed rows, scoped to one vendor."""
    rows = (
        await session.execute(
            select(VendorRfqLine, QuoteItem, Component, Part, Process)
            .join(QuoteItem, QuoteItem.id == VendorRfqLine.quote_item_id)
            .join(Component, Component.id == QuoteItem.root_component_id)
            .join(Part, Part.id == Component.part_id)
            .outerjoin(Process, Process.id == Component.process_id)
            .where(VendorRfqLine.rfq_id == rfq_id)
            .order_by(VendorRfqLine.position)
        )
    ).all()

    breaks: dict[uuid.UUID, list[int]] = {}
    for component_id, quantity in (
        await session.execute(
            select(ComponentQuantity.component_id, ComponentQuantity.quantity)
            .where(ComponentQuantity.component_id.in_([c.id for _, _, c, _, _ in rows]))
            .order_by(ComponentQuantity.quantity)
        )
    ).all():
        breaks.setdefault(component_id, []).append(quantity)

    allowed_set = set(allowed)
    files = (
        await session.execute(
            select(PartFile.id, PartFile.part_id, PartFile.filename).where(
                PartFile.id.in_(allowed_set)
            )
        )
    ).all()
    filenames = {file_id: filename for file_id, _part_id, filename in files}
    by_part: dict[uuid.UUID, list[uuid.UUID]] = {}
    for file_id, part_id, _filename in files:
        by_part.setdefault(part_id, []).append(file_id)

    lines = [
        EmailLine(
            part_id=part.id,
            part_number=part.part_number,
            revision=part.revision,
            description=part.description,
            process=(process.external_name or process.name) if process else None,
            quantities=breaks.get(component.id, []),
            estimator_notes=line.estimator_notes,
            # Only this vendor's files, matched to their own line's part.
            file_ids=by_part.get(part.id, []),
        )
        for line, _item, component, part, process in rows
    ]
    return lines, filenames


async def run_vendor_rfq_send(
    db_url: str, storage: ObjectStorage, *, org_id: uuid.UUID, rfq_id: uuid.UUID
) -> dict[str, Any]:
    """Mail one vendor its RFQ. Idempotent: a recipient already stamped ``sent_at`` is
    skipped, so a Celery redelivery cannot mail a vendor twice."""
    from .db import make_engine, make_sessionmaker, org_scoped_session
    from .merge_fields import _org_members_by_id

    settings = get_settings()
    engine = make_engine(db_url)
    try:
        async with org_scoped_session(make_sessionmaker(engine), org_id) as session:
            rfq = await session.get(VendorRfq, rfq_id)
            if rfq is None:
                return {"skipped": "no_rfq", "rfq_id": str(rfq_id)}
            recipient = (
                (
                    await session.execute(
                        select(VendorRfqRecipient).where(VendorRfqRecipient.rfq_id == rfq_id)
                    )
                )
                .scalars()
                .first()
            )
            if recipient is None:  # pragma: no cover — M6.4 always creates one
                return {"skipped": "no_recipient", "rfq_id": str(rfq_id)}
            if recipient.sent_at is not None:
                return {"skipped": "already_sent", "rfq_id": str(rfq_id)}

            token_row = (
                (
                    await session.execute(
                        select(QuoteToken).where(QuoteToken.vendor_rfq_recipient_id == recipient.id)
                    )
                )
                .scalars()
                .first()
            )
            if token_row is None:  # pragma: no cover — minted with the recipient
                return {"skipped": "no_token", "rfq_id": str(rfq_id)}

            org = await session.get(Organization, org_id)
            if org is None:  # pragma: no cover
                return {"skipped": "no_org", "rfq_id": str(rfq_id)}

            allowed = [
                uuid.UUID(str(f))
                for f in (token_row.file_permissions or {}).get("part_file_ids", [])
            ]
            lines, filenames = await _send_batch_lines(session, rfq_id, allowed)

            members = await _org_members_by_id(session)
            estimator = members.get(str(rfq.created_by)) if rfq.created_by else None
            contact_name = None
            if recipient.vendor_contact_id is not None:
                contact = await session.get(VendorContact, recipient.vendor_contact_id)
                contact_name = contact.name if contact is not None else None

            sent = await send_to_recipient(
                session,
                settings,
                storage,
                org=org,
                rfq=rfq,
                recipient=recipient,
                lines=lines,
                token_jwt=token_row.token,
                contact_name=contact_name,
                estimator_name=_member_display_name(estimator),
                estimator_email=(estimator or {}).get("email") or None,
                filenames=filenames,
                sender=await resolve_sender(session, settings, user_id=rfq.created_by),
            )
            if sent.sent:
                await emit_event(
                    session,
                    org_id,
                    "vendor_rfq.sent",
                    {
                        "rfq_id": str(rfq.id),
                        "rfq_number": rfq.number,
                        "recipient_id": str(recipient.id),
                        "vendor_id": str(recipient.vendor_id) if recipient.vendor_id else None,
                        "vendor_name": recipient.vendor_name,
                        "line_count": len(lines),
                    },
                )
            return {"rfq_id": str(rfq_id), "sent": sent.sent, "error": sent.error}
    finally:
        await engine.dispose()


def _member_display_name(member: dict[str, Any] | None) -> str | None:
    """The estimator's name for the email's "Ihr Ansprechpartner" line."""
    if not member:
        return None
    name = " ".join(p for p in (member.get("first_name"), member.get("last_name")) if p).strip()
    return name or None


@celery_app.task(
    base=BaseTask, name="app.vendor_rfq_send", bind=True, soft_time_limit=120, time_limit=180
)
def vendor_rfq_send_task(self: Any, org_id: str, rfq_id: str) -> dict[str, Any]:
    """Celery wrapper around :func:`run_vendor_rfq_send` (idempotent, §5)."""
    task_id = self.request.id
    if task_id is not None:
        # Redelivery guard (M3.1 precedent): worker died after commit, before ack.
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    from .task_resources import resolve as resolve_task_resources

    db_url, storage = resolve_task_resources()
    result = _run_on_own_loop(
        run_vendor_rfq_send(db_url, storage, org_id=uuid.UUID(org_id), rfq_id=uuid.UUID(rfq_id))
    )
    return cast("dict[str, Any]", result)


def enqueue_vendor_rfq_send(org_id: uuid.UUID, rfq_id: uuid.UUID) -> None:
    """Post-commit enqueue. Never raises: the batch is committed and its portal link
    already works, so a broker outage must not turn a successful send into a 500 — the
    recipient simply stays unmailed with ``sent_at`` NULL, which is visible."""
    try:
        vendor_rfq_send_task.delay(str(org_id), str(rfq_id))
    except Exception:
        logger.warning(
            "vendor_rfq_send_enqueue_failed",
            extra={"org_id": str(org_id), "rfq_id": str(rfq_id)},
            exc_info=True,
        )
