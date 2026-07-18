"""M5.7 — Facilitate Order drawer (internal build + pre-ship edit + history).

Spec ``#order`` (Build Order / order-editing) + ``#shipping-options``. Exercises,
against a real RLS-bound Postgres:

* an estimator builds an Order from a quote internally (``source=facilitated``)
  with the chosen break + Ships-On;
* per-line **Discounts** (Percent) reduce and **Additional Charges** (Price) add
  to the line total, and the order net + §14 tax follow;
* a Ships-On override is respected; the default = placement + lead time;
* a pre-ship edit (PO change / add / remove line) succeeds and writes a history
  entry, and is **rejected once shipped** or when the shop has not opted in;
* the history endpoint returns the trail; cross-org ids are invisible.

The priced portion is re-derived server-side (like checkout); only the shop's
discounts/charges cross as money. Reuses the M5.1 quote-builder + M5.6 helpers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.vat_service import ViesResult, get_vies_client
from tests.conftest import Seeder
from tests.test_buyer_portal_m51 import _as_admin, _org_admin, _priced_quote
from tests.test_orders_m56 import _enable_facilitate, _set_shipped


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _quote_with_item(client: TestClient) -> tuple[str, str, int]:
    """Build the M5.1 priced quote and return (quote_id, quote_item_id, break_qty)."""
    qid, _ = _priced_quote(client)
    detail = client.get(f"/api/quotes/{qid}").json()
    item = detail["items"][0]
    return qid, str(item["id"]), int(item["quantities"][0]["quantity"])


def _price_component(client: TestClient, component_id: str) -> None:
    """Price a bare component to the same 200,00 €/ea, 10-day core as ``_priced_quote``
    (op cost 100 + 100% markup) so a second line item has an orderable break."""
    op = client.post(f"/api/components/{component_id}/operations", json={"name": "Fräsen"})
    op_id = next(o for o in op.json()["operations"] if o["name"] == "Fräsen")["id"]
    client.patch(f"/api/operations/{op_id}/cells/1", json={"manual_cost": "100.0000"})
    client.post(
        f"/api/components/{component_id}/pricing-items",
        json={
            "name": "Aufschlag",
            "calc_type": "markup",
            "category": "general",
            "default_pct": "100",
        },
    )
    client.patch(f"/api/components/{component_id}/lead-time/1", json={"manual_lead_time_days": 10})
    # Match _priced_quote's required add-on so two items net identically (200 + 25).
    client.post(
        f"/api/components/{component_id}/add-ons",
        json={"name": "Zertifikat", "default_price": "25", "is_required": True},
    )


def _quote_with_two_items(client: TestClient) -> tuple[str, str, str, int]:
    """A quote with two identically-priced line items → (quote_id, item0, item1, qty)."""
    qid, item0, qty = _quote_with_item(client)
    second = client.post(f"/api/quotes/{qid}/items").json()["items"]
    item1 = next(i for i in second if str(i["id"]) != item0)
    _price_component(client, str(item1["root_component_id"]))
    return qid, item0, str(item1["id"]), qty


def _facilitate(
    client: TestClient, qid: str, selections: list[dict[str, Any]], **order: Any
) -> Any:
    body = {"selections": selections, **order}
    return client.post(f"/api/quotes/{qid}/facilitate-order", json=body)


def _order_detail(client: TestClient, order_id: str) -> dict[str, Any]:
    res = client.get(f"/api/orders/{order_id}")
    assert res.status_code == 200, res.text
    return dict(res.json())


def _history(client: TestClient, order_id: str) -> list[dict[str, Any]]:
    res = client.get(f"/api/orders/{order_id}/history")
    assert res.status_code == 200, res.text
    return list(res.json())


class _StubVIES:
    """A VIES double (satisfies the ``VIESClient`` protocol) with a fixed verdict."""

    def __init__(self, valid: bool) -> None:
        self._valid = valid

    async def check(self, ust_id_nr: str) -> ViesResult:
        return ViesResult(valid=self._valid, checked_at=datetime(2026, 7, 18, tzinfo=UTC))


# --------------------------------------------------------------------------- #
# Build Order (create)
# --------------------------------------------------------------------------- #
def test_facilitate_creates_facilitated_order_with_line_and_ships_on(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "fac-create")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, qty = _quote_with_item(client)
        res = _facilitate(
            client,
            qid,
            [{"quote_item_id": item_id, "quantity": qty}],
            po_number="PO-77",
            shipping_method="bill_at_shipment",
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["source"] == "facilitated"
        assert body["po_number"] == "PO-77"

        detail = _order_detail(client, body["order_id"])
        assert detail["source"] == "facilitated"
        assert len(detail["lines"]) == 1
        line = detail["lines"][0]
        assert line["quantity"] == qty
        # Ships-On defaults to placement + the break's lead time (10 calendar days).
        assert line["lead_time_days"] == 10
        expected = date.today() + timedelta(days=10)
        assert line["ships_on"] == expected.isoformat()


def test_facilitate_ships_on_override_is_respected(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "fac-ships")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, qty = _quote_with_item(client)
        res = _facilitate(
            client,
            qid,
            [{"quote_item_id": item_id, "quantity": qty, "ships_on": "2026-12-24"}],
        )
        assert res.status_code == 201, res.text
        line = _order_detail(client, res.json()["order_id"])["lines"][0]
        assert line["ships_on"] == "2026-12-24"


def test_facilitate_discount_reduces_line_and_order_net(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "fac-disc")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, qty = _quote_with_item(client)
        # Baseline (no adjustment) to learn the line's base net.
        base = _order_detail(
            client,
            _facilitate(client, qid, [{"quote_item_id": item_id, "quantity": qty}]).json()[
                "order_id"
            ],
        )
        base_line_minor = base["lines"][0]["total_price_minor"]

        # A fresh order with a 10% discount on the same line.
        res = _facilitate(
            client,
            qid,
            [
                {
                    "quote_item_id": item_id,
                    "quantity": qty,
                    "discounts": [{"label": "Kundentreue", "percent": "10"}],
                }
            ],
        )
        assert res.status_code == 201, res.text
        detail = _order_detail(client, res.json()["order_id"])
        expected_discount = round(base_line_minor * 0.10)
        assert detail["lines"][0]["total_price_minor"] == base_line_minor - expected_discount
        # Order net follows the discounted line; gross = net + vat (DE 19%).
        assert detail["net_minor"] == base_line_minor - expected_discount
        assert detail["gross_minor"] == detail["net_minor"] + detail["vat_minor"]


def test_facilitate_additional_charge_adds_to_line_and_net(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "fac-charge")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, qty = _quote_with_item(client)
        base = _order_detail(
            client,
            _facilitate(client, qid, [{"quote_item_id": item_id, "quantity": qty}]).json()[
                "order_id"
            ],
        )
        base_line_minor = base["lines"][0]["total_price_minor"]

        res = _facilitate(
            client,
            qid,
            [
                {
                    "quote_item_id": item_id,
                    "quantity": qty,
                    "additional_charges": [{"label": "Tooling (Required)", "amount": "500"}],
                }
            ],
        )
        assert res.status_code == 201, res.text
        detail = _order_detail(client, res.json()["order_id"])
        assert detail["lines"][0]["total_price_minor"] == base_line_minor + 50000
        assert detail["net_minor"] == base_line_minor + 50000


def test_facilitate_rejects_over_100pct_discount(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "fac-overdisc")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, qty = _quote_with_item(client)
        res = _facilitate(
            client,
            qid,
            [
                {
                    "quote_item_id": item_id,
                    "quantity": qty,
                    "discounts": [
                        {"label": "A", "percent": "60"},
                        {"label": "B", "percent": "60"},
                    ],
                }
            ],
        )
        assert res.status_code == 422, res.text


def test_facilitate_missing_quote_is_404(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "fac-404")
    with _as_admin(app_client, org, user) as client:
        res = _facilitate(
            client,
            str(uuid.uuid4()),
            [{"quote_item_id": str(uuid.uuid4()), "quantity": 1}],
        )
        assert res.status_code == 404, res.text


def test_facilitate_cross_org_quote_is_invisible(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_admin(seeder, "fac-orga")
    org_b, user_b = _org_admin(seeder, "fac-orgb")
    with _as_admin(app_client, org_a, user_a) as client:
        qid, item_id, qty = _quote_with_item(client)
    # Org B cannot facilitate org A's quote (RLS → 404, not another org's order).
    with _as_admin(app_client, org_b, user_b) as client:
        res = _facilitate(client, qid, [{"quote_item_id": item_id, "quantity": qty}])
        assert res.status_code == 404, res.text


def test_facilitate_reverse_charge_with_vies_valid_id(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "fac-rc")
    _set_shop_ust(seeder, org, "DE111111125")
    app = cast(FastAPI, app_client.app)
    app.dependency_overrides[get_vies_client] = lambda: _StubVIES(True)
    try:
        with _as_admin(app_client, org, user) as client:
            qid, item_id, qty = _quote_with_item(client)
            res = _facilitate(
                client,
                qid,
                [{"quote_item_id": item_id, "quantity": qty}],
                buyer_ust_id_nr="FR12345678901",
            )
            assert res.status_code == 201, res.text
            detail = _order_detail(client, res.json()["order_id"])
            assert detail["reverse_charge"] is True
            assert detail["vat_minor"] == 0
            assert detail["gross_minor"] == detail["net_minor"]
    finally:
        app.dependency_overrides.pop(get_vies_client, None)


# --------------------------------------------------------------------------- #
# Pre-ship edit + history
# --------------------------------------------------------------------------- #
def _built_order(
    seeder: Seeder, app_client: TestClient, slug: str
) -> tuple[uuid.UUID, uuid.UUID, str, str, str]:
    """A facilitated order on a fresh org with Facilitate-Order-Updates enabled.
    Returns (org, user, order_id, quote_id, quote_item_id)."""
    org, user = _org_admin(seeder, slug)
    _enable_facilitate(seeder, org)
    with _as_admin(app_client, org, user) as client:
        qid, item_id, qty = _quote_with_item(client)
        order_id = _facilitate(
            client, qid, [{"quote_item_id": item_id, "quantity": qty}], po_number="PO-1"
        ).json()["order_id"]
    return org, user, order_id, qid, item_id


def test_edit_changes_po_and_writes_history(seeder: Seeder, app_client: TestClient) -> None:
    org, user, order_id, _, _ = _built_order(seeder, app_client, "edit-po")
    with _as_admin(app_client, org, user) as client:
        res = client.patch(f"/api/orders/{order_id}", json={"po_number": "PO-2"})
        assert res.status_code == 200, res.text
        assert res.json()["changes"]["po_number"] == ["PO-1", "PO-2"]

        assert _order_detail(client, order_id)["po_number"] == "PO-2"
        trail = _history(client, order_id)
        assert [e["kind"] for e in trail] == ["created", "edited"]
        assert trail[1]["changes"]["po_number"] == ["PO-1", "PO-2"]


def test_edit_add_line_recomputes_net(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "edit-add")
    _enable_facilitate(seeder, org)
    with _as_admin(app_client, org, user) as client:
        # A two-item quote; facilitate only the first, then add the second on edit.
        qid, item0, item1, qty = _quote_with_two_items(client)
        order_id = _facilitate(client, qid, [{"quote_item_id": item0, "quantity": qty}]).json()[
            "order_id"
        ]
        before = _order_detail(client, order_id)
        res = client.patch(
            f"/api/orders/{order_id}",
            json={"add_lines": [{"quote_item_id": item1, "quantity": qty}]},
        )
        assert res.status_code == 200, res.text
        assert res.json()["changes"]["lines_added"] == 1
        after = _order_detail(client, order_id)
        assert len(after["lines"]) == len(before["lines"]) + 1
        # The two items are priced identically → net doubles.
        assert after["net_minor"] == before["net_minor"] * 2


def test_edit_add_duplicate_line_item_is_rejected(seeder: Seeder, app_client: TestClient) -> None:
    # Adding a quote item already on the order must 422 (mirrors the create path's
    # one-line-per-item rule) so an edit can't bill the same item twice.
    org, user, order_id, _qid, item_id = _built_order(seeder, app_client, "edit-dup")
    with _as_admin(app_client, org, user) as client:
        res = client.patch(
            f"/api/orders/{order_id}",
            json={"add_lines": [{"quote_item_id": item_id, "quantity": 1}]},
        )
        assert res.status_code == 422, res.text


def test_edit_remove_last_line_is_rejected(seeder: Seeder, app_client: TestClient) -> None:
    org, user, order_id, _, _ = _built_order(seeder, app_client, "edit-empty")
    with _as_admin(app_client, org, user) as client:
        line_id = _order_detail(client, order_id)["lines"][0]["id"]
        res = client.patch(f"/api/orders/{order_id}", json={"remove_line_ids": [line_id]})
        assert res.status_code == 422, res.text


def test_edit_blocked_when_shipped(seeder: Seeder, app_client: TestClient) -> None:
    org, user, order_id, _, _ = _built_order(seeder, app_client, "edit-shipped")
    _set_shipped(seeder, uuid.UUID(order_id), datetime(2026, 7, 18, tzinfo=UTC))
    with _as_admin(app_client, org, user) as client:
        res = client.patch(f"/api/orders/{order_id}", json={"po_number": "PO-9"})
        assert res.status_code == 409, res.text
        assert res.json()["code"] == "order_not_editable"


def test_edit_blocked_when_facilitate_disabled(seeder: Seeder, app_client: TestClient) -> None:
    # Org WITHOUT the opt-in flag (do not enable it).
    org, user = _org_admin(seeder, "edit-off")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, qty = _quote_with_item(client)
        order_id = _facilitate(client, qid, [{"quote_item_id": item_id, "quantity": qty}]).json()[
            "order_id"
        ]
        res = client.patch(f"/api/orders/{order_id}", json={"po_number": "PO-9"})
        assert res.status_code == 409, res.text


def test_edit_notify_buyer_flag_recorded(seeder: Seeder, app_client: TestClient) -> None:
    org, user, order_id, _, _ = _built_order(seeder, app_client, "edit-notify")
    with _as_admin(app_client, org, user) as client:
        res = client.patch(
            f"/api/orders/{order_id}",
            json={"billing_address": "Neue Str. 5\n80331 München", "notify_buyer": True},
        )
        assert res.status_code == 200, res.text
        assert res.json()["buyer_notified"] is True
        assert _history(client, order_id)[1]["buyer_notified"] is True


def test_history_missing_order_is_404(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "hist-404")
    with _as_admin(app_client, org, user) as client:
        res = client.get(f"/api/orders/{uuid.uuid4()}/history")
        assert res.status_code == 404, res.text


def _set_shop_ust(seeder: Seeder, org_id: uuid.UUID, ust_id: str) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Organization

    async def _run() -> None:
        async with AsyncSession(seeder._engine) as session, session.begin():
            org = await session.get(Organization, org_id)
            assert org is not None
            org.ust_id_nr = ust_id

    seeder._loop.run_until_complete(_run())
