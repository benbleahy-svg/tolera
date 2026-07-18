"""M5.6 — Orders tab (list + detail + ERP-push stub), spec ``#orderslist``.

Exercises the read surface against a real RLS-bound Postgres: the list renders the
spec columns (Order Total is **net**, Source chip, Parts count, earliest-ship
Expected Ship Date), the toolbar filters/searches narrow rows, the Edit-order
affordance is gated on ``facilitate_order_updates AND shipped_at IS NULL``, there is
**no create-order affordance**, the detail view returns the persisted §14 tax
breakdown + lines, a cross-org id is invisible, and the ERP push is a stub.

Most rows are planted bare via ``seeder.order`` (varied source / account / date /
shipment); one **real buyer-portal checkout** produces an order with a real line so
the Parts + Expected-Ship + detail-tax columns are exercised end-to-end.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderSource, Organization
from tests.conftest import Seeder, authed
from tests.test_buyer_portal_m51 import (
    ADMIN,
    _as_admin,
    _mint,
    _org_admin,
    _priced_quote,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _portal(app_client: TestClient, token: str) -> dict[str, Any]:
    return dict(app_client.get(f"/api/public/quotes/{token}").json())


def _checkout_order(
    seeder: Seeder, app_client: TestClient, org: uuid.UUID, user: uuid.UUID, *, po: str = "PO-500"
) -> dict[str, Any]:
    """Drive a real domestic buyer-portal checkout → Order (with one real line, so
    Parts count / Expected Ship Date / detail lines are genuine). Returns the
    checkout response body (``order_id``, ``order_number``, ``net_minor`` …)."""
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    portal = _portal(app_client, token)
    item = portal["line_items"][0]
    qty = item["breaks"][0]["quantity"]
    res = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [{"quote_item_id": item["quote_item_id"], "quantity": qty}],
            "po_number": po,
            "company_name": "Muster GmbH",
            "billing_address": "Musterstr. 1\n10115 Berlin",
            "shipping_method": "bill_at_shipment",
        },
    )
    assert res.status_code == 201, res.text
    return dict(res.json())


def _enable_facilitate(seeder: Seeder, org_id: uuid.UUID) -> None:
    """Flip the org's Facilitate-Order-Updates opt-in (the M5.8 settings surface)."""

    async def _run() -> None:
        async with AsyncSession(seeder._engine) as session, session.begin():
            org = await session.get(Organization, org_id)
            assert org is not None
            org.facilitate_order_updates = True

    seeder._loop.run_until_complete(_run())


def _set_shipped(seeder: Seeder, order_id: uuid.UUID, when: datetime) -> None:
    async def _run() -> None:
        async with AsyncSession(seeder._engine) as session, session.begin():
            order = await session.get(Order, order_id)
            assert order is not None
            order.shipped_at = when

    seeder._loop.run_until_complete(_run())


def _search(client: TestClient, **body: Any) -> dict[str, Any]:
    res = client.post("/api/orders/search", json=body)
    assert res.status_code == 200, res.text
    return dict(res.json())


# --------------------------------------------------------------------------- #
# Columns (real checkout order)
# --------------------------------------------------------------------------- #
def test_search_renders_spec_columns(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-cols")
    body = _checkout_order(seeder, app_client, org, user, po="PO-4711")

    with _as_admin(app_client, org, user) as client:
        listed = _search(client)

    assert listed["total"] == 1
    (row,) = listed["rows"]
    assert row["id"] == body["order_id"]
    assert row["number"] == body["order_number"]
    assert row["po_number"] == "PO-4711"
    assert row["source"] == "buyer_portal"
    # Order Total is NET (excl. VAT) — a direct read of persisted net_minor.
    assert row["net_minor"] == body["net_minor"]
    assert isinstance(row["net_minor"], int)
    assert row["currency"] == "EUR"
    # One ordered line → Parts = 1; the line carries a ships_on → Expected Ship set.
    assert row["parts_count"] == 1
    assert row["expected_ship_date"] is not None
    # No shipment recorded; opt-in off by default → Edit-order not offered.
    assert row["shipped_at"] is None
    assert row["can_edit"] is False
    # The computed system views ride along for the sidebar/tabs.
    assert [v["key"] for v in listed["views"]] == [
        "all-orders",
        "buyer-portal",
        "facilitated",
        "awaiting-shipment",
    ]


# --------------------------------------------------------------------------- #
# Filters / search / views (bare seeded orders)
# --------------------------------------------------------------------------- #
def _seed_two_accounts_orders(seeder: Seeder, org: uuid.UUID) -> dict[str, uuid.UUID]:
    acc_a = seeder.account(org, "Alpha GmbH")
    acc_b = seeder.account(org, "Beta AG")
    q = seeder.quote(org, "Q-1")
    now = datetime.now(UTC)
    o_a = seeder.order(
        org,
        q,
        "O-A",
        source=OrderSource.buyer_portal,
        account_id=acc_a,
        po_number="PO-AAA",
        created_at=now - timedelta(days=10),
    )
    o_b = seeder.order(
        org,
        q,
        "O-B",
        source=OrderSource.facilitated,
        account_id=acc_b,
        po_number="PO-BBB",
        created_at=now - timedelta(days=1),
    )
    return {"acc_a": acc_a, "acc_b": acc_b, "o_a": o_a, "o_b": o_b}


def test_account_filter_narrows(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-acct")
    ids = _seed_two_accounts_orders(seeder, org)
    with _as_admin(app_client, org, user) as client:
        listed = _search(
            client, filters=[{"field": "account_id", "op": "eq", "value": str(ids["acc_a"])}]
        )
    assert {r["number"] for r in listed["rows"]} == {"O-A"}
    assert listed["rows"][0]["account_name"] == "Alpha GmbH"


def test_source_filter_narrows(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-source")
    _seed_two_accounts_orders(seeder, org)
    with _as_admin(app_client, org, user) as client:
        facilitated = _search(
            client, filters=[{"field": "source", "op": "eq", "value": "facilitated"}]
        )
    assert {r["number"] for r in facilitated["rows"]} == {"O-B"}


def test_date_placed_range_filter(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-date")
    _seed_two_accounts_orders(seeder, org)
    cutoff = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    with _as_admin(app_client, org, user) as client:
        recent = _search(client, filters=[{"field": "created_at", "op": "gte", "value": cutoff}])
    # Only O-B (placed 1 day ago) is on/after the cutoff; O-A (10 days) is excluded.
    assert {r["number"] for r in recent["rows"]} == {"O-B"}


def test_free_text_search(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-search")
    _seed_two_accounts_orders(seeder, org)
    with _as_admin(app_client, org, user) as client:
        by_po = _search(client, search="PO-AAA")
        by_account = _search(client, search="beta")  # case-insensitive, account name
        by_number = _search(client, search="O-B")
    assert {r["number"] for r in by_po["rows"]} == {"O-A"}
    assert {r["number"] for r in by_account["rows"]} == {"O-B"}
    assert {r["number"] for r in by_number["rows"]} == {"O-B"}


def test_system_views(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-views")
    q = seeder.quote(org, "Q-1")
    portal = seeder.order(org, q, "O-P", source=OrderSource.buyer_portal)
    facil = seeder.order(org, q, "O-F", source=OrderSource.facilitated)
    _set_shipped(seeder, facil, datetime.now(UTC))  # shipped → not awaiting
    with _as_admin(app_client, org, user) as client:
        assert {r["number"] for r in _search(client, system_view="buyer-portal")["rows"]} == {"O-P"}
        assert {r["number"] for r in _search(client, system_view="facilitated")["rows"]} == {"O-F"}
        assert {r["number"] for r in _search(client, system_view="awaiting-shipment")["rows"]} == {
            "O-P"
        }
        assert {r["number"] for r in _search(client, system_view="all-orders")["rows"]} == {
            "O-P",
            "O-F",
        }
    # portal order is unused as a variable beyond seeding
    assert portal != facil


def test_unknown_system_view_is_422(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-badview")
    with _as_admin(app_client, org, user) as client:
        res = client.post("/api/orders/search", json={"system_view": "nope"})
    assert res.status_code == 422


def test_filter_grammar_rejects_bad_operator(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-badop")
    with _as_admin(app_client, org, user) as client:
        # source only supports eq/in — gte is a 422, never a 500.
        res = client.post(
            "/api/orders/search",
            json={"filters": [{"field": "source", "op": "gte", "value": "facilitated"}]},
        )
    assert res.status_code == 422


def test_system_view_and_filters_are_mutually_exclusive(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "orders-excl")
    with _as_admin(app_client, org, user) as client:
        res = client.post(
            "/api/orders/search",
            json={
                "system_view": "all-orders",
                "filters": [{"field": "source", "op": "eq", "value": "facilitated"}],
            },
        )
    assert res.status_code == 422


# --------------------------------------------------------------------------- #
# Edit-order gating
# --------------------------------------------------------------------------- #
def test_edit_order_gating(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-edit")
    q = seeder.quote(org, "Q-1")
    oid = seeder.order(org, q, "O-1", source=OrderSource.facilitated)

    with _as_admin(app_client, org, user) as client:
        # Opt-in off (default) → not editable.
        row = _search(client)["rows"][0]
        assert row["can_edit"] is False

    _enable_facilitate(seeder, org)
    with _as_admin(app_client, org, user) as client:
        row = _search(client)["rows"][0]
        assert row["can_edit"] is True  # flag on + no shipment
        assert client.get(f"/api/orders/{oid}").json()["can_edit"] is True

    _set_shipped(seeder, oid, datetime.now(UTC))
    with _as_admin(app_client, org, user) as client:
        row = _search(client)["rows"][0]
        # Shipment recorded → not editable even with the flag on.
        assert row["can_edit"] is False
        assert client.get(f"/api/orders/{oid}").json()["can_edit"] is False


# --------------------------------------------------------------------------- #
# No create affordance
# --------------------------------------------------------------------------- #
def test_no_create_order_endpoint(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-nocreate")
    with _as_admin(app_client, org, user) as client:
        res = client.post("/api/orders", json={})
    # Orders are only created by checkout/facilitate — there is no POST /api/orders.
    assert res.status_code in (404, 405)


# --------------------------------------------------------------------------- #
# Detail
# --------------------------------------------------------------------------- #
def test_order_detail_returns_lines_and_tax(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-detail")
    body = _checkout_order(seeder, app_client, org, user, po="PO-9")

    with _as_admin(app_client, org, user) as client:
        detail = client.get(f"/api/orders/{body['order_id']}").json()

    assert detail["number"] == body["order_number"]
    assert detail["source"] == "buyer_portal"
    assert detail["po_number"] == "PO-9"
    assert detail["net_minor"] == body["net_minor"]
    assert detail["gross_minor"] == body["gross_minor"]
    assert detail["gross_minor"] == detail["net_minor"] + detail["vat_minor"]
    assert detail["currency"] == "EUR"
    assert len(detail["lines"]) == 1
    line = detail["lines"][0]
    assert line["quantity"] >= 1
    assert isinstance(line["total_price_minor"], int)
    # Each line carries its quote position + an (optional) part label so multiple
    # lines are distinguishable (bare checkout part → label may be null).
    assert line["position"] >= 1
    assert "part_label" in line
    assert detail["expected_ship_date"] is not None


def test_detail_missing_is_404(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-detail-404")
    with _as_admin(app_client, org, user) as client:
        res = client.get(f"/api/orders/{uuid.uuid4()}")
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
# Tenancy — cross-org isolation
# --------------------------------------------------------------------------- #
def test_cross_org_isolation(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_admin(seeder, "orders-iso-a")
    org_b, user_b = _org_admin(seeder, "orders-iso-b")
    q_a = seeder.quote(org_a, "Q-A")
    oid_a = seeder.order(org_a, q_a, "O-A")

    # Org B cannot see Org A's order in the list or by id (RLS).
    with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
        assert app_client.post("/api/orders/search", json={}).json()["total"] == 0
        assert app_client.get(f"/api/orders/{oid_a}").status_code == 404
    # Org A sees its own order.
    with authed(app_client, user_id=user_a, org_id=org_a, roles=ADMIN):
        assert app_client.post("/api/orders/search", json={}).json()["total"] == 1


# --------------------------------------------------------------------------- #
# ERP push — stub
# --------------------------------------------------------------------------- #
def test_erp_push_is_stub_not_configured(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-erp")
    q = seeder.quote(org, "Q-1")
    oid = seeder.order(org, q, "O-1")
    with _as_admin(app_client, org, user) as client:
        res = client.post(f"/api/orders/{oid}/push-to-erp")
    assert res.status_code == 200, res.text
    assert res.json() == {"order_id": str(oid), "status": "not_configured"}


def test_erp_push_missing_order_is_404(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "orders-erp-404")
    with _as_admin(app_client, org, user) as client:
        res = client.post(f"/api/orders/{uuid.uuid4()}/push-to-erp")
    assert res.status_code == 404
