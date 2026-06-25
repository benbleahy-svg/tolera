"""M1.3 — saved views (``/api/saved-views``) + the persistence round-trip.

Exercises the acceptance criteria for the saved-view engine: a saved view reloads
with its filters intact and, replayed against ``/quotes/search``, narrows to the same
rows; views are org- AND owner-scoped; the v1 rulings (quotes-scope-only, private-only)
are enforced.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.models import MembershipRole, QuoteStatus
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
_DRAFT_FILTER = [{"field": "status", "op": "eq", "value": "draft"}]


def _org_user(seeder: Seeder, slug: str, email: str = "u") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"{email}@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def test_create_and_list_round_trip(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        created = app_client.post(
            "/api/saved-views",
            json={"name": "My drafts", "filters": _DRAFT_FILTER},
        )
        assert created.status_code == 201, created.text
        assert created.json()["filters"] == _DRAFT_FILTER

        listed = app_client.get("/api/saved-views").json()
    # System views are advertised (All Quotes is the default); the custom view appears.
    assert any(v["key"] == "all-quotes" and v["is_default"] for v in listed["system"])
    assert [v["name"] for v in listed["custom"]] == ["My drafts"]
    assert listed["custom"][0]["filters"] == _DRAFT_FILTER


def test_saved_filter_replays_to_same_rows(app_client: TestClient, seeder: Seeder) -> None:
    """AC: a saved view reloads with its filters and the rows match.

    Save a draft-only view, re-fetch it (simulating reload), then POST its stored
    filters to ``/quotes/search`` — it must narrow to exactly the draft quotes."""
    org, user = _org_user(seeder, "org-a")
    seeder.quote(org, "D-1", status=QuoteStatus.draft)
    seeder.quote(org, "D-2", status=QuoteStatus.draft)
    seeder.quote(org, "S-1", status=QuoteStatus.sent)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        app_client.post("/api/saved-views", json={"name": "Drafts", "filters": _DRAFT_FILTER})
        # Reload: fetch the view back, then replay its stored filters.
        view = app_client.get("/api/saved-views").json()["custom"][0]
        result = app_client.post(
            "/api/quotes/search", json={"filters": view["filters"], "sort": view["sort"]}
        ).json()
    assert {r["number"] for r in result["rows"]} == {"D-1", "D-2"}


def test_update_view(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        view_id = app_client.post("/api/saved-views", json={"name": "A"}).json()["id"]
        patched = app_client.patch(
            f"/api/saved-views/{view_id}",
            json={"name": "B", "filters": _DRAFT_FILTER},
        )
        assert patched.status_code == 200
        assert patched.json()["name"] == "B"
        assert patched.json()["filters"] == _DRAFT_FILTER


def test_delete_view(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        view_id = app_client.post("/api/saved-views", json={"name": "A"}).json()["id"]
        assert app_client.delete(f"/api/saved-views/{view_id}").status_code == 204
        assert app_client.get("/api/saved-views").json()["custom"] == []


def test_views_are_owner_scoped_within_an_org(app_client: TestClient, seeder: Seeder) -> None:
    """Two users in the SAME org don't see or edit each other's views (private v1)."""
    org, alice = _org_user(seeder, "org-a", email="alice")
    bob = seeder.user("bob@org-a.example")
    seeder.membership(bob, org, ADMIN)

    with authed(app_client, user_id=alice, org_id=org, roles=ADMIN):
        alice_view = app_client.post("/api/saved-views", json={"name": "Alice"}).json()["id"]

    with authed(app_client, user_id=bob, org_id=org, roles=ADMIN):
        assert app_client.get("/api/saved-views").json()["custom"] == []  # bob sees none
        # ...and cannot touch Alice's view (404, not 403 — it's invisible to him).
        patch = app_client.patch(f"/api/saved-views/{alice_view}", json={"name": "X"})
        assert patch.status_code == 404
        assert app_client.delete(f"/api/saved-views/{alice_view}").status_code == 404


def test_cross_org_isolation(app_client: TestClient, seeder: Seeder) -> None:
    org_a, alice = _org_user(seeder, "org-a", email="alice")
    org_b, bob = _org_user(seeder, "org-b", email="bob")
    with authed(app_client, user_id=alice, org_id=org_a, roles=ADMIN):
        a_view = app_client.post("/api/saved-views", json={"name": "A"}).json()["id"]
    with authed(app_client, user_id=bob, org_id=org_b, roles=ADMIN):
        assert app_client.get("/api/saved-views").json()["custom"] == []
        assert app_client.patch(f"/api/saved-views/{a_view}", json={"name": "X"}).status_code == 404


def test_duplicate_name_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        assert app_client.post("/api/saved-views", json={"name": "Dup"}).status_code == 201
        conflict = app_client.post("/api/saved-views", json={"name": "Dup"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "name_conflict"


def test_line_items_scope_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post("/api/saved-views", json={"name": "LI", "view_scope": "line_items"})
    assert res.status_code == 422
    assert res.json()["code"] == "unsupported_scope"


def test_org_visibility_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post("/api/saved-views", json={"name": "Shared", "visibility": "org"})
    assert res.status_code == 422
    assert res.json()["code"] == "unsupported_visibility"


def test_invalid_filter_rejected_on_create(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/saved-views",
            json={"name": "Bad", "filters": [{"field": "status", "op": "gte", "value": "draft"}]},
        )
    assert res.status_code == 422  # status has no range operator


def test_view_all_permission_required(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=[]):  # no view_all
        assert app_client.get("/api/saved-views").status_code == 403
        assert app_client.post("/api/saved-views", json={"name": "X"}).status_code == 403
