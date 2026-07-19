"""Vendor RFQ portal — the public, unauthenticated vendor surface (M6.2).

Spec ``#vendor-rfq`` ("Vendor Portal (unauthenticated)"): a vendor opens
``/vendor-rfq/:token`` from the RFQ email with no account, sees the parts table for
**exactly its RFQ batch**, fills the per-line response form, and submits.

Three invariants shape it, two inherited from the buyer portal (M5.1) and one new:

* **No auth, but still org-scoped.** The endpoints bypass ``get_principal`` (there is
  no Clerk session) and open an :func:`~app.db.org_scoped_session` for the *token's*
  org — the signed ``org`` claim — so Postgres RLS is in force before any read.
* **Field-gating is an allowlist.** The vendor payload is built field by field from the
  loaded rows; it carries part identity, process, quantity breaks and the estimator's
  vendor-facing note, and **never** the customer, the customer price, the internal cost
  or margin, or any line outside the batch. A vendor is a different counterparty from
  the buyer — it must not learn what the shop is charging for the part.
* **Scoped to a recipient, not a quote.** The token names one
  :class:`~app.models.VendorRfqRecipient`; sends are blind, so nothing in the payload
  reveals the other vendors on the same batch.

**The portal never closes.** ``need_by_date`` is a soft cutoff: a submission after it
succeeds and is merely stamped ``is_late`` (the estimator's alert is M6.6). This is the
same soft-expiry posture as the buyer token's missing ``exp`` claim (M5.1) — the spec is
explicit that "the portal never shows a hard 'closed' state".

Money is exchanged as **exact decimal strings** parsed to ``Decimal`` (never a float —
CLAUDE.md §5), with the currency carried on the response.
"""

from __future__ import annotations

import contextlib
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import org_scoped_session
from .deps import get_storage
from .errors import AppError
from .events import emit_event
from .metrics import vendor_rfq_portal_events
from .models import (
    Component,
    ComponentQuantity,
    Organization,
    Part,
    PartFile,
    Process,
    QuoteItem,
    QuoteToken,
    QuoteTokenAccess,
    QuoteTokenScope,
    VendorRfq,
    VendorRfqLine,
    VendorRfqRecipient,
    VendorRfqResponse,
    VendorRfqResponseLine,
    VendorRfqResponsePrice,
)
from .parts import _safe_filename  # house convention: email_ingest/email_sync do the same
from .pdf import html_to_pdf, render_vendor_rfq_html, weasyprint_available
from .quote_tokens import InvalidToken, decode_jwt
from .storage import ObjectStorage

vendor_portal_router = APIRouter(prefix="/api/public/vendor-rfq", tags=["vendor-portal"])

#: A vendor's own quote PDF is the only upload the portal accepts, and it is capped
#: well below the authenticated CAD limits — this surface is unauthenticated.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
#: Bounds mirroring what ``vendor_rfq_response_price`` can actually store, so an
#: out-of-range answer is a clean 422 rather than a database error on insert.
_PRICE_DECIMALS = 4  # numeric(14, 4)
MAX_UNIT_PRICE = Decimal(10) ** 10  # numeric(14, 4) → ten integral digits
MAX_LEAD_TIME_DAYS = 3650  # ten years; anything beyond is a typo, not a lead time
MAX_QUANTITY = 10_000_000


# --------------------------------------------------------------------------- #
# Submission payload (validated at the edge — Pydantic v2, CLAUDE.md §5).
# --------------------------------------------------------------------------- #
class VendorPriceIn(BaseModel):
    """One quantity break's answer. ``unit_price`` is an exact decimal string."""

    model_config = ConfigDict(extra="forbid")

    # Both bounds are upper-bounded as well as lower-bounded: the columns are plain
    # ``integer``, so an unbounded value would be a 500 on insert, not a 422.
    quantity: int = Field(gt=0, le=MAX_QUANTITY)
    unit_price: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0, le=MAX_LEAD_TIME_DAYS)


class VendorLineIn(BaseModel):
    """The vendor's answer for one line of the batch."""

    model_config = ConfigDict(extra="forbid")

    rfq_line_id: uuid.UUID
    cannot_quote: bool = False
    notes: str | None = None
    prices: list[VendorPriceIn] = Field(default_factory=list)


class VendorResponseIn(BaseModel):
    """A whole portal submission (quote-level fields + the per-line answers)."""

    model_config = ConfigDict(extra="forbid")

    currency: str = "EUR"
    valid_until: date | None = None
    notes: str | None = None
    lines: list[VendorLineIn] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Token resolution.
# --------------------------------------------------------------------------- #
def _rejected() -> AppError:
    """A single, non-enumerating rejection for every bad-token path (no oracle).

    Malformed, forged, revoked, wrong-scope and dangling-recipient all return the
    same 401 so the endpoint cannot be used to probe which RFQs exist."""
    return AppError("invalid_token", "This RFQ link is not valid.", status_code=401)


@dataclass
class _Scope:
    """Everything a verified vendor token unlocks — resolved once per request."""

    token_row: QuoteToken
    recipient: VendorRfqRecipient
    rfq: VendorRfq
    org: Organization


async def _resolve(session: AsyncSession, token: str, secret: str) -> _Scope:
    """Verify ``token`` and load its recipient + batch + org, or raise 401.

    Both halves of the credential are checked: the **signature** (an attacker cannot
    forge a token for another org without the HMAC secret) and the **row**, which is
    the authority for revocation and must still point at the recipient the claim
    names — a re-pointed row can never widen a live link's scope."""
    try:
        claims = decode_jwt(secret, token)
    except InvalidToken as exc:
        raise _rejected() from exc
    if claims.scope is not QuoteTokenScope.vendor_rfq or claims.rfq_recipient_id is None:
        raise _rejected()

    token_row = await session.get(QuoteToken, claims.token_id)
    if (
        token_row is None
        or token_row.is_revoked
        or token_row.scope is not QuoteTokenScope.vendor_rfq
        or token_row.vendor_rfq_recipient_id != claims.rfq_recipient_id
    ):
        raise _rejected()

    recipient = await session.get(VendorRfqRecipient, claims.rfq_recipient_id)
    if recipient is None:
        raise _rejected()
    rfq = await session.get(VendorRfq, recipient.rfq_id)
    if rfq is None:
        raise _rejected()
    org = await session.get(Organization, rfq.org_id)
    if org is None:  # RLS breakage — never invent shop identity
        raise _rejected()
    return _Scope(token_row=token_row, recipient=recipient, rfq=rfq, org=org)


def _allowed_file_ids(token_row: QuoteToken) -> set[uuid.UUID]:
    """The vendor's file allowlist from ``file_permissions`` (empty when unset).

    Fail **closed**: a token with no allowlist grants no downloads. The per-vendor
    redacted-variant choice (M6.4) is therefore enforced by the credential, not by
    whichever file ids the UI happened to render."""
    perms = token_row.file_permissions or {}
    raw = perms.get("part_file_ids") or []
    out: set[uuid.UUID] = set()
    for value in raw:
        try:
            out.add(uuid.UUID(str(value)))
        except ValueError:  # a malformed entry grants nothing, it never widens access
            continue
    return out


# --------------------------------------------------------------------------- #
# The vendor-facing projection.
# --------------------------------------------------------------------------- #
@dataclass
class _LineRow:
    """One batch line joined to the part identity the vendor is allowed to see."""

    line: VendorRfqLine
    part: Part
    process: Process | None
    quantities: list[int]


async def _load_lines(session: AsyncSession, rfq: VendorRfq) -> list[_LineRow]:
    """Load the batch's lines with part identity, process and quantity breaks."""
    rows = (
        await session.execute(
            select(VendorRfqLine, QuoteItem, Part, Process)
            .join(
                QuoteItem,
                (QuoteItem.id == VendorRfqLine.quote_item_id)
                & (QuoteItem.org_id == VendorRfqLine.org_id),
            )
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
            .where(VendorRfqLine.rfq_id == rfq.id)
            .order_by(VendorRfqLine.position, VendorRfqLine.created_at)
        )
    ).all()

    component_ids = [qi.root_component_id for _, qi, _, _ in rows]
    breaks: dict[uuid.UUID, list[int]] = {}
    if component_ids:
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

    return [
        _LineRow(
            line=line,
            part=part,
            process=process,
            quantities=breaks.get(qi.root_component_id, []),
        )
        for line, qi, part, process in rows
    ]


async def _files_for(
    session: AsyncSession, rows: list[_LineRow], allowed: set[uuid.UUID]
) -> dict[uuid.UUID, list[PartFile]]:
    """Map each batch line to the files this vendor may download for it.

    Two filters, both required: the file must belong to the line's part *and* be on the
    token's allowlist. A file on the allowlist but not on a batch part is not offered."""
    if not allowed:
        return {}
    part_ids = {row.part.id for row in rows}
    files = (
        (
            await session.execute(
                select(PartFile)
                .where(PartFile.part_id.in_(part_ids), PartFile.id.in_(allowed))
                .order_by(PartFile.created_at)
            )
        )
        .scalars()
        .all()
    )
    by_part: dict[uuid.UUID, list[PartFile]] = {}
    for pf in files:
        by_part.setdefault(pf.part_id, []).append(pf)
    return {row.line.id: by_part.get(row.part.id, []) for row in rows}


def _money(value: Decimal | None) -> str | None:
    """Exact decimal string (never a float over the wire — CLAUDE.md §5)."""
    return None if value is None else str(value)


async def _existing_response(
    session: AsyncSession, recipient: VendorRfqRecipient
) -> dict[str, Any] | None:
    """The vendor's own prior submission, so the portal reopens pre-filled.

    A vendor has no login: without this, correcting a typo would mean retyping the whole
    form (or the estimator receiving a second, ambiguous response)."""
    response = (
        await session.execute(
            select(VendorRfqResponse).where(VendorRfqResponse.recipient_id == recipient.id)
        )
    ).scalar_one_or_none()
    if response is None:
        return None

    lines = (
        (
            await session.execute(
                select(VendorRfqResponseLine).where(
                    VendorRfqResponseLine.response_id == response.id
                )
            )
        )
        .scalars()
        .all()
    )
    prices_by_line: dict[uuid.UUID, list[VendorRfqResponsePrice]] = {}
    if lines:
        for price in (
            (
                await session.execute(
                    select(VendorRfqResponsePrice)
                    .where(VendorRfqResponsePrice.response_line_id.in_([ln.id for ln in lines]))
                    .order_by(VendorRfqResponsePrice.quantity)
                )
            )
            .scalars()
            .all()
        ):
            prices_by_line.setdefault(price.response_line_id, []).append(price)

    return {
        "currency": response.currency,
        "valid_until": response.valid_until.isoformat() if response.valid_until else None,
        "notes": response.notes,
        "is_late": response.is_late,
        "submitted_at": response.submitted_at.isoformat(),
        "attachment_filename": response.attachment_filename,
        "lines": [
            {
                "rfq_line_id": str(ln.rfq_line_id),
                "cannot_quote": ln.cannot_quote,
                "notes": ln.notes,
                "prices": [
                    {
                        "quantity": p.quantity,
                        "unit_price": _money(p.unit_price),
                        "lead_time_days": p.lead_time_days,
                    }
                    for p in prices_by_line.get(ln.id, [])
                ],
            }
            for ln in lines
        ],
    }


async def build_vendor_payload(
    session: AsyncSession, scope: _Scope, now: datetime
) -> dict[str, Any]:
    """Assemble the vendor-facing payload for one RFQ batch (allowlist projection).

    ``is_past_due`` is **informational only** — the form stays open and submittable
    after it (spec "Soft cutoff behaviour")."""
    rows = await _load_lines(session, scope.rfq)
    files = await _files_for(session, rows, _allowed_file_ids(scope.token_row))
    past_due = scope.rfq.need_by_date is not None and scope.rfq.need_by_date < now.date()

    return {
        "rfq_number": scope.rfq.number,
        "need_by_date": (
            scope.rfq.need_by_date.isoformat() if scope.rfq.need_by_date is not None else None
        ),
        # Informational: the portal never renders a closed state (spec).
        "is_past_due": past_due,
        "message": scope.rfq.message,
        "shop": {
            "name": scope.org.name,
            "slug": scope.org.slug,
            "country": scope.org.country.value,
            "locale": scope.org.locale,
        },
        # The vendor's own identity only — the batch's other recipients are never
        # exposed (blind multi-send, spec "BCC-isolated").
        "vendor": {"name": scope.recipient.vendor_name},
        "lines": [
            {
                "id": str(row.line.id),
                "part_number": row.part.part_number,
                "revision": row.part.revision,
                "description": row.part.description,
                "process": (
                    (row.process.external_name or row.process.name)
                    if row.process is not None
                    else None
                ),
                "quantities": row.quantities,
                "estimator_notes": row.line.estimator_notes,
                "files": [
                    {
                        "id": str(pf.id),
                        "filename": pf.filename,
                        "size_bytes": pf.size_bytes,
                    }
                    for pf in files.get(row.line.id, [])
                ],
            }
            for row in rows
        ],
        "response": await _existing_response(session, scope.recipient),
    }


# --------------------------------------------------------------------------- #
# Submission.
# --------------------------------------------------------------------------- #
def _invalid(message: str) -> AppError:
    """A 422 the vendor can act on (unlike the deliberately opaque token rejection)."""
    return AppError("invalid_response", message, status_code=422)


def _parse_price(raw: str | None) -> Decimal | None:
    """Parse a money string exactly, or raise 422 — never a float, never a guess.

    Every rejection here is a value the ``numeric(14,4)`` column could not store
    faithfully, so refusing is the only honest answer on a *money* field:

    * ``NaN``/``Infinity`` parse as valid Decimals but are not prices — and comparing
      a NaN raises, so the range check itself must not run before this guard.
    * A magnitude past ``numeric(14,4)``'s ten integral digits would be a database
      error on insert (an unauthenticated 500) rather than a usable answer.
    * **More than four decimal places is refused, never rounded** — silently storing
      ``1.00005`` as ``1.0001`` would show the vendor a price it did not quote."""
    if raw is None or raw.strip() == "":
        return None
    try:
        value = Decimal(raw.strip())
    except InvalidOperation as exc:
        raise _invalid(f"'{raw}' is not a valid price.") from exc
    if not value.is_finite():
        raise _invalid(f"'{raw}' is not a valid price.")
    if value < 0:
        raise _invalid("A price cannot be negative.")
    if value >= MAX_UNIT_PRICE:
        raise _invalid("That price is too large.")
    if -value.as_tuple().exponent > _PRICE_DECIMALS:  # type: ignore[operator]
        raise _invalid(f"A price may have at most {_PRICE_DECIMALS} decimal places.")
    return value


async def _save_response(
    session: AsyncSession,
    scope: _Scope,
    payload: VendorResponseIn,
    now: datetime,
) -> VendorRfqResponse:
    """Persist (or replace) this recipient's submission.

    A re-submit **replaces** the prior answer rather than appending a second one: the
    portal has no login, so two live responses from one vendor would leave M6.6's Apply
    ambiguous. The batch's own lines are the allowlist — a line id from another batch is
    rejected, which is what keeps one vendor's form from writing into another's RFQ."""
    valid_lines = {
        row.line.id: row
        for row in await _load_lines(session, scope.rfq)  # re-read under the request's RLS session
    }
    seen: set[uuid.UUID] = set()
    for line in payload.lines:
        if line.rfq_line_id not in valid_lines:
            raise _invalid("A submitted line is not part of this RFQ.")
        if line.rfq_line_id in seen:
            raise _invalid("Each line may be answered only once.")
        seen.add(line.rfq_line_id)
        if line.cannot_quote and line.prices:
            raise _invalid("A line marked 'cannot quote' must carry no prices.")
        offered = set(valid_lines[line.rfq_line_id].quantities)
        quantities: set[int] = set()
        for price in line.prices:
            if offered and price.quantity not in offered:
                raise _invalid(f"Quantity {price.quantity} was not requested for this part.")
            # ``UNIQUE (response_line_id, quantity)`` would otherwise turn a repeated
            # break into an integrity error (a 500 on a public endpoint), and there is
            # no honest way to pick which of two prices for the same quantity wins.
            if price.quantity in quantities:
                raise _invalid(f"Quantity {price.quantity} was priced twice for this part.")
            quantities.add(price.quantity)
            # Parse every price up front: validation must fully precede persistence, so
            # a bad value on the last line cannot leave the first lines' rows written.
            _parse_price(price.unit_price)

    currency = payload.currency.strip().upper()
    if len(currency) != 3:
        raise _invalid("Currency must be a 3-letter ISO code.")

    existing = (
        await session.execute(
            select(VendorRfqResponse).where(VendorRfqResponse.recipient_id == scope.recipient.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        response = VendorRfqResponse(
            org_id=scope.rfq.org_id,
            recipient_id=scope.recipient.id,
            source="portal",
        )
        session.add(response)
    else:
        response = existing
        # Replace the prior answer wholesale — the cascade clears its lines/prices.
        for stale in (
            (
                await session.execute(
                    select(VendorRfqResponseLine).where(
                        VendorRfqResponseLine.response_id == response.id
                    )
                )
            )
            .scalars()
            .all()
        ):
            await session.delete(stale)
        await session.flush()

    response.currency = currency
    response.valid_until = payload.valid_until
    response.notes = payload.notes
    response.submitted_at = now
    # The vendor typed these numbers themselves, so there is nothing for the estimator
    # to verify — unlike M6.5's Lens-extracted email channel, which lands
    # ``ai_extracted``/not ``verified`` and must be confirmed before M6.6 may apply it.
    # A portal submission also *supersedes* an earlier extraction: a human's own figures
    # outrank a model's reading of their email.
    response.source = "portal"
    response.ai_extracted = False
    response.verified = True
    # Soft cutoff: a late submission is accepted and merely stamped (spec).
    response.is_late = scope.rfq.need_by_date is not None and scope.rfq.need_by_date < now.date()
    await session.flush()

    for line in payload.lines:
        response_line = VendorRfqResponseLine(
            org_id=scope.rfq.org_id,
            response_id=response.id,
            rfq_line_id=line.rfq_line_id,
            cannot_quote=line.cannot_quote,
            notes=line.notes,
        )
        session.add(response_line)
        await session.flush()
        for price in line.prices:
            session.add(
                VendorRfqResponsePrice(
                    org_id=scope.rfq.org_id,
                    response_line_id=response_line.id,
                    quantity=price.quantity,
                    unit_price=_parse_price(price.unit_price),
                    lead_time_days=price.lead_time_days,
                )
            )
    await session.flush()
    return response


# --------------------------------------------------------------------------- #
# The public endpoints.
# --------------------------------------------------------------------------- #
def _secret(request: Request) -> str:
    secret: str = request.app.state.settings.resolve_quote_token_secret()
    return secret


def _sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    maker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    return maker


@vendor_portal_router.get("/{token}")
async def get_vendor_rfq(token: str, request: Request) -> dict[str, Any]:
    """Return the vendor view of one RFQ batch for a valid ``vendor_rfq`` token.

    401 on a malformed/forged/revoked/wrong-scope token. A successful load is recorded
    in the access log and counted on the open→submit funnel (spec: usage instrumentation
    from day one)."""
    now = datetime.now(UTC)
    async with org_scoped_session(_sessionmaker(request), _claim_org(request, token)) as session:
        scope = await _resolve(session, token, _secret(request))
        payload = await build_vendor_payload(session, scope, now)
        session.add(
            QuoteTokenAccess(
                org_id=scope.rfq.org_id,
                quote_token_id=scope.token_row.id,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await emit_event(
            session,
            scope.rfq.org_id,
            "vendor_rfq.opened",
            {
                "rfq_id": str(scope.rfq.id),
                "rfq_number": scope.rfq.number,
                "recipient_id": str(scope.recipient.id),
                "vendor_name": scope.recipient.vendor_name,
            },
        )
    vendor_rfq_portal_events.labels(event="opened").inc()
    return payload


def _claim_org(request: Request, token: str) -> uuid.UUID:
    """The signed ``org`` claim — read *before* the DB session so RLS can be set.

    Verifying the signature here is what makes the org id trustworthy enough to open a
    tenant session with; :func:`_resolve` then re-verifies everything inside it."""
    try:
        claims = decode_jwt(_secret(request), token)
    except InvalidToken as exc:
        raise _rejected() from exc
    return claims.org_id


@vendor_portal_router.post("/{token}/response")
async def submit_vendor_response(
    token: str, payload: VendorResponseIn, request: Request
) -> dict[str, Any]:
    """Accept the vendor's per-line response. **Never refused for lateness** (spec)."""
    now = datetime.now(UTC)
    async with org_scoped_session(_sessionmaker(request), _claim_org(request, token)) as session:
        scope = await _resolve(session, token, _secret(request))
        response = await _save_response(session, scope, payload, now)
        await emit_event(
            session,
            scope.rfq.org_id,
            "vendor_rfq.submitted",
            {
                "rfq_id": str(scope.rfq.id),
                "rfq_number": scope.rfq.number,
                "recipient_id": str(scope.recipient.id),
                "vendor_name": scope.recipient.vendor_name,
                "response_id": str(response.id),
                "is_late": response.is_late,
            },
        )
        result = {"submitted_at": response.submitted_at.isoformat(), "is_late": response.is_late}
    vendor_rfq_portal_events.labels(event="submitted").inc()
    return result


@vendor_portal_router.post("/{token}/response/attachment")
async def upload_vendor_attachment(
    token: str,
    request: Request,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Attach the vendor's own PDF quote to its (already submitted) response.

    One attachment per response — re-uploading replaces it. The blob lands in the org's
    object store under the RFQ's prefix; the old key is best-effort purged so a replaced
    file does not linger (GDPR erasure posture, M1.2).

    The credential is checked **before** the body is buffered: this surface is
    unauthenticated, so an anonymous caller must not be able to make the process hold
    10 MB per request on the strength of a garbage token. The filename is sanitised with
    the same helper the authenticated uploads use — a crafted name would otherwise escape
    the per-response object-key prefix or inject into a ``Content-Disposition`` header
    when the estimator downloads it."""
    filename = _safe_filename(file.filename)
    storage: ObjectStorage = get_storage(request)
    async with org_scoped_session(_sessionmaker(request), _claim_org(request, token)) as session:
        scope = await _resolve(session, token, _secret(request))
        response = (
            await session.execute(
                select(VendorRfqResponse).where(
                    VendorRfqResponse.recipient_id == scope.recipient.id
                )
            )
        ).scalar_one_or_none()
        if response is None:
            raise _invalid("Submit your response before attaching a file.")

        body = await file.read(MAX_ATTACHMENT_BYTES + 1)
        if len(body) > MAX_ATTACHMENT_BYTES:
            raise _invalid("The attachment is larger than 10 MB.")

        previous = response.attachment_object_key
        key = (
            f"orgs/{scope.rfq.org_id}/vendor-rfq/{scope.rfq.id}/"
            f"{scope.recipient.id}/{uuid.uuid4()}/{filename}"
        )
        size = await storage.put(key, io.BytesIO(body), content_type=file.content_type)
        response.attachment_object_key = key
        response.attachment_filename = filename
        response.attachment_size_bytes = size
        response.attachment_content_type = file.content_type
        filename = response.attachment_filename

    if previous:
        with contextlib.suppress(Exception):
            await storage.delete(previous)
    return {"filename": filename, "size_bytes": size}


@vendor_portal_router.get("/{token}/files/{file_id}")
async def download_vendor_file(
    token: str, file_id: uuid.UUID, request: Request
) -> StreamingResponse:
    """Stream a drawing/CAD file the token's allowlist grants.

    A file not on the allowlist is a 401, not a 404: the vendor must not be able to
    distinguish "exists but not yours" from "does not exist"."""
    storage: ObjectStorage = get_storage(request)
    async with org_scoped_session(_sessionmaker(request), _claim_org(request, token)) as session:
        scope = await _resolve(session, token, _secret(request))
        if file_id not in _allowed_file_ids(scope.token_row):
            raise _rejected()
        rows = await _load_lines(session, scope.rfq)
        part_ids = {row.part.id for row in rows}
        part_file = await session.get(PartFile, file_id)
        # Belt and braces: the allowlist alone must not reach a file off this batch.
        if part_file is None or part_file.part_id not in part_ids:
            raise _rejected()
        key, filename, content_type = (
            part_file.storage_key,
            part_file.filename,
            part_file.content_type,
        )
    return StreamingResponse(
        storage.stream(key),
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@vendor_portal_router.get("/{token}/pdf")
async def get_vendor_rfq_pdf(token: str, request: Request) -> Response:
    """Render the RFQ as a PDF for the vendor's records (spec: Download RFQ PDF).

    Same data as the portal page — no price, no customer, no other vendor."""
    now = datetime.now(UTC)
    async with org_scoped_session(_sessionmaker(request), _claim_org(request, token)) as session:
        scope = await _resolve(session, token, _secret(request))
        payload = await build_vendor_payload(session, scope, now)

    if not weasyprint_available():
        raise AppError(
            "pdf_unavailable",
            "PDF rendering is not available on this server.",
            status_code=503,
        )
    pdf = html_to_pdf(render_vendor_rfq_html(payload))
    filename = f"RFQ-{payload['rfq_number']}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
