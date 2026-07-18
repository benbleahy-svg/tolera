"""M5.0 — the quotes grid's derived ``MAX(line-item priority)`` (spec #partview;
DECISIONS 2026-07-17 *Quote-level priority home*). Exercises the row value, the
filter-grammar field, the sort, and the "Highest Priority" system view — all
against a real RLS-bound Postgres.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]


def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _quote_with_priorities(client: TestClient, priorities: list[int | None]) -> str:
    """Create a quote with one line item per entry, each set to that priority
    (``None`` = leave blank). Returns the quote id."""
    qid = str(client.post("/api/quotes", json={}).json()["id"])
    for pr in priorities:
        detail = client.post(f"/api/quotes/{qid}/items").json()
        if pr is not None:
            item_id = detail["items"][-1]["id"]
            res = client.patch(f"/api/quotes/{qid}/items/{item_id}", json={"priority": pr})
            assert res.status_code == 200, res.text
    return qid


def _search(client: TestClient, **body: Any) -> dict[str, Any]:
    res = client.post("/api/quotes/search", json=body)
    assert res.status_code == 200, res.text
    data: dict[str, Any] = res.json()
    return data


def test_row_priority_is_max_over_line_items(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        q_hot = _quote_with_priorities(app_client, [3, 7, None])
        q_blank = _quote_with_priorities(app_client, [None, None])
        q_empty = app_client.post("/api/quotes", json={}).json()["id"]
        rows = {r["id"]: r["priority"] for r in _search(app_client)["rows"]}
    assert rows[q_hot] == 7  # MAX(3, 7, blank)
    assert rows[q_blank] is None  # items exist but none prioritised
    assert rows[q_empty] is None  # no line items at all


def test_filter_priority_gte(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        q_hi = _quote_with_priorities(app_client, [8])
        _quote_with_priorities(app_client, [2])
        _quote_with_priorities(app_client, [None])
        body = _search(app_client, filters=[{"field": "priority", "op": "gte", "value": 5}])
    assert {r["id"] for r in body["rows"]} == {q_hi}


def test_filter_priority_is_null(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        _quote_with_priorities(app_client, [4])
        q_blank = _quote_with_priorities(app_client, [None])
        q_empty = app_client.post("/api/quotes", json={}).json()["id"]
        body = _search(app_client, filters=[{"field": "priority", "op": "is_null", "value": True}])
    assert {r["id"] for r in body["rows"]} == {q_blank, q_empty}


def test_sort_priority_desc_nulls_last(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        q_lo = _quote_with_priorities(app_client, [2])
        q_hi = _quote_with_priorities(app_client, [9])
        q_none = _quote_with_priorities(app_client, [None])
        body = _search(app_client, sort=[{"field": "priority", "dir": "desc"}])
    order = [r["id"] for r in body["rows"]]
    # highest first, blanks always last
    assert order.index(q_hi) < order.index(q_lo) < order.index(q_none)


def test_highest_priority_system_view(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        q_lo = _quote_with_priorities(app_client, [1])
        q_hi = _quote_with_priorities(app_client, [10])
        q_none = app_client.post("/api/quotes", json={}).json()["id"]
        body = _search(app_client, system_view="highest-priority")
    order = [r["id"] for r in body["rows"]]
    assert order[0] == q_hi
    assert order.index(q_hi) < order.index(q_lo) < order.index(q_none)


def test_priority_filter_rejects_bad_op(app_client: TestClient, seeder: Seeder) -> None:
    """The grammar still rejects an unsupported op cleanly (422, not a 500)."""
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/quotes/search",
            json={"filters": [{"field": "priority", "op": "gte", "value": "not-an-int"}]},
        )
    assert res.status_code == 422


def test_highest_priority_view_org_scoped(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b, admin_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        q_a = _quote_with_priorities(app_client, [5])
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        body = _search(app_client, system_view="highest-priority")
    assert q_a not in {r["id"] for r in body["rows"]}
