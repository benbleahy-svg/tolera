"""Org provisioning service — the single source of truth for creating an org.

Per spec ``#onboarding`` the seed CLI is "a thin wrapper around
``OrgService.create_org()`` — the same service a future self-serve signup
endpoint will call. No special-casing … from day one." So the seed runner
(``app.seed``) and any later signup path both go through :class:`OrgService`.

``create_org`` is **idempotent** (DECISIONS.md 2026-06-24 "M0.5 seed scope"):
each entity is upserted on its natural key (``organization.slug``,
``app_user.email``, the ``(user_id, org_id)`` membership constraint) via
``INSERT … ON CONFLICT DO UPDATE``, so re-running reconciles to the spec rather
than duplicating rows. A pre-select on the same natural key classifies each row
as created-vs-reconciled for the run report (it does not gate the write).

Scope is Part 1 §1 of ``SEED-AND-FIXTURES.md`` only — org identity + users +
memberships. Clerk identity linkage is deliberately out of scope and left to the
Clerk→DB webhook mirror (DECISIONS.md 2026-06-24 "Seed framework — Clerk
provisioning scope"); ``clerk_org_id`` / ``clerk_user_id`` stay null here.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AppUser,
    MembershipRole,
    MembershipStatus,
    OrgAiSettings,
    Organization,
    OrgCountry,
    UserOrgMembership,
)

# Org-scoped RFQ ingest is derived from the slug, never stored
# (DECISIONS.md 2026-06-14 "Pilot customer org slug for RFQ ingest").
RFQ_INGEST_DOMAIN = "rfq.tolera.eu"
_SLUG_RE = r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_VALID_CURRENCIES = frozenset({"EUR", "CHF"})  # mirrors the DB CHECK constraint


# --------------------------------------------------------------------------- #
# Input contract (validated at the edge — CLAUDE.md §5)
# --------------------------------------------------------------------------- #
class UserSpec(BaseModel):
    """A user + the role(s) they hold in the org being provisioned."""

    model_config = ConfigDict(extra="forbid")

    email: str
    roles: list[MembershipRole] = Field(min_length=1)
    first_name: str | None = None
    last_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_singular_role(cls, data: Any) -> Any:
        """Allow the seed-skeleton's singular ``role`` as a shorthand for ``roles``."""
        if isinstance(data, dict) and "role" in data and "roles" not in data:
            rest = {key: value for key, value in data.items() if key != "role"}
            rest["roles"] = [data["role"]]
            return rest
        return data

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        # Canonicalise so the email natural key is stable regardless of casing /
        # surrounding whitespace (the column is CITEXT, but normalise anyway).
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            # Never echo the address back — it is customer PII (CLAUDE.md §5).
            raise ValueError("not a valid email address")
        return value


class OrgSpec(BaseModel):
    """A provisionable org (identity + its initial members). The neutral contract
    a seed file *or* a future signup request is parsed into."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=_SLUG_RE, min_length=2, max_length=63)
    name: str = Field(min_length=1)
    country: OrgCountry = OrgCountry.DE
    currency: str = "EUR"
    locale: str = "de-DE"
    # Optional legal identity for the Impressum footer on customer-facing PDFs +
    # quote emails (M5.9; DACH-DELTA §Email/§37). Seed-provided; omitted fields are
    # never written (a re-seed does not clobber). ``ust_id_nr`` is also the shop's
    # supplier VAT-ID carried onto reverse-charge invoices (§14 UStG).
    ust_id_nr: str | None = None
    facility_address: str | None = None
    commercial_register: str | None = None
    users: list[UserSpec] = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str) -> str:
        if value not in _VALID_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(_VALID_CURRENCIES)}, got {value!r}")
        return value

    @model_validator(mode="after")
    def _currency_matches_country(self) -> Self:
        # DACH money: CH bills in CHF, DE/AT in EUR (DACH-DELTA §1, CLAUDE.md §5).
        # ``currency`` defaults to EUR, so guard against a CH org silently keeping it.
        expected = "CHF" if self.country is OrgCountry.CH else "EUR"
        if self.currency != expected:
            raise ValueError(f"country {self.country.value} requires currency {expected}")
        return self

    @model_validator(mode="after")
    def _unique_user_emails(self) -> Self:
        # Emails are already normalised; a dup would upsert one membership twice
        # (later roles clobber earlier) while still being reported as two members.
        seen: set[str] = set()
        for user in self.users:
            if user.email in seen:
                raise ValueError("users must not contain duplicate email addresses")
            seen.add(user.email)
        return self

    @property
    def rfq_ingest(self) -> str:
        """The derived RFQ ingest address (``{slug}@rfq.tolera.eu``)."""
        return f"{self.slug}@{RFQ_INGEST_DOMAIN}"


# --------------------------------------------------------------------------- #
# Result (what the run report is built from)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class UserResult:
    """Outcome of upserting one user + their membership."""

    email: str
    user_id: uuid.UUID
    roles: tuple[MembershipRole, ...]
    user_created: bool
    membership_created: bool


@dataclass(frozen=True)
class OrgResult:
    """Outcome of provisioning one org."""

    slug: str
    org_id: uuid.UUID
    org_created: bool
    rfq_ingest: str
    users: tuple[UserResult, ...]


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class OrgService:
    """Provision (create-or-reconcile) an org and its members in one session.

    The caller owns the transaction and the session's privilege: provisioning
    writes the RLS-self-isolated ``organization`` table and across orgs, so it
    must run on the owner/superuser connection (the seed CLI supplies it). A
    future signup endpoint would call the same method via an elevated path.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_org(self, spec: OrgSpec) -> OrgResult:
        """Idempotently create or reconcile the org described by ``spec``."""
        org_id, org_created = await self._upsert_org(spec)
        members: list[UserResult] = []
        for user in spec.users:
            user_id, user_created = await self._upsert_user(user)
            membership_created = await self._upsert_membership(user_id, org_id, user.roles)
            members.append(
                UserResult(
                    email=user.email,
                    user_id=user_id,
                    roles=tuple(user.roles),
                    user_created=user_created,
                    membership_created=membership_created,
                )
            )
        return OrgResult(
            slug=spec.slug,
            org_id=org_id,
            org_created=org_created,
            rfq_ingest=spec.rfq_ingest,
            users=tuple(members),
        )

    async def _upsert_org(self, spec: OrgSpec) -> tuple[uuid.UUID, bool]:
        existing = await self._session.scalar(
            select(Organization.id).where(Organization.slug == spec.slug)
        )
        values: dict[str, Any] = {
            "name": spec.name,
            "country": spec.country,
            "currency": spec.currency,
            "locale": spec.locale,
        }
        # Legal identity is optional; only write provided fields so a re-seed of an
        # org that later sets these (or a future editor) is never clobbered by NULL.
        for legal_field in ("ust_id_nr", "facility_address", "commercial_register"):
            provided = getattr(spec, legal_field)
            if provided is not None:
                values[legal_field] = provided
        stmt = (
            pg_insert(Organization)
            .values(slug=spec.slug, **values)
            .on_conflict_do_update(index_elements=[Organization.slug], set_=values)
            .returning(Organization.id)
        )
        org_id: uuid.UUID = (await self._session.execute(stmt)).scalar_one()
        # M3.9 — every org owns exactly one AI-settings row (spec #ai-settings:
        # "Default row is inserted on org creation with the above defaults").
        # Idempotent so reconciling an existing org is a no-op; the all-TRUE
        # column defaults ship the org AI-fully-enabled.
        await self._session.execute(
            pg_insert(OrgAiSettings)
            .values(org_id=org_id)
            .on_conflict_do_nothing(index_elements=[OrgAiSettings.org_id])
        )
        return org_id, existing is None

    async def _upsert_user(self, user: UserSpec) -> tuple[uuid.UUID, bool]:
        existing = await self._session.scalar(select(AppUser.id).where(AppUser.email == user.email))
        insert_stmt = pg_insert(AppUser).values(
            email=user.email, first_name=user.first_name, last_name=user.last_name
        )
        # AppUser is global: the same user may be seeded again via another org
        # (E4-a). The seed is not an identity-admin flow, so it must not rewrite a
        # reused user's profile — COALESCE keeps the EXISTING name and only fills a
        # gap from the incoming seed (first-writer-wins; order-independent).
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[AppUser.email],
            set_={
                "first_name": func.coalesce(AppUser.first_name, insert_stmt.excluded.first_name),
                "last_name": func.coalesce(AppUser.last_name, insert_stmt.excluded.last_name),
            },
        ).returning(AppUser.id)
        user_id: uuid.UUID = (await self._session.execute(stmt)).scalar_one()
        return user_id, existing is None

    async def _upsert_membership(
        self, user_id: uuid.UUID, org_id: uuid.UUID, roles: list[MembershipRole]
    ) -> bool:
        existing = await self._session.scalar(
            select(UserOrgMembership.id).where(
                UserOrgMembership.user_id == user_id,
                UserOrgMembership.org_id == org_id,
            )
        )
        values = {"roles": roles, "status": MembershipStatus.active}
        stmt = (
            pg_insert(UserOrgMembership)
            .values(user_id=user_id, org_id=org_id, **values)
            .on_conflict_do_update(constraint="uq_membership_user_org", set_=values)
        )
        await self._session.execute(stmt)
        return existing is None
