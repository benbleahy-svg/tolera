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
from decimal import Decimal
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
    Integer,
    Numeric,
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


class ObtainMethod(enum.StrEnum):
    """How a part/component is sourced — the make-vs-buy axis (canonical ``obtain_method``
    enum, DB-SCHEMA.sql; M1.5). Values are **UPPERCASE** to match the DDL. ``MANUFACTURED``
    is the default; ``PURCHASED`` drives purchased-component costing (linked at M4)."""

    manufactured = "MANUFACTURED"
    purchased = "PURCHASED"


# Native Postgres enums — created by the migration, referenced (not re-created) here.
_role_enum = Enum(MembershipRole, name="membership_role", create_type=False)
_status_enum = Enum(MembershipStatus, name="membership_status", create_type=False)
_country_enum = Enum(OrgCountry, name="org_country", create_type=False)
_account_type_enum = Enum(AccountType, name="account_type", create_type=False)
# UPPERCASE DB values ('MANUFACTURED'/'PURCHASED') differ from the lowercase member
# names, so map by ``.value`` (the other enums have name == value and need no callable).
_obtain_method_enum = Enum(
    ObtainMethod,
    name="obtain_method",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


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
        # Shipped list filter (`GET /api/accounts?salesperson_id=`) + FK-enforcement
        # scans when a membership row changes (migration 0011).
        Index("ix_account_org_salesperson", "org_id", "salesperson_id"),
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
        # Part-library historical match by geometry signature (populated at M4).
        Index("ix_part_org_geom_hash", "org_id", "geom_hash"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    primary_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Identity (M1.5) — free-text, nullable, NOT unique (matching/dedup is M2;
    # DECISIONS.md 2026-06-26 "Part identity uniqueness").
    name: Mapped[str | None] = mapped_column(String)
    part_number: Mapped[str | None] = mapped_column(String)
    revision: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    is_assembly: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    obtain_method: Mapped[ObtainMethod] = mapped_column(
        _obtain_method_enum, nullable=False, server_default=ObtainMethod.manufactured.value
    )
    custom_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Interrogation signature for part-library match — NULL until M4.
    geom_hash: Mapped[str | None] = mapped_column(Text)
    # EU dual-use export flag (DACH delta; primary home is the Part — it travels across
    # quotes). Stored only in M1.5; runtime enforcement → M6 (DECISIONS.md 2026-06-26).
    export_controlled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
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


class PartGeometry(Base):
    """A part's geometry — the **geometry↔Kalk contract** (PartGeometry-Attribute-Catalog;
    M1.5). 1:1 with :class:`Part`. Stores effective **metric** dims (mm/mm²/mm³/g) that
    Kalk reads as ``part.size_x`` etc.

    Calc-vs-override (DECISIONS.md 2026-06-26): the numeric columns hold the *effective*
    value = ``COALESCE(override, raw)``. ``raw`` is the interrogation extraction (NULL
    until M4); ``overrides`` records which dims a human set (its keys are the column names).
    In M1.5 (manual-only) a typed dim writes both the numeric column and its ``overrides``
    key, so M4 interrogation fills ``raw`` without clobbering a manual value. The IN/MM
    toggle is presentation-only — storage is always metric (DACH units invariant)."""

    __tablename__ = "part_geometry"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        UniqueConstraint("part_id", name="uq_part_geometry_part"),
        ForeignKeyConstraint(
            ["org_id", "part_id"],
            ["part.org_id", "part.id"],
            name="fk_part_geometry_part_org",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    size_x: Mapped[Decimal | None] = mapped_column(Numeric)
    size_y: Mapped[Decimal | None] = mapped_column(Numeric)
    size_z: Mapped[Decimal | None] = mapped_column(Numeric)
    max_dim: Mapped[Decimal | None] = mapped_column(Numeric)
    med_dim: Mapped[Decimal | None] = mapped_column(Numeric)
    min_dim: Mapped[Decimal | None] = mapped_column(Numeric)
    area: Mapped[Decimal | None] = mapped_column(Numeric)
    volume: Mapped[Decimal | None] = mapped_column(Numeric)
    weight: Mapped[Decimal | None] = mapped_column(Numeric)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class Node(Base):
    """An occurrence of a :class:`Part` in a BOM tree (DOMAIN-MODEL; M1.5). One Part may
    have many Nodes; a repeated part is quoted once. ``parent_node_id`` NULL = the **root**
    node (qty 1, linked to the root part). M1.5 populates only the root node; child nodes /
    the BOM Builder are M4. ``root_part_id`` denormalizes the tree root for fast scoping.

    Composite FKs pin both the part and the parent node to the **same org** (the parent FK
    is MATCH SIMPLE, so a NULL ``parent_node_id`` skips the check)."""

    __tablename__ = "node"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_node_org_id_id"),
        CheckConstraint("qty_relative_to_parent > 0", name="ck_node_qty_positive"),
        ForeignKeyConstraint(
            ["org_id", "part_id"], ["part.org_id", "part.id"], name="fk_node_part_org"
        ),
        # The denormalized tree root must be a same-org part too (NOT NULL) — else a
        # tree lookup keyed on (org_id, root_part_id) could read a rootless/cross-org node.
        ForeignKeyConstraint(
            ["org_id", "root_part_id"], ["part.org_id", "part.id"], name="fk_node_root_part_org"
        ),
        ForeignKeyConstraint(
            ["org_id", "parent_node_id"],
            ["node.org_id", "node.id"],
            name="fk_node_parent_org",
        ),
        Index("ix_node_parent", "parent_node_id"),
        Index("ix_node_org_part", "org_id", "part_id"),
        Index("ix_node_org_root_part", "org_id", "root_part_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    qty_relative_to_parent: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    root_part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = _ts()


# --------------------------------------------------------------------------- #
# M1.3 — quotes (stub) + saved views
# --------------------------------------------------------------------------- #
class QuoteStatus(enum.StrEnum):
    """A quote's lifecycle status (spec ``#quotelifecycle``, "decided").

    The canonical 5 (``draft, sent, won, lost, expired``) plus the three M1.4
    rulings (DECISIONS.md 2026-06-26 "Quote status enum"): ``cancelled`` (abandoned
    by the shop, kept for audit), ``no_quote`` (formally declining the **whole** RFQ
    — terminal, distinct from the line-item :class:`QiWorkflowStatus.no_quote`), and
    ``on_hold`` (a reversible manual pause that returns to the prior status — see
    ``quote.status_before_hold``). **Trash** is soft-delete (``quote.deleted_at``),
    not a status. **Superseded** + the revision/reopen flows are M5, so no
    ``superseded`` value yet — values are append-only (ADD VALUE), so M5 adds it with
    no rebuild. M1.4 owns the **enforced** transitions (``app.quote_lifecycle``)."""

    draft = "draft"
    sent = "sent"
    won = "won"
    lost = "lost"
    expired = "expired"
    cancelled = "cancelled"
    no_quote = "no_quote"
    on_hold = "on_hold"


class QiWorkflowStatus(enum.StrEnum):
    """A quote item's (line-item's) own progress status — the canonical
    ``qi_workflow_status`` enum (DB-SCHEMA.sql). Independent of the parent quote's
    status: a line item runs Not Started → In Progress → Complete, may be paused
    (``on_hold``) or declined (``no_quote``, which counts as complete for the
    quote's incomplete-items rollup but is unselectable on the digital quote)."""

    not_started = "not_started"
    in_progress = "in_progress"
    on_hold = "on_hold"
    completed = "completed"
    no_quote = "no_quote"


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
# ``quote_status`` gains its three M1.4 values via ALTER TYPE in migration 0008;
# ``qi_workflow_status`` is created there too.
_quote_status_enum = Enum(QuoteStatus, name="quote_status", create_type=False)
_qi_workflow_status_enum = Enum(QiWorkflowStatus, name="qi_workflow_status", create_type=False)
_saved_view_scope_enum = Enum(SavedViewScope, name="saved_view_scope", create_type=False)
_saved_view_visibility_enum = Enum(
    SavedViewVisibility, name="saved_view_visibility", create_type=False
)


class Quote(Base):
    """A quote — created in M1.3 as a list/filter stub, **extended by M1.4** with the
    lifecycle state machine, ``quote_item``, and same-org composite-FK hardening.

    M1.4 (DECISIONS.md 2026-06-26) drops the stub's plain global FKs and re-adds
    **composite same-org FKs** — ``(org_id, account_id) → account``, ``(org_id,
    contact_id) → contact``, and ``(salesperson_id|estimator_id, org_id) →
    user_org_membership`` — so a cross-org reference is a DB impossibility, not merely
    an RLS/app check (the M1.1 salesperson rationale). It adds the canonical columns it
    needs (contact, the workflow-tracker timestamps, ``status_before_hold`` for un-hold,
    ``deleted_at`` for Trash, ``config_frozen_at`` column-only per E4-d) but **defers**
    the send/digital-quote columns and the revision flow to M5 (no reshaping). The app
    role gains INSERT/UPDATE here (it was SELECT-only in M1.3)."""

    __tablename__ = "quote"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        # DACH money convention: a quote's currency is EUR (DE/AT) or CHF (CH) only.
        CheckConstraint("currency IN ('EUR', 'CHF')", name="ck_quote_currency_dach"),
        UniqueConstraint("org_id", "number", name="uq_quote_org_number"),
        # Composite-FK target so quote_item.(org_id, quote_id) is pinned same-org.
        UniqueConstraint("org_id", "id", name="uq_quote_org_id_id"),
        # Same-org FK hardening (M1.4): each reference must live in THIS org. The
        # columns are nullable; MATCH SIMPLE skips the check when the ref is NULL.
        ForeignKeyConstraint(
            ["org_id", "account_id"],
            ["account.org_id", "account.id"],
            name="fk_quote_account_org",
        ),
        ForeignKeyConstraint(
            ["org_id", "contact_id"],
            ["contact.org_id", "contact.id"],
            name="fk_quote_contact_org",
        ),
        ForeignKeyConstraint(
            ["salesperson_id", "org_id"],
            ["user_org_membership.user_id", "user_org_membership.org_id"],
            name="fk_quote_salesperson_membership",
        ),
        ForeignKeyConstraint(
            ["estimator_id", "org_id"],
            ["user_org_membership.user_id", "user_org_membership.org_id"],
            name="fk_quote_estimator_membership",
        ),
        Index("ix_quote_org_status", "org_id", "status"),
        Index("ix_quote_org_created_at", "org_id", "created_at"),
        # Every /api/quotes/search starts with `deleted_at IS NULL` — same
        # (org_id, deleted_at) convention as account/contact/part (migration 0011).
        Index("ix_quote_org_deleted_at", "org_id", "deleted_at"),
        # The filter grammar's allow-listed FK fields (account/salesperson/estimator)
        # — the hottest list in the product must not seq-scan per filter.
        Index("ix_quote_org_account", "org_id", "account_id"),
        Index("ix_quote_org_salesperson", "org_id", "salesperson_id"),
        Index("ix_quote_org_estimator", "org_id", "estimator_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    number: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    status: Mapped[QuoteStatus] = mapped_column(
        _quote_status_enum, nullable=False, server_default=QuoteStatus.draft.value
    )
    # Set when the quote enters ``on_hold``; the un-hold transition's only legal
    # target is this stored status, then it is cleared (DECISIONS.md 2026-06-26).
    status_before_hold: Mapped[QuoteStatus | None] = mapped_column(_quote_status_enum)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    # FK columns (constraints declared compositely above — no inline ForeignKey).
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    estimator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rfq_number: Mapped[str | None] = mapped_column(String)
    private_notes: Mapped[str | None] = mapped_column(Text)
    # E4-d freeze marker — column only in M1.4; freeze/Refresh-Pricing is pricing-engine work.
    config_frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Workflow-tracker + lifecycle timestamps.
    rfq_received_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expiration_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimator_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    salesperson_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Trash = recoverable soft-delete (any status), distinct from the ``cancelled`` status.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class Component(Base):
    """A Part **with pricing** — the quoting layer over a Part (KB
    ``assemblies-data-types-and-terminology``). M1.4 lands a **minimal stub**: just
    enough to anchor a :class:`QuoteItem`'s root component to a Part. **M1.5 extends**
    it with process/material/``obtain_method``/``is_assembly`` + the BOM tree, by
    forward ALTER (DECISIONS.md 2026-06-26 "QuoteItem anchoring"). ``UNIQUE (org_id,
    id)`` is the composite-FK target for ``quote_item.(org_id, root_component_id)``."""

    __tablename__ = "component"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_component_org_id_id"),
        ForeignKeyConstraint(
            ["org_id", "part_id"], ["part.org_id", "part.id"], name="fk_component_part_org"
        ),
        Index("ix_component_org_part", "org_id", "part_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_root_component: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # M1.5 structural extensions. ``process_id``/``material_id``/``purchased_component_id``
    # are deferred to M1.7/M4 (their tables don't exist yet).
    obtain_method: Mapped[ObtainMethod] = mapped_column(
        _obtain_method_enum, nullable=False, server_default=ObtainMethod.manufactured.value
    )
    is_assembly: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class QuoteItem(Base):
    """A line item: the **root component** tied to a Quote at a position (DOMAIN-MODEL).
    Carries its own ``workflow_status`` (Not Started → … → Complete), independent of
    the parent quote's status. Composite FKs pin both the quote and the root component
    to the **same org** as the item."""

    __tablename__ = "quote_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "quote_id"], ["quote.org_id", "quote.id"], name="fk_quote_item_quote_org"
        ),
        ForeignKeyConstraint(
            ["org_id", "root_component_id"],
            ["component.org_id", "component.id"],
            name="fk_quote_item_component_org",
        ),
        # Positions are unique within a quote — the DB backstop against a
        # concurrent add-item race (the API also serialises via a row lock).
        UniqueConstraint("quote_id", "position", name="uq_quote_item_quote_position"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    root_component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    workflow_status: Mapped[QiWorkflowStatus] = mapped_column(
        _qi_workflow_status_enum, nullable=False, server_default=QiWorkflowStatus.not_started.value
    )
    was_won: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    export_controlled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class ComponentQuantity(Base):
    """One **quantity break** of a component — the per-break cell every downstream
    cost/price renders into (DOMAIN-MODEL "the richest entity"; M1.6). M1.6 lands only
    the **quantity** triple; the cost/price/discount/profit/lead-time columns from
    ``DB-SCHEMA.sql`` are added by their owning milestones (M1.7/M1.10/M1.11) via
    forward ALTER — and the money representation they use is the open question logged
    in DECISIONS.md 2026-06-27 (so no money column lands here yet).

    The three quantities are the geometry↔Kalk contract's ``part.qty`` / ``part.bom_qty``
    list backing (`#partview` Pricing & Quantities):

    * ``quantity`` — the **customer-requested** break value (1, 5, 20 …).
    * ``make_quantity`` — qty to **make** (``part.qty``); = requested qty propagated
      through tree position, plus scrap. **M1.6 root-only identity:** equals ``quantity``
      (no children, no scrap yet — real tree/scrap math is M4).
    * ``deliver_quantity`` — qty to **deliver** (``part.bom_qty``); also = ``quantity``
      for the root in M1.6. ``part.innate_quantity`` (deliver per one top-level part = 1
      for the root) is **derived**, not stored.

    Breaks live on the **root component** only in M1.6 (child-component cells arrive with
    the BOM Builder at M4). ``UNIQUE (component_id, quantity)`` forbids duplicate breaks
    (a deliberate divergence from PP's KB, which allows them — the schema, a higher tier,
    governs; DECISIONS.md/M1.6 grill). Composite same-org FK pins the cell to its
    component's org."""

    __tablename__ = "component_quantity"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "component_id"],
            ["component.org_id", "component.id"],
            name="fk_component_quantity_component_org",
            ondelete="CASCADE",
        ),
        # No duplicate breaks for one component (the index-aligned lists key on the
        # quantity value); also the M1.7+ cost-cell tables FK onto (component, quantity).
        UniqueConstraint("component_id", "quantity", name="uq_component_quantity_comp_qty"),
        CheckConstraint("quantity > 0", name="ck_component_quantity_positive"),
        Index("ix_component_quantity_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable per DB-SCHEMA (M4 may leave them unresolved mid-interrogation); the M1.6
    # service always populates them (= quantity) so the iterators never align a NULL.
    make_quantity: Mapped[int | None] = mapped_column(Integer)
    deliver_quantity: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class QuoteStatusEvent(Base):
    """Append-only audit of quote status changes (DECISIONS.md 2026-06-26). One row per
    transition — and one for creation (``from_status = NULL → draft``). Home of the
    optional Lost reason ``note``; the trail behind win/loss analysis + reopen. The app
    role gets SELECT/INSERT only (never UPDATE/DELETE) so history can't be rewritten."""

    __tablename__ = "quote_status_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "quote_id"], ["quote.org_id", "quote.id"], name="fk_qse_quote_org"
        ),
        Index("ix_qse_org_quote_created", "org_id", "quote_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_status: Mapped[QuoteStatus | None] = mapped_column(_quote_status_enum)
    to_status: Mapped[QuoteStatus] = mapped_column(_quote_status_enum, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


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
