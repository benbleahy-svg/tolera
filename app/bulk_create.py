"""Bulk Create Line Items (M3.4 — spec ``#wingman`` "pre-fills Bulk Create
Line Items"; DemoB/04 is the UI ground truth).

Two endpoints on the quote:

* ``GET /api/quotes/{id}/bulk-create`` — the dialog prefill: the RFQ's
  ``ORIGINAL RFQ`` file chip, the guarded parts-list suggestions the
  email-body parse persisted (:mod:`app.email_parts`), and the deterministic
  file→part distribution preview.
* ``POST /api/quotes/{id}/bulk-create`` — the **explicit Accept** (AI-Governor,
  spec ``#lens-accept``): only here are line items created. Each accepted row
  binds the matching ingest-created part (attachments distributed) or a fresh
  file-less one, writes the human-confirmed part identity, and runs the
  add-line-item chain — root Component → quantity breaks → default-pricing
  snapshot → QuoteItem. Draft-only, serialized on the quote row lock (the
  ``add_quote_item`` precedent). No pricing math happens here (M1 owns it);
  Lens suggestions never touch Kalk (CLAUDE.md §5).

A quote with no ingested RFQ still gets the dialog (PP's generic paste-in
tool): ``status: none``, empty rows, Accept works the same.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .email_parts import RawLineItem, match_rows_to_parts
from .errors import AppError
from .models import Component, Part, PartFile, Quote, QuoteItem, RequestForQuote
from .parts import create_root_part
from .pricing import attach_default_pricing
from .quantities import MAX_QUANTITY_BREAKS, set_quantity_breaks
from .quotes import QuoteDetail, _is_editable, _load_detail

bulk_create_router = APIRouter(prefix="/api/quotes", tags=["bulk-create"])

#: More rows than any real RFQ email carries — a request-size guard, not a
#: product limit (the dialog's ADD ROW has no practical ceiling in PP).
MAX_BULK_ROWS = 100


class BulkCreateRow(BaseModel):
    """One dialog row at Accept time — human-owned input (the operator may
    have edited or added rows; the never-hallucinate guard applies to the AI
    *suggestions*, not to what the human typed)."""

    model_config = ConfigDict(extra="forbid")

    part_number: str = Field(min_length=1, max_length=200)
    revision: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    # Blank quantities default to 1 (the dialog's own copy — DemoB/04).
    quantities: list[Annotated[int, Field(ge=1)]] = Field(
        default_factory=list, max_length=MAX_QUANTITY_BREAKS
    )
    # The file-distribution binding the human REVIEWED in the prefill (its
    # ``matched_part_id``) — passed through so Accept binds what was previewed,
    # not a re-derivation over edited input (fresh-eyes review 🟡4). Rows
    # without one (hand-added, or part number edited) fall back to the
    # deterministic matcher.
    matched_part_id: uuid.UUID | None = None

    @field_validator("part_number")
    @classmethod
    def _strip_part_number(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("part_number must not be blank")
        return stripped


class BulkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[BulkCreateRow] = Field(min_length=1, max_length=MAX_BULK_ROWS)


class RfqFileOut(BaseModel):
    filename: str
    original_rfq: bool


class PrefillRow(BaseModel):
    """A suggestion row + its file-distribution preview."""

    part_number: str
    revision: str | None
    description: str | None
    quantities: list[int]
    requested_date: str | None
    confidence: float
    matched_part_id: uuid.UUID | None
    matched_filenames: list[str]


class BulkCreatePrefill(BaseModel):
    #: ``none`` (no ingested RFQ) | ``pending`` (parse not finished) |
    #: ``completed`` | ``failed`` — mirrors the persisted payload's status.
    status: str
    found_in: str | None
    rfq_files: list[RfqFileOut]
    rows: list[PrefillRow]


async def _candidate_parts(
    session: AsyncSession, rfq_id: uuid.UUID
) -> list[tuple[uuid.UUID, list[str]]]:
    """This RFQ's ingest-created parts still free to bind: live, filed with
    RFQ provenance, and not yet anchoring any component/line item."""
    bound = select(Component.part_id)
    rows = (
        await session.execute(
            select(PartFile.part_id, PartFile.filename)
            .join(Part, Part.id == PartFile.part_id)
            .where(
                PartFile.rfq_id == rfq_id,
                Part.deleted_at.is_(None),
                Part.id.not_in(bound),
            )
            # Part.id tiebreak: one ingest run stamps every part the same
            # created_at, and the matcher consumes "the first" candidate —
            # without a total order the GET preview and the POST accept could
            # distribute files differently (fresh-eyes review 🟡5).
            .order_by(Part.created_at, Part.id, PartFile.filename)
        )
    ).all()
    grouped: dict[uuid.UUID, list[str]] = {}
    for part_id, filename in rows:
        grouped.setdefault(part_id, []).append(filename)
    return list(grouped.items())


def _suggested_items(rfq: RequestForQuote | None) -> tuple[str, list[RawLineItem]]:
    """(status, items) from the persisted parse payload — tolerant of a
    payload written by an older prompt version (bad items are skipped)."""
    if rfq is None:
        return "none", []
    payload = rfq.suggested_line_items
    if payload is None:
        return "pending", []
    items: list[RawLineItem] = []
    for raw in payload.get("items", []):
        try:
            items.append(RawLineItem.model_validate(raw))
        except ValueError:
            continue
    return str(payload.get("status", "failed")), items


@bulk_create_router.get("/{quote_id}/bulk-create")
async def bulk_create_prefill(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> BulkCreatePrefill:
    """The dialog's opening state (RLS scopes everything to the active org)."""
    quote = await session.get(Quote, quote_id)
    if quote is None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    rfq = await session.scalar(select(RequestForQuote).where(RequestForQuote.quote_id == quote_id))
    parse_status, items = _suggested_items(rfq)

    candidates = await _candidate_parts(session, rfq.id) if rfq is not None else []
    matches = match_rows_to_parts([item.part_number for item in items], candidates)
    filenames_of = dict(candidates)
    rows = [
        PrefillRow(
            part_number=item.part_number,
            revision=item.revision,
            description=item.description,
            quantities=item.quantities,
            requested_date=item.requested_date,
            confidence=item.confidence,
            matched_part_id=matches.get(index),
            matched_filenames=filenames_of.get(matches[index], []) if index in matches else [],
        )
        for index, item in enumerate(items)
    ]
    eml = rfq.eml_filename if rfq is not None else None
    return BulkCreatePrefill(
        status=parse_status,
        found_in=eml,
        rfq_files=[RfqFileOut(filename=eml, original_rfq=True)] if eml else [],
        rows=rows,
    )


@bulk_create_router.post("/{quote_id}/bulk-create", status_code=status.HTTP_201_CREATED)
async def bulk_create_accept(
    quote_id: uuid.UUID,
    payload: BulkCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> QuoteDetail:
    """CREATE LINE ITEMS — the explicit Accept. Creates one line item per row,
    distributing this RFQ's still-unbound parts to their matching rows."""
    # Lock the quote FIRST (the add_quote_item TOCTOU + position-allocation
    # rationale) — bulk creation is serialized per quote.
    quote = await session.scalar(
        select(Quote)
        .where(Quote.id == quote_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if quote is None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    if not _is_editable(quote):
        raise AppError(
            "quote_locked",
            "Line items can only be added while the quote is a draft.",
            status_code=409,
        )

    rfq = await session.scalar(select(RequestForQuote).where(RequestForQuote.quote_id == quote_id))
    candidates = await _candidate_parts(session, rfq.id) if rfq is not None else []
    candidate_ids = {part_id for part_id, _ in candidates}

    # Explicitly-reviewed bindings first (each part consumable once) …
    matches: dict[int, uuid.UUID] = {}
    consumed: set[uuid.UUID] = set()
    for index, row in enumerate(payload.rows):
        if row.matched_part_id is None:
            continue
        if row.matched_part_id not in candidate_ids:
            # Stale (already bound / other quote / other org — RLS hides it):
            # a silent fallback would bind files the human never previewed.
            raise AppError(
                "invalid_matched_part",
                "Die vorgeschlagene Datei-Zuordnung ist nicht mehr verfügbar — Dialog neu öffnen.",
                status_code=422,
            )
        if row.matched_part_id not in consumed:
            matches[index] = row.matched_part_id
            consumed.add(row.matched_part_id)
    # … then the deterministic matcher for the rest.
    remaining = [(p, files) for p, files in candidates if p not in consumed]
    fallback = match_rows_to_parts(
        [row.part_number if i not in matches else "" for i, row in enumerate(payload.rows)],
        remaining,
    )
    matches.update(fallback)

    max_position = await session.scalar(
        select(func.max(QuoteItem.position)).where(QuoteItem.quote_id == quote.id)
    )
    next_position = (max_position or 0) + 1

    for index, row in enumerate(payload.rows):
        part: Part | None = None
        if index in matches:
            part = await session.get(Part, matches[index])
        if part is None:
            part = await create_root_part(session, quote.org_id)
        # The human confirmed this identity in the dialog — write it through.
        part.part_number = row.part_number
        if row.revision is not None:
            part.revision = row.revision
        if row.description is not None:
            part.description = row.description
        if not part.name:
            part.name = row.part_number

        component = Component(org_id=quote.org_id, part_id=part.id, is_root_component=True)
        session.add(component)
        await session.flush()
        # Duplicate values in the free-text quantity field are forgiven here
        # (deduped), not 422d — set_quantity_breaks keeps the strict contract
        # for its other callers.
        quantities = sorted(set(row.quantities)) or [1]
        await set_quantity_breaks(session, quote.org_id, component.id, quantities)
        # M1.10 attach-time snapshot of the org's pricing/discount defs.
        await attach_default_pricing(session, quote.org_id, component.id)
        session.add(
            QuoteItem(
                org_id=quote.org_id,
                quote_id=quote.id,
                root_component_id=component.id,
                position=next_position,
            )
        )
        next_position += 1

    if quote.started_at is None:
        quote.started_at = datetime.now(UTC)
    await session.flush()
    return await _load_detail(session, quote)
