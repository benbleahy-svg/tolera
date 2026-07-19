"""Vendor RFQ batch send (M6.4) — the compose payload and the blind multi-send.

Spec ``#vendor-rfq`` → "Outbound RFQ Flow". Two entry points (Quote Detail line
multi-select, and the Part Estimating Outside-Services section) open **one** modal; this
module is its server side:

* ``GET  /api/vendor-rfqs/compose`` — everything the modal renders: the selected lines
  with their quantity breaks and files (including the M2.4 **redacted** variants), the
  candidate vendors *filtered to the lines' process types* and ordered by the documented
  ranking (:mod:`app.vendor_rfq_ranking`), with the top few pre-checked.
* ``POST /api/vendor-rfqs/batch`` — the send. **One batch per vendor**, never one batch
  with many recipients: the spec requires BCC-isolation ("vendors cannot see each
  other"), and M6.2 made the batch+recipient the unit of token scoping, so blind send
  is structural rather than a filter someone must remember to apply. Each batch mints
  its own ``vendor_rfq``-scoped :class:`QuoteToken` carrying that vendor's own file
  allowlist.

**This block does not send email** — M6.5 owns the transport. A batch created here is
``open`` with ``sent_at`` unset until M6.5 mails it; the portal link already works,
which is what makes the M6.5 email a thin layer over an already-tested surface.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .av import scan_gate_error
from .config import Settings
from .deps import get_app_settings, get_session
from .errors import AppError
from .models import (
    Component,
    ComponentQuantity,
    CostingMode,
    Material,
    Operation,
    Part,
    PartFile,
    Process,
    Quote,
    QuoteItem,
    Vendor,
    VendorContact,
    VendorRfq,
    VendorRfqLine,
    VendorRfqRecipient,
    VendorRfqResponse,
    VendorRfqStatus,
    VendorStatus,
)
from .pricing import _lock_editable, reprice_component
from .quote_tokens import create_vendor_rfq_token
from .vendor_rfq_ranking import RankedVendor, VendorSignals, rank_vendors, suggested_ids

vendor_rfq_router = APIRouter(prefix="/api/vendor-rfqs", tags=["vendor-rfq"])

#: Suffix M2.4 gives a redacted copy (``<stem>-redacted.pdf``; DECISIONS 2026-07-13).
_REDACTED_SUFFIX = "-redacted"


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class RecipientIn(BaseModel):
    """One vendor on the send, with the files *that vendor* receives.

    ``part_file_ids`` is an allowlist and **fails closed**: omitting it grants no
    downloads at all, exactly as M6.2's token gate reads it. That is deliberate — the
    safe default for an outward disclosure is nothing, and the modal always sends an
    explicit list."""

    model_config = ConfigDict(extra="forbid")

    vendor_id: uuid.UUID
    #: Which quoting contact the RFQ addresses; defaults to the vendor's primary.
    vendor_contact_id: uuid.UUID | None = None
    part_file_ids: list[uuid.UUID] = Field(default_factory=list)


class BatchSendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_id: uuid.UUID
    quote_item_ids: Annotated[list[uuid.UUID], Field(min_length=1)]
    recipients: Annotated[list[RecipientIn], Field(min_length=1)]
    #: Soft response deadline (spec: the portal never closes on it).
    need_by_date: date | None = None
    #: Free text appended to the outbound email and shown verbatim on the portal.
    message: str | None = None
    #: Vendor-facing note per line item, keyed by quote-item id.
    estimator_notes: dict[uuid.UUID, str] = Field(default_factory=dict)
    #: ``buy`` flips every selected line to part-level Buy as part of the send —
    #: "the entire part is outsourced" is a decision the estimator makes *in* the
    #: modal, so recording it here is what lets M6.6 map the response to the right
    #: cost. ``None`` leaves each line's existing mode untouched.
    costing_mode: str | None = None


# --------------------------------------------------------------------------- #
# Compose — what the modal renders
# --------------------------------------------------------------------------- #
def _process_tags(op_names: Iterable[str], process_name: str | None) -> list[str]:
    """The capability tags a vendor must carry to be offered for these lines.

    For **operation-level** outsourcing the relevant process is the outsourced *step*
    (anodizing on an otherwise in-house CNC part — spec's own example), not the part's
    primary process, so outside-service operation names win. A line with no outside
    step at all (a part-level Buy candidate) falls back to its primary process, which
    is what a vendor quoting the whole part would need to do."""
    tags = {name.strip().casefold() for name in op_names if name and name.strip()}
    if not tags and process_name:
        tags = {process_name.strip().casefold()}
    return sorted(tags)


async def _line_rows(
    session: AsyncSession, quote_id: uuid.UUID, item_ids: Sequence[uuid.UUID]
) -> list[tuple[QuoteItem, Component, Part, Process | None]]:
    rows = (
        await session.execute(
            select(QuoteItem, Component, Part, Process)
            .join(
                Component,
                (Component.id == QuoteItem.root_component_id)
                & (Component.org_id == QuoteItem.org_id),
            )
            .join(Part, (Part.id == Component.part_id) & (Part.org_id == Component.org_id))
            .outerjoin(
                Process,
                (Process.id == Component.process_id) & (Process.org_id == Component.org_id),
            )
            .where(QuoteItem.quote_id == quote_id, QuoteItem.id.in_(item_ids))
            .order_by(QuoteItem.position)
        )
    ).all()
    found = {item.id for item, _, _, _ in rows}
    missing = [str(i) for i in item_ids if i not in found]
    if missing:
        # Either not this quote's line, or not this org's at all (RLS hid it) — one
        # message either way, so the error is not an existence oracle.
        raise AppError(
            "unknown_line_item",
            "One or more line items do not belong to this quote.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"quote_item_ids": missing},
        )
    return [(item, component, part, process) for item, component, part, process in rows]


def _default_file_ids(files: Sequence[PartFile]) -> list[uuid.UUID]:
    """Which of a part's files the modal pre-selects for a vendor.

    Everything, **except** that where a redacted copy exists its original is swapped
    out for it: a redaction was made precisely so the un-redacted drawing would not
    leave the shop, so the default must not re-offer the original. The estimator can
    still tick it back on — the spec's toggle is per vendor and per file.

    Pairing keeps the **extension**, not just the stem: ``zeichnung-redacted.pdf``
    supersedes ``zeichnung.pdf`` but must not also drop ``zeichnung.dxf``, which no
    one has redacted and which the vendor needs to quote."""

    def superseded_name(filename: str) -> str:
        stem, dot, ext = filename.rpartition(".")
        return f"{stem.removesuffix(_REDACTED_SUFFIX)}{dot}{ext}" if dot else filename

    superseded = {superseded_name(f.filename) for f in files if f.is_redacted}
    return [f.id for f in files if f.is_redacted or f.filename not in superseded]


async def _rank_candidates(
    session: AsyncSession,
    required_processes: list[str],
    materials: list[str],
    *,
    include_all: bool,
) -> list[RankedVendor]:
    """Candidate vendors for these lines, in the spec's documented order.

    Filtered to **active, non-archived** vendors whose capabilities carry one of the
    required process tags (an inactive vendor is a live row deliberately excluded from
    suggestions — M6.3). ``include_all`` is the estimator's explicit escape hatch for
    the case the directory's capability tags are simply incomplete."""
    vendors = (
        (
            await session.execute(
                select(Vendor).where(
                    Vendor.deleted_at.is_(None), Vendor.status == VendorStatus.active
                )
            )
        )
        .scalars()
        .all()
    )
    wanted = set(required_processes)
    material_tags = {m.casefold() for m in materials}

    def tags(vendor: Vendor, key: str) -> set[str]:
        raw: dict[str, Any] = vendor.capabilities or {}
        return {str(t).casefold() for t in (raw.get(key) or [])}

    candidates = [
        v for v in vendors if include_all or not wanted or (tags(v, "processes") & wanted)
    ]
    history = await _acceptance_history(session, [v.id for v in candidates])
    return rank_vendors(
        [
            VendorSignals(
                vendor_id=v.id,
                name=v.name,
                last_accepted_at=history[v.id][0] if v.id in history else None,
                acceptance_rate=history[v.id][1] if v.id in history else None,
                process_match=bool(tags(v, "processes") & wanted),
                material_match=bool(tags(v, "materials") & material_tags),
            )
            for v in candidates
        ]
    )


async def _acceptance_history(
    session: AsyncSession, vendor_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[datetime | None, float]]:
    """Per vendor: when a response of theirs was last **applied**, and their applied /
    submitted rate. Vendors absent from the result have no response history at all —
    which is exactly what earns them the spec's **New** label."""
    if not vendor_ids:
        return {}
    rows = (
        await session.execute(
            select(
                VendorRfqRecipient.vendor_id,
                func.max(VendorRfqResponse.applied_at),
                func.count(VendorRfqResponse.id),
                func.count(VendorRfqResponse.applied_at),
            )
            .join(
                VendorRfqResponse,
                (VendorRfqResponse.recipient_id == VendorRfqRecipient.id)
                & (VendorRfqResponse.org_id == VendorRfqRecipient.org_id),
            )
            .where(VendorRfqRecipient.vendor_id.in_(vendor_ids))
            .group_by(VendorRfqRecipient.vendor_id)
        )
    ).all()
    return {
        vendor_id: (last_applied, (applied / submitted) if submitted else 0.0)
        for vendor_id, last_applied, submitted, applied in rows
        if vendor_id is not None
    }


@vendor_rfq_router.get("/compose")
async def compose_batch(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    quote_id: Annotated[uuid.UUID, Query()],
    quote_item_ids: Annotated[list[uuid.UUID], Query()],
    include_all_vendors: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """Everything the batch-send modal renders for the selected line items."""
    rows = await _line_rows(session, quote_id, quote_item_ids)
    component_ids = [c.id for _, c, _, _ in rows]

    outside_ops = (
        (
            await session.execute(
                select(Operation).where(
                    Operation.component_id.in_(component_ids),
                    Operation.is_outside_service.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    ops_by_component: dict[uuid.UUID, list[str]] = {}
    for op in outside_ops:
        ops_by_component.setdefault(op.component_id, []).append(op.name)

    breaks: dict[uuid.UUID, list[int]] = {}
    for cq in (
        (
            await session.execute(
                select(ComponentQuantity)
                .where(ComponentQuantity.component_id.in_(component_ids))
                .order_by(ComponentQuantity.quantity)
            )
        )
        .scalars()
        .all()
    ):
        breaks.setdefault(cq.component_id, []).append(cq.quantity)

    files_by_part: dict[uuid.UUID, list[PartFile]] = {}
    for pf in (
        (
            await session.execute(
                select(PartFile)
                .where(PartFile.part_id.in_([p.id for _, _, p, _ in rows]))
                .order_by(PartFile.created_at)
            )
        )
        .scalars()
        .all()
    ):
        files_by_part.setdefault(pf.part_id, []).append(pf)

    required: set[str] = set()
    lines: list[dict[str, Any]] = []
    for item, component, part, process in rows:
        tags = _process_tags(
            ops_by_component.get(component.id, []),
            (process.external_name or process.name) if process is not None else None,
        )
        required.update(tags)
        files = files_by_part.get(part.id, [])
        lines.append(
            {
                "quote_item_id": str(item.id),
                "part_number": part.part_number,
                "revision": part.revision,
                "description": part.description,
                "process": (process.external_name or process.name) if process else None,
                "outside_processes": tags,
                "quantities": breaks.get(component.id, []),
                "costing_mode": item.costing_mode.value,
                # Surfaced so the estimator sees *before* sending that this part is
                # export-flagged; screening the disclosure itself is M6.9's audit.
                "export_controlled": item.export_controlled,
                "files": [
                    {
                        "id": str(f.id),
                        "filename": f.filename,
                        "size_bytes": f.size_bytes,
                        "is_redacted": f.is_redacted,
                    }
                    for f in files
                ],
                "default_file_ids": [str(i) for i in _default_file_ids(files)],
            }
        )

    # Signal 4 of the ranking: does the vendor work this material? Read off the
    # selected lines' components (a vendor's ``materials`` tags are free text, so the
    # match is a case-folded set intersection like the process one).
    material_ids = [c.material_id for _, c, _, _ in rows if c.material_id is not None]
    materials = (
        [
            m
            for m in (
                (
                    await session.execute(
                        select(Material.display_name).where(Material.id.in_(material_ids))
                    )
                )
                .scalars()
                .all()
            )
            if m
        ]
        if material_ids
        else []
    )
    ranked = await _rank_candidates(
        session, sorted(required), materials, include_all=include_all_vendors
    )
    suggested = suggested_ids(ranked)
    contacts = await _primary_contacts(session, [r.vendor_id for r in ranked])

    return {
        "quote_id": str(quote_id),
        "required_processes": sorted(required),
        "lines": lines,
        "vendors": [
            {
                "id": str(r.vendor_id),
                "name": r.name,
                "is_new": r.is_new,
                "suggested": r.vendor_id in suggested,
                "reasons": list(r.reasons),
                "process_match": r.signals.process_match,
                "material_match": r.signals.material_match,
                "contact_id": (str(contacts[r.vendor_id].id) if r.vendor_id in contacts else None),
                "contact_email": (contacts[r.vendor_id].email if r.vendor_id in contacts else None),
            }
            for r in ranked
        ],
    }


async def _primary_contacts(
    session: AsyncSession, vendor_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, VendorContact]:
    """The quoting contact each vendor's RFQ addresses — primary first, else any."""
    if not vendor_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(VendorContact)
                .where(VendorContact.vendor_id.in_(vendor_ids), VendorContact.deleted_at.is_(None))
                .order_by(VendorContact.is_primary.desc(), VendorContact.created_at)
            )
        )
        .scalars()
        .all()
    )
    contacts: dict[uuid.UUID, VendorContact] = {}
    for contact in rows:
        contacts.setdefault(contact.vendor_id, contact)
    return contacts


# --------------------------------------------------------------------------- #
# Send
# --------------------------------------------------------------------------- #
async def _next_rfq_number(session: AsyncSession, org_id: uuid.UUID) -> str:
    """Atomically allocate this org's next RFQ number (the ``quote_counter`` pattern,
    0008): the upsert row-locks the counter, so a concurrent multi-send serialises."""
    result = await session.execute(
        text(
            "INSERT INTO vendor_rfq_counter AS vc (org_id, last_number) VALUES (:org, 1) "
            "ON CONFLICT (org_id) DO UPDATE SET last_number = vc.last_number + 1 "
            "RETURNING last_number"
        ),
        {"org": str(org_id)},
    )
    return str(result.scalar_one())


@vendor_rfq_router.post("/batch", status_code=status.HTTP_201_CREATED)
async def send_batch(
    payload: BatchSendIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, Any]:
    """Blind multi-vendor send: **one batch, one recipient, one token per vendor**."""
    org_id = principal.active_org_id
    quote = await session.get(Quote, payload.quote_id)
    if quote is None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)

    rows = await _line_rows(session, payload.quote_id, payload.quote_item_ids)
    part_ids = {part.id for _, _, part, _ in rows}

    vendors = await _resolve_vendors(session, [r.vendor_id for r in payload.recipients])
    contacts = await _primary_contacts(session, list(vendors))
    allowed_files = await _validate_files(
        session, payload.recipients, part_ids, get_app_settings(request)
    )

    if payload.costing_mode is not None:
        # Flipping Make/Buy changes what the line costs, so it goes through the same
        # two gates the dedicated endpoint uses: the config-freeze/edit lock, and a
        # reprice. Without the reprice the line would persist a self-contradictory
        # state — flagged Buy but still carrying make-mode internal cost — until some
        # unrelated edit silently repriced it later.
        mode = _parse_costing_mode(payload.costing_mode)
        for item, component, _, _ in rows:
            await _lock_editable(session, component)
            item.costing_mode = mode
        await session.flush()
        for _, component, _, _ in rows:
            await reprice_component(session, org_id, component.id)

    secret = request.app.state.settings.resolve_quote_token_secret()
    now = datetime.now(UTC)
    created: list[dict[str, Any]] = []

    for recipient_in in payload.recipients:
        vendor = vendors[recipient_in.vendor_id]
        rfq = VendorRfq(
            org_id=org_id,
            quote_id=payload.quote_id,
            number=await _next_rfq_number(session, org_id),
            need_by_date=payload.need_by_date,
            message=payload.message,
            status=VendorRfqStatus.open,
            created_by=principal.user_id,
        )
        session.add(rfq)
        await session.flush()

        for position, (item, _, _, _) in enumerate(rows):
            session.add(
                VendorRfqLine(
                    org_id=org_id,
                    rfq_id=rfq.id,
                    quote_item_id=item.id,
                    position=position,
                    estimator_notes=payload.estimator_notes.get(item.id),
                )
            )

        contact = (
            await _resolve_contact(session, vendor, recipient_in.vendor_contact_id)
            if recipient_in.vendor_contact_id is not None
            else contacts.get(vendor.id)
        )
        recipient = VendorRfqRecipient(
            org_id=org_id,
            rfq_id=rfq.id,
            # Snapshot, not a join: renaming the vendor must not rewrite history.
            vendor_name=vendor.name,
            contact_email=contact.email if contact is not None else None,
            vendor_id=vendor.id,
            vendor_contact_id=contact.id if contact is not None else None,
        )
        session.add(recipient)
        await session.flush()

        _token_row, token = await create_vendor_rfq_token(
            session,
            secret,
            recipient,
            part_file_ids=allowed_files[recipient_in.vendor_id],
        )
        created.append(
            {
                "rfq_id": str(rfq.id),
                "number": rfq.number,
                "status": rfq.status.value,
                "vendor_id": str(vendor.id),
                "vendor_name": vendor.name,
                "contact_email": recipient.contact_email,
                "recipient_id": str(recipient.id),
                # M6.5 turns this into the "Submit Your Quote" link; returned here so
                # the send is verifiable end-to-end before the email layer exists.
                "portal_token": token,
                "created_at": now.isoformat(),
            }
        )

    await session.flush()
    return {"rfqs": created}


def _parse_costing_mode(raw: str) -> CostingMode:
    try:
        return CostingMode(raw)
    except ValueError as exc:
        raise AppError(
            "invalid_costing_mode",
            "costing_mode must be 'make' or 'buy'.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc


async def _resolve_contact(
    session: AsyncSession, vendor: Vendor, contact_id: uuid.UUID
) -> VendorContact:
    """The quoting contact this vendor's RFQ addresses — **checked against the vendor**.

    The composite FK only pins the contact to the same *org*, not the same *vendor*, so
    without this a client-supplied id could address vendor A's RFQ — and the portal
    token carrying A's file allowlist — to a competing supplier's inbox. That would
    defeat both the blind send and the per-vendor file scoping this block exists for."""
    contact = await session.get(VendorContact, contact_id)
    if contact is None or contact.vendor_id != vendor.id or contact.deleted_at is not None:
        raise AppError(
            "unknown_vendor_contact",
            "The selected quoting contact does not belong to this vendor.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"vendor_id": str(vendor.id), "vendor_contact_id": str(contact_id)},
        )
    return contact


async def _resolve_vendors(
    session: AsyncSession, vendor_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Vendor]:
    """Load the picked vendors, refusing anything not a live vendor of this org.

    RLS already hides another org's rows, so a foreign id simply fails to load — the
    422 below is what the estimator sees, never a cross-org read."""
    if len(set(vendor_ids)) != len(vendor_ids):
        raise AppError(
            "duplicate_vendor",
            "A vendor may appear only once in a batch send.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    rows = (
        (
            await session.execute(
                select(Vendor).where(Vendor.id.in_(vendor_ids), Vendor.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    vendors = {v.id: v for v in rows}
    missing = [str(v) for v in vendor_ids if v not in vendors]
    if missing:
        raise AppError(
            "unknown_vendor",
            "One or more selected vendors do not exist in this organization.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"vendor_ids": missing},
        )
    return vendors


async def _validate_files(
    session: AsyncSession,
    recipients: Sequence[RecipientIn],
    part_ids: set[uuid.UUID],
    settings: Settings,
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Every per-vendor allowlist may only name files of the parts in this batch.

    The portal's download route enforces the same rule at fetch time (M6.2); rejecting
    it here too means the estimator finds out at send, not the vendor at download."""
    requested = {fid for r in recipients for fid in r.part_file_ids}
    if requested:
        rows = (
            (
                await session.execute(
                    select(PartFile).where(
                        PartFile.id.in_(requested), PartFile.part_id.in_(part_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        valid = {row.id for row in rows}
        stray = sorted(str(f) for f in requested - valid)
        if stray:
            raise AppError(
                "file_not_in_batch",
                "A selected file does not belong to a part in this RFQ.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"part_file_ids": stray},
            )
        # M3.13 — the forward gate at *send* time. Granting a vendor a token for a
        # file is the outbound disclosure; catching it here means the estimator
        # finds out now, not the vendor at download (the same reasoning as the
        # allowlist check above). The portal download re-checks independently, so
        # a file that turns infected after the send is still blocked.
        blocked = sorted(str(row.id) for row in rows if scan_gate_error(row, settings) is not None)
        if blocked:
            raise AppError(
                "file_scan_not_clean",
                "Eine ausgewählte Datei ist noch nicht virengeprüft oder wurde gesperrt.",
                status_code=status.HTTP_409_CONFLICT,
                details={"part_file_ids": blocked},
            )
    return {r.vendor_id: list(r.part_file_ids) for r in recipients}


# --------------------------------------------------------------------------- #
# Awaiting counts — the in-flight chip + the workflow soft warning
# --------------------------------------------------------------------------- #
async def awaiting_counts_by_item(
    session: AsyncSession, quote_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Per line item: how many vendors on **open** batches have not answered yet.

    Drives the spec's "⏳ Awaiting N vendor response(s)" chip, and — summed over the
    lines that have any — the soft warning when the estimator advances the workflow
    stage. A recipient stops counting the moment its response row exists, which is
    what makes the chip disappear "once all vendors have responded"."""
    rows = (
        await session.execute(
            select(VendorRfqLine.quote_item_id, func.count(VendorRfqRecipient.id))
            .join(
                VendorRfq,
                (VendorRfq.id == VendorRfqLine.rfq_id) & (VendorRfq.org_id == VendorRfqLine.org_id),
            )
            .join(
                VendorRfqRecipient,
                (VendorRfqRecipient.rfq_id == VendorRfq.id)
                & (VendorRfqRecipient.org_id == VendorRfq.org_id),
            )
            .outerjoin(
                VendorRfqResponse,
                (VendorRfqResponse.recipient_id == VendorRfqRecipient.id)
                & (VendorRfqResponse.org_id == VendorRfqRecipient.org_id),
            )
            .where(
                VendorRfq.quote_id == quote_id,
                VendorRfq.status == VendorRfqStatus.open,
                VendorRfqResponse.id.is_(None),
            )
            .group_by(VendorRfqLine.quote_item_id)
        )
    ).all()
    return dict(rows)  # type: ignore[arg-type]
