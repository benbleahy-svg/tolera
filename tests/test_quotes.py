"""M1.3 — quotes list (``POST /api/quotes/search``).

Exercises the acceptance criteria for the list side: filters narrow rows, computed
system views (My Quotes / Overdue) resolve, pagination reports the right total, and
all reads are org-scoped (RLS). The quote rows are planted via the owner-connection
``seeder`` (the M1.3 app role has SELECT-only on ``quote``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole, QuoteStatus
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
_PAST = datetime(2020, 1, 1, tzinfo=UTC)
_FUTURE = datetime(2999, 1, 1, tzinfo=UTC)


def _org_user(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"u@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _search(client: TestClient, **body: object) -> dict[str, Any]:
    res = client.post("/api/quotes/search", json=body)
    assert res.status_code == 200, res.text
    data: dict[str, Any] = res.json()
    return data


def test_search_lists_all_org_quotes(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    for i in range(3):
        seeder.quote(org, f"Q-{i}")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        body = _search(app_client)
    assert body["total"] == 3
    assert len(body["rows"]) == 3


def test_filter_narrows_rows(app_client: TestClient, seeder: Seeder) -> None:
    """AC: a filter narrows the rows."""
    org, user = _org_user(seeder, "org-a")
    seeder.quote(org, "Q-1", status=QuoteStatus.draft)
    seeder.quote(org, "Q-2", status=QuoteStatus.draft)
    seeder.quote(org, "Q-3", status=QuoteStatus.sent)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        body = _search(app_client, filters=[{"field": "status", "op": "eq", "value": "draft"}])
    assert body["total"] == 2
    assert {r["status"] for r in body["rows"]} == {"draft"}


def test_filter_in_operator(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    seeder.quote(org, "Q-1", status=QuoteStatus.draft)
    seeder.quote(org, "Q-2", status=QuoteStatus.sent)
    seeder.quote(org, "Q-3", status=QuoteStatus.won)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        body = _search(
            app_client, filters=[{"field": "status", "op": "in", "value": ["draft", "sent"]}]
        )
    assert {r["status"] for r in body["rows"]} == {"draft", "sent"}


def test_system_view_my_quotes(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "org-a")
    other = seeder.user("other@org-a.example")
    # M1.4 hardened quote.estimator_id to a same-org membership FK, so the assignee
    # must be a member of this org (the salesperson/estimator tenancy guard).
    seeder.membership(other, org, [MembershipRole.estimator])
    seeder.quote(org, "MINE-E", estimator_id=me)
    seeder.quote(org, "MINE-S", salesperson_id=me)
    seeder.quote(org, "THEIRS", estimator_id=other)
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        body = _search(app_client, system_view="my-quotes")
    assert {r["number"] for r in body["rows"]} == {"MINE-E", "MINE-S"}


def test_system_view_overdue_excludes_future_and_closed(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_user(seeder, "org-a")
    seeder.quote(org, "OVERDUE", status=QuoteStatus.draft, due_date=_PAST)
    seeder.quote(org, "FUTURE", status=QuoteStatus.draft, due_date=_FUTURE)
    seeder.quote(org, "WON-PAST", status=QuoteStatus.won, due_date=_PAST)  # closed → not overdue
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        body = _search(app_client, system_view="overdue")
    assert {r["number"] for r in body["rows"]} == {"OVERDUE"}


def test_pagination_reports_total_and_pages(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    for i in range(5):
        seeder.quote(org, f"Q-{i}")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        first = _search(app_client, limit=2, offset=0)
        last = _search(app_client, limit=2, offset=4)
    assert first["total"] == 5 and len(first["rows"]) == 2
    assert last["total"] == 5 and len(last["rows"]) == 1


def test_sort_by_number_asc(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    for n in ("Q-3", "Q-1", "Q-2"):
        seeder.quote(org, n)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        body = _search(app_client, sort=[{"field": "number", "dir": "asc"}])
    assert [r["number"] for r in body["rows"]] == ["Q-1", "Q-2", "Q-3"]


def test_cross_org_isolation(app_client: TestClient, seeder: Seeder) -> None:
    org_a, user_a = _org_user(seeder, "org-a")
    org_b, _user_b = _org_user(seeder, "org-b")
    seeder.quote(org_a, "A-1")
    seeder.quote(org_b, "B-1")
    with authed(app_client, user_id=user_a, org_id=org_a, roles=ADMIN):
        body = _search(app_client)
    assert {r["number"] for r in body["rows"]} == {"A-1"}  # never B-1


# --------------------------------------------------------------------------- #
# Rejected requests
# --------------------------------------------------------------------------- #
def test_unknown_system_view_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post("/api/quotes/search", json={"system_view": "nope"})
    assert res.status_code == 422
    assert res.json()["code"] == "unknown_system_view"


def test_system_view_with_filters_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/quotes/search",
            json={
                "system_view": "drafts",
                "filters": [{"field": "status", "op": "eq", "value": "draft"}],
            },
        )
    assert res.status_code == 422  # mutually exclusive


def test_unknown_filter_field_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/quotes/search",
            json={"filters": [{"field": "priority", "op": "eq", "value": "high"}]},
        )
    assert res.status_code == 422  # priority is not a v1 field


def test_view_all_permission_required(app_client: TestClient, seeder: Seeder) -> None:
    """The endpoint is gated on ``view_all`` — a principal without it is forbidden."""
    org, user = _org_user(seeder, "org-a")
    with authed(app_client, user_id=user, org_id=org, roles=[]):  # no roles → no view_all
        res = app_client.post("/api/quotes/search", json={})
    assert res.status_code == 403
