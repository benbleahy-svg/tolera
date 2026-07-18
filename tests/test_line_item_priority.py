"""M5.0 — per-line-item ``priority`` (``PATCH /api/quotes/{id}/items/{item_id}``).

Spec ``#partview``: priority is a line-item field the estimating sidebar sets;
the quotes grid derives MAX(priority) per quote (that derivation is exercised in
``test_quotes.py``). Runs against a real RLS-bound Postgres.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
VIEWER = [MembershipRole.viewer]


def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _quote_with_item(client: TestClient) -> tuple[str, str]:
    qid = client.post("/api/quotes", json={}).json()["id"]
    detail = client.post(f"/api/quotes/{qid}/items").json()
    return qid, detail["items"][0]["id"]


def test_priority_defaults_null(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        _, item_id = _quote_with_item(app_client)
        qid = app_client.post("/api/quotes", json={}).json()["id"]
        detail = app_client.post(f"/api/quotes/{qid}/items").json()
    assert detail["items"][0]["priority"] is None
    assert item_id is not None


def test_set_and_clear_priority(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item_id = _quote_with_item(app_client)
        res = app_client.patch(f"/api/quotes/{qid}/items/{item_id}", json={"priority": 7})
        assert res.status_code == 200, res.text
        assert res.json()["items"][0]["priority"] == 7
        # explicit null clears it back to blank
        cleared = app_client.patch(f"/api/quotes/{qid}/items/{item_id}", json={"priority": None})
        assert cleared.json()["items"][0]["priority"] is None


def test_priority_out_of_range_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item_id = _quote_with_item(app_client)
        low = app_client.patch(f"/api/quotes/{qid}/items/{item_id}", json={"priority": 0})
        high = app_client.patch(f"/api/quotes/{qid}/items/{item_id}", json={"priority": 11})
    assert low.status_code == 422
    assert high.status_code == 422


def test_unknown_field_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item_id = _quote_with_item(app_client)
        res = app_client.patch(f"/api/quotes/{qid}/items/{item_id}", json={"was_won": True})
    assert res.status_code == 422


def test_patch_unknown_item_404(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, _ = _quote_with_item(app_client)
        res = app_client.patch(f"/api/quotes/{qid}/items/{uuid.uuid4()}", json={"priority": 3})
    assert res.status_code == 404


def test_item_from_other_quote_rejected(app_client: TestClient, seeder: Seeder) -> None:
    """An item id that belongs to a *different* quote in the same org is a 404 —
    the path must match (quote_id, item_id), not just the item."""
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid_a, _ = _quote_with_item(app_client)
        _, item_b = _quote_with_item(app_client)
        res = app_client.patch(f"/api/quotes/{qid_a}/items/{item_b}", json={"priority": 3})
    assert res.status_code == 404


def test_priority_requires_quote_edit(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    viewer = seeder.user("viewer@org-a.example")
    seeder.membership(viewer, org, VIEWER)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item_id = _quote_with_item(app_client)
    with authed(app_client, user_id=viewer, org_id=org, roles=VIEWER):
        res = app_client.patch(f"/api/quotes/{qid}/items/{item_id}", json={"priority": 3})
    assert res.status_code == 403


def test_priority_locked_once_not_draft(app_client: TestClient, seeder: Seeder) -> None:
    """Line-item edits are draft-only; a non-draft (here ``cancelled``) quote 409s."""
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item_id = _quote_with_item(app_client)
        tr = app_client.post(f"/api/quotes/{qid}/transition", json={"to_status": "cancelled"})
        assert tr.status_code == 200, tr.text
        res = app_client.patch(f"/api/quotes/{qid}/items/{item_id}", json={"priority": 3})
    assert res.status_code == 409


def test_cross_org_isolation(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b, admin_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        qid_a, item_a = _quote_with_item(app_client)
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        res: Any = app_client.patch(f"/api/quotes/{qid_a}/items/{item_a}", json={"priority": 3})
    # RLS hides the other org's quote entirely → 404, never a cross-org write.
    assert res.status_code == 404
