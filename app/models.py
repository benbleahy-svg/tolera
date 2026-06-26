"""ORM models for the M0.2 tenancy spine.

Only the identity/tenancy core lands here — ``organization``, ``app_user``,
``user_org_membership`` (multi-role per DECISIONS.md 2026-06-24) — plus a
deliberately trivial ``note`` entity used solely to prove org-scoped RLS
isolation end-to-end. Real domain tables accrete from M1 onward.

The Postgres enums and tables are authored by the Alembic migration (which also
declares the row-level-security policies the ORM cannot express); these mappings
reference the existing types with ``create_type=False`` and never emit their own
type DDL. Conventions (UUID PKs, snake_case, timestamptz) per CLAUDE.md §5.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class MembershipRole(enum.StrEnum):
    """App role held within an org. The canonical persona set from the spec
    ``#authz``/``#personas`` matrix (DECISIONS.md 2026-06-24 "Authorization role
    set"). ``viewer`` is an explicit non-spec read-only role we retain. The
    role→capability mapping lives in ``app.authz`` (the single source of truth);
    a user may hold several roles and effective permissions are their union.

    Values are append-only — the order here mirrors the Postgres enum (M0.2's
    four, then M0.3's four). Renaming/removing a value is a type rebuild."""

    admin = "admin"
    estimator = "estimator"
    salesperson = "salesperson"
    viewer = "viewer"
    manager = "manager"
    engineer = "engineer"
    material_purchasing = "material_purchasing"
    outside_service = "outside_service"


class MembershipStatus(enum.StrEnum):
    """Lifecycle of a membership. ``pending`` = invited-not-accepted (M5.12),
    ``disabled`` = soft-disabled (sessions revoked, history preserved)."""

    active = "active"
    pending = "pending"
    disabled = "disabled"


class OrgCountry(enum.StrEnum):
    """DACH region (metric-native, EUR/CHF). DACH-DELTA §1."""

    DE = "DE"
    AT = "AT"
    CH = "CH"


class AccountType(enum.StrEnum):
    """A CRM account's kind (canonical ``account_type`` enum, DB-SCHEMA.sql).

    A ``vendor`` cannot be assigned to a quote; that rule is enforced when the
    quote↔account link lands (M1.4). ``customer`` is the default."""

    customer = "customer"
    vendor = "vendor"


# Native Postgres enums — created by the migration, referenced (not re-created) here.
_role_enum = Enum(MembershipRole, name="membership_role", create_type=False)
_status_enum = Enum(MembershipStatus, name="membership_status", create_type=False)
_country_enum = Enum(OrgCountry, name="org_country", create_type=False)
_account_type_enum = Enum(AccountType, name="account_type", create_type=False)


def _pk() -> Mapped[uuid.UUID]:
    """A UUID primary key defaulted by ``gen_random_uuid()`` (pgcrypto)."""
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


def _ts() -> Mapped[datetime]:
    """A non-null ``timestamptz`` defaulting to ``now()`` (set once on insert)."""
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_ts() -> Mapped[datetime]:
    """A non-null ``timestamptz`` that also bumps to ``now()`` on every update."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def _org_fk() -> Mapped[uuid.UUID]:
    """The ``org_id`` foreign key every tenant-scoped row carries (RLS keys on it)."""
    return mapped_column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)


def _salesperson_fk() -> Mapped[uuid.UUID | None]:
    """Optional assigned salesperson. The single-column FK to ``app_user`` is
    deliberately *not* used: a composite ``(salesperson_id, org_id)`` FK to
    ``user_org_membership`` (declared per-table in ``__table_args__``) pins the
    reference to a member of the row's own org — a DB-level tenancy invariant RLS
    alone can't give for the org-less ``app_user`` (DECISIONS.md 2026-06-25). The
    app layer adds the *active*-membership check + clean 422."""
    return mapped_column(UUID(as_uuid=True))


def _salesperson_membership_fk(table: str) -> ForeignKeyConstraint:
    """Composite FK pinning ``(salesperson_id, org_id)`` to an org membership."""
    return ForeignKeyConstraint(
        ["salesperson_id", "org_id"],
        ["user_org_membership.user_id", "user_org_membership.org_id"],
        name=f"fk_{table}_salesperson_membership",
    )


def _deleted_at() -> Mapped[datetime | None]:
    """Soft-delete marker (archive). NULL = live; set = archived but retained
    (DECISIONS.md 2026-06-25). No default — only an explicit archive sets it."""
    return mapped_column(DateTime(timezone=True))


class Organization(Base):
    """A tenant. Every org-scoped row carries ``org_id``; RLS keys on it."""

    __tablename__ = "organization"
    __table_args__ = (
        # DACH money convention: EUR (DE/AT) or CHF (CH) only — no bare currency.
        CheckConstraint("currency IN ('EUR', 'CHF')", name="ck_organization_currency"),
    )

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    country: Mapped[OrgCountry] = mapped_column(
        _country_enum, nullable=False, server_default=OrgCountry.DE.value
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    locale: Mapped[str] = mapped_column(String, nullable=False, server_default="de-DE")
    # Clerk Organizations mirror (DECISIONS.md 2026-06-24 "Org identity model").
    clerk_org_id: Mapped[str | None] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class AppUser(Base):
    """A global identity (NOT org-scoped — one user may belong to many orgs)."""

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = _pk()
    # CITEXT to match the DB column (case-insensitive uniqueness; see migration).
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    first_name: Mapped[str | None] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String)
    clerk_user_id: Mapped[str | None] = mapped_column(String, unique=True)  # Clerk identity mirror
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class UserOrgMembership(Base):
    """User ⋈ Org (M:N). Multi-role per membership (DECISIONS.md 2026-06-24);
    effective permissions are the union over ``roles`` (computed in M0.3)."""

    __tablename__ = "user_org_membership"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_membership_user_org"),
        CheckConstraint("cardinality(roles) > 0", name="ck_membership_roles_nonempty"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = _org_fk()
    roles: Mapped[list[MembershipRole]] = mapped_column(ARRAY(_role_enum), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(
        _status_enum, nullable=False, server_default=MembershipStatus.active.value
    )
    created_at: Mapped[datetime] = _ts()

    org: Mapped[Organization] = relationship()
    user: Mapped[AppUser] = relationship()


class Note(Base):
    """Throwaway org-scoped entity — exists only to prove RLS isolation (M0.2).
    Not a domain concept; safe to drop once a real org-scoped table exists."""

    __tablename__ = "note"

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    body: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _ts()


class Account(Base):
    """A CRM company — the customer (or vendor) a quote is raised for (spec
    ``#contacts``; DOMAIN-MODEL §3). Org-scoped (RLS keys on ``org_id``);
    archived via soft-delete (``deleted_at``).

    **Lean M1.1 column set** by design: the VAT/tax/ERP/billing-address fields the
    canonical ``account`` carries in DB-SCHEMA.sql are deferred to their consuming
    blocks (VAT → M1.11, DATEV/ERP → M5/M6), each added by its own reversible
    migration — mirroring how M0 built ``organization`` lean (DECISIONS.md
    2026-06-24 "M0.5 seed scope")."""

    __tablename__ = "account"
    __table_args__ = (
        # Composite-FK target so contact.account_id can be scoped same-org.
        UniqueConstraint("org_id", "id", name="uq_account_org_id_id"),
        _salesperson_membership_fk("account"),
        # List/archive paths filter org_id (RLS) + deleted_at; lead with org_id.
        Index("ix_account_org_deleted_at", "org_id", "deleted_at"),
    )
    # Fetch server-generated values (created_at/updated_at) via RETURNING on the
    # write itself, so building the response after flush() doesn't trigger an
    # implicit refresh — which would raise MissingGreenlet on the async session.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[AccountType] = mapped_column(
        _account_type_enum, nullable=False, server_default=AccountType.customer.value
    )
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None] = mapped_column(String)
    phone_ext: Mapped[str | None] = mapped_column(String)
    website: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    salesperson_id: Mapped[uuid.UUID | None] = _salesperson_fk()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()
    deleted_at: Mapped[datetime | None] = _deleted_at()


class Contact(Base):
    """A person at an Account — the human a quote is emailed to (spec ``#contacts``;
    DOMAIN-MODEL §3). Org-scoped; archived via soft-delete.

    ``account_id`` is **nullable**: the CRUD happy path always creates a contact
    under an account, but RFQ intake (M3) may produce account-less contacts
    (DECISIONS.md 2026-06-25). ``email`` is unique per org among **live** rows only
    — the partial unique index — so an archived contact's email can be reused."""

    __tablename__ = "contact"
    # See Account: fetch server defaults via RETURNING so post-flush response
    # building doesn't trip the async MissingGreenlet refresh.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        # A contact's account must be in the SAME org (composite FK to the account's
        # (org_id, id)). NULL account_id skips the check (MATCH SIMPLE) so account-
        # less RFQ-origin contacts are allowed (DECISIONS.md 2026-06-25).
        ForeignKeyConstraint(
            ["org_id", "account_id"],
            ["account.org_id", "account.id"],
            name="fk_contact_account_same_org",
        ),
        _salesperson_membership_fk("contact"),
        # Unique per org among live rows only; an archived email frees up for reuse
        # (DECISIONS.md 2026-06-25). Postgres needs the predicate spelled out here.
        Index(
            "uq_contact_org_email_live",
            "org_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Contacts are listed by their parent account; index the FK we filter on.
        Index("ix_contact_account_id", "account_id"),
        # The cross-account list filters org_id (RLS) + deleted_at, like account.
        Index("ix_contact_org_deleted_at", "org_id", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String)
    role: Mapped[str | None] = mapped_column(String)  # free text, e.g. "Purchasing Agent"
    phone: Mapped[str | None] = mapped_column(String)
    phone_ext: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    salesperson_id: Mapped[uuid.UUID | None] = _salesperson_fk()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()
    deleted_at: Mapped[datetime | None] = _deleted_at()


class FileRole(enum.StrEnum):
    """A part file's role. The canonical schema stores this as ``text`` (not a
    native enum) with a CHECK; this StrEnum is the app-side type. ``primary`` is the
    part's geometry source of truth — at most one per part (DECISIONS.md 2026-06-25)."""

    primary = "primary"
    supporting = "supporting"


class Part(Base):
    """A manufacturable part — the entity uploaded files attach to (M1.2 **stub**).

    Files belong to a Part, never to a quote/line-item: a Part can exist on its own
    (the Part Library is created by a file upload alone), and the quote-level "Files"
    panel is just a UI aggregation (DECISIONS.md 2026-06-25). M1.2 lays down only the
    columns ``part_file`` needs; M1.5 **extends** this table (part_number, revision,
    is_assembly, obtain_method, BOM/Node tree, geom_hash, export_controlled …) via a
    forward reversible migration — it does not reshape what M1.2 creates.

    ``primary_file_id`` is the authoritative pointer to the PRIMARY file; the FK to
    ``part_file`` is added at the DB level by the migration (after ``part_file``
    exists) — declared here as a plain column to avoid a circular ORM mapping, the
    same way ``salesperson_id`` carries its FK in the migration only. That FK is
    **composite** (``(primary_file_id, id) → part_file(id, part_id)``), so a part
    can only point at one of its OWN files — a DB invariant, not just an app check."""

    __tablename__ = "part"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        # Composite-FK target so part_file.(org_id, part_id) is pinned same-org.
        UniqueConstraint("org_id", "id", name="uq_part_org_id_id"),
        # List/archive paths filter org_id (RLS) + deleted_at; lead with org_id.
        Index("ix_part_org_deleted_at", "org_id", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    primary_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()
    deleted_at: Mapped[datetime | None] = _deleted_at()


class PartFile(Base):
    """An uploaded file belonging to a :class:`Part` (M1.2; canonical ``part_file``).

    Org-scoped (RLS keys on ``org_id``); the composite FK ``(org_id, part_id)`` pins
    each file to a Part in its own org. Exactly one file per part may have
    ``role = 'primary'`` — enforced by a partial unique index — and ``part.primary_
    file_id`` is the authority kept in sync with it (DECISIONS.md 2026-06-25).

    **Hard-deleted** (no ``deleted_at``): removing a file purges its row *and* the
    object-store blob (GDPR erasure). ``is_redacted`` exists for the later
    GDPR-redaction feature; it is always ``false`` in M1.2."""

    __tablename__ = "part_file"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "part_id"],
            ["part.org_id", "part.id"],
            name="fk_part_file_part_same_org",
            ondelete="CASCADE",
        ),
        CheckConstraint("role IN ('primary', 'supporting')", name="ck_part_file_role"),
        # File size is a byte count — never negative (integrity at the boundary).
        CheckConstraint("size_bytes >= 0", name="ck_part_file_size_nonneg"),
        # Composite-FK target so part.(primary_file_id, id) can be pinned to a file
        # OF THIS PART (the migration adds that FK on `part`).
        UniqueConstraint("id", "part_id", name="uq_part_file_id_part"),
        # At most one PRIMARY per part (DECISIONS.md 2026-06-25) — the DB backstop
        # behind part.primary_file_id being the authority.
        Index(
            "uq_part_file_one_primary",
            "part_id",
            unique=True,
            postgresql_where=text("role = 'primary'"),
        ),
        # Files are listed per part; index the FK we filter on.
        Index("ix_part_file_part_id", "part_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)  # FileCategory value
    content_type: Mapped[str | None] = mapped_column(String)  # MIME, for download headers
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default=FileRole.supporting)
    is_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = _ts()


# --------------------------------------------------------------------------- #
# M1.3 — quotes (stub) + saved views
# --------------------------------------------------------------------------- #
class QuoteStatus(enum.StrEnum):
    """A quote's lifecycle status — the canonical 5-value ``quote_status`` enum
    (DB-SCHEMA.sql). The spec's 7 UI "folders" map onto these (Drafts→draft,
    Outstanding→sent, Accepted→won, Expired→expired, Lost→lost); Cancelled/Trash are
    M1.4 lifecycle rulings (DECISIONS.md 2026-06-25). M1.3 only reads/filters this;
    M1.4 owns the **enforced** transitions."""

    draft = "draft"
    sent = "sent"
    won = "won"
    lost = "lost"
    expired = "expired"


class SavedViewScope(enum.StrEnum):
    """Which list a saved view targets. M1.3 implements ``quotes`` only; the
    ``line_items`` scope exists in the type for forward-compat (M1.6) and is rejected
    at the API for now (DECISIONS.md 2026-06-25)."""

    quotes = "quotes"
    line_items = "line_items"


class SavedViewVisibility(enum.StrEnum):
    """Who can see a saved view. **Reserved**: only ``private`` is honored in v1;
    ``org`` (org-wide sharing) is deferred (DECISIONS.md 2026-06-25)."""

    private = "private"
    org = "org"


# Native Postgres enums — created by migration 0007, referenced (not re-created) here.
_quote_status_enum = Enum(QuoteStatus, name="quote_status", create_type=False)
_saved_view_scope_enum = Enum(SavedViewScope, name="saved_view_scope", create_type=False)
_saved_view_visibility_enum = Enum(
    SavedViewVisibility, name="saved_view_visibility", create_type=False
)


class Quote(Base):
    """A quote — the **minimal M1.3 stub** the quotes list renders/filters.

    Only the list/filter columns land here (number, status, account/salesperson/
    estimator, rfq_number, due_date). This mirrors the M1.2 ``part`` stub: **M1.4
    extends** this table with the lifecycle state machine, ``quote_item``, the
    Trash/soft-delete + ``cancelled`` rulings, and same-org composite-FK hardening —
    by forward ALTER, never reshaping (DECISIONS.md 2026-06-25 "M1.3 build path").
    The app role has **SELECT only** (no create endpoint in M1.3); rows are planted by
    the seeder/owner for the list, and by M1.4's create flow thereafter."""

    __tablename__ = "quote"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        UniqueConstraint("org_id", "number", name="uq_quote_org_number"),
        # Composite-FK target so M1.4's quote_item.(org_id, quote_id) is pinned same-org.
        UniqueConstraint("org_id", "id", name="uq_quote_org_id_id"),
        Index("ix_quote_org_status", "org_id", "status"),
        Index("ix_quote_org_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    number: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[QuoteStatus] = mapped_column(
        _quote_status_enum, nullable=False, server_default=QuoteStatus.draft.value
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id")
    )
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id")
    )
    estimator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id")
    )
    rfq_number: Mapped[str | None] = mapped_column(String)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class SavedView(Base):
    """A user-owned filter/sort preset for a list (spec ``#quoteslist``).

    Org-scoped (RLS) + ``owner_id`` (the creating user); the composite FK
    ``(owner_id, org_id) → user_org_membership`` pins the owner to a member of this
    org. ``filters``/``sort`` are JSONB whose shape is **identical** to the
    ``/api/quotes/search`` request body, so applying a view replays its stored clauses
    with no translation. ``visibility`` is reserved (only ``private`` honored in v1).
    System/derived views are computed in code, never stored (DECISIONS.md 2026-06-25)."""

    __tablename__ = "saved_view"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "org_id"],
            ["user_org_membership.user_id", "user_org_membership.org_id"],
            name="fk_saved_view_owner_membership",
        ),
        UniqueConstraint(
            "org_id", "owner_id", "view_scope", "name", name="uq_saved_view_owner_scope_name"
        ),
        Index("ix_saved_view_org_owner_scope", "org_id", "owner_id", "view_scope"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    view_scope: Mapped[SavedViewScope] = mapped_column(_saved_view_scope_enum, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    filters: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    sort: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    visibility: Mapped[SavedViewVisibility] = mapped_column(
        _saved_view_visibility_enum,
        nullable=False,
        server_default=SavedViewVisibility.private.value,
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()
