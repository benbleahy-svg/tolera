"""M0.2 tenancy + auth spine — the M0 exit-gate tests.

Proves the one property the whole product is built on: org-scoped data isolation,
authenticated, enforced at the database (not merely in the app).
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed


def test_cross_org_isolation_both_directions(app_client: TestClient, seeder: Seeder) -> None:
    """Each member sees only their active org's notes — proven both ways."""
    org_a = seeder.org("org-a")
    org_b = seeder.org("org-b")
    alice = seeder.user("alice@org-a.example")
    bob = seeder.user("bob@org-b.example")
    seeder.membership(alice, org_a, [MembershipRole.admin])
    seeder.membership(bob, org_b, [MembershipRole.estimator])
    seeder.note(org_a, "alpha")
    seeder.note(org_b, "bravo")

    with authed(app_client, user_id=alice, org_id=org_a, roles=[MembershipRole.admin]):
        a_notes = app_client.get("/notes").json()
    with authed(app_client, user_id=bob, org_id=org_b, roles=[MembershipRole.estimator]):
        b_notes = app_client.get("/notes").json()

    assert [n["body"] for n in a_notes] == ["alpha"]
    assert [n["body"] for n in b_notes] == ["bravo"]


def test_unauthenticated_request_is_rejected(app_client: TestClient) -> None:
    """No session → 401, via the standard error envelope."""
    resp = app_client.get("/notes")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


def test_wrong_role_is_rejected_at_api_layer(app_client: TestClient, seeder: Seeder) -> None:
    """A viewer cannot create a note; an admin can (API-layer RBAC)."""
    org = seeder.org("org-a")
    viewer = seeder.user("viewer@org-a.example")
    admin = seeder.user("admin@org-a.example")

    with authed(app_client, user_id=viewer, org_id=org, roles=[MembershipRole.viewer]):
        denied = app_client.post("/notes", json={"body": "nope"})
    assert denied.status_code == 403
    assert denied.json()["code"] == "forbidden"

    with authed(app_client, user_id=admin, org_id=org, roles=[MembershipRole.admin]):
        created = app_client.post("/notes", json={"body": "yes"})
        listed = app_client.get("/notes").json()
    assert created.status_code == 201
    assert [n["body"] for n in listed] == ["yes"]


def test_rls_is_enforced_at_the_database(tenancy_db: str, seeder: Seeder) -> None:
    """The restricted role gets ZERO rows with no org GUC set — RLS is a DB
    guarantee, not an app-layer filter. The owner (superuser) sees the rows."""
    org = seeder.org("org-a")
    seeder.note(org, "secret")

    async def _counts() -> tuple[int, int]:
        app_engine = create_async_engine(app_role_url(tenancy_db))
        owner_engine = create_async_engine(tenancy_db)
        try:
            async with app_engine.connect() as conn:  # no set_config → GUC unset
                restricted = (await conn.execute(text("SELECT count(*) FROM note"))).scalar_one()
            async with owner_engine.connect() as conn:
                owner = (await conn.execute(text("SELECT count(*) FROM note"))).scalar_one()
        finally:
            await app_engine.dispose()
            await owner_engine.dispose()
        return restricted, owner

    restricted_count, owner_count = asyncio.run(_counts())
    assert restricted_count == 0  # RLS blocks the app role when no org is pinned
    assert owner_count == 1  # superuser bypasses RLS — the row really exists
