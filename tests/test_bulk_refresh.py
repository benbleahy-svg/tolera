"""M5.0 — Bulk Refresh Pricing (``POST /api/quotes/bulk-refresh-pricing``).

The batch action re-prices a quotes-list multi-selection by looping M1.10's
single-quote engine, **preserving every ``manual_*``** (DECISIONS 2026-07-09). The
core assertion mirrors ``test_refresh_pricing_preserves_manual_overrides`` but drives
it over several quotes at once. Runs against a real RLS-bound Postgres.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

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


def _pricing(client: TestClient, component_id: str) -> dict[str, Any]:
    res = client.get(f"/api/components/{component_id}/pricing")
    assert res.status_code == 200, res.text
    return cast("dict[str, Any]", res.json())


def _total(pricing: dict[str, Any], qty: int) -> dict[str, Any]:
    return next(t for t in pricing["totals"] if t["quantity"] == qty)


def _item_cell(pricing: dict[str, Any], name: str, qty: int) -> dict[str, Any]:
    item = next(i for i in pricing["pricing_items"] if i["name"] == name)
    return next(c for c in item["cells"] if c["quantity"] == qty)


def _add_manual_op(client: TestClient, component_id: str, name: str, cost: str) -> None:
    created = client.post(f"/api/components/{component_id}/operations", json={"name": name})
    assert created.status_code == 201, created.text
    op = next(o for o in created.json()["operations"] if o["name"] == name)
    res = client.patch(f"/api/operations/{op['id']}/cells/1", json={"manual_cost": cost})
    assert res.status_code == 200, res.text


def _quote_with_factory_markup(client: TestClient, cost: str) -> tuple[str, str]:
    """A quote whose single line item has the org's factory markup attached + a
    manual op cost. Returns (quote_id, component_id)."""
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    component = str(item["root_component_id"])
    _add_manual_op(client, component, "CNC", cost)
    return qid, component


def _bulk(client: TestClient, quote_ids: list[str]) -> Any:
    return client.post("/api/quotes/bulk-refresh-pricing", json={"quote_ids": quote_ids})


def test_bulk_refresh_preserves_manual_overrides(app_client: TestClient, seeder: Seeder) -> None:
    """The M5.0 headline: bulk re-price re-snapshots the factory def yet keeps every
    estimator override — over a multi-select, exactly as the single refresh does."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/pricing-item-defs",
            json={"name": "General Markup", "calc_type": "markup", "default_pct": "10"},
        )
        def_id = res.json()["id"]

        q1, c1 = _quote_with_factory_markup(app_client, "100.0000")
        q2, c2 = _quote_with_factory_markup(app_client, "200.0000")

        # Override the markup on quote 1 only; quote 2 keeps the calc side.
        item1 = _pricing(app_client, c1)["pricing_items"][0]["id"]
        r = app_client.patch(f"/api/pricing-items/{item1}/cells/1", json={"manual_pct": "50"})
        assert r.status_code == 200, r.text

        # Edit the def — existing drafts stay frozen until a refresh.
        app_client.patch(f"/api/pricing-item-defs/{def_id}", json={"default_pct": "30"})

        res = _bulk(app_client, [q1, q2])
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["mode"] == "sync"
        assert body["refreshed_quotes"] == 2
        assert body["refreshed_items"] == 2
        assert body["skipped"] == 0

        # Quote 1: calc side re-snapshotted to 30%, but the 50% override still wins.
        cell1 = _item_cell(_pricing(app_client, c1), "General Markup", 1)
        assert Decimal(cell1["calc_pct"]) == Decimal("30.0000")
        assert Decimal(cell1["manual_pct"]) == Decimal("50.0000")
        assert Decimal(_total(_pricing(app_client, c1), 1)["total_price"]) == Decimal("150.00")
        # Quote 2: no override → picks up the new 30% (200 → 260).
        assert Decimal(_total(_pricing(app_client, c2), 1)["total_price"]) == Decimal("260.00")


def test_bulk_refresh_counts_and_skips_missing(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        q1, _ = _quote_with_factory_markup(app_client, "100.0000")
        q2, _ = _quote_with_factory_markup(app_client, "100.0000")
        ghost = str(uuid.uuid4())
        res = _bulk(app_client, [q1, q2, ghost])
    body = res.json()
    assert body["refreshed_quotes"] == 2
    assert body["skipped"] == 1


def test_bulk_refresh_dedupes_ids(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        q1, _ = _quote_with_factory_markup(app_client, "100.0000")
        res = _bulk(app_client, [q1, q1, q1])
    body = res.json()
    assert body["refreshed_quotes"] == 1


def test_bulk_refresh_empty_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = _bulk(app_client, [])
    assert res.status_code == 422


def test_bulk_refresh_requires_quote_edit(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    viewer = seeder.user("viewer@org-a.example")
    seeder.membership(viewer, org, VIEWER)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        q1, _ = _quote_with_factory_markup(app_client, "100.0000")
    with authed(app_client, user_id=viewer, org_id=org, roles=VIEWER):
        res = _bulk(app_client, [q1])
    assert res.status_code == 403


def test_bulk_refresh_org_scoped(app_client: TestClient, seeder: Seeder) -> None:
    """A quote from another org is invisible → skipped, and its pricing is provably
    left untouched (not just an unchanged skip counter)."""
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b, admin_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        # Org A: a factory markup at 10%, then bump the def to 30% so a refresh WOULD
        # move the total (100 → 130). Capture the current (frozen) total = 110.
        res = app_client.post(
            "/api/pricing-item-defs",
            json={"name": "General Markup", "calc_type": "markup", "default_pct": "10"},
        )
        def_id = res.json()["id"]
        q_a, c_a = _quote_with_factory_markup(app_client, "100.0000")
        app_client.patch(f"/api/pricing-item-defs/{def_id}", json={"default_pct": "30"})
        before = Decimal(_total(_pricing(app_client, c_a), 1)["total_price"])
        assert before == Decimal("110.00")  # frozen — def edit alone never reprices

    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        res = _bulk(app_client, [q_a])
    body = res.json()
    assert body["refreshed_quotes"] == 0
    assert body["skipped"] == 1

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        after = Decimal(_total(_pricing(app_client, c_a), 1)["total_price"])
    assert after == before  # org B's bulk refresh never touched org A's quote


def test_bulk_refresh_isolates_a_failing_quote(
    app_client: TestClient, seeder: Seeder, monkeypatch: Any
) -> None:
    """One quote that errors mid-refresh is counted ``failed`` and rolled back (its
    SAVEPOINT), while the other quotes in the same batch still commit."""
    import app.pricing as pricing

    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/pricing-item-defs",
            json={"name": "General Markup", "calc_type": "markup", "default_pct": "10"},
        )
        def_id = res.json()["id"]
        q_ok, c_ok = _quote_with_factory_markup(app_client, "100.0000")
        q_bad, c_bad = _quote_with_factory_markup(app_client, "100.0000")
        app_client.patch(f"/api/pricing-item-defs/{def_id}", json={"default_pct": "30"})

        real = pricing.refresh_quote_pricing

        async def flaky(session: Any, org_id: Any, quote_id: Any) -> Any:
            if str(quote_id) == q_bad:
                raise RuntimeError("boom")
            return await real(session, org_id, quote_id)

        monkeypatch.setattr(pricing, "refresh_quote_pricing", flaky)
        body = _bulk(app_client, [q_ok, q_bad]).json()
        monkeypatch.undo()

        assert body["refreshed_quotes"] == 1
        assert body["failed"] == 1
        # The good quote committed at the new 30% (100 → 130); the bad one rolled
        # back its savepoint and stays frozen at 10% (110).
        assert Decimal(_total(_pricing(app_client, c_ok), 1)["total_price"]) == Decimal("130.00")
        assert Decimal(_total(_pricing(app_client, c_bad), 1)["total_price"]) == Decimal("110.00")


def test_bulk_refresh_broker_down_is_503(
    app_client: TestClient, seeder: Seeder, monkeypatch: Any
) -> None:
    """A large selection when the broker is down must fail loudly (503), not a false
    202 "queued" — otherwise the client drops the selection and nothing runs."""
    import app.bulk_refresh as bulk

    monkeypatch.setattr(bulk, "enqueue_bulk_refresh", lambda *a, **k: None)
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        quotes = [_quote_with_factory_markup(app_client, "100.0000") for _ in range(11)]
        res = _bulk(app_client, [q for q, _ in quotes])
    assert res.status_code == 503
    assert res.json()["code"] == "bulk_refresh_unavailable"


def test_bulk_refresh_async_over_threshold(
    app_client: TestClient, seeder: Seeder, eager_celery: None
) -> None:
    """Above the sync cap the request hands off to Celery (202 + task id); the eager
    task still applies the refresh end-to-end."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/pricing-item-defs",
            json={"name": "General Markup", "calc_type": "markup", "default_pct": "10"},
        )
        def_id = res.json()["id"]
        quotes = [_quote_with_factory_markup(app_client, "100.0000") for _ in range(11)]
        app_client.patch(f"/api/pricing-item-defs/{def_id}", json={"default_pct": "30"})

        res = _bulk(app_client, [q for q, _ in quotes])
        assert res.status_code == 202, res.text
        body = res.json()
        assert body["mode"] == "async"
        assert body["quote_count"] == 11
        assert body["task_id"] is not None
        # The eager task ran: every quote picked up the 30% def (100 → 130).
        first_component = quotes[0][1]
        assert Decimal(_total(_pricing(app_client, first_component), 1)["total_price"]) == Decimal(
            "130.00"
        )
