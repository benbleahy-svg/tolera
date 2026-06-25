"""M0.5 seed framework tests — idempotent org provisioning.

Proves the M0 exit slice "two seeded orgs + login works": the shipped seeds
provision the ``fechner`` pilot plus a second org, re-running the seed is
idempotent (no duplication), one global user may span orgs (E4-a), and a seeded
user authenticates with the M0.2 cross-org isolation holding against the seeded
pair. Real Clerk linkage is out of scope (DECISIONS.md 2026-06-24 "Seed
framework — Clerk provisioning scope"): "login" is exercised via the test
harness principal injection, exactly as the M0.2 tenancy gate does.

DB-backed, so every test depends on ``tenancy_db`` (skips without a reachable
``TEST_DATABASE_URL``). ``seeder`` is requested purely for its post-test
TRUNCATE — the seed itself writes via its own owner engine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.db import make_engine, make_sessionmaker
from app.models import MembershipRole
from app.seed import DEFAULT_SEEDS_DIR, apply_seeds, load_seeds
from app.services.org_service import OrgResult, OrgSpec, UserSpec
from tests.conftest import Seeder, authed


# --------------------------------------------------------------------------- #
# Helpers — each opens a short-lived OWNER engine (bypasses RLS) and disposes.
# --------------------------------------------------------------------------- #
async def _apply(owner_url: str, specs: Sequence[OrgSpec]) -> list[OrgResult]:
    engine = make_engine(owner_url)
    try:
        return await apply_seeds(make_sessionmaker(engine), specs)
    finally:
        await engine.dispose()


async def _counts(owner_url: str) -> dict[str, int]:
    engine = make_engine(owner_url)
    try:
        async with engine.connect() as conn:
            return {
                "orgs": await _scalar(conn, "SELECT count(*) FROM organization"),
                "users": await _scalar(conn, "SELECT count(*) FROM app_user"),
                "memberships": await _scalar(conn, "SELECT count(*) FROM user_org_membership"),
            }
    finally:
        await engine.dispose()


async def _fetch_org(owner_url: str, slug: str) -> dict[str, Any]:
    engine = make_engine(owner_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT slug, name, country, currency, locale "
                        "FROM organization WHERE slug = :slug"
                    ),
                    {"slug": slug},
                )
            ).one()
        return dict(row._mapping)
    finally:
        await engine.dispose()


async def _scalar(conn: Any, sql: str) -> int:
    return int((await conn.execute(text(sql))).scalar_one())


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_shipped_seeds_provision_two_orgs_including_fechner(
    tenancy_db: str, seeder: Seeder
) -> None:
    """The committed ``scripts/seeds/*.json`` provision >=2 orgs incl. the pilot."""
    specs = load_seeds(DEFAULT_SEEDS_DIR)
    slugs = {spec.slug for spec in specs}
    assert "fechner" in slugs
    assert len(specs) >= 2

    results = asyncio.run(_apply(tenancy_db, specs))
    by_slug = {result.slug: result for result in results}

    fechner = by_slug["fechner"]
    assert fechner.org_created is True
    # Ingest address is derived from the slug, not stored (DECISIONS 2026-06-14).
    assert fechner.rfq_ingest == "fechner@rfq.tolera.eu"
    assert fechner.users, "fechner must have at least one seeded membership"

    # Every seeded membership names a real role (drawn from the M0.3 enum).
    for result in results:
        for member in result.users:
            assert member.roles
            assert all(isinstance(role, MembershipRole) for role in member.roles)

    assert asyncio.run(_counts(tenancy_db))["orgs"] == len(specs)


def test_seeded_fechner_org_has_expected_dach_identity(tenancy_db: str, seeder: Seeder) -> None:
    """The pilot is seeded metric-native DACH: DE / EUR / de-DE."""
    asyncio.run(_apply(tenancy_db, load_seeds(DEFAULT_SEEDS_DIR)))
    fechner = asyncio.run(_fetch_org(tenancy_db, "fechner"))
    assert fechner["country"] == "DE"
    assert fechner["currency"] == "EUR"
    assert fechner["locale"] == "de-DE"


def test_seed_is_idempotent_on_rerun(tenancy_db: str, seeder: Seeder) -> None:
    """Running the seed twice yields the same state — no duplicated rows."""
    specs = load_seeds(DEFAULT_SEEDS_DIR)

    first = asyncio.run(_apply(tenancy_db, specs))
    after_first = asyncio.run(_counts(tenancy_db))

    second = asyncio.run(_apply(tenancy_db, specs))
    after_second = asyncio.run(_counts(tenancy_db))

    assert after_first == after_second  # re-seed adds nothing
    assert all(result.org_created for result in first)  # all fresh on pass 1
    assert not any(result.org_created for result in second)  # reconciled on pass 2
    assert not any(
        member.user_created or member.membership_created
        for result in second
        for member in result.users
    )


def test_seed_reuses_one_global_user_across_orgs(tenancy_db: str, seeder: Seeder) -> None:
    """One global AppUser may hold a membership in each org (E4-a multi-org)."""
    shared = "shared.admin@example.com"
    specs = [
        OrgSpec(
            slug="org-one",
            name="Org One",
            users=[UserSpec(email=shared, roles=[MembershipRole.admin])],
        ),
        OrgSpec(
            slug="org-two",
            name="Org Two",
            locale="en",
            users=[UserSpec(email=shared, roles=[MembershipRole.estimator])],
        ),
    ]

    asyncio.run(_apply(tenancy_db, specs))

    counts = asyncio.run(_counts(tenancy_db))
    assert counts["orgs"] == 2
    assert counts["users"] == 1  # the shared identity is reused, not duplicated
    assert counts["memberships"] == 2  # one membership per org


def test_seeded_user_authenticates_and_isolation_holds(
    app_client: TestClient, tenancy_db: str, seeder: Seeder
) -> None:
    """A seeded admin authenticates; the M0.2 cross-org denial holds for the pair.

    Satisfies the M0 exit gate ("two seeded orgs + login works") against the
    *seeded* orgs rather than ad-hoc fixture rows.
    """
    results = asyncio.run(_apply(tenancy_db, load_seeds(DEFAULT_SEEDS_DIR)))
    org_a, org_b = results[0], results[1]
    admin_a = _first_admin(org_a)
    admin_b = _first_admin(org_b)

    seeder.note(org_a.org_id, "a-note")
    seeder.note(org_b.org_id, "b-note")

    with authed(
        app_client, user_id=admin_a.user_id, org_id=org_a.org_id, roles=list(admin_a.roles)
    ):
        a_notes = app_client.get("/notes").json()
    with authed(
        app_client, user_id=admin_b.user_id, org_id=org_b.org_id, roles=list(admin_b.roles)
    ):
        b_notes = app_client.get("/notes").json()

    assert [note["body"] for note in a_notes] == ["a-note"]
    assert [note["body"] for note in b_notes] == ["b-note"]


def _first_admin(result: OrgResult) -> Any:
    """The first seeded member holding the admin role (each shipped org has one)."""
    return next(member for member in result.users if MembershipRole.admin in member.roles)


# --------------------------------------------------------------------------- #
# Input-contract validation (pure Python — no DB; runs everywhere)
# --------------------------------------------------------------------------- #
def test_userspec_accepts_singular_role_shorthand() -> None:
    """The seed-skeleton's singular ``role`` is coerced to a one-element ``roles``."""
    spec = UserSpec.model_validate({"email": "a@b.co", "role": "admin"})
    assert spec.roles == [MembershipRole.admin]


def test_userspec_rejects_a_malformed_email() -> None:
    with pytest.raises(ValidationError):
        UserSpec(email="not-an-email", roles=[MembershipRole.admin])


def test_orgspec_rejects_unsupported_currency() -> None:
    """Only EUR/CHF are valid — mirrors the DB CHECK + DACH money convention."""
    with pytest.raises(ValidationError):
        OrgSpec(
            slug="acme",
            name="Acme",
            currency="USD",
            users=[UserSpec(email="a@b.co", roles=[MembershipRole.admin])],
        )


def test_orgspec_rejects_unknown_fields() -> None:
    """``extra='forbid'`` keeps a seed file from silently carrying ignored keys."""
    with pytest.raises(ValidationError):
        OrgSpec.model_validate(
            {
                "slug": "acme",
                "name": "Acme",
                "export_regime": "eu_dual_use",  # deferred column — not in M0.5 scope
                "users": [{"email": "a@b.co", "roles": ["admin"]}],
            }
        )
