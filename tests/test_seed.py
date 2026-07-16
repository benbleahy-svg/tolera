"""M0.5 seed framework tests — idempotent org provisioning.

Proves the M0 exit slice "two seeded orgs + login works": the shipped seeds
provision the ``fechner`` pilot plus a second org, re-running the seed is
idempotent (no duplication), one global user may span orgs (E4-a), and a seeded
user authenticates with the M0.2 cross-org isolation holding against the seeded
pair. Real Clerk linkage is out of scope (DECISIONS.md 2026-06-24 "Seed
framework — Clerk provisioning scope"): "login" is exercised via the test
harness principal injection, exactly as the M0.2 tenancy gate does.

DB-backed tests take the ``clean_db`` fixture (empties the tenant tables first,
so created-vs-reconciled assertions don't depend on global DB state or test
order); they skip without a reachable ``TEST_DATABASE_URL``. The pure-Python
input-contract tests need no database.
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

_TENANT_TABLES = "note, user_org_membership, app_user, organization"


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


async def _fetch_user(owner_url: str, email: str) -> dict[str, Any]:
    engine = make_engine(owner_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT email, first_name, last_name FROM app_user WHERE email = :email"),
                    {"email": email},
                )
            ).one()
        return dict(row._mapping)
    finally:
        await engine.dispose()


async def _scalar(conn: Any, sql: str) -> int:
    return int((await conn.execute(text(sql))).scalar_one())


async def _truncate(owner_url: str) -> None:
    engine = make_engine(owner_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"TRUNCATE {_TENANT_TABLES} CASCADE"))
            await conn.commit()
    finally:
        await engine.dispose()


@pytest.fixture
def clean_db(tenancy_db: str) -> str:
    """Owner DSN whose tenant tables are emptied before the test runs."""
    asyncio.run(_truncate(tenancy_db))
    return tenancy_db


def _first_admin(result: OrgResult) -> Any:
    """The first seeded member holding the admin role (each shipped org has one)."""
    return next(member for member in result.users if MembershipRole.admin in member.roles)


# --------------------------------------------------------------------------- #
# DB-backed tests
# --------------------------------------------------------------------------- #
def test_shipped_seeds_provision_two_orgs_including_fechner(clean_db: str) -> None:
    """The committed ``scripts/seeds/*.json`` provision exactly the pilot + org #2."""
    specs = load_seeds(DEFAULT_SEEDS_DIR)
    slugs = {spec.slug for spec in specs}
    assert slugs == {"acme", "fechner"}  # pins the shipped fixture set against drift

    results = asyncio.run(_apply(clean_db, specs))
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

    assert asyncio.run(_counts(clean_db))["orgs"] == len(specs)


def test_seeded_fechner_org_has_expected_dach_identity(clean_db: str) -> None:
    """The pilot is seeded metric-native DACH: DE / EUR / de-DE."""
    asyncio.run(_apply(clean_db, load_seeds(DEFAULT_SEEDS_DIR)))
    fechner = asyncio.run(_fetch_org(clean_db, "fechner"))
    assert fechner["country"] == "DE"
    assert fechner["currency"] == "EUR"
    assert fechner["locale"] == "de-DE"


def test_seed_is_idempotent_on_rerun(clean_db: str) -> None:
    """Running the seed twice yields the same state — no duplicated rows."""
    specs = load_seeds(DEFAULT_SEEDS_DIR)

    first = asyncio.run(_apply(clean_db, specs))
    after_first = asyncio.run(_counts(clean_db))

    second = asyncio.run(_apply(clean_db, specs))
    after_second = asyncio.run(_counts(clean_db))

    assert after_first == after_second  # re-seed adds nothing
    assert all(result.org_created for result in first)  # all fresh on pass 1
    assert not any(result.org_created for result in second)  # reconciled on pass 2
    assert not any(
        member.user_created or member.membership_created
        for result in second
        for member in result.users
    )


def test_provisioning_creates_one_ai_settings_row_per_org(clean_db: str) -> None:
    """Every provisioned org owns exactly one all-enabled ``org_ai_settings``
    row (spec #ai-settings; M3.9), and re-seeding stays at one row per org."""

    async def _ai_rows(owner_url: str) -> tuple[int, int]:
        engine = make_engine(owner_url)
        try:
            async with engine.connect() as conn:
                total = await _scalar(conn, "SELECT count(*) FROM org_ai_settings")
                enabled = await _scalar(
                    conn,
                    "SELECT count(*) FROM org_ai_settings "
                    "WHERE master_enabled AND triage_brief_enabled",
                )
                return total, enabled
        finally:
            await engine.dispose()

    specs = load_seeds(DEFAULT_SEEDS_DIR)
    asyncio.run(_apply(clean_db, specs))
    total, enabled = asyncio.run(_ai_rows(clean_db))
    assert total == len(specs)  # one row per org
    assert enabled == len(specs)  # shipped AI-fully-enabled

    asyncio.run(_apply(clean_db, specs))  # re-seed is idempotent
    assert asyncio.run(_ai_rows(clean_db))[0] == len(specs)


def test_seed_reuses_one_global_user_across_orgs(clean_db: str) -> None:
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

    asyncio.run(_apply(clean_db, specs))

    counts = asyncio.run(_counts(clean_db))
    assert counts["orgs"] == 2
    assert counts["users"] == 1  # the shared identity is reused, not duplicated
    assert counts["memberships"] == 2  # one membership per org


def test_reseeding_a_shared_user_does_not_rewrite_profile(clean_db: str) -> None:
    """A second org seed must not rewrite a reused user's name (first-writer-wins).

    Covers both the omit case (NULL can't blank an existing name) and the
    supplied-but-different case (the seed is not an identity-admin flow).
    """
    email = "named.user@example.com"
    asyncio.run(
        _apply(
            clean_db,
            [
                OrgSpec(
                    slug="org-named",
                    name="Named Org",
                    users=[
                        UserSpec(
                            email=email,
                            roles=[MembershipRole.admin],
                            first_name="Greta",
                            last_name="Müller",
                        )
                    ],
                )
            ],
        )
    )
    asyncio.run(
        _apply(
            clean_db,
            [
                OrgSpec(
                    slug="org-other",
                    name="Other Org",
                    locale="en",
                    users=[
                        UserSpec(
                            email=email,
                            roles=[MembershipRole.estimator],
                            first_name="Hans",  # a conflicting name from a later org
                            last_name="Schmidt",
                        )
                    ],
                )
            ],
        )
    )

    user = asyncio.run(_fetch_user(clean_db, email))
    assert user["first_name"] == "Greta"  # the first writer's profile is preserved
    assert user["last_name"] == "Müller"


def test_seeded_user_authenticates_and_isolation_holds(
    app_client: TestClient, clean_db: str, seeder: Seeder
) -> None:
    """A seeded admin authenticates; the M0.2 cross-org denial holds for the pair.

    Satisfies the M0 exit gate ("two seeded orgs + login works") against the
    *seeded* orgs rather than ad-hoc fixture rows.
    """
    results = asyncio.run(_apply(clean_db, load_seeds(DEFAULT_SEEDS_DIR)))
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


# --------------------------------------------------------------------------- #
# Input-contract validation (pure Python — no DB; runs everywhere)
# --------------------------------------------------------------------------- #
def test_userspec_accepts_singular_role_shorthand() -> None:
    """The seed-skeleton's singular ``role`` is coerced to a one-element ``roles``."""
    spec = UserSpec.model_validate({"email": "a@b.co", "role": "admin"})
    assert spec.roles == [MembershipRole.admin]


def test_userspec_normalizes_email_casing_and_whitespace() -> None:
    spec = UserSpec(email="  Admin@Fechner.Example  ", roles=[MembershipRole.admin])
    assert spec.email == "admin@fechner.example"


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


def test_orgspec_rejects_a_country_currency_mismatch() -> None:
    """A CH org must bill in CHF, not the EUR default (DACH-DELTA §1)."""
    with pytest.raises(ValidationError):
        OrgSpec.model_validate(
            {
                "slug": "swiss-co",
                "name": "Swiss Co",
                "country": "CH",  # currency omitted → defaults to EUR → must be rejected
                "users": [{"email": "a@b.co", "roles": ["admin"]}],
            }
        )


def test_orgspec_accepts_ch_with_chf() -> None:
    spec = OrgSpec.model_validate(
        {
            "slug": "swiss-co",
            "name": "Swiss Co",
            "country": "CH",
            "currency": "CHF",
            "locale": "de-CH",
            "users": [{"email": "a@b.co", "roles": ["admin"]}],
        }
    )
    assert spec.currency == "CHF"


def test_orgspec_rejects_duplicate_user_emails() -> None:
    """Two members with the same (normalised) email would double-upsert one membership."""
    with pytest.raises(ValidationError):
        OrgSpec(
            slug="acme",
            name="Acme",
            users=[
                UserSpec(email="Dup@b.co", roles=[MembershipRole.admin]),
                UserSpec(email="dup@b.co", roles=[MembershipRole.estimator]),
            ],
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
