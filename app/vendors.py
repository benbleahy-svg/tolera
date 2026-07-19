"""Vendor Library & Directory — the Supplier Directory's API (M6.3).

Backs the spec's ``#vendor-rfq`` → "Supplier Directory (nav: Suppliers)": the
directory list (search + process/material filter), the vendor detail tabs
(Overview / RFQ History / Capabilities / Notes), CRUD over a vendor and its
quoting contacts, and CSV import. Every read and write goes through the org-pinned
:func:`app.deps.get_session`, so isolation is a database guarantee (RLS), and a
foreign-org row surfaces as **404** — it is invisible, not forbidden.

Three rules from the block's sources are load-bearing here:

* **Notes never reach the vendor.** The Notes tab is "internal notes — never
  visible to the vendor". Rather than trusting future callers to remember,
  :class:`VendorExternalOut` is the one DTO a vendor-facing surface should
  serialize through, and it *cannot express* ``notes`` — a leak would have to be a
  deliberate new field. Adoption is still ahead (M6.4's batch send, M6.5's
  outbound email); M6.2's portal renders from ``vendor_rfq_recipient``, not
  ``Vendor``, so nothing serializes a vendor's notes today.
* **ERP identity is read-only.** The vendor sync is one-way ERP → Tolera: "ERP is
  source of truth for company identity and contact data", while BF-only data
  (capabilities, notes, portal creds, response history) "never writes back". So a
  row with ``erp_vendor_id`` rejects writes to its identity fields and to its
  contacts (409 ``vendor_erp_managed``), and accepts capabilities/notes/status.
* **Writes need ``config_edit``.** Vendors are org master data managed from the
  Configure-tier surfaces, not quote-line data — so the gate is ``config_edit``
  rather than ``quote_edit``. Reads need only an authenticated org session.

Capability tags are free text typed by estimators (the spec's "tag chips"), stored
normalized-lowercase under ``{"processes": [...], "materials": [...]}`` so the
directory filter is an indexed JSONB containment probe rather than a scan.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from sqlalchemy import false, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import Vendor, VendorContact, VendorStatus

vendors_router = APIRouter(prefix="/api/vendors", tags=["vendors"])
vendor_contacts_router = APIRouter(prefix="/api/vendor-contacts", tags=["vendors"])

#: Same permissive shape the project already uses for contact addresses
#: (``app.accounts._EMAIL_RE``) — the DB column is CITEXT; this is a sanity check.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_MAX_LENGTH = 320  # RFC 5321 max (64 local + @ + 255 domain)

# List endpoints are bounded so a large org can't turn a list into unbounded work.
_LIST_LIMIT_DEFAULT = 100
_LIST_LIMIT_MAX = 500

#: The two capability axes the spec's chips + filters are built on.
_CAPABILITY_KEYS = ("processes", "materials")
_MAX_TAGS_PER_AXIS = 50
_MAX_TAG_LENGTH = 80

#: The identity fields the connected ERP owns — writes to these are rejected on an
#: ERP-sourced vendor (one-way ERP → Tolera).
_ERP_OWNED_FIELDS = frozenset({"name", "address", "vat_id", "phone", "website", "erp_vendor_id"})

_CSV_MAX_BYTES = 2 * 1024 * 1024  # a vendor list is small; cap the parse surface
_CSV_MAX_ROWS = 5_000


def _normalize_email(value: str) -> str:
    """Canonicalise + light-validate an email. Never echo the address back in an
    error — vendor contacts are B2B data subjects but still personal data
    (CLAUDE.md §5; DACH-DELTA §5)."""
    cleaned = value.strip().lower()
    if not _EMAIL_RE.match(cleaned):
        raise ValueError("not a valid email address")
    return cleaned


def _reject_explicit_null[T](value: T, info: ValidationInfo) -> T:
    """Reject an explicit ``null`` for a field the DB declares NOT NULL.

    These update schemas type such fields as ``X | None`` only to express
    *"omitted"* — the partial-update idiom — but a client sending an explicit
    ``{"name": null}`` is indistinguishable from that at the ORM layer, and the
    ``None`` sails through to a ``NotNullViolation`` and an opaque **500**.

    A ``field_validator`` runs only for fields actually **present** in the
    payload (defaults are not validated), so this rejects the explicit null while
    leaving omission untouched — and it fires during request validation, so the
    caller gets a normal 422 naming the field rather than an internal error."""
    if value is None:
        raise ValueError(f"{info.field_name} cannot be null; omit it to leave it unchanged")
    return value


def _normalize_tags(values: list[str]) -> list[str]:
    """Trim, lowercase, drop blanks, de-duplicate — preserving first-seen order.

    Normalizing on write is what lets the directory filter be a containment probe
    ('ANODIZE' typed in the toolbar finds the vendor tagged 'anodize')."""
    seen: dict[str, None] = {}
    for raw in values:
        tag = " ".join(raw.strip().lower().split())
        if tag:
            seen.setdefault(tag[:_MAX_TAG_LENGTH], None)
    return list(seen)[:_MAX_TAGS_PER_AXIS]


class Capabilities(BaseModel):
    """The processes + materials a vendor serves — the spec's tag chips."""

    model_config = ConfigDict(extra="forbid")

    processes: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)

    @field_validator("processes", "materials")
    @classmethod
    def _norm(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class VendorContactCreate(BaseModel):
    """Payload to create a quoting contact (email required — a contact is reachable)."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=_EMAIL_MAX_LENGTH)
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    is_primary: bool = False
    cc: bool = False

    _norm_email = field_validator("email")(staticmethod(_normalize_email))


class VendorContactUpdate(BaseModel):
    """Partial update — only the fields present are changed.

    ``name``/``phone`` are nullable columns, so an explicit ``null`` legitimately
    *clears* them. ``email``/``is_primary``/``cc`` are NOT NULL — for those the
    ``| None`` means "omitted", and an explicit null is rejected as a 422."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, max_length=_EMAIL_MAX_LENGTH)
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    is_primary: bool | None = None
    cc: bool | None = None

    _no_null = field_validator("email", "is_primary", "cc")(_reject_explicit_null)

    @field_validator("email")
    @classmethod
    def _norm_optional_email(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_email(value)


class VendorContactOut(BaseModel):
    """A quoting contact as returned to the estimator-side UI."""

    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str | None
    email: str
    phone: str | None
    is_primary: bool
    cc: bool
    created_at: datetime
    updated_at: datetime


class VendorCreate(BaseModel):
    """Payload to create a vendor. ``primary_contact`` mirrors the ADD VENDOR
    modal (company + a first quoting contact); when present it is created under
    the new vendor in the same transaction.

    ``erp_vendor_id`` is deliberately **absent**: setting it permanently freezes
    the vendor's identity fields (:func:`_reject_erp_identity_write`) and no route
    can clear it, so a client typo would strand the row — archive-and-recreate
    being the only escape. It is server-set by the ERP sync (M6.8) alone."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    address: str | None = Field(default=None, max_length=1000)
    vat_id: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=500)
    status: VendorStatus = VendorStatus.active
    capabilities: Capabilities = Field(default_factory=Capabilities)
    notes: str | None = None
    primary_contact: VendorContactCreate | None = None


class VendorUpdate(BaseModel):
    """Partial update — only the fields present are changed. On an ERP-sourced
    vendor the identity fields are rejected (see :func:`_reject_erp_identity_write`).

    ``address``/``vat_id``/``phone``/``website``/``notes`` are nullable columns, so
    an explicit ``null`` legitimately *clears* them — that is how the UI empties a
    field. ``name``/``status``/``capabilities`` are NOT NULL: there the ``| None``
    only means "omitted", and an explicit null is rejected as a 422."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=300)
    address: str | None = Field(default=None, max_length=1000)
    vat_id: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=500)
    status: VendorStatus | None = None
    capabilities: Capabilities | None = None
    notes: str | None = None

    _no_null = field_validator("name", "status", "capabilities")(_reject_explicit_null)


class VendorOut(BaseModel):
    """A vendor as returned to the **internal** UI — carries ``notes``.

    Never hand this to a vendor-facing surface; use :class:`VendorExternalOut`."""

    id: uuid.UUID
    name: str
    address: str | None
    vat_id: str | None
    phone: str | None
    website: str | None
    erp_vendor_id: str | None
    #: Convenience mirror of ``erp_vendor_id is not None`` so the UI can grey out
    #: the identity fields without duplicating the rule.
    erp_managed: bool
    status: VendorStatus
    capabilities: Capabilities
    notes: str | None
    #: Open vendor RFQs awaiting a response (spec list column "Active RFQs").
    active_rfq_count: int
    archived: bool
    created_at: datetime
    updated_at: datetime


class VendorExternalOut(BaseModel):
    """The **only** vendor DTO a vendor-facing surface may serialize.

    Deliberately minimal: the vendor's own identity, nothing about how the shop
    regards them. It cannot express ``notes`` (spec ``#vendor-rfq``, Notes tab:
    "never visible to the vendor"), nor capabilities, response history or ERP ids.
    **Not yet consumed** — M6.2's portal renders from ``vendor_rfq_recipient``
    and never touches ``Vendor``. M6.4's batch send and M6.5's outbound email are
    the intended adopters; until one lands, this enforces the confidentiality rule
    by construction for future callers rather than guarding a live payload."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    address: str | None
    vat_id: str | None


class VendorImportError(BaseModel):
    """One rejected CSV row — reported, never fatal to the rest of the import."""

    #: 1-based line number in the uploaded file (header counts as line 1), so the
    #: operator can jump straight to it in their spreadsheet.
    row: int
    message: str


class VendorImportResult(BaseModel):
    """Outcome of a CSV import: what landed, and every row that didn't."""

    created: int
    errors: list[VendorImportError]


class _ExternalVendorSource(Protocol):
    """What :func:`vendor_external_out` needs — satisfied by :class:`app.models.Vendor`."""

    id: uuid.UUID
    name: str
    address: str | None
    vat_id: str | None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def vendor_external_out(vendor: _ExternalVendorSource) -> VendorExternalOut:
    """Project a vendor onto the vendor-facing contract (drops everything internal)."""
    return VendorExternalOut(
        id=vendor.id, name=vendor.name, address=vendor.address, vat_id=vendor.vat_id
    )


def _capabilities_of(vendor: Vendor) -> Capabilities:
    raw: dict[str, Any] = vendor.capabilities or {}
    return Capabilities(
        processes=list(raw.get("processes") or []),
        materials=list(raw.get("materials") or []),
    )


def _vendor_out(vendor: Vendor, *, active_rfq_count: int = 0) -> VendorOut:
    return VendorOut(
        id=vendor.id,
        name=vendor.name,
        address=vendor.address,
        vat_id=vendor.vat_id,
        phone=vendor.phone,
        website=vendor.website,
        erp_vendor_id=vendor.erp_vendor_id,
        erp_managed=vendor.erp_vendor_id is not None,
        status=vendor.status,
        capabilities=_capabilities_of(vendor),
        notes=vendor.notes,
        active_rfq_count=active_rfq_count,
        archived=vendor.deleted_at is not None,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
    )


def _contact_out(contact: VendorContact) -> VendorContactOut:
    return VendorContactOut(
        id=contact.id,
        vendor_id=contact.vendor_id,
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        is_primary=contact.is_primary,
        cc=contact.cc,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


async def _active_rfq_counts(
    session: AsyncSession, vendor_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Open vendor RFQs per vendor — the directory's "Active RFQs" column.

    Returns zero for every vendor today, and that is the *correct* answer rather
    than a placeholder: M6.2's ``vendor_rfq_recipient`` identifies its vendor by
    a denormalized ``vendor_name`` text column with **no FK to** ``vendor`` (the
    entity did not exist when the portal was built), so there is no join from a
    vendor row to an RFQ to count. M6.4 — the batch-send modal, which is what
    actually creates recipients from picked vendors — adds the ``vendor_id`` link
    and replaces this body with the real aggregate.

    Keeping it a single seam means the column, the DTO field and the UI ship now
    and M6.4 lands as one query. Deliberately not feature-flagged."""
    return {}


async def _get_vendor_or_404(session: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    """Fetch a vendor in the active org (archived included), or raise 404.

    A foreign-org vendor is invisible under RLS, so it lands here as 404 — never
    403, which would confirm the row exists."""
    vendor = await session.get(Vendor, vendor_id)
    if vendor is None:
        raise AppError("not_found", "Vendor not found.", status_code=status.HTTP_404_NOT_FOUND)
    return vendor


async def _get_contact_or_404(session: AsyncSession, contact_id: uuid.UUID) -> VendorContact:
    contact = await session.get(VendorContact, contact_id)
    if contact is None:
        raise AppError(
            "not_found", "Vendor contact not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    return contact


def _reject_erp_identity_write(vendor: Vendor, fields: set[str]) -> None:
    """Guard the one-way ERP → Tolera boundary.

    The ERP owns company identity + contact data; Tolera owns capabilities, notes,
    status and (later) portal creds + response history, and never writes any of it
    back. So an identity write against an ERP-sourced vendor is refused rather than
    silently overwritten on the next sync."""
    if vendor.erp_vendor_id is None:
        return
    blocked = sorted(fields & _ERP_OWNED_FIELDS)
    if blocked:
        raise AppError(
            "vendor_erp_managed",
            "This vendor's identity is maintained in the connected ERP and cannot be "
            "edited here. Capabilities, notes and status remain editable.",
            status_code=status.HTTP_409_CONFLICT,
            details={"fields": blocked},
        )


def _reject_erp_contact_write(vendor: Vendor) -> None:
    """Contact data is ERP-owned too (same one-way boundary as identity)."""
    if vendor.erp_vendor_id is not None:
        raise AppError(
            "vendor_erp_managed",
            "Contacts for this vendor are maintained in the connected ERP and cannot "
            "be edited here.",
            status_code=status.HTTP_409_CONFLICT,
        )


async def _flush_unique(session: AsyncSession) -> None:
    """Flush pending vendor writes, mapping a partial-unique violation to a 409
    envelope instead of a 500 (the ``app.accounts._flush_unique_email`` pattern).

    Two live-only indexes can trip: re-adding a quoting contact someone already
    added (everyday), and restoring an archived ERP vendor whose ``erp_vendor_id``
    the sync has since re-created (rarer, but the 500 would be baffling). The
    transaction rolls back on the raised error."""
    try:
        await session.flush()
    except IntegrityError as exc:
        detail = str(exc.orig)
        if "uq_vendor_contact_vendor_email_live" in detail:
            raise AppError(
                "email_conflict",
                "This vendor already has a contact with this email address.",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        if "uq_vendor_org_erp_id_live" in detail:
            raise AppError(
                "erp_vendor_id_conflict",
                "Another vendor in this organization already carries this ERP vendor id.",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise


def _new_contact(
    org_id: uuid.UUID, vendor_id: uuid.UUID, payload: VendorContactCreate
) -> VendorContact:
    return VendorContact(
        org_id=org_id,
        vendor_id=vendor_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        is_primary=payload.is_primary,
        cc=payload.cc,
    )


# --------------------------------------------------------------------------- #
# Directory
# --------------------------------------------------------------------------- #
@vendors_router.get("")
async def list_vendors(
    session: Annotated[AsyncSession, Depends(get_session)],
    include_archived: Annotated[bool, Query()] = False,
    q: Annotated[str | None, Query(max_length=200)] = None,
    process: Annotated[str | None, Query(max_length=_MAX_TAG_LENGTH)] = None,
    material: Annotated[str | None, Query(max_length=_MAX_TAG_LENGTH)] = None,
    status_filter: Annotated[VendorStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=_LIST_LIMIT_MAX)] = _LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[VendorOut]:
    """The Supplier Directory list (org isolation enforced at the DB by RLS).

    ``q`` searches name/VAT-ID; ``process`` + ``material`` narrow by capability
    chips and **intersect** (a vendor must serve both, matching the toolbar's two
    filters); archived rows are excluded unless asked for."""
    stmt = select(Vendor)
    if not include_archived:
        stmt = stmt.where(Vendor.deleted_at.is_(None))
    if status_filter is not None:
        stmt = stmt.where(Vendor.status == status_filter)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Vendor.name.ilike(pattern), Vendor.vat_id.ilike(pattern)))
    # Containment against the normalized (lowercase) tags — the GIN index serves it.
    # Guard on the NORMALIZED tag, not the raw string: a whitespace-only filter
    # normalizes to [], and `capabilities @> '{"processes": []}'` is satisfied by
    # every row — the filter would silently become a no-op instead of matching
    # nothing. Treat "the caller asked for a tag we can't represent" as no match.
    if process:
        tags = _normalize_tags([process])
        stmt = stmt.where(Vendor.capabilities.contains({"processes": tags}) if tags else false())
    if material:
        tags = _normalize_tags([material])
        stmt = stmt.where(Vendor.capabilities.contains({"materials": tags}) if tags else false())
    stmt = stmt.order_by(Vendor.name).limit(limit).offset(offset)

    vendors = list((await session.execute(stmt)).scalars())
    counts = await _active_rfq_counts(session, [v.id for v in vendors])
    return [_vendor_out(v, active_rfq_count=counts.get(v.id, 0)) for v in vendors]


@vendors_router.post("", status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> VendorOut:
    """Create a vendor (and, optionally, its first quoting contact)."""
    vendor = Vendor(
        org_id=principal.active_org_id,
        name=payload.name,
        address=payload.address,
        vat_id=payload.vat_id,
        phone=payload.phone,
        website=payload.website,
        status=payload.status,
        capabilities=payload.capabilities.model_dump(),
        notes=payload.notes,
    )
    session.add(vendor)
    await session.flush()

    if payload.primary_contact is not None:
        session.add(_new_contact(principal.active_org_id, vendor.id, payload.primary_contact))
        await _flush_unique(session)

    return _vendor_out(vendor)


@vendors_router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_vendors(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> VendorImportResult:
    """Bulk-create vendors from a CSV body (the block's "CSV-or-manual import").

    Columns: ``name`` (required), ``address``, ``vat_id``, ``phone``, ``website``,
    ``processes``, ``materials`` (``;``-separated tags), ``contact_name``,
    ``contact_email``. A bad row is **reported, not fatal** — an operator pasting a
    40-line supplier list should not lose 39 good rows to one typo, and the row
    numbers point them straight at the fixes."""
    raw = await request.body()
    if len(raw) > _CSV_MAX_BYTES:
        raise AppError(
            "csv_too_large",
            "The uploaded vendor list is too large.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    try:
        text_body = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(
            "csv_not_utf8",
            "The vendor list must be UTF-8 encoded.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc

    reader = csv.DictReader(io.StringIO(text_body))
    created = 0
    errors: list[VendorImportError] = []

    for index, row in enumerate(reader, start=1):
        if index > _CSV_MAX_ROWS:
            errors.append(VendorImportError(row=index, message="Import row limit exceeded."))
            break
        # Report the line number the operator sees in their spreadsheet (header
        # included), not the data-row ordinal — they have to go and fix that line.
        line = reader.line_num
        cell = _flatten_row(row)
        name = cell.get("name", "")
        if not name:
            errors.append(VendorImportError(row=line, message="Column 'name' is required."))
            continue

        contact_payload: VendorContactCreate | None = None
        if cell.get("contact_email"):
            try:
                contact_payload = VendorContactCreate(
                    email=cell["contact_email"],
                    name=cell.get("contact_name") or None,
                    is_primary=True,
                )
            except ValueError:
                # Reject the whole row: a vendor whose only contact is unreachable
                # can't be sent an RFQ, so importing it half-formed helps nobody.
                errors.append(
                    VendorImportError(row=line, message="Column 'contact_email' is not valid.")
                )
                continue

        vendor = Vendor(
            org_id=principal.active_org_id,
            name=name[:300],
            address=cell.get("address") or None,
            vat_id=cell.get("vat_id") or None,
            phone=cell.get("phone") or None,
            website=cell.get("website") or None,
            capabilities=Capabilities(
                processes=_split_tags(cell.get("processes", "")),
                materials=_split_tags(cell.get("materials", "")),
            ).model_dump(),
        )
        # Each row commits inside its own SAVEPOINT: a unique violation (a repeated
        # contact email, an ERP id already used) then rolls back just this row and is
        # reported, leaving every good row in the file intact. Without the savepoint
        # the failed statement would poison the outer transaction and lose them all.
        try:
            async with session.begin_nested():
                session.add(vendor)
                await session.flush()
                if contact_payload is not None:
                    session.add(_new_contact(principal.active_org_id, vendor.id, contact_payload))
                    await session.flush()
        except IntegrityError:
            errors.append(
                VendorImportError(row=line, message="Row conflicts with an existing record.")
            )
            continue
        created += 1

    return VendorImportResult(created=created, errors=errors)


def _split_tags(raw: str) -> list[str]:
    """Split a ``;``-separated CSV tag cell (``anodize;polish``)."""
    return [part for part in raw.split(";") if part.strip()]


def _flatten_row(row: dict[str | None, Any]) -> dict[str, str]:
    """Normalize one ``csv.DictReader`` row to ``{column: value}`` strings.

    A **ragged** row is the case that matters: given more fields than the header
    declares (a stray comma in ``Müller GmbH, Sitz Köln,mail@x.de``), DictReader
    files the surplus under the ``None`` restkey as a **list**, and given fewer it
    yields ``None`` values. Both must survive — this endpoint's contract is that a
    bad row is *reported*, never fatal, and letting an ``AttributeError`` escape
    would roll back every good row in the file with an opaque 500.

    The surplus is dropped rather than guessed at: the row still imports if its
    named columns are valid, which is what the operator meant."""
    cell: dict[str, str] = {}
    for key, value in row.items():
        if key is None:  # restkey: surplus fields, no column to put them in
            continue
        if isinstance(value, list):  # defensive; only the restkey is ever a list
            value = ",".join(part for part in value if part)
        cell[key.strip()] = (value or "").strip()
    return cell


@vendors_router.get("/{vendor_id}")
async def get_vendor(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VendorOut:
    """Fetch one vendor — the detail view's Overview tab (archived included)."""
    vendor = await _get_vendor_or_404(session, vendor_id)
    counts = await _active_rfq_counts(session, [vendor.id])
    return _vendor_out(vendor, active_rfq_count=counts.get(vendor.id, 0))


@vendors_router.patch("/{vendor_id}")
async def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> VendorOut:
    """Update a vendor. On an ERP-sourced row the identity fields are refused
    (409) while capabilities / notes / status stay editable."""
    vendor = await _get_vendor_or_404(session, vendor_id)
    fields = payload.model_dump(exclude_unset=True)
    _reject_erp_identity_write(vendor, set(fields))

    for key, value in fields.items():
        if key == "capabilities":
            vendor.capabilities = Capabilities.model_validate(value).model_dump()
        else:
            setattr(vendor, key, value)
    await session.flush()
    counts = await _active_rfq_counts(session, [vendor.id])
    return _vendor_out(vendor, active_rfq_count=counts.get(vendor.id, 0))


@vendors_router.post("/{vendor_id}/archive")
async def archive_vendor(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> VendorOut:
    """Archive (soft-delete) a vendor — it leaves the directory but its RFQ history
    is retained. Idempotent."""
    vendor = await _get_vendor_or_404(session, vendor_id)
    if vendor.deleted_at is None:
        vendor.deleted_at = datetime.now(UTC)
        await session.flush()
    return _vendor_out(vendor)


@vendors_router.post("/{vendor_id}/restore")
async def restore_vendor(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> VendorOut:
    """Bring an archived vendor back into the directory. Idempotent."""
    vendor = await _get_vendor_or_404(session, vendor_id)
    if vendor.deleted_at is not None:
        vendor.deleted_at = None
        # Restoring can collide with an ERP id the sync re-created meanwhile.
        await _flush_unique(session)
    return _vendor_out(vendor)


@vendors_router.get("/{vendor_id}/rfq-history")
async def list_vendor_rfq_history(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, Any]]:
    """The detail view's **RFQ History** tab — read-only here.

    M6.3 owns the tab; its *content* is written by M6.4+ (the batch send that
    creates a ``VendorRFQ``) and M6.6 (the responses + which quote a price was
    applied to). Until then a vendor genuinely has no history, so this returns an
    empty list rather than 404 — the tab renders its empty state, and M6.4 fills
    this query in without the UI changing shape."""
    await _get_vendor_or_404(session, vendor_id)
    return []


# --------------------------------------------------------------------------- #
# Quoting contacts
# --------------------------------------------------------------------------- #
@vendors_router.get("/{vendor_id}/contacts")
async def list_vendor_contacts(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    include_archived: Annotated[bool, Query()] = False,
) -> list[VendorContactOut]:
    """List a vendor's quoting contacts (primary first, then CC, then the rest)."""
    await _get_vendor_or_404(session, vendor_id)
    stmt = select(VendorContact).where(VendorContact.vendor_id == vendor_id)
    if not include_archived:
        stmt = stmt.where(VendorContact.deleted_at.is_(None))
    stmt = stmt.order_by(
        VendorContact.is_primary.desc(), VendorContact.cc.desc(), VendorContact.email
    )
    return [_contact_out(c) for c in (await session.execute(stmt)).scalars()]


@vendors_router.post("/{vendor_id}/contacts", status_code=status.HTTP_201_CREATED)
async def create_vendor_contact(
    vendor_id: uuid.UUID,
    payload: VendorContactCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> VendorContactOut:
    """Add a quoting contact. Refused on an ERP-sourced vendor (ERP owns contacts)."""
    vendor = await _get_vendor_or_404(session, vendor_id)
    _reject_erp_contact_write(vendor)
    contact = _new_contact(principal.active_org_id, vendor.id, payload)
    session.add(contact)
    await _flush_unique(session)
    return _contact_out(contact)


@vendor_contacts_router.patch("/{contact_id}")
async def update_vendor_contact(
    contact_id: uuid.UUID,
    payload: VendorContactUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> VendorContactOut:
    """Update a quoting contact. Refused on an ERP-sourced vendor."""
    contact = await _get_contact_or_404(session, contact_id)
    _reject_erp_contact_write(await _get_vendor_or_404(session, contact.vendor_id))
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)
    await _flush_unique(session)
    return _contact_out(contact)


@vendor_contacts_router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_contact(
    contact_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> Response:
    """Remove a quoting contact — a **soft**-delete, so an RFQ already sent to this
    address keeps a resolvable recipient. Idempotent. Refused on an ERP vendor."""
    contact = await _get_contact_or_404(session, contact_id)
    _reject_erp_contact_write(await _get_vendor_or_404(session, contact.vendor_id))
    if contact.deleted_at is None:
        contact.deleted_at = datetime.now(UTC)
        await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
