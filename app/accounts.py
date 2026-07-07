"""Accounts & Contacts CRUD — the first real org-scoped domain resource (M1.1).

Bid Factory is the system of record for CRM Accounts (a customer/vendor company)
and Contacts (a person at an account — the human a quote is emailed to). Every
read and write goes through the org-pinned :func:`app.deps.get_session`, so RLS
makes isolation a database guarantee (the M0.2 pattern, inherited verbatim).

Conventions encoded here (DECISIONS.md 2026-06-25, M1.1 grill):
  * **Archive = soft-delete** (``deleted_at``), reversible via restore; default
    lists exclude archived rows, a direct ``GET /{id}`` still returns one. There
    is no hard delete in v1. Archiving an account doesn't touch its contacts'
    rows — the cross-account contact list just hides contacts of archived accounts.
  * **Salesperson must be an active member of the active org.** ``salesperson_id``
    is a global ``app_user`` ref RLS can't guard, so writes validate it against
    ``user_org_membership`` (which IS org-scoped) — closing a cross-tenant leak.
  * Contact **email is unique per org among live rows only** (partial index); a
    duplicate live email surfaces as a clean ``409`` rather than a 500.

Permission gates mirror the M0.3 matrix: create/edit need ``quote_edit``;
archive/restore need ``quote_delete`` (the only destructive-ish capability granted
to admin/manager). Reads need only an authenticated org session (every role has
``view_all``), matching ``notes.py``.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import Account, AccountType, Contact, MembershipStatus, UserOrgMembership

accounts_router = APIRouter(prefix="/api/accounts", tags=["accounts"])
contacts_router = APIRouter(prefix="/api/contacts", tags=["contacts"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_MAX_LENGTH = 320  # RFC 5321 max (64 local + @ + 255 domain)

# List endpoints are bounded so a large org can't turn a list into unbounded
# DB/API work. Cursor pagination can layer on later; offset is enough for v1.
_LIST_LIMIT_DEFAULT = 100
_LIST_LIMIT_MAX = 500


def _normalize_email(value: str) -> str:
    """Canonicalise + light-validate an email (CITEXT column, but normalise anyway).

    Never echo the address back in the error — it is customer PII (CLAUDE.md §5)."""
    cleaned = value.strip().lower()
    if not _EMAIL_RE.match(cleaned):
        raise ValueError("not a valid email address")
    return cleaned


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ContactCreate(BaseModel):
    """Payload to create a contact (email required — a contact is reachable)."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=_EMAIL_MAX_LENGTH)
    first_name: str | None = Field(default=None, max_length=200)
    last_name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    phone_ext: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    salesperson_id: uuid.UUID | None = None

    _norm_email = field_validator("email")(staticmethod(_normalize_email))


class ContactUpdate(BaseModel):
    """Partial update — only the fields present are changed. ``account_id`` may be
    set to move the contact (or ``null`` to detach it)."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, max_length=_EMAIL_MAX_LENGTH)
    first_name: str | None = Field(default=None, max_length=200)
    last_name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    phone_ext: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    salesperson_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None

    @field_validator("email")
    @classmethod
    def _norm_optional_email(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_email(value)


class ContactOut(BaseModel):
    """A contact as returned to clients."""

    id: uuid.UUID
    account_id: uuid.UUID | None
    email: str
    first_name: str | None
    last_name: str | None
    role: str | None
    phone: str | None
    phone_ext: str | None
    notes: str | None
    salesperson_id: uuid.UUID | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class AccountCreate(BaseModel):
    """Payload to create an account. ``primary_contact`` mirrors the spec's Create
    Account modal (Company Name + a first contact); when present it is created
    under the new account in the same transaction."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    type: AccountType = AccountType.customer
    email: str | None = Field(default=None, max_length=_EMAIL_MAX_LENGTH)
    phone: str | None = Field(default=None, max_length=50)
    phone_ext: str | None = Field(default=None, max_length=20)
    website: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    salesperson_id: uuid.UUID | None = None
    primary_contact: ContactCreate | None = None

    @field_validator("email")
    @classmethod
    def _norm_optional_email(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_email(value)


class AccountUpdate(BaseModel):
    """Partial update — only the fields present are changed."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=300)
    type: AccountType | None = None
    email: str | None = Field(default=None, max_length=_EMAIL_MAX_LENGTH)
    phone: str | None = Field(default=None, max_length=50)
    phone_ext: str | None = Field(default=None, max_length=20)
    website: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    salesperson_id: uuid.UUID | None = None

    @field_validator("email")
    @classmethod
    def _norm_optional_email(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_email(value)


class AccountOut(BaseModel):
    """An account as returned to clients."""

    id: uuid.UUID
    name: str
    type: AccountType
    email: str | None
    phone: str | None
    phone_ext: str | None
    website: str | None
    notes: str | None
    salesperson_id: uuid.UUID | None
    archived: bool
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _account_out(account: Account) -> AccountOut:
    return AccountOut(
        id=account.id,
        name=account.name,
        type=account.type,
        email=account.email,
        phone=account.phone,
        phone_ext=account.phone_ext,
        website=account.website,
        notes=account.notes,
        salesperson_id=account.salesperson_id,
        archived=account.deleted_at is not None,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _contact_out(contact: Contact) -> ContactOut:
    return ContactOut(
        id=contact.id,
        account_id=contact.account_id,
        email=contact.email,
        first_name=contact.first_name,
        last_name=contact.last_name,
        role=contact.role,
        phone=contact.phone,
        phone_ext=contact.phone_ext,
        notes=contact.notes,
        salesperson_id=contact.salesperson_id,
        archived=contact.deleted_at is not None,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


async def _validate_salesperson(session: AsyncSession, salesperson_id: uuid.UUID | None) -> None:
    """Reject a salesperson who isn't an **active member of the active org**.

    The query runs on the org-pinned session, so RLS scopes ``user_org_membership``
    to the active org — a foreign-org user simply has no visible membership row.
    This is the tenancy guard the global ``app_user`` FK can't give us
    (DECISIONS.md 2026-06-25)."""
    if salesperson_id is None:
        return
    member = await session.scalar(
        select(UserOrgMembership.id).where(
            UserOrgMembership.user_id == salesperson_id,
            UserOrgMembership.status == MembershipStatus.active,
        )
    )
    if member is None:
        raise AppError(
            "invalid_salesperson",
            "Salesperson must be an active member of this organization.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


async def _get_account_or_404(session: AsyncSession, account_id: uuid.UUID) -> Account:
    """Fetch an account in the active org (archived included), or raise 404."""
    account = await session.get(Account, account_id)
    if account is None:
        raise AppError("not_found", "Account not found.", status_code=status.HTTP_404_NOT_FOUND)
    return account


async def _require_live_account(session: AsyncSession, account_id: uuid.UUID) -> Account:
    """An account a contact is created under / moved onto must not be archived —
    the contact would silently vanish from the default cross-account list (the
    archived-parent hide, DECISIONS.md 2026-06-25). Mirrors quotes'
    ``_validate_account`` archived rule."""
    account = await _get_account_or_404(session, account_id)
    if account.deleted_at is not None:
        raise AppError(
            "account_archived",
            "Cannot attach a contact to an archived account; restore it first.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return account


async def _get_contact_or_404(session: AsyncSession, contact_id: uuid.UUID) -> Contact:
    """Fetch a contact in the active org (archived included), or raise 404."""
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise AppError("not_found", "Contact not found.", status_code=status.HTTP_404_NOT_FOUND)
    return contact


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
@accounts_router.get("")
async def list_accounts(
    session: Annotated[AsyncSession, Depends(get_session)],
    include_archived: Annotated[bool, Query()] = False,
    salesperson_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=_LIST_LIMIT_MAX)] = _LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AccountOut]:
    """List the active org's accounts (org isolation enforced at the DB by RLS).

    Archived rows are excluded unless ``include_archived``; ``salesperson_id`` and
    a name/email search (``q``) narrow the list; results are paginated
    (``limit``/``offset``, hard cap ``_LIST_LIMIT_MAX``)."""
    stmt = select(Account)
    if not include_archived:
        stmt = stmt.where(Account.deleted_at.is_(None))
    if salesperson_id is not None:
        stmt = stmt.where(Account.salesperson_id == salesperson_id)
    if q:
        # Escape LIKE metacharacters so a literal "%"/"_" in the query matches
        # itself instead of acting as a wildcard (e.g. q="50%" must not match
        # every row). Parameterisation already rules out SQL injection.
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                Account.name.ilike(pattern, escape="\\"),
                Account.email.ilike(pattern, escape="\\"),
            )
        )
    stmt = stmt.order_by(Account.name).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [_account_out(account) for account in result.scalars()]


@accounts_router.post("", status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> AccountOut:
    """Create an account (and, optionally, its first contact) in the active org."""
    await _validate_salesperson(session, payload.salesperson_id)
    account = Account(
        org_id=_.active_org_id,
        name=payload.name,
        type=payload.type,
        email=payload.email,
        phone=payload.phone,
        phone_ext=payload.phone_ext,
        website=payload.website,
        notes=payload.notes,
        salesperson_id=payload.salesperson_id,
    )
    session.add(account)
    await session.flush()

    if payload.primary_contact is not None:
        await _create_contact(session, _.active_org_id, account.id, payload.primary_contact)

    return _account_out(account)


@accounts_router.get("/{account_id}")
async def get_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccountOut:
    """Fetch one account (archived rows included, so the detail/restore UI works)."""
    return _account_out(await _get_account_or_404(session, account_id))


@accounts_router.patch("/{account_id}")
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> AccountOut:
    """Edit an account. Only the fields present in the body change."""
    account = await _get_account_or_404(session, account_id)
    changes = payload.model_dump(exclude_unset=True)
    if "salesperson_id" in changes:
        await _validate_salesperson(session, changes["salesperson_id"])
    for field, value in changes.items():
        setattr(account, field, value)
    await session.flush()
    return _account_out(account)


@accounts_router.post("/{account_id}/archive")
async def archive_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_delete))],
) -> AccountOut:
    """Soft-delete (archive) an account. Idempotent; its contacts are left intact
    but vanish from the cross-account contact list while the account is archived."""
    account = await _get_account_or_404(session, account_id)
    if account.deleted_at is None:
        account.deleted_at = datetime.now(UTC)
        await session.flush()
    return _account_out(account)


@accounts_router.post("/{account_id}/restore")
async def restore_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_delete))],
) -> AccountOut:
    """Un-archive an account (clear ``deleted_at``). Idempotent."""
    account = await _get_account_or_404(session, account_id)
    if account.deleted_at is not None:
        account.deleted_at = None
        await session.flush()
    return _account_out(account)


@accounts_router.get("/{account_id}/contacts")
async def list_account_contacts(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    include_archived: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=_LIST_LIMIT_MAX)] = _LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ContactOut]:
    """List one account's contacts (the account-detail Contacts tab).

    Unlike the cross-account list, this shows the contacts even when the account
    itself is archived: you've navigated into that specific account (e.g. to review
    or restore it), so its contacts are wanted context, not general browsing
    (DECISIONS.md 2026-06-25 — the cascade-hide applies to the cross-account list)."""
    await _get_account_or_404(session, account_id)
    stmt = select(Contact).where(Contact.account_id == account_id)
    if not include_archived:
        stmt = stmt.where(Contact.deleted_at.is_(None))
    stmt = (
        stmt.order_by(Contact.last_name, Contact.first_name, Contact.email)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [_contact_out(contact) for contact in result.scalars()]


@accounts_router.post("/{account_id}/contacts", status_code=status.HTTP_201_CREATED)
async def create_account_contact(
    account_id: uuid.UUID,
    payload: ContactCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ContactOut:
    """Create a contact under an account."""
    await _require_live_account(session, account_id)
    contact = await _create_contact(session, _.active_org_id, account_id, payload)
    return _contact_out(contact)


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #
@contacts_router.get("")
async def list_contacts(
    session: Annotated[AsyncSession, Depends(get_session)],
    include_archived: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=_LIST_LIMIT_MAX)] = _LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ContactOut]:
    """List the active org's contacts. By default this excludes archived contacts
    **and** contacts whose parent account is archived (DECISIONS.md 2026-06-25);
    ``include_archived`` returns everything in the org."""
    stmt = select(Contact).outerjoin(Account, Contact.account_id == Account.id)
    if not include_archived:
        stmt = stmt.where(
            Contact.deleted_at.is_(None),
            or_(Account.id.is_(None), Account.deleted_at.is_(None)),
        )
    stmt = (
        stmt.order_by(Contact.last_name, Contact.first_name, Contact.email)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [_contact_out(contact) for contact in result.scalars()]


@contacts_router.get("/{contact_id}")
async def get_contact(
    contact_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ContactOut:
    """Fetch one contact (archived included)."""
    return _contact_out(await _get_contact_or_404(session, contact_id))


@contacts_router.patch("/{contact_id}")
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ContactOut:
    """Edit a contact. Only the fields present in the body change."""
    contact = await _get_contact_or_404(session, contact_id)
    changes = payload.model_dump(exclude_unset=True)
    # email is NOT NULL; an explicit null would otherwise reach the DB as an
    # IntegrityError (500) — reject it at the edge with the standard envelope.
    if "email" in changes and changes["email"] is None:
        raise AppError(
            "invalid_email",
            "Contact email cannot be null.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if "salesperson_id" in changes:
        await _validate_salesperson(session, changes["salesperson_id"])
    if changes.get("account_id") is not None:
        await _require_live_account(session, changes["account_id"])
    for field, value in changes.items():
        setattr(contact, field, value)
    await _flush_unique_email(session)
    return _contact_out(contact)


@contacts_router.post("/{contact_id}/archive")
async def archive_contact(
    contact_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_delete))],
) -> ContactOut:
    """Soft-delete (archive) a contact. Idempotent. The freed email becomes
    reusable by a new live contact (live-only partial unique index)."""
    contact = await _get_contact_or_404(session, contact_id)
    if contact.deleted_at is None:
        contact.deleted_at = datetime.now(UTC)
        await session.flush()
    return _contact_out(contact)


@contacts_router.post("/{contact_id}/restore")
async def restore_contact(
    contact_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_delete))],
) -> ContactOut:
    """Un-archive a contact. Fails with 409 if a live contact now holds its email."""
    contact = await _get_contact_or_404(session, contact_id)
    if contact.deleted_at is not None:
        contact.deleted_at = None
        await _flush_unique_email(session)
    return _contact_out(contact)


# --------------------------------------------------------------------------- #
# Shared write helpers
# --------------------------------------------------------------------------- #
async def _create_contact(
    session: AsyncSession,
    org_id: uuid.UUID,
    account_id: uuid.UUID | None,
    payload: ContactCreate,
) -> Contact:
    """Insert a contact, validating the salesperson and surfacing a duplicate live
    email as a clean 409."""
    await _validate_salesperson(session, payload.salesperson_id)
    contact = Contact(
        org_id=org_id,
        account_id=account_id,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=payload.role,
        phone=payload.phone,
        phone_ext=payload.phone_ext,
        notes=payload.notes,
        salesperson_id=payload.salesperson_id,
    )
    session.add(contact)
    await _flush_unique_email(session)
    return contact


async def _flush_unique_email(session: AsyncSession) -> None:
    """Flush pending contact writes, mapping the live-email unique violation to a
    409 envelope instead of a 500. The transaction rolls back on the raised error."""
    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_contact_org_email_live" in str(exc.orig):
            raise AppError(
                "email_conflict",
                "A contact with this email already exists in this organization.",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise
