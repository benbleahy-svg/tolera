"""M1.1 — Accounts & Contacts CRUD.

Exercises the acceptance criteria (CRUD round-trips; soft-deleted records hide but
persist; all reads org-scoped) and the four DECISIONS.md 2026-06-25 rulings:
nullable ``contact.account_id``, the live-only unique email index, archive
semantics + cascade, and the salesperson active-member guard. All requests run
through the restricted (RLS-bound) ``app_client``; cross-org rows are planted via
the owner-connection ``seeder``.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import MembershipRole, MembershipStatus
from tests.conftest import Seeder, app_role_url, authed

ADMIN = [MembershipRole.admin]
ESTIMATOR = [MembershipRole.estimator]
VIEWER = [MembershipRole.viewer]


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed an org + an admin user/membership; return (org_id, admin_user_id)."""
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


# --------------------------------------------------------------------------- #
# CRUD round-trips
# --------------------------------------------------------------------------- #
def test_account_crud_round_trip(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        created = app_client.post("/api/accounts", json={"name": "Fechner GmbH"})
        assert created.status_code == 201
        body = created.json()
        account_id = body["id"]
        assert body["name"] == "Fechner GmbH"
        assert body["type"] == "customer"
        assert body["archived"] is False

        fetched = app_client.get(f"/api/accounts/{account_id}")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "Fechner GmbH"

        patched = app_client.patch(f"/api/accounts/{account_id}", json={"name": "Fechner AG"})
        assert patched.status_code == 200
        assert patched.json()["name"] == "Fechner AG"

        listed = app_client.get("/api/accounts").json()
        assert [a["name"] for a in listed] == ["Fechner AG"]


def test_create_account_with_primary_contact(app_client: TestClient, seeder: Seeder) -> None:
    """The Create-Account modal can seed a first contact in one call (spec #contacts)."""
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        created = app_client.post(
            "/api/accounts",
            json={
                "name": "Fechner GmbH",
                "primary_contact": {"email": "Buyer@Fechner.example", "first_name": "Bea"},
            },
        )
        assert created.status_code == 201
        account_id = created.json()["id"]

        contacts = app_client.get(f"/api/accounts/{account_id}/contacts").json()
        assert len(contacts) == 1
        assert contacts[0]["email"] == "buyer@fechner.example"  # normalised lower-case
        assert contacts[0]["account_id"] == account_id


def test_contact_crud_round_trip(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        account_id = app_client.post("/api/accounts", json={"name": "Acme"}).json()["id"]

        created = app_client.post(
            f"/api/accounts/{account_id}/contacts",
            json={"email": "p@acme.example", "first_name": "Pat", "role": "Purchasing"},
        )
        assert created.status_code == 201
        contact_id = created.json()["id"]
        assert created.json()["role"] == "Purchasing"

        patched = app_client.patch(f"/api/contacts/{contact_id}", json={"role": "Buyer"})
        assert patched.status_code == 200
        assert patched.json()["role"] == "Buyer"

        assert app_client.get(f"/api/contacts/{contact_id}").json()["email"] == "p@acme.example"
        assert [c["id"] for c in app_client.get("/api/contacts").json()] == [contact_id]


def test_contact_account_id_is_nullable(app_client: TestClient, seeder: Seeder) -> None:
    """A contact may exist without an account (DECISIONS.md 2026-06-25 — RFQ-origin
    contacts). Seeded directly here (the API happy path always supplies an account)."""
    org = seeder.org("org-a")
    admin = seeder.user("admin@org-a.example")
    seeder.membership(admin, org, ADMIN)
    seeder.contact(org, None, "loose@org-a.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        listed = app_client.get("/api/contacts").json()
    assert [c["account_id"] for c in listed] == [None]


# --------------------------------------------------------------------------- #
# Archive / soft-delete (DECISIONS.md 2026-06-25)
# --------------------------------------------------------------------------- #
def test_archive_account_hides_from_list_but_persists_and_restores(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        account_id = app_client.post("/api/accounts", json={"name": "Acme"}).json()["id"]

        archived = app_client.post(f"/api/accounts/{account_id}/archive")
        assert archived.status_code == 200
        assert archived.json()["archived"] is True

        # Hidden from the default list, but persists (direct GET + include_archived).
        assert app_client.get("/api/accounts").json() == []
        assert app_client.get(f"/api/accounts/{account_id}").json()["archived"] is True
        assert len(app_client.get("/api/accounts?include_archived=true").json()) == 1

        restored = app_client.post(f"/api/accounts/{account_id}/restore")
        assert restored.json()["archived"] is False
        assert len(app_client.get("/api/accounts").json()) == 1


def test_archiving_account_hides_its_contacts_from_cross_account_list(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Archiving an account doesn't mutate its contacts, but they drop out of the
    cross-account contact list (DECISIONS.md 2026-06-25)."""
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        account_id = app_client.post("/api/accounts", json={"name": "Acme"}).json()["id"]
        contact_id = app_client.post(
            f"/api/accounts/{account_id}/contacts", json={"email": "p@acme.example"}
        ).json()["id"]

        assert [c["id"] for c in app_client.get("/api/contacts").json()] == [contact_id]

        app_client.post(f"/api/accounts/{account_id}/archive")
        # Gone from the cross-account list...
        assert app_client.get("/api/contacts").json() == []
        # ...but the contact row is untouched and still directly reachable.
        contact = app_client.get(f"/api/contacts/{contact_id}").json()
        assert contact["archived"] is False
        assert len(app_client.get("/api/contacts?include_archived=true").json()) == 1

        app_client.post(f"/api/accounts/{account_id}/restore")
        assert [c["id"] for c in app_client.get("/api/contacts").json()] == [contact_id]


def test_archive_contact_hides_and_restores(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        account_id = app_client.post("/api/accounts", json={"name": "Acme"}).json()["id"]
        contact_id = app_client.post(
            f"/api/accounts/{account_id}/contacts", json={"email": "p@acme.example"}
        ).json()["id"]

        app_client.post(f"/api/contacts/{contact_id}/archive")
        assert app_client.get(f"/api/accounts/{account_id}/contacts").json() == []
        assert app_client.get(f"/api/contacts/{contact_id}").json()["archived"] is True

        app_client.post(f"/api/contacts/{contact_id}/restore")
        assert len(app_client.get(f"/api/accounts/{account_id}/contacts").json()) == 1


def test_no_hard_delete_route(app_client: TestClient, seeder: Seeder) -> None:
    """v1 has no destructive DELETE — only archive (DECISIONS.md 2026-06-25)."""
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        account_id = app_client.post("/api/accounts", json={"name": "Acme"}).json()["id"]
        assert app_client.delete(f"/api/accounts/{account_id}").status_code == 405


def test_restricted_role_cannot_delete_crm_rows(tenancy_db: str, seeder: Seeder) -> None:
    """The app role is granted SELECT/INSERT/UPDATE only — no DELETE — so even raw
    SQL can't hard-delete a CRM row (least-privilege backing the no-hard-delete
    decision, 2026-06-25)."""
    org = seeder.org("org-a")
    seeder.account(org, "A GmbH")

    async def _attempt_delete() -> str:
        engine = create_async_engine(app_role_url(tenancy_db))
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM account"))
            return ""  # empty == DELETE was (wrongly) permitted
        except Exception as exc:  # SQLAlchemy wraps asyncpg InsufficientPrivilegeError
            return str(exc)
        finally:
            await engine.dispose()

    message = asyncio.run(_attempt_delete())
    assert "permission denied" in message.lower()


# --------------------------------------------------------------------------- #
# Live-only unique email (DECISIONS.md 2026-06-25)
# --------------------------------------------------------------------------- #
def test_contact_email_unique_among_live_only(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        account_id = app_client.post("/api/accounts", json={"name": "Acme"}).json()["id"]
        first = app_client.post(
            f"/api/accounts/{account_id}/contacts", json={"email": "dup@acme.example"}
        )
        assert first.status_code == 201

        # A second LIVE contact with the same email is rejected cleanly (409, not 500).
        conflict = app_client.post(
            f"/api/accounts/{account_id}/contacts", json={"email": "dup@acme.example"}
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "email_conflict"

        # Archive the first → its email frees up for a new live contact.
        app_client.post(f"/api/contacts/{first.json()['id']}/archive")
        reused = app_client.post(
            f"/api/accounts/{account_id}/contacts", json={"email": "dup@acme.example"}
        )
        assert reused.status_code == 201


# --------------------------------------------------------------------------- #
# Org isolation (RLS)
# --------------------------------------------------------------------------- #
def test_cross_org_isolation_both_directions(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_with_admin(seeder, "org-a")
    org_b, admin_b = _org_with_admin(seeder, "org-b")
    acct_a = seeder.account(org_a, "A GmbH")
    acct_b = seeder.account(org_b, "B GmbH")

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        a_list = app_client.get("/api/accounts").json()
        a_sees_b = app_client.get(f"/api/accounts/{acct_b}")
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        b_list = app_client.get("/api/accounts").json()

    assert [a["name"] for a in a_list] == ["A GmbH"]
    assert [a["name"] for a in b_list] == ["B GmbH"]
    assert str(acct_a) == a_list[0]["id"]
    # Org A cannot reach org B's account at all — RLS makes it a 404, not a 403.
    assert a_sees_b.status_code == 404


def test_account_rls_enforced_at_the_database(tenancy_db: str, seeder: Seeder) -> None:
    """The restricted role sees ZERO accounts with no org GUC set — a DB guarantee,
    not an app filter (mirrors the M0.2 note proof for the new table)."""
    org = seeder.org("org-a")
    seeder.account(org, "Secret GmbH")

    async def _counts() -> tuple[int, int]:
        app_engine = create_async_engine(app_role_url(tenancy_db))
        owner_engine = create_async_engine(tenancy_db)
        try:
            async with app_engine.connect() as conn:  # no set_config → GUC unset
                restricted = (await conn.execute(text("SELECT count(*) FROM account"))).scalar_one()
            async with owner_engine.connect() as conn:
                owner = (await conn.execute(text("SELECT count(*) FROM account"))).scalar_one()
        finally:
            await app_engine.dispose()
            await owner_engine.dispose()
        return restricted, owner

    restricted_count, owner_count = asyncio.run(_counts())
    assert restricted_count == 0
    assert owner_count == 1


def test_contact_cross_org_isolation(app_client: TestClient, seeder: Seeder) -> None:
    """Contacts are isolated like accounts — org A can't list or fetch org B's."""
    org_a, admin_a = _org_with_admin(seeder, "org-a")
    org_b, _admin_b = _org_with_admin(seeder, "org-b")
    acct_a = seeder.account(org_a, "A GmbH")
    seeder.contact(org_a, acct_a, "a@org-a.example")
    acct_b = seeder.account(org_b, "B GmbH")
    contact_b = seeder.contact(org_b, acct_b, "b@org-b.example")

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        a_emails = [c["email"] for c in app_client.get("/api/contacts").json()]
        a_sees_b = app_client.get(f"/api/contacts/{contact_b}")

    assert a_emails == ["a@org-a.example"]
    assert a_sees_b.status_code == 404  # RLS → 404, not 403


def test_contact_rls_enforced_at_the_database(tenancy_db: str, seeder: Seeder) -> None:
    """The restricted role sees ZERO contacts with no org GUC set (DB guarantee)."""
    org = seeder.org("org-a")
    acct = seeder.account(org, "Secret GmbH")
    seeder.contact(org, acct, "secret@org-a.example")

    async def _counts() -> tuple[int, int]:
        app_engine = create_async_engine(app_role_url(tenancy_db))
        owner_engine = create_async_engine(tenancy_db)
        try:
            async with app_engine.connect() as conn:  # no set_config → GUC unset
                restricted = (await conn.execute(text("SELECT count(*) FROM contact"))).scalar_one()
            async with owner_engine.connect() as conn:
                owner = (await conn.execute(text("SELECT count(*) FROM contact"))).scalar_one()
        finally:
            await app_engine.dispose()
            await owner_engine.dispose()
        return restricted, owner

    restricted_count, owner_count = asyncio.run(_counts())
    assert restricted_count == 0
    assert owner_count == 1


# --------------------------------------------------------------------------- #
# Salesperson must be an active member of the active org (DECISIONS.md 2026-06-25)
# --------------------------------------------------------------------------- #
def test_salesperson_must_be_active_member_of_active_org(
    app_client: TestClient, seeder: Seeder
) -> None:
    org_a, admin_a = _org_with_admin(seeder, "org-a")
    org_b, _admin_b = _org_with_admin(seeder, "org-b")

    member = seeder.user("sales@org-a.example")
    seeder.membership(member, org_a, [MembershipRole.salesperson])

    non_member = seeder.user("nobody@example.com")  # no membership anywhere

    foreign = seeder.user("sales@org-b.example")
    seeder.membership(foreign, org_b, [MembershipRole.salesperson])  # member of B, not A

    disabled = seeder.user("ex@org-a.example")
    seeder.membership(
        disabled, org_a, [MembershipRole.salesperson], status=MembershipStatus.disabled
    )

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        ok = app_client.post("/api/accounts", json={"name": "Acme", "salesperson_id": str(member)})
        assert ok.status_code == 201

        for bad in (non_member, foreign, disabled):
            resp = app_client.post(
                "/api/accounts", json={"name": "Acme", "salesperson_id": str(bad)}
            )
            assert resp.status_code == 422, bad
            assert resp.json()["code"] == "invalid_salesperson"


# --------------------------------------------------------------------------- #
# RBAC gates (M0.3 matrix)
# --------------------------------------------------------------------------- #
def test_rbac_create_edit_archive_gates(app_client: TestClient, seeder: Seeder) -> None:
    org = seeder.org("org-a")
    viewer = seeder.user("viewer@org-a.example")
    estimator = seeder.user("est@org-a.example")
    admin = seeder.user("admin@org-a.example")
    for user, roles in ((viewer, VIEWER), (estimator, ESTIMATOR), (admin, ADMIN)):
        seeder.membership(user, org, roles)

    # viewer: no quote_edit → cannot create.
    with authed(app_client, user_id=viewer, org_id=org, roles=VIEWER):
        assert app_client.post("/api/accounts", json={"name": "X"}).status_code == 403

    # estimator: quote_edit yes, quote_delete no → create/edit ok, archive denied.
    with authed(app_client, user_id=estimator, org_id=org, roles=ESTIMATOR):
        created = app_client.post("/api/accounts", json={"name": "X"})
        assert created.status_code == 201
        account_id = created.json()["id"]
        assert (
            app_client.patch(f"/api/accounts/{account_id}", json={"name": "Y"}).status_code == 200
        )
        assert app_client.post(f"/api/accounts/{account_id}/archive").status_code == 403

    # admin: full rights → archive ok.
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        assert app_client.post(f"/api/accounts/{account_id}/archive").status_code == 200


def test_unauthenticated_request_is_rejected(app_client: TestClient) -> None:
    resp = app_client.get("/api/accounts")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


def test_invalid_email_is_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        account_id = app_client.post("/api/accounts", json={"name": "Acme"}).json()["id"]
        resp = app_client.post(
            f"/api/accounts/{account_id}/contacts", json={"email": "not-an-email"}
        )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_missing_account_is_404(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        resp = app_client.get(f"/api/accounts/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_edit_revalidates_salesperson(app_client: TestClient, seeder: Seeder) -> None:
    """The active-member guard fires on EDIT too, not just create — a foreign-org
    user can't be slipped in via PATCH (DECISIONS.md 2026-06-25)."""
    org_a, admin_a = _org_with_admin(seeder, "org-a")
    org_b, _admin_b = _org_with_admin(seeder, "org-b")
    member = seeder.user("sales@org-a.example")
    seeder.membership(member, org_a, [MembershipRole.salesperson])
    foreign = seeder.user("sales@org-b.example")
    seeder.membership(foreign, org_b, [MembershipRole.salesperson])

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        account_id = app_client.post("/api/accounts", json={"name": "Acme"}).json()["id"]
        contact_id = app_client.post(
            f"/api/accounts/{account_id}/contacts", json={"email": "p@acme.example"}
        ).json()["id"]

        ok = app_client.patch(f"/api/accounts/{account_id}", json={"salesperson_id": str(member)})
        assert ok.status_code == 200
        assert ok.json()["salesperson_id"] == str(member)

        bad_account = app_client.patch(
            f"/api/accounts/{account_id}", json={"salesperson_id": str(foreign)}
        )
        assert bad_account.status_code == 422
        assert bad_account.json()["code"] == "invalid_salesperson"

        bad_contact = app_client.patch(
            f"/api/contacts/{contact_id}", json={"salesperson_id": str(foreign)}
        )
        assert bad_contact.status_code == 422
        assert bad_contact.json()["code"] == "invalid_salesperson"


def test_account_list_search_and_salesperson_filters(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    member = seeder.user("sales@org-a.example")
    seeder.membership(member, org, [MembershipRole.salesperson])
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        app_client.post(
            "/api/accounts",
            json={
                "name": "Fechner GmbH",
                "email": "info@fechner.example",
                "salesperson_id": str(member),
            },
        )
        app_client.post("/api/accounts", json={"name": "Acme Corp"})

        assert [a["name"] for a in app_client.get("/api/accounts?q=fechner").json()] == [
            "Fechner GmbH"
        ]
        # q matches email too.
        assert [a["name"] for a in app_client.get("/api/accounts?q=info@fechner").json()] == [
            "Fechner GmbH"
        ]
        assert [
            a["name"] for a in app_client.get(f"/api/accounts?salesperson_id={member}").json()
        ] == ["Fechner GmbH"]


def test_move_contact_to_another_account(app_client: TestClient, seeder: Seeder) -> None:
    """A contact can be re-parented via PATCH account_id (validated to exist)."""
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        a1 = app_client.post("/api/accounts", json={"name": "A1"}).json()["id"]
        a2 = app_client.post("/api/accounts", json={"name": "A2"}).json()["id"]
        contact_id = app_client.post(
            f"/api/accounts/{a1}/contacts", json={"email": "p@acme.example"}
        ).json()["id"]

        moved = app_client.patch(f"/api/contacts/{contact_id}", json={"account_id": a2})
        assert moved.status_code == 200
        assert moved.json()["account_id"] == a2
        assert [c["id"] for c in app_client.get(f"/api/accounts/{a2}/contacts").json()] == [
            contact_id
        ]

        # Moving to a non-existent account is a 404.
        gone = app_client.patch(
            f"/api/contacts/{contact_id}", json={"account_id": str(uuid.uuid4())}
        )
        assert gone.status_code == 404
