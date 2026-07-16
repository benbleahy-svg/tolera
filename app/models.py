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
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as PyUUID  # for classes whose own `uuid` column shadows the module

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
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


def _ai_flag() -> Mapped[bool]:
    """A per-org AI toggle: non-null boolean defaulting TRUE (see OrgAiSettings)."""
    return mapped_column(Boolean, nullable=False, server_default=text("true"))


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
    # DACH Costing Mode (spec #dach-costing): opt-in config switch — default
    # off, DACH orgs provisioned on. Gates the Zuschlagskalkulation seed and
    # the get_herstellkosten()/get_selbstkosten() Kalk helpers (M1.12).
    dach_costing_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # §6 expedite default set — prefills the M1.11 top-of-quote editor:
    # [{"days_faster": int, "markup_pct": "<decimal string>"}]
    default_expedite_tiers: Mapped[list[Any] | None] = mapped_column(JSONB)
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
    # Lifecycle (spec#partlib, M2.12): Active → archived_at (restorable, Archived
    # tab) → deleted_at (irreversible; files purged, quote costing preserved).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    # Provenance for derived files (M2.5 split pages; later redacted copies/merges).
    # DDL (0017): composite same-org FK → part_file(org_id, id) with column-list
    # SET NULL (source_file_id) — PG15+ form the ORM can't express, so authored raw.
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Intake provenance (M3.3): which ingested RFQ this file arrived with —
    # lets the quote Files panel group "Supporting Files (n) — auto-extracted
    # from the email" and lets M3.4 distribute files to line items. Composite
    # same-org FK added in migration 0022.
    rfq_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Match-index fields (M2.12, spec#partlib "How matching works") — computed
    # deterministically at ingest by app.part_index; geometry signature/vector
    # land with GeometryService (M4). pdf_text is filled async (Celery).
    file_hash: Mapped[str | None] = mapped_column(Text)  # SHA-256 hex of raw bytes
    filename_normalized: Mapped[str | None] = mapped_column(Text)
    part_number_extracted: Mapped[str | None] = mapped_column(Text)
    pdf_text: Mapped[str | None] = mapped_column(Text)
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
class RequestForQuote(Base):
    """An intake RFQ — the canonical ``request_for_quote`` (DB-SCHEMA.sql
    "intake (RFQ)"; M3.3). Email ingest (spec ``#wingman`` pipeline 1) creates
    one per inbound message to ``{org-slug}@rfq.tolera.eu``; the Smart RFQ form
    (M3.4 ⟂) will create them without the email-specific fields.

    **Additive ingest columns** beyond the frozen DDL (the lean-extend
    precedent): ``email_message_id`` — the RFC 5322 Message-Id (or a
    ``sha256:…`` content-hash surrogate), unique per org so a Mailgun retry can
    never mint a duplicate quote (M3.3 "dedupe on message-id"); ``subject``;
    and the stored raw ``.eml`` (``eml_*``) — the quote's **ORIGINAL RFQ**
    (spec quote-files: "RFQ (1) — the original .eml with an ORIGINAL RFQ
    badge"). Files otherwise belong to Parts, and the ``.eml`` is not a part,
    so its blob is keyed here."""

    __tablename__ = "request_for_quote"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        # Mirror migration 0022 so a metadata-created schema (tests) carries
        # the same integrity rule (CodeRabbit).
        CheckConstraint(
            "eml_size_bytes IS NULL OR eml_size_bytes >= 0", name="ck_rfq_eml_size_nonneg"
        ),
        # Composite-FK target so part_file.(org_id, rfq_id) pins same-org.
        UniqueConstraint("org_id", "id", name="uq_rfq_org_id_id"),
        # The converted quote must live in THIS org (fk added in migration —
        # composite same-org form, MATCH SIMPLE skips pre-conversion NULLs).
        ForeignKeyConstraint(
            ["org_id", "quote_id"], ["quote.org_id", "quote.id"], name="fk_rfq_quote_org"
        ),
        # Webhook idempotency: same Message-Id ⇒ same RFQ ⇒ no duplicate quote.
        # Partial: form-created RFQs (M3.4 ⟂) have no email at all.
        Index(
            "uq_rfq_org_message_id",
            "org_id",
            "email_message_id",
            unique=True,
            postgresql_where=text("email_message_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    rfq_number: Mapped[str | None] = mapped_column(String)
    business_name: Mapped[str | None] = mapped_column(String)
    first_name: Mapped[str | None] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    referrer: Mapped[str | None] = mapped_column(String)
    marketing_source: Mapped[str | None] = mapped_column(String)
    requested_delivery_date: Mapped[date | None] = mapped_column(Date)
    export_controlled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Email-ingest additions (M3.3).
    email_message_id: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    eml_storage_key: Mapped[str | None] = mapped_column(Text)
    eml_filename: Mapped[str | None] = mapped_column(String)
    eml_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    # Conversion state: set once the ingest task has built the draft quote.
    quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    processed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M3.4 — the guarded parts-list suggestion the body-parse task persists
    # (``{status, prompt_version, parsed_at, dropped, error_code, items[]}``,
    # app.email_parts._payload). A suggestion snapshot, org-scoped with the row;
    # NULL until the parse task has run. Additive (lean-extend precedent).
    suggested_line_items: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _ts()


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
    # Canonical ``quote.email_thread_id`` (DB-SCHEMA.sql), added by M3.3: the
    # inbound RFC 5322 Message-Id — M3.5 threads replies onto it via
    # In-Reply-To/References matching.
    email_thread_id: Mapped[str | None] = mapped_column(Text)
    # E4-d freeze marker — column only in M1.4; freeze/Refresh-Pricing is pricing-engine work.
    config_frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M1.11 — the top-of-quote dynamic-lead-time editor state (spec #addons
    # "Expedite: configured at quote level; APPLY TO ALL pushes the tiers to
    # every line item"): {"standard_lead_time_days": int|null, "tiers":
    # [{"days_faster": int, "markup_pct": "<decimal string>"}]}. Staging only — the math
    # reads the per-component expedite_option rows the apply writes.
    expedite_tiers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # M3.9 — the cached RFQ Triage Brief (spec #ai-triage build-note: "Add
    # triage_brief JSONB to Quote"). Regenerable cache written by the
    # ``generate_triage_brief`` task after the email-parse job; NULL until then.
    triage_brief: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
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
        # M1.7 same-org pins for the estimating assignments (the material picker /
        # Change Process); ``purchased_component_id`` stays deferred to M4.
        ForeignKeyConstraint(
            ["org_id", "material_id"],
            ["material.org_id", "material.id"],
            name="fk_component_material_org",
        ),
        ForeignKeyConstraint(
            ["org_id", "process_id"],
            ["process.org_id", "process.id"],
            name="fk_component_process_org",
        ),
        Index("ix_component_org_part", "org_id", "part_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_root_component: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # M1.5 structural extensions; material/process assignment landed with M1.7.
    material_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    process_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    obtain_method: Mapped[ObtainMethod] = mapped_column(
        _obtain_method_enum, nullable=False, server_default=ObtainMethod.manufactured.value
    )
    is_assembly: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # M1.10 pre-M4 cost sources (DECISIONS.md 2026-07-09): per-unit piece price
    # (PURCHASED children → the Purchased-Components bucket) and a per-unit
    # manual override that replaces a child's rolled-up cost (→ Component
    # Overrides bucket). The full purchased_component entity lands at M4.
    piece_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    manual_override_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
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
    # M1.10 per-break roll-up + price results (spec #costing / #kalk-rollup;
    # folded DDL minus lead_time_days → M1.11). The pricing engine writes the
    # calc side; manual_unit_price is the estimator's override; unit_price /
    # total_price are the buyer-facing resolved values (incl. discounts),
    # rounded HALF-UP to 2 dp at this boundary (DECISIONS.md 2026-07-09).
    material_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    inside_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    outside_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    purchased_component_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    child_override_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    manual_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    total_discount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    total_discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    total_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    profit_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    # M1.11 per-break lead time (spec #addons Lead Times; the folded-DDL
    # ``lead_time_days`` split into the CLAUDE.md §5 calc-vs-override pair,
    # the same divergence M1.10 made for unit_price). calc = process default
    # + material adder + Σ effective operation DAYS at this break; manual =
    # the estimator's blue-text edit; lead_time_days = the resolved value.
    calc_lead_time_days: Mapped[int | None] = mapped_column(Integer)
    manual_lead_time_days: Mapped[int | None] = mapped_column(Integer)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
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


# --------------------------------------------------------------------------- #
# M1.7 — Materials catalog, processes, operation library, per-qty cost cells
# --------------------------------------------------------------------------- #
class OpCategory(enum.StrEnum):
    """An operation row's kind (canonical ``op_category`` enum, DB-SCHEMA.sql /
    SEED §3). ``material`` rows are the stock/material lines ("ADD MATERIAL
    OPERATION" — spec ``#partview`` Materials section); ``operation`` rows are
    the router work steps."""

    operation = "operation"
    material = "material"


class CalculationMode(enum.StrEnum):
    """How an operation's cost is computed (spec ``#oplibrary`` operation data
    model). Controls which rate fields apply:

    * ``machine_plus_operator`` — MSS machine rate (``run_rate``) on Hauptzeit
      plus operator rate (``labour_rate``) on Nebenzeit.
    * ``labour_only`` — one labour rate (``run_rate``) on Arbeitszeit.
    * ``outside_process`` — routed to the Vendor-RFQ portal (M6); **no internal
      calc** — cost cells are manual until then.
    """

    machine_plus_operator = "machine_plus_operator"
    labour_only = "labour_only"
    outside_process = "outside_process"


class SetupBasis(enum.StrEnum):
    """How setup is charged (spec ``#oplibrary``): a **flat €** amount per lot
    (default) or **time-based** (Advanced toggle — setup minutes x rate; rate =
    ``run_rate`` per the DECISIONS.md 2026-07-07 OPEN default). The two are
    mutually exclusive by construction: the basis picks which field applies."""

    flat = "flat"
    time = "time"


class ProcessFamily(enum.StrEnum):
    """The interrogation/routing family a process belongs to (DB-SCHEMA
    ``process_family``; spec ``#geometryservice`` families). M1.12 stores it;
    family-specific interrogation arrives with M4."""

    SHEET_METAL = "SHEET_METAL"
    MILLING = "MILLING"
    LATHE = "LATHE"
    TUBE_LASER = "TUBE_LASER"
    WIRE_EDM = "WIRE_EDM"
    CAST_URETHANE = "CAST_URETHANE"
    ADDITIVE = "ADDITIVE"
    ASSEMBLY = "ASSEMBLY"
    GENERIC = "GENERIC"


_op_category_enum = Enum(OpCategory, name="op_category", create_type=False)
_calculation_mode_enum = Enum(CalculationMode, name="calculation_mode", create_type=False)
_setup_basis_enum = Enum(SetupBasis, name="setup_basis", create_type=False)
_process_family_enum = Enum(ProcessFamily, name="process_family", create_type=False)


class MaterialClass(Base):
    """Top level of the 3-level materials hierarchy (Class → Family → Material;
    DB-SCHEMA "materials"). Seeded per org (Metall in M1.7; the full class set —
    Polymer, Holz, Sonstige, … — arrives with M1.12). ``UNIQUE (org_id, name)``
    keys the idempotent seed; ``UNIQUE (org_id, id)`` is the composite-FK target."""

    __tablename__ = "material_class"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_material_class_org_id_id"),
        UniqueConstraint("org_id", "name", name="uq_material_class_org_name"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class MaterialFamily(Base):
    """Middle level of the materials hierarchy — e.g. Nichtrostender Stahl,
    Werkzeugstahl (German-first display names; DECISIONS.md 2026-07-07 "M1.7
    material catalog content"). ``alias`` keeps the English/hubs family name for
    the type-ahead. Same-org composite FK to the class."""

    __tablename__ = "material_family"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_material_family_org_id_id"),
        UniqueConstraint("org_id", "class_id", "name", name="uq_material_family_org_class_name"),
        ForeignKeyConstraint(
            ["org_id", "class_id"],
            ["material_class.org_id", "material_class.id"],
            name="fk_material_family_class_org",
        ),
        Index("ix_material_family_org_class", "org_id", "class_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    alias: Mapped[str | None] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class Material(Base):
    """A concrete stock material (leaf of the hierarchy), DACH-keyed: DIN EN 10027
    ``werkstoffnummer`` (e.g. ``1.4301``), EN short name (``X5CrNi18-10``), AISI
    alias (``304``) — DACH-DELTA §4. ``density`` is g/cm³; ``cost_per_volume`` /
    ``cost_per_area`` stay NULL until the shop sets rates (the M1.14 missing-rates
    guard flags this). "Edit Material Properties" (spec ``#partview``) edits this
    org-library row."""

    __tablename__ = "material"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_material_org_id_id"),
        UniqueConstraint("org_id", "family_id", "display_name", name="uq_material_org_family_name"),
        ForeignKeyConstraint(
            ["org_id", "family_id"],
            ["material_family.org_id", "material_family.id"],
            name="fk_material_family_org",
        ),
        Index("ix_material_org_family", "org_id", "family_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    werkstoffnummer: Mapped[str | None] = mapped_column(String)
    en_name: Mapped[str | None] = mapped_column(String)
    aisi_alias: Mapped[str | None] = mapped_column(String)
    density: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    cost_per_volume: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    cost_per_area: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    added_lead_time_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class Process(Base):
    """A manufacturing process a component can be assigned to (spec ``#partview``
    Change Process). **M1.7 lands the minimal entity** — name + external name;
    router templates, process↔operation membership and the ``process_family``
    enum arrive with M1.12/M4 by forward ALTER (the M1.4/M1.5 stub-then-extend
    precedent). Core-4 names are seeded so Change Process has real targets."""

    __tablename__ = "process"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_process_org_id_id"),
        UniqueConstraint("org_id", "name", name="uq_process_org_name"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    external_name: Mapped[str | None] = mapped_column(String)
    default_lead_time_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    # M1.12 forward-ALTER (the deferred M1.7 columns): routing family, the
    # default purchased-component process flag, Smart-RFQ visibility.
    family: Mapped[ProcessFamily] = mapped_column(
        _process_family_enum, nullable=False, server_default=ProcessFamily.GENERIC.value
    )
    is_default_purchased_component_process: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    available_in_smart_rfq: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    deleted_at: Mapped[datetime | None] = _deleted_at()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class OperationDef(Base):
    """An org-library operation definition (spec ``#oplibrary`` data model — the
    DACH shape; DECISIONS.md 2026-07-07 "Operation model shape"). Times are
    **minutes** product-wide. ``setup_basis`` picks flat-€ ``setup_cost`` vs
    time-based ``setup_time_mins`` (Advanced toggle). Rates are €/hr; NULL until
    the shop configures them (rates are never pre-seeded). ``is_pre_installed``
    rows (the 54-op M1.12 seed) can be renamed or hidden (``deleted_at``) but
    never hard-deleted. The Kalk ``cost_formula`` column lands at M1.9."""

    __tablename__ = "operation_def"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_operation_def_org_id_id"),
        # Live library names are unique per org (the auto-save dedup key); soft-
        # deleted rows fall out of the constraint via the partial index in the
        # migration (uq_operation_def_org_name_live) — not expressible here.
        CheckConstraint(
            "surcharge_pct >= 0 AND surcharge_pct <= 100", name="ck_operation_def_surcharge_range"
        ),
        Index("ix_operation_def_org_sort", "org_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[OpCategory] = mapped_column(
        _op_category_enum, nullable=False, server_default=OpCategory.operation.value
    )
    calculation_mode: Mapped[CalculationMode] = mapped_column(
        _calculation_mode_enum,
        nullable=False,
        server_default=CalculationMode.machine_plus_operator.value,
    )
    run_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    labour_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    setup_basis: Mapped[SetupBasis] = mapped_column(
        _setup_basis_enum, nullable=False, server_default=SetupBasis.flat.value
    )
    setup_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    setup_time_mins: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    surcharge_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, server_default=text("0")
    )
    is_outside_service: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_finish: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_pre_installed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_formula: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = _deleted_at()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class Operation(Base):
    """An operation **instance** on a component — a router row (``category =
    operation``) or a material line (``category = material``), spec ``#partview``
    Materials · Operations. Mode/rates/setup are **copied from the library def at
    attach time** so a later library edit never silently reprices an existing
    quote (E4-d config-freeze posture).

    Time inputs are per-row **calc/manual pairs in minutes** (drawer PRIMARY:
    Calculated vs Override): ``runtime_mins`` = Hauptzeit (machine mode) or
    Arbeitszeit (labour mode); ``attend_mins`` = Nebenzeit (machine mode only).
    In M1.7 the ``calc_*`` times seed from the def and manual overrides sit on
    top; M1.9 makes the calc side formula-driven. ``yield_factor`` (material
    lines) grosses up material quantity/cost for scrap once a material calc
    source exists (``#oplibrary`` Material line — yield factor).

    ``position`` is the router order (drag-reorder); not DB-unique — the full
    order is reassigned in one transaction and reads sort ``(position, id)``.
    ``UNIQUE (org_id, id)`` is the same-org composite-FK target for cells."""

    __tablename__ = "operation"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_operation_org_id_id"),
        ForeignKeyConstraint(
            ["org_id", "component_id"],
            ["component.org_id", "component.id"],
            name="fk_operation_component_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["org_id", "operation_def_id"],
            ["operation_def.org_id", "operation_def.id"],
            name="fk_operation_def_org",
        ),
        CheckConstraint(
            "surcharge_pct >= 0 AND surcharge_pct <= 100", name="ck_operation_surcharge_range"
        ),
        CheckConstraint(
            "yield_factor > 0 AND yield_factor <= 1", name="ck_operation_yield_factor_range"
        ),
        Index("ix_operation_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation_def_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[OpCategory] = mapped_column(
        _op_category_enum, nullable=False, server_default=OpCategory.operation.value
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    calculation_mode: Mapped[CalculationMode] = mapped_column(
        _calculation_mode_enum,
        nullable=False,
        server_default=CalculationMode.machine_plus_operator.value,
    )
    run_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    labour_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    setup_basis: Mapped[SetupBasis] = mapped_column(
        _setup_basis_enum, nullable=False, server_default=SetupBasis.flat.value
    )
    setup_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_setup_mins: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    manual_setup_mins: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    calc_runtime_mins: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    manual_runtime_mins: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_attend_mins: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    manual_attend_mins: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    surcharge_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, server_default=text("0")
    )
    yield_factor: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("1.0")
    )
    is_outside_service: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_finish: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_from_factory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # M3.10 (Rule Auto-Suggestion): TRUE when an estimator added this operation
    # directly (the manual-add path in ``app.operations``); FALSE when a rule
    # resolution added it (ADD_OPERATION, ``app.review_items``). Only manual adds
    # feed the "tribal knowledge that should be a rule" pattern detector, so this
    # flag is the aggregate's filter (spec ``#ai-rule-suggest``). Defaults TRUE:
    # pre-M3.10 rows were all estimator/manual adds (no auto-add path existed).
    added_manually: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # Kalk (M1.9): formula snapshot copied from the def at attach (E4-d freeze);
    # variable_overrides = {name: value} / {name: {"<qty>": value}} — the
    # runtime/setup_time specials keep using the manual_*_mins columns instead.
    cost_formula: Mapped[str | None] = mapped_column(Text)
    variable_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class QuoteCell(Base):
    """One operation's cost at one quantity break — the per-qty cost cell (spec
    ``#partview`` per-quantity columns; DB-SCHEMA ``quote_cell``). Carries the
    **Calculated-vs-Override pair**: ``calc_cost`` (mode arithmetic in M1.7, Kalk
    from M1.9) and ``manual_cost`` (the estimator's override) — persist both,
    resolve ``COALESCE(manual_cost, calc_cost)``, recalculation never touches
    ``manual_cost`` (CLAUDE.md §5). ``numeric(14,4)`` per the resolved money
    decision (DECISIONS.md 2026-06-27): 4-dp intermediates, minor-unit rounding
    only at the quote-total boundary.

    The ``(component_id, quantity)`` composite FK onto ``component_quantity``
    ties every cell to a **real break** — removing a break cascades its cells
    away; adding one gets cells on the next recalc."""

    __tablename__ = "quote_cell"
    __table_args__ = (
        UniqueConstraint("operation_id", "quantity", name="uq_quote_cell_operation_qty"),
        ForeignKeyConstraint(
            ["org_id", "operation_id"],
            ["operation.org_id", "operation.id"],
            name="fk_quote_cell_operation_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["component_id", "quantity"],
            ["component_quantity.component_id", "component_quantity.quantity"],
            name="fk_quote_cell_component_quantity",
            ondelete="CASCADE",
        ),
        Index("ix_quote_cell_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    calc_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    manual_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    # M1.11 — the operation's Kalk ``DAYS`` output (business days), the
    # deferred column from the M1.7 quote_cell decision. Calc-only: the
    # break-level ``manual_lead_time_days`` is the human override point.
    days: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class CustomTable(Base):
    """An org Custom Table backing Kalk ``table_var``/``table_lookup`` (spec
    ``#kalk-tables``, ``#customcat``; DECISIONS.md 2026-07-08). ``columns`` is
    ``[{name, type}]`` with type ∈ boolean | numeric | string; names are
    alphanumeric with no leading digit because formulas dot-access them."""

    __tablename__ = "custom_table"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_custom_table_org_id_id"),
        UniqueConstraint("org_id", "name", name="uq_custom_table_org_name"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()

    rows: Mapped[list[CustomTableRow]] = relationship(
        back_populates="table",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CustomTableRow.row_number",
        primaryjoin="and_(CustomTable.id == foreign(CustomTableRow.table_id), "
        "CustomTable.org_id == CustomTableRow.org_id)",
    )


class CustomTableRow(Base):
    """One Custom Table row; ``data`` is ``{column: value}`` (null = empty cell).
    Carries its own ``org_id`` + composite FK so a row can never reference
    another org's table (tier-1 org-scoping)."""

    __tablename__ = "custom_table_row"
    __table_args__ = (
        UniqueConstraint("table_id", "row_number", name="uq_custom_table_row_table_number"),
        ForeignKeyConstraint(
            ["org_id", "table_id"],
            ["custom_table.org_id", "custom_table.id"],
            name="fk_custom_table_row_table_org",
            ondelete="CASCADE",
        ),
        Index("ix_custom_table_row_org_table", "org_id", "table_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()

    table: Mapped[CustomTable] = relationship(
        back_populates="rows",
        primaryjoin="and_(CustomTable.id == foreign(CustomTableRow.table_id), "
        "CustomTable.org_id == CustomTableRow.org_id)",
    )


# --------------------------------------------------------------------------- #
# M1.10 — Pricing layer: cost roll-up columns, pricing items, discounts
# --------------------------------------------------------------------------- #
class CalcType(enum.StrEnum):
    """A pricing item's calculation type (spec ``#costing`` Pricing section;
    canonical ``calc_type`` enum + the M1.10 ``target_margin`` extension,
    DECISIONS.md 2026-07-09). Every amount is computed **off cost,
    independently** — items sum, they never compound:

    * ``markup`` — ``amount = category_cost x pct``.
    * ``margin`` — ``amount = category_cost x pct/(1-pct)`` (nets ``pct``
      margin on that slice; DECISIONS.md 2026-06-14).
    * ``target_margin`` — back-solve the amount so the line's overall
      profit/total (excl. discounts) hits the target, holding the other items
      fixed; negative solution ⇒ **unreachable** (contribution 0 + flag).
    """

    markup = "markup"
    margin = "margin"
    target_margin = "target_margin"


class CostCategory(enum.StrEnum):
    """The five standard cost categories (spec ``#costing`` — mutually
    exclusive and exhaustive; ``general`` targets the whole Total Estimated
    Cost). Custom categories are **not** enum values — they live on their
    pricing item (``is_custom + custom_category_name``)."""

    general = "general"
    material = "material"
    inside = "inside"
    outside = "outside"
    purchased_component = "purchased_component"


_calc_type_enum = Enum(CalcType, name="calc_type", create_type=False)
_cost_category_enum = Enum(CostCategory, name="cost_category", create_type=False)


class PricingItemDef(Base):
    """An org-library pricing item (Configure → Pricing; spec ``#costing``,
    DemoE frame 16). Quote items receive **snapshot-on-attach** copies (E4-d
    freeze; DECISIONS.md 2026-07-09) — editing a def never reprices an
    existing draft; Refresh Pricing re-copies deliberately. A custom def
    carries its category's ``custom_category_name`` + ``color`` + the Kalk
    ``formula`` that computes the category cost via ``set_custom_cost()``."""

    __tablename__ = "pricing_item_def"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_pricing_item_def_org_id_id"),
        CheckConstraint(
            "NOT is_custom OR custom_category_name IS NOT NULL",
            name="ck_pricing_item_def_custom_named",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    calc_type: Mapped[CalcType] = mapped_column(
        _calc_type_enum, nullable=False, server_default=CalcType.markup.value
    )
    category: Mapped[CostCategory] = mapped_column(
        _cost_category_enum, nullable=False, server_default=CostCategory.general.value
    )
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    custom_category_name: Mapped[str | None] = mapped_column(String)
    color: Mapped[str | None] = mapped_column(String)
    formula: Mapped[str | None] = mapped_column(Text)
    default_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deleted_at: Mapped[datetime | None] = _deleted_at()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class DiscountDef(Base):
    """An org-library discount (Configure → Discounts; spec ``#costing``
    Discounts). Same snapshot-on-attach posture as :class:`PricingItemDef`.
    ``PERCENTAGE`` is positive; fixed via ``default_pct`` or Kalk-computed."""

    __tablename__ = "discount_def"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_discount_def_org_id_id"),
        CheckConstraint(
            "default_pct IS NULL OR default_pct >= 0", name="ck_discount_def_pct_positive"
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    formula: Mapped[str | None] = mapped_column(Text)
    default_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deleted_at: Mapped[datetime | None] = _deleted_at()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class PricingItem(Base):
    """A pricing item on a quote item's **root component** — one row of the
    Pricing stack (spec ``#costing``: independent, additive, each targeting a
    standard category or its own custom category). Config is a snapshot
    (``source_def_id`` remembers provenance for Refresh Pricing);
    ``is_from_factory`` rows re-snapshot on refresh, manual rows don't.
    ``position`` is the stack order (display only — the math is additive)."""

    __tablename__ = "pricing_item"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_pricing_item_org_id_id"),
        ForeignKeyConstraint(
            ["org_id", "component_id"],
            ["component.org_id", "component.id"],
            name="fk_pricing_item_component_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["org_id", "source_def_id"],
            ["pricing_item_def.org_id", "pricing_item_def.id"],
            name="fk_pricing_item_source_def_org",
        ),
        CheckConstraint(
            "NOT is_custom OR custom_category_name IS NOT NULL",
            name="ck_pricing_item_custom_named",
        ),
        Index("ix_pricing_item_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_def_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String, nullable=False)
    calc_type: Mapped[CalcType] = mapped_column(
        _calc_type_enum, nullable=False, server_default=CalcType.markup.value
    )
    category: Mapped[CostCategory] = mapped_column(
        _cost_category_enum, nullable=False, server_default=CostCategory.general.value
    )
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    custom_category_name: Mapped[str | None] = mapped_column(String)
    color: Mapped[str | None] = mapped_column(String)
    formula: Mapped[str | None] = mapped_column(Text)
    default_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_from_factory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class PricingItemCell(Base):
    """One pricing item's value at one quantity break. Calc-vs-override pairs
    for both the **%** and the **$ amount** (folded DDL ``calc_profit`` /
    ``manual_profit``); resolution: ``manual_profit`` wins outright, else the
    amount recomputes from ``COALESCE(manual_pct, calc_pct)``. Custom rows
    persist their ``set_custom_cost()`` output as ``calc_custom_cost`` (the
    colored Costing row). ``unreachable`` flags a target-margin back-solve
    that went negative (contribution 0; DECISIONS.md 2026-07-09)."""

    __tablename__ = "pricing_item_cell"
    __table_args__ = (
        UniqueConstraint("pricing_item_id", "quantity", name="uq_pricing_item_cell_item_qty"),
        ForeignKeyConstraint(
            ["org_id", "pricing_item_id"],
            ["pricing_item.org_id", "pricing_item.id"],
            name="fk_pricing_item_cell_item_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["component_id", "quantity"],
            ["component_quantity.component_id", "component_quantity.quantity"],
            name="fk_pricing_item_cell_component_quantity",
            ondelete="CASCADE",
        ),
        Index("ix_pricing_item_cell_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    pricing_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    calc_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    manual_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    calc_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    manual_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_custom_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    unreachable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class Discount(Base):
    """A discount row on a root component (spec ``#costing`` Discounts —
    applied **after** pricing items to the rounded unit price; percentages
    **sum**, they don't compound). Snapshot posture mirrors
    :class:`PricingItem`."""

    __tablename__ = "discount"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_discount_org_id_id"),
        ForeignKeyConstraint(
            ["org_id", "component_id"],
            ["component.org_id", "component.id"],
            name="fk_discount_component_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["org_id", "source_def_id"],
            ["discount_def.org_id", "discount_def.id"],
            name="fk_discount_source_def_org",
        ),
        Index("ix_discount_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_def_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String, nullable=False)
    formula: Mapped[str | None] = mapped_column(Text)
    default_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_from_factory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class DiscountCell(Base):
    """One discount's % at one quantity break (calc-vs-override pair)."""

    __tablename__ = "discount_cell"
    __table_args__ = (
        UniqueConstraint("discount_id", "quantity", name="uq_discount_cell_discount_qty"),
        ForeignKeyConstraint(
            ["org_id", "discount_id"],
            ["discount.org_id", "discount.id"],
            name="fk_discount_cell_discount_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["component_id", "quantity"],
            ["component_quantity.component_id", "component_quantity.quantity"],
            name="fk_discount_cell_component_quantity",
            ondelete="CASCADE",
        ),
        Index("ix_discount_cell_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    discount_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    calc_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    manual_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class AddOnDef(Base):
    """An org's add-on **type** (spec ``#addons``: the searchable,
    admin-configurable ``AddOnType`` dropdown behind ADD ADD-ON). Carries a
    flat ``default_price`` or a Kalk ``add_on``-context ``formula`` (spec:
    "flat or computed price") plus the Required default. Soft-delete +
    live-name unique mirror :class:`PricingItemDef` (M1.10)."""

    __tablename__ = "add_on_def"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_add_on_def_org_id_id"),
        CheckConstraint(
            "default_price IS NULL OR default_price >= 0",
            name="ck_add_on_def_price_positive",
        ),
        Index(
            "uq_add_on_def_org_name_live",
            "org_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    formula: Mapped[str | None] = mapped_column(Text)
    default_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    default_is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class AddOn(Base):
    """An add-on on a quote item's root component (spec ``#addons``: per-line
    extra charge, per-qty, Required toggle) — a line-item one-time fee that
    never touches the unit price (KB ``add-ons-p3l-cheat-sheet``) and applies
    **after** discounts (PRICING-ENGINE-SPEC §3.5). Snapshot-on-attach from
    :class:`AddOnDef` (E4-d). Required-ness resolves ``manual_is_required ??
    calc_is_required ?? default_is_required`` (CLAUDE.md §5 pair; the calc
    side is the formula's ``set_is_required``)."""

    __tablename__ = "add_on"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_add_on_org_id_id"),
        ForeignKeyConstraint(
            ["org_id", "component_id"],
            ["component.org_id", "component.id"],
            name="fk_add_on_component_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["org_id", "source_def_id"],
            ["add_on_def.org_id", "add_on_def.id"],
            name="fk_add_on_source_def_org",
        ),
        CheckConstraint(
            "default_price IS NULL OR default_price >= 0",
            name="ck_add_on_price_positive",
        ),
        Index("ix_add_on_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_def_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String, nullable=False)
    formula: Mapped[str | None] = mapped_column(Text)
    default_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    default_is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    calc_is_required: Mapped[bool | None] = mapped_column(Boolean)
    manual_is_required: Mapped[bool | None] = mapped_column(Boolean)
    # the formula's set_add_on_name() output (KB: naming conventions that
    # depend on part attributes); display resolves calc_name ?? name
    calc_name: Mapped[str | None] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_from_factory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()

    @property
    def is_required(self) -> bool:
        if self.manual_is_required is not None:
            return self.manual_is_required
        if self.calc_is_required is not None:
            return self.calc_is_required
        return self.default_is_required

    @property
    def display_name(self) -> str:
        return self.calc_name if self.calc_name else self.name


class AddOnCell(Base):
    """One add-on's PRICE at one quantity break (calc-vs-override pair —
    ``calc_price`` from the Kalk formula or the flat default, ``manual_price``
    the estimator's edit). One-time fee per break: never multiplied by qty."""

    __tablename__ = "add_on_cell"
    __table_args__ = (
        UniqueConstraint("add_on_id", "quantity", name="uq_add_on_cell_add_on_qty"),
        ForeignKeyConstraint(
            ["org_id", "add_on_id"],
            ["add_on.org_id", "add_on.id"],
            name="fk_add_on_cell_add_on_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["component_id", "quantity"],
            ["component_quantity.component_id", "component_quantity.quantity"],
            name="fk_add_on_cell_component_quantity",
            ondelete="CASCADE",
        ),
        Index("ix_add_on_cell_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    add_on_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    calc_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    manual_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class ExpediteOption(Base):
    """One dynamic-lead-time tier on a root component (E4-c; folded DDL
    ``expedite_option``): relative ``days_faster`` + ``markup_pct`` on price
    (KB ``dynamic-lead-times-guide``: relative days + %, never a date or a
    flat fee). Buyer-facing options only — they enter order money at M5."""

    __tablename__ = "expedite_option"
    __table_args__ = (
        UniqueConstraint("component_id", "days_faster", name="uq_expedite_option_comp_days"),
        ForeignKeyConstraint(
            ["org_id", "component_id"],
            ["component.org_id", "component.id"],
            name="fk_expedite_option_component_org",
            ondelete="CASCADE",
        ),
        CheckConstraint("days_faster > 0", name="ck_expedite_option_days_positive"),
        CheckConstraint("markup_pct >= 0", name="ck_expedite_option_markup_positive"),
        Index("ix_expedite_option_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    days_faster: Mapped[int] = mapped_column(Integer, nullable=False)
    markup_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class ProcessOperation(Base):
    """One router row: the operation def a process generates when applied to a
    part, ordered, with the §4 flags (per_setup / is_assembly /
    root_component_only). Stored as configuration in M1.12 — the auto-routing
    that instantiates these rows onto components arrives with M4."""

    __tablename__ = "process_operation"
    __table_args__ = (
        UniqueConstraint("process_id", "position", name="uq_process_operation_process_position"),
        ForeignKeyConstraint(
            ["org_id", "process_id"],
            ["process.org_id", "process.id"],
            name="fk_process_operation_process_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["org_id", "operation_def_id"],
            ["operation_def.org_id", "operation_def.id"],
            name="fk_process_operation_def_org",
            ondelete="CASCADE",
        ),
        Index("ix_process_operation_org_process", "org_id", "process_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    process_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation_def_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    per_setup: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_assembly: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    root_component_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class WorkflowStepDef(Base):
    """An org's custom quote-item workflow step (SEED-AND-FIXTURES §7; folded
    DDL ``workflow_step_def``). M1.12 seeds the default set; the per-item
    ``quote_item_workflow_step`` tracking table lands with its consumer."""

    __tablename__ = "workflow_step_def"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_workflow_step_def_org_name"),
        UniqueConstraint("org_id", "id", name="uq_workflow_step_def_org_id_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class EmailTemplate(Base):
    """A customer-facing email template (SEED-AND-FIXTURES §7 — German-first,
    keyed ``quote_sent`` / ``rfq_received`` / …). Seeded in M1.12; the M5 send
    flow consumes and edits them."""

    __tablename__ = "email_template"
    __table_args__ = (
        UniqueConstraint("org_id", "key", "locale", name="uq_email_template_org_key_locale"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    key: Mapped[str] = mapped_column(String, nullable=False)
    locale: Mapped[str] = mapped_column(String, nullable=False, server_default="de-DE")
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class FileAnnotationLayer(Base):
    """The persisted markup layer for one part file (M2.2, spec
    ``#pdf-capabilities`` Annotate/Shapes). ``data`` is one JSONB document:
    ``{"objects": [{id, page, type, style, geometry…}]}`` in pdf-unit page
    coordinates — written by the viewer, drawn into a copy on
    download-with-annotations. One row per file; collaboration threading of
    individual annotations arrives with M2.11."""

    __tablename__ = "file_annotation_layer"
    __table_args__ = (
        UniqueConstraint("part_file_id", name="uq_file_annotation_layer_file"),
        ForeignKeyConstraint(
            ["org_id", "part_file_id"],
            ["part_file.org_id", "part_file.id"],
            name="fk_file_annotation_layer_file_org",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{\"objects\": []}'::jsonb")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


# --------------------------------------------------------------------------- #
# Collaboration (M2.11, spec #collab / DB-SCHEMA "collaboration / sourcing")
# --------------------------------------------------------------------------- #


class TaskStatus(enum.StrEnum):
    """Task lifecycle (DB-SCHEMA ``task_status``). ``overdue`` is derived from a
    passed ``due_date`` at read time; stored state is ``open`` until resolved."""

    open = "open"
    overdue = "overdue"
    resolved = "resolved"


_task_status_enum = Enum(TaskStatus, name="task_status", create_type=False)


class Channel(Base):
    """A collaboration channel on a part (spec #collab). ``scope='team'`` is the
    single internal channel (one per part); ``scope='external'`` are per
    vendor/customer channels (many, optionally ``label``-named). Anchored to a
    part (the viewer's subject); ``quote_id`` optionally ties it to a quote."""

    __tablename__ = "channel"
    __table_args__ = (
        CheckConstraint("scope IN ('team', 'external')", name="ck_channel_scope"),
        UniqueConstraint("org_id", "id", name="uq_channel_org_id_id"),
        ForeignKeyConstraint(
            ["org_id", "part_id"],
            ["part.org_id", "part.id"],
            name="fk_channel_part_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["org_id", "quote_id"],
            ["quote.org_id", "quote.id"],
            name="fk_channel_quote_org",
            ondelete="SET NULL",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    scope: Mapped[str] = mapped_column(String, nullable=False, server_default="team")
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class Annotation(Base):
    """A feature/region locator a message can bind to (spec #collab annotation
    suite). ``kind='face'`` → ``geometry_ref = {file_id, entity{bodyId,kind,index}}``
    (the M2.7 ``EntityRef``); ``kind='region'`` → ``{file_id, page, rect}`` (M2.2
    pdf-unit coords). Clicking a bound message re-opens the file zoomed to it."""

    __tablename__ = "annotation"
    __table_args__ = (
        CheckConstraint("kind IN ('face', 'region')", name="ck_annotation_kind"),
        UniqueConstraint("org_id", "id", name="uq_annotation_org_id_id"),
        ForeignKeyConstraint(
            ["org_id", "part_id"],
            ["part.org_id", "part.id"],
            name="fk_annotation_part_org",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    geometry_ref: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class Message(Base):
    """A message in a channel (spec #collab). May bind an ``annotation`` (post a
    message on a picked face/region), reply to a ``parent`` message, and
    ``@mention`` teammates (``mentions`` = app_user ids → notifications). Edit
    stamps ``edited_at``; Delete tombstones (``deleted_at``, body cleared) so
    replies survive. ``author_id`` FKs the org-less ``app_user`` (membership
    validated at the edge)."""

    __tablename__ = "message"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_message_org_id_id"),
        ForeignKeyConstraint(
            ["org_id", "channel_id"],
            ["channel.org_id", "channel.id"],
            name="fk_message_channel_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["org_id", "annotation_id"],
            ["annotation.org_id", "annotation.id"],
            name="fk_message_annotation_org",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["org_id", "parent_id"],
            ["message.org_id", "message.id"],
            name="fk_message_parent_org",
            ondelete="SET NULL",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id")
    )
    annotation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()


class Task(Base):
    """A task (spec #collab Assign Task → surfaces on the Dashboard). Optionally
    bound to a part/quote/annotation; ``assignee_id``/``created_by`` FK the
    org-less ``app_user`` (active-membership validated at the edge). ``status``
    starts ``open``; ``overdue`` is derived from ``due_date`` at read time."""

    __tablename__ = "task"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "part_id"],
            ["part.org_id", "part.id"],
            name="fk_task_part_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["org_id", "quote_id"],
            ["quote.org_id", "quote.id"],
            name="fk_task_quote_org",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["org_id", "annotation_id"],
            ["annotation.org_id", "annotation.id"],
            name="fk_task_annotation_org",
            ondelete="SET NULL",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    annotation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id")
    )
    message: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[TaskStatus] = mapped_column(
        _task_status_enum, nullable=False, server_default=TaskStatus.open.value
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()


class Notification(Base):
    """A per-recipient notification (spec #collab: @mention → email/notification;
    Assign Task notifies the assignee). ``kind`` ∈ ``mention`` | ``task_assigned``;
    ``payload`` carries the deep-link context. ``org_id`` is the source org."""

    __tablename__ = "notification"

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()


class OrgAiSettings(Base):
    """Per-org AI feature toggles (spec ``#ai-settings`` build-note).

    ``master_enabled`` gates every AI feature and is checked first; each
    per-feature flag then gates its own code path. All default TRUE (fixture
    orgs ship AI fully enabled). ``org_id`` is the PK — exactly one row per org
    — and an *absent* row is treated as all-enabled by the accessor
    (:mod:`app.ai_settings`), so a missing row is never a silent disable.

    M3.9 (RFQ Triage Brief) is the first consumer and reads only
    ``master_enabled`` then ``triage_brief_enabled``; the remaining flags exist
    for M3.10 / M5 / M6."""

    __tablename__ = "org_ai_settings"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    master_enabled: Mapped[bool] = _ai_flag()
    wingman_enabled: Mapped[bool] = _ai_flag()
    triage_brief_enabled: Mapped[bool] = _ai_flag()
    quote_assembly_enabled: Mapped[bool] = _ai_flag()
    estimation_coaching_enabled: Mapped[bool] = _ai_flag()
    presend_review_enabled: Mapped[bool] = _ai_flag()
    assistant_enabled: Mapped[bool] = _ai_flag()
    mcp_enabled: Mapped[bool] = _ai_flag()
    customer_brief_enabled: Mapped[bool] = _ai_flag()
    requote_diff_enabled: Mapped[bool] = _ai_flag()
    rule_suggest_enabled: Mapped[bool] = _ai_flag()
    margin_coach_enabled: Mapped[bool] = _ai_flag()
    benchmarking_opt_out: Mapped[bool] = _ai_flag()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


class SuggestedActionKind(enum.StrEnum):
    """The kind of a :class:`SuggestedAction` (stored as text, mirroring
    ``Notification.kind``). M3.10 introduces ``rule_suggestion``; later AI
    features (requote diff, quote assembly) can add their own kinds."""

    rule_suggestion = "rule_suggestion"


class SuggestedActionStatus(enum.StrEnum):
    """Lifecycle of a :class:`SuggestedAction`. ``open`` surfaces on the drawer
    chip + dashboard strip; ``dismissed`` is hidden and never re-surfaced (so a
    junior estimator who waved it away isn't re-nagged — spec ``#ai-settings``
    rationale for the whole feature being toggleable); ``acted`` records that a
    rule was authored from it."""

    open = "open"
    dismissed = "dismissed"
    acted = "acted"


class SuggestedAction(Base):
    """A non-blocking, human-gated AI suggestion surfaced on the dashboard
    suggested-actions strip and (for rule suggestions) the operation drawer chip
    (spec ``#ai-rule-suggest`` build-note: "surfaces suggestions via the existing
    ``SuggestedAction`` mechanism").

    M3.10 is the first consumer: when the same operation has been *manually*
    added to 3+ parts in the same process family + material class in the last 90
    days, a ``rule_suggestion`` row is upserted. ``payload`` carries the
    deterministic pre-seed for the Create Rule dialog plus the (optionally
    Claude-written) human-readable sentence. **The AI never creates a rule** — a
    suggestion only pre-seeds the dialog; the human clicks CREATE RULE.

    ``dedup_key`` makes the upsert idempotent across the nightly scan and the
    on-add trigger: one open row per distinct pattern per org. ``UNIQUE (org_id,
    dedup_key)`` enforces it; RLS keys on ``org_id``."""

    __tablename__ = "suggested_action"
    __table_args__ = (UniqueConstraint("org_id", "dedup_key", name="uq_suggested_action_dedup"),)

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'open'"))
    #: Stable identity of the underlying pattern, e.g.
    #: ``rule_suggestion:<op_def_id>:<family>:<material_class_id>`` — dedupes the
    #: on-add trigger against the nightly scan.
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)
    #: The operation the pattern is about (nullable; a non-rule kind may omit it).
    operation_def_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- #
# AI / Lens extractions (M3.1 — spec #lens-finding; AI-LENS-ENGINE §8)
# --------------------------------------------------------------------------- #
class FindingCategory(enum.StrEnum):
    """The 5-category extraction taxonomy (spec ``#lens-extraction``)."""

    quote_setup = "quote_setup"
    requirements = "requirements"
    features = "features"
    dimensions = "dimensions"
    regions = "regions"


class FindingStatus(enum.StrEnum):
    """AI-Governor lifecycle: every finding is born a *suggestion*; only an
    explicit human action moves it on (spec ``#lens-accept`` — never auto-applied)."""

    suggested = "suggested"
    accepted = "accepted"
    rejected = "rejected"
    edited = "edited"


# Map by .value (the _obtain_method_enum precedent) so a future name/value
# divergence can't silently write the wrong label to the native enum.
_finding_category_enum = Enum(
    FindingCategory,
    name="finding_category",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)
_finding_status_enum = Enum(
    FindingStatus,
    name="finding_status",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class ExtractionFinding(Base):
    """One structured Lens extraction from a print/document (spec ``#lens-finding``).

    Suggestions only — consumed by part-field fill (M3.2), Rules/Review signals
    (M3.7) and the viewer overlay; **never** fed into Kalk costing (CLAUDE.md §5).
    M3.1 findings bind to their source file (+ ``page``); ``component_id`` stays
    NULL until a consumer links one (M3.2 click-to-fill / M4 pipeline 5).

    ``bbox`` uses the M2.2 annotation-layer convention — unrotated pdf-unit page
    coordinates ``{x, y, width, height}`` (DECISIONS.md 2026-07-12). ``tolerance``
    is ``{kind: unilateral|bilateral|limit, upper, lower}``; ``gdt`` is ISO GPS
    ``{symbol, datum_refs[], material_condition}``. ``units`` defaults to the
    document's detected units, mm-native (DACH)."""

    __tablename__ = "extraction_finding"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        # Same-org composite FKs (tenancy invariant at the DB level, the
        # part_file/component precedent). File deletion is a HARD delete (GDPR
        # erasure, M1.2) — findings carry print content, so they cascade with it.
        ForeignKeyConstraint(
            ["org_id", "source_file_id"],
            ["part_file.org_id", "part_file.id"],
            name="fk_extraction_finding_file_org",
            ondelete="CASCADE",
        ),
        # No ondelete here: the DDL (0019) uses the column-list form
        # ``ON DELETE SET NULL (component_id)`` — nulling only component_id,
        # not org_id — which the ORM can't express (the 0017 precedent).
        ForeignKeyConstraint(
            ["org_id", "component_id"],
            ["component.org_id", "component.id"],
            name="fk_extraction_finding_component_org",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_extraction_finding_confidence"
        ),
        # Correction rows FK the (org_id, id) pair (added in 0021).
        UniqueConstraint("org_id", "id", name="uq_extraction_finding_org_id_id"),
        # Findings are listed per file (Found-in-Files panel) and per component.
        Index("ix_extraction_finding_org_file", "org_id", "source_file_id"),
        Index("ix_extraction_finding_org_component", "org_id", "component_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    component_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    page: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[FindingCategory] = mapped_column(_finding_category_enum, nullable=False)
    # Open taxonomy ('part_number' | 'hole' | 'control_frame' | …) — text per the
    # canonical DDL, NOT NULL per the spec contract (type is required there).
    type: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    units: Mapped[str | None] = mapped_column(Text)
    tolerance: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    role: Mapped[str | None] = mapped_column(Text)
    gdt: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    status: Mapped[FindingStatus] = mapped_column(
        _finding_status_enum, nullable=False, server_default=FindingStatus.suggested.value
    )
    created_at: Mapped[datetime] = _ts()


class CorrectionType(enum.StrEnum):
    """The three training labels (spec ``#wingman`` §3 / AI-LENS-ENGINE §7):
    false positive, wrong-value, false negative."""

    mark_inaccurate = "mark_inaccurate"
    # The member shadows str.replace on the class — fine for an enum (members
    # are class-level), but mypy flags the base-class clash.
    replace = "replace"  # type: ignore[assignment]
    add_missing = "add_missing"


_correction_type_enum = Enum(
    CorrectionType,
    name="correction_type",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class ExtractionCorrection(Base):
    """One user correction on a Lens finding — the training label
    (M3.2 — spec ``#wingman`` §3; AI-LENS-ENGINE §7).

    Persists ``{finding, predicted, corrected, tenant, file_ref, source_region}``:
    ``predicted`` snapshots the finding as the model emitted it (NULL for
    ``add_missing`` — there was no prediction); ``corrected`` is what the human
    said instead (NULL for ``mark_inaccurate`` — the label IS "this is wrong").
    ``page``/``bbox`` carry the source region for retraining/QA.

    **Per-tenant storage** (DECISIONS.md 2026-07-15): org-scoped RLS rows; a
    global/anonymised pool is a later opt-in, not built here. Labels must
    outlive their finding (they feed the M3.11 eval set), so ``finding_id``
    nulls on finding deletion while the snapshot stays; but they must NOT
    outlive their source *file* — corrections carry print content, and file
    deletion is GDPR erasure (the 0020 cascade precedent).
    """

    __tablename__ = "extraction_correction"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "source_file_id"],
            ["part_file.org_id", "part_file.id"],
            name="fk_extraction_correction_file_org",
            ondelete="CASCADE",
        ),
        # Column-list SET NULL (finding_id only, not org_id) — DDL-only form
        # the ORM can't express (the 0017/0019 precedent).
        ForeignKeyConstraint(
            ["org_id", "finding_id"],
            ["extraction_finding.org_id", "extraction_finding.id"],
            name="fk_extraction_correction_finding_org",
        ),
        # A corrupt training label is silent poison for the M3.11 eval set —
        # enforce the type↔payload shape at the DB, not just in the endpoints.
        CheckConstraint(
            "(correction_type = 'mark_inaccurate'"
            "    AND predicted IS NOT NULL AND corrected IS NULL)"
            " OR (correction_type = 'replace'"
            "    AND predicted IS NOT NULL AND corrected IS NOT NULL)"
            " OR (correction_type = 'add_missing'"
            "    AND predicted IS NULL AND corrected IS NOT NULL)",
            name="ck_extraction_correction_shape",
        ),
        Index("ix_extraction_correction_org_file", "org_id", "source_file_id"),
        # Keeps the SET NULL FK's referencing-row scan cheap on re-run deletes.
        Index("ix_extraction_correction_org_finding", "org_id", "finding_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    finding_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # NOT NULL: the file is the label's GDPR lifecycle owner (CASCADE above) —
    # an unanchored correction row would have no eraser.
    source_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    correction_type: Mapped[CorrectionType] = mapped_column(_correction_type_enum, nullable=False)
    # none_as_null: an explicit Python None must land as SQL NULL, not jsonb
    # 'null' — the shape CHECK tests IS NULL and would reject it otherwise.
    predicted: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    corrected: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    page: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id")
    )
    created_at: Mapped[datetime] = _ts()


# --------------------------------------------------------------------------- #
# Two-way email threading (M3.5 — spec #email-connectivity)
# --------------------------------------------------------------------------- #
class EmailConnectionType(enum.StrEnum):
    """How a user's mailbox is connected (spec ``#email-connectivity`` v1 set)."""

    gmail = "gmail"
    outlook = "outlook"
    smtp_imap = "smtp_imap"


class EmailDirection(enum.StrEnum):
    """Message direction on the quote communications timeline."""

    outbound = "outbound"
    inbound = "inbound"


_email_connection_type_enum = Enum(
    EmailConnectionType,
    name="email_connection_type",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)
_email_direction_enum = Enum(
    EmailDirection,
    name="email_direction",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class UserEmailConnection(Base):
    """A user's connected mailbox — quotes send from ``from_address``, replies
    sync back through the same connection (spec ``#email-connectivity``).

    ``encrypted_credentials`` is AES-256-GCM ciphertext (``email_crypto``):
    the OAuth refresh token (gmail/outlook) or the SMTP/IMAP credential bundle.
    It is never logged and never serialized into an API response.
    ``gmail_history_id`` / ``outlook_delta_link`` are the incremental sync
    cursors; per (org, user) with at most one ``is_primary`` (partial unique
    index in migration 0024)."""

    __tablename__ = "user_email_connection"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_user_email_connection_org_id_id"),
        Index("ix_email_connection_org_user", "org_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    connection_type: Mapped[EmailConnectionType] = mapped_column(
        _email_connection_type_enum, nullable=False
    )
    from_address: Mapped[str] = mapped_column(CITEXT, nullable=False)
    from_name: Mapped[str | None] = mapped_column(Text)
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    gmail_history_id: Mapped[str | None] = mapped_column(Text)
    outlook_delta_link: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class QuoteEmailThread(Base):
    """One row per quote that has been sent by email: ``sent_message_id`` is
    the RFC 2822 Message-ID of the FIRST outbound message, ``provider_thread_id``
    the Gmail ``threadId`` / Outlook ``conversationId`` — the reply-matching
    keys (spec ``#email-connectivity`` threading mechanism)."""

    __tablename__ = "quote_email_thread"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_quote_email_thread_org_id_id"),
        UniqueConstraint("org_id", "quote_id", name="uq_quote_email_thread_quote"),
        ForeignKeyConstraint(
            ["org_id", "quote_id"],
            ["quote.org_id", "quote.id"],
            name="fk_quote_email_thread_quote_org",
        ),
        Index("ix_quote_email_thread_sent_message_id", "org_id", "sent_message_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sent_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_thread_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class EmailMessage(Base):
    """Every message in a quote thread, both directions — the communications
    timeline row (spec ``#email-connectivity``). The partial unique index on
    (org, ``rfc_message_id``) makes the 5-minute sync idempotent. Attachments
    live in Object Storage; this row links them as
    ``[{filename, storage_key, size_bytes, content_type}]``."""

    __tablename__ = "email_message"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "thread_id"],
            ["quote_email_thread.org_id", "quote_email_thread.id"],
            name="fk_email_message_thread_org",
        ),
        Index("ix_email_message_org_thread", "org_id", "thread_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: Which mailbox sent/received it; survives a disconnect (SET NULL, 0024).
    connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    direction: Mapped[EmailDirection] = mapped_column(_email_direction_enum, nullable=False)
    rfc_message_id: Mapped[str | None] = mapped_column(Text)
    in_reply_to: Mapped[str | None] = mapped_column(Text)
    from_address: Mapped[str] = mapped_column(CITEXT, nullable=False)
    to_addresses: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    subject: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()


# --------------------------------------------------------------------------- #
# M3.6 — Review rules (the portable query AST)
# --------------------------------------------------------------------------- #
class Rule(Base):
    """A Requirements-Review rule — the persisted form of the canonical query
    AST (spec ``#rules-schema``; DB-SCHEMA.sql ``rule``). The AST lives in
    JSONB exactly as serialized (``signals``/``resolutions``); scalar columns
    carry the identity/config fields. ``uuid`` is the *portable* identity from
    the import/export JSON (upsert key per org — unique cross-org so the same
    pasted set imports into any org); ``id`` stays the internal PK.

    ``default_assignee_id`` is deliberately un-FK'd: an imported set may name
    a user absent from this org; M3.8 validates at assignment time.
    ``is_active`` is internal only — never part of the canonical JSON."""

    __tablename__ = "rule"
    __table_args__ = (
        UniqueConstraint("org_id", "uuid", name="uq_rule_org_uuid"),
        CheckConstraint("logical_operator IN ('AND', 'OR')", name="ck_rule_logical_operator"),
        Index("ix_rule_org_active", "org_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    uuid: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    logical_operator: Mapped[str] = mapped_column(Text, nullable=False)
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    resolutions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    default_assignee_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


#: §3 resolution catalogue — the effect a user picks on a review item. Mirrors
#: ``app.rules_schema.Resolution.type`` (the AST's own literal set) and the
#: ``ck_review_item_resolution_type`` CHECK.
class ResolutionType(enum.StrEnum):
    NO_QUOTE = "NO_QUOTE"
    RESOLVE = "RESOLVE"
    ADD_OPERATION = "ADD_OPERATION"
    SET_PROCESS = "SET_PROCESS"
    ASSIGN_ESTIMATOR = "ASSIGN_ESTIMATOR"


class ReviewItemStatus(enum.StrEnum):
    open = "open"
    resolved = "resolved"


class ReviewItem(Base):
    """One matched rule on one component — the assignable, resolvable unit of
    Requirements Review (spec ``#rules-lifecycle``; RULES-ENGINE-SPEC §6).

    The **component** is the subject (§1: "when a rule's signals match a
    component, a review item is created"); ``quote_item_id`` is the line item
    its resolutions mutate, and ``quote_id`` is what the panel aggregates over.

    ``UNIQUE (org_id, component_id, rule_id)`` is what makes generation
    idempotent: the spec's contract is "on any extraction/geometry change,
    evaluate all org rules against the part → **create/update** ReviewItems",
    and Lens re-runs on every upload — so re-evaluation must converge on the
    same row rather than pile up duplicates.

    ``status``/``resolution_*``/``resolved_*`` carry §6's audit trail. The
    stored ``detail`` holds the matched callout text + finding ids the card
    renders as entity pills; ``assignee_id``/``resolved_by`` point at the
    global ``app_user`` (active-membership is checked in the service layer —
    the ``collab.py`` precedent), so they carry no composite FK."""

    __tablename__ = "review_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "quote_id"], ["quote.org_id", "quote.id"], name="fk_review_item_quote_org"
        ),
        ForeignKeyConstraint(
            ["org_id", "quote_item_id"],
            ["quote_item.org_id", "quote_item.id"],
            name="fk_review_item_quote_item_org",
        ),
        ForeignKeyConstraint(
            ["org_id", "component_id"],
            ["component.org_id", "component.id"],
            name="fk_review_item_component_org",
        ),
        ForeignKeyConstraint(
            ["org_id", "rule_id"], ["rule.org_id", "rule.id"], name="fk_review_item_rule_org"
        ),
        UniqueConstraint("org_id", "id", name="uq_review_item_org_id_id"),
        UniqueConstraint("org_id", "component_id", "rule_id", name="uq_review_item_component_rule"),
        CheckConstraint("status IN ('open', 'resolved')", name="ck_review_item_status"),
        CheckConstraint(
            "resolution_type IS NULL OR resolution_type IN "
            "('NO_QUOTE', 'RESOLVE', 'ADD_OPERATION', 'SET_PROCESS', 'ASSIGN_ESTIMATOR')",
            name="ck_review_item_resolution_type",
        ),
        # A resolved item without its decision is an audit hole; an open one
        # carrying a decision is a contradiction. Mirrors migration 0026.
        CheckConstraint(
            "(status = 'open' AND resolution_type IS NULL AND resolved_at IS NULL"
            " AND resolved_by IS NULL)"
            " OR (status = 'resolved' AND resolution_type IS NOT NULL"
            " AND resolved_at IS NOT NULL)",
            name="ck_review_item_resolved_is_complete",
        ),
        Index("ix_review_item_org_quote_status", "org_id", "quote_id", "status"),
        Index("ix_review_item_org_component", "org_id", "component_id"),
        Index("ix_review_item_org_assignee", "org_id", "assignee_id"),
        # §6.4's "up to 5 past parts this rule flagged", newest first.
        Index(
            "ix_review_item_org_rule_resolved",
            "org_id",
            "rule_id",
            text("resolved_at DESC"),
            postgresql_where=text("status = 'resolved'"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quote_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    assignee_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id")
    )
    resolution_type: Mapped[str | None] = mapped_column(Text)
    resolution_label: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id")
    )
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _updated_ts()


# --------------------------------------------------------------------------- #
# M4.1 — interrogation runs (GeometryService job state + result cache)
# --------------------------------------------------------------------------- #
class InterrogationStatus(enum.StrEnum):
    """Lifecycle of one interrogation job — powers the part view's
    ``interrogating…`` state (INTERROGATION-ENGINE-SPEC §5.6)."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class InterrogationRun(Base):
    """One GeometryService job on a part's PRIMARY CAD file (M4.1).

    The spec's persist+cache step (INTERROGATION-ENGINE-SPEC §5.4): the
    AnalysisResult is cached keyed by ``(geom_hash, family, inputs_hash)`` —
    org-scoped, so the viewer and costing share one run and an identical body
    re-uploaded in the same org can reuse a finished result, never across orgs.
    ``family`` is nullable in M4.1 (core-dims pass is family-agnostic; the
    per-family recognizers land M4.2+). ``inputs_hash`` is ``''`` until custom
    interrogations (M4.8) hash their resolved threshold sets. The dims
    extraction ALSO lands in ``part_geometry.raw`` (the canonical output cache);
    this row carries job state, error taxonomy, and the audit copy.

    ``file_id`` is pinned to the same part via the composite FK onto
    ``part_file (id, part_id)`` and CASCADEs with the file (a deleted file's
    runs are meaningless); org isolation rides the same-org part FK + RLS."""

    __tablename__ = "interrogation_run"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy config dunder)
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "part_id"],
            ["part.org_id", "part.id"],
            name="fk_interrogation_run_part_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["file_id", "part_id"],
            ["part_file.id", "part_file.part_id"],
            name="fk_interrogation_run_file_part",
            ondelete="CASCADE",
            # The M2.12 merge re-parents part_file.part_id onto the surviving
            # part; historical runs follow their file instead of blocking it.
            onupdate="CASCADE",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_interrogation_run_status",
        ),
        # Latest-run-per-part lookup (the status endpoint).
        Index("ix_interrogation_run_org_part_created", "org_id", "part_id", "created_at"),
        # The §5.4 cache probe: finished result for an identical body+inputs.
        Index(
            "ix_interrogation_run_cache",
            "org_id",
            "geom_hash",
            "family",
            "inputs_hash",
            postgresql_where=text("status = 'succeeded'"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org_fk()
    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    family: Mapped[str | None] = mapped_column(Text)
    #: Versioned geometry signature (``gs1:<sha256>``) — set once the body parsed.
    geom_hash: Mapped[str | None] = mapped_column(Text)
    inputs_hash: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    #: Density source used for ``weight`` (caller-resolved; engine never invents).
    material_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=InterrogationStatus.queued
    )
    #: Machine-readable failure: multi_body | parse_error | file_too_large | internal.
    error_code: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    #: The AnalysisResult (dimensions block in M4.1), as persisted JSON.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _ts()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
