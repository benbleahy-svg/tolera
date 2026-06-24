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

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, UUID
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


# Native Postgres enums — created by the migration, referenced (not re-created) here.
_role_enum = Enum(MembershipRole, name="membership_role", create_type=False)
_status_enum = Enum(MembershipStatus, name="membership_status", create_type=False)
_country_enum = Enum(OrgCountry, name="org_country", create_type=False)


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
