"""M5.2 — Quote Checkout → Order (PO only).

Drives the thread's priced quote through the token-authenticated buyer checkout
and asserts the terminal Order/OrderLine records: prices are **re-derived
server-side** (client money is never trusted), money is **integer minor units +
currency**, ``source=buyer_portal``, the PO persists, VAT is resolved by
``app.vat_service`` (domestic / §13b reverse-charge / §19), and the shop
notification fires. Real RLS-bound Postgres through the API.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, Order, OrderLine, Quote
from app.vat_service import VIESClient, ViesResult, get_vies_client
from tests.conftest import Seeder
from tests.test_buyer_portal_m51 import _as_admin, _mint, _org_admin, _priced_quote


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _StubVies:
    def __init__(self, *, valid: bool = True) -> None:
        self._valid = valid
        self.calls: list[str] = []

    async def check(self, ust_id_nr: str) -> ViesResult:
        self.calls.append(ust_id_nr)
        return ViesResult(valid=self._valid, checked_at=datetime.now(UTC), name="ACME GmbH")


def _override_vies(app_client: TestClient, stub: VIESClient) -> None:
    cast(FastAPI, app_client.app).dependency_overrides[get_vies_client] = lambda: stub


def _clear_vies(app_client: TestClient) -> None:
    cast(FastAPI, app_client.app).dependency_overrides.pop(get_vies_client, None)


def _portal(app_client: TestClient, token: str) -> dict[str, Any]:
    res = app_client.get(f"/api/public/quotes/{token}")
    assert res.status_code == 200, res.text
    return cast(dict[str, Any], res.json())


def _first_line_ids(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract the checkout-relevant IDs from the first priced line item."""
    item = payload["line_items"][0]
    brk = item["breaks"][0]
    return {
        "quote_item_id": item["quote_item_id"],
        "quantity": brk["quantity"],
        "expedite_id": brk["expedites"][0]["id"] if brk["expedites"] else None,
        "required_add_on": next(a["id"] for a in item["add_ons"] if a["is_required"]),
        "optional_add_on": next(a["id"] for a in item["add_ons"] if not a["is_required"]),
    }


def _count(seeder: Seeder, model: Any, **where: Any) -> int:
    async def _run() -> int:
        async with AsyncSession(seeder._engine) as session:
            stmt = select(func.count()).select_from(model)
            for col, val in where.items():
                stmt = stmt.where(getattr(model, col) == val)
            return int((await session.execute(stmt)).scalar_one())

    return seeder._loop.run_until_complete(_run())


# --------------------------------------------------------------------------- #
# Happy path — domestic DE, PO only
# --------------------------------------------------------------------------- #
def test_checkout_creates_order_with_correct_totals(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "checkout-de")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    res = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [{"quote_item_id": ids["quote_item_id"], "quantity": ids["quantity"]}],
            "po_number": "PO-4711",
            "company_name": "Muster GmbH",
            "billing_address": "Musterstr. 1\n10115 Berlin",
            "shipping_method": "bill_at_shipment",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()

    # net = base 200,00 € + required add-on 25,00 € = 225,00 €; 19% MwSt.
    assert body["net_minor"] == 22500
    assert body["vat_minor"] == 4275
    assert body["gross_minor"] == 26775
    assert body["gross_minor"] == body["net_minor"] + body["vat_minor"]
    assert body["currency"] == "EUR"
    assert body["vat_rate_pct"] == "19"
    assert body["reverse_charge"] is False
    assert body["po_number"] == "PO-4711"
    assert body["order_number"]
    # money is integer minor units
    assert isinstance(body["net_minor"], int) and isinstance(body["gross_minor"], int)


def test_checkout_persists_order_and_orderline(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "checkout-persist")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    body = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [{"quote_item_id": ids["quote_item_id"], "quantity": ids["quantity"]}],
            "po_number": "PO-1",
            "shipping_method": "no_shipping_fees",
        },
    ).json()
    order_id = uuid.UUID(body["order_id"])

    async def _load() -> tuple[Order, list[OrderLine]]:
        async with AsyncSession(seeder._engine) as session:
            order = await session.get(Order, order_id)
            assert order is not None
            lines = list(
                (
                    await session.execute(select(OrderLine).where(OrderLine.order_id == order_id))
                ).scalars()
            )
            return order, lines

    order, lines = seeder._loop.run_until_complete(_load())
    assert order.source.value == "buyer_portal"
    assert order.quote_id == uuid.UUID(qid)
    assert order.po_number == "PO-1"
    assert order.net_minor == 22500
    assert order.currency == "EUR"
    assert len(lines) == 1
    line = lines[0]
    assert line.quantity == ids["quantity"]
    assert line.total_price_minor == 22500  # 200 base + 25 required add-on
    assert line.unit_price_minor == 20000
    assert line.lead_time_days == 10  # the line's standard lead time
    assert line.ships_on is not None


def test_checkout_includes_expedite_and_optional_add_on(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "checkout-expedite")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    body = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [
                {
                    "quote_item_id": ids["quote_item_id"],
                    "quantity": ids["quantity"],
                    "expedite_option_id": ids["expedite_id"],
                    "add_on_ids": [ids["optional_add_on"]],
                }
            ],
            "po_number": "PO-EXP",
            "shipping_method": "use_my_shipping_account",
        },
    ).json()
    # expedited unit 220,00 € + required 25,00 € + optional 15,00 € = 260,00 € net
    assert body["net_minor"] == 26000
    assert body["vat_minor"] == 4940  # 19%
    assert body["gross_minor"] == 30940
    assert body["lines"][0]["expedites_fee_minor"] == 2000  # 20,00 € surcharge


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_checkout_requires_at_least_one_line(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "checkout-empty")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)

    res = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={"selections": [], "po_number": "PO-0", "shipping_method": "no_shipping_fees"},
    )
    assert res.status_code == 422, res.text


def test_checkout_rejects_unknown_quantity(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "checkout-badqty")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    res = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [{"quote_item_id": ids["quote_item_id"], "quantity": 9999}],
            "po_number": "PO-X",
            "shipping_method": "no_shipping_fees",
        },
    )
    assert res.status_code == 422, res.text


def test_checkout_blocked_on_soft_expired_quote(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "checkout-expired")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    async def _expire() -> None:
        async with AsyncSession(seeder._engine) as session, session.begin():
            quote = await session.get(Quote, uuid.UUID(qid))
            assert quote is not None
            quote.expiration_date = datetime.now(UTC) - timedelta(days=1)

    seeder._loop.run_until_complete(_expire())
    res = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [{"quote_item_id": ids["quote_item_id"], "quantity": ids["quantity"]}],
            "po_number": "PO-LATE",
            "shipping_method": "no_shipping_fees",
        },
    )
    assert res.status_code == 409, res.text


def test_checkout_rejects_bad_token(app_client: TestClient) -> None:
    res = app_client.post(
        "/api/public/quotes/not-a-real-token/checkout",
        json={"selections": [], "po_number": "X", "shipping_method": "no_shipping_fees"},
    )
    assert res.status_code == 401, res.text


# --------------------------------------------------------------------------- #
# Notification
# --------------------------------------------------------------------------- #
def test_checkout_fires_shop_notification(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "checkout-notify")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    before = _count(seeder, Notification, org_id=org, kind="order_placed")
    app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [{"quote_item_id": ids["quote_item_id"], "quantity": ids["quantity"]}],
            "po_number": "PO-N",
            "shipping_method": "no_shipping_fees",
        },
    )
    after = _count(seeder, Notification, org_id=org, kind="order_placed")
    assert after > before  # the admin (shop) is notified


# --------------------------------------------------------------------------- #
# VAT posture — reverse charge / Kleinunternehmer / CH
# --------------------------------------------------------------------------- #
def test_checkout_eu_reverse_charge(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "checkout-rc")

    async def _set_shop_vat_id() -> None:
        from app.models import Organization

        async with AsyncSession(seeder._engine) as session, session.begin():
            shop = await session.get(Organization, org)
            assert shop is not None
            shop.ust_id_nr = "DE999999999"

    seeder._loop.run_until_complete(_set_shop_vat_id())

    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    _override_vies(app_client, _StubVies(valid=True))
    try:
        body = app_client.post(
            f"/api/public/quotes/{token}/checkout",
            json={
                "selections": [
                    {"quote_item_id": ids["quote_item_id"], "quantity": ids["quantity"]}
                ],
                "po_number": "PO-RC",
                "buyer_ust_id_nr": "ATU12345678",
                "shipping_method": "no_shipping_fees",
            },
        ).json()
    finally:
        _clear_vies(app_client)

    assert body["reverse_charge"] is True
    assert body["vat_minor"] == 0
    assert body["net_minor"] == 22500
    assert body["gross_minor"] == 22500
    assert body["tax_note"] == "Steuerschuldnerschaft des Leistungsempfängers"

    async def _load_order() -> Order:
        async with AsyncSession(seeder._engine) as session:
            order = (
                await session.execute(select(Order).where(Order.quote_id == uuid.UUID(qid)))
            ).scalar_one()
            return order

    order = seeder._loop.run_until_complete(_load_order())
    assert order.supplier_ust_id_nr == "DE999999999"
    assert order.buyer_ust_id_nr == "ATU12345678"
    assert order.vies_valid is True
    assert order.vies_checked_at is not None


def test_checkout_invalid_vies_falls_back_to_vat(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "checkout-badvies")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    _override_vies(app_client, _StubVies(valid=False))
    try:
        body = app_client.post(
            f"/api/public/quotes/{token}/checkout",
            json={
                "selections": [
                    {"quote_item_id": ids["quote_item_id"], "quantity": ids["quantity"]}
                ],
                "po_number": "PO-BV",
                "buyer_ust_id_nr": "ATU12345678",
                "shipping_method": "no_shipping_fees",
            },
        ).json()
    finally:
        _clear_vies(app_client)

    assert body["reverse_charge"] is False
    assert body["vat_minor"] == 4275  # 19% charged — fail-safe


def test_checkout_ch_charges_mwst_and_currency(seeder: Seeder, app_client: TestClient) -> None:
    org = seeder.org("checkout-ch", country="CH", currency="CHF")
    user = seeder.user("admin@checkout-ch.example")
    from app.models import MembershipRole

    seeder.membership(user, org, [MembershipRole.admin])
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    ids = _first_line_ids(_portal(app_client, token))

    body = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [{"quote_item_id": ids["quote_item_id"], "quantity": ids["quantity"]}],
            "po_number": "PO-CH",
            "shipping_method": "no_shipping_fees",
        },
    ).json()
    assert body["currency"] == "CHF"
    assert body["vat_rate_pct"] == "8.1"
    # 225,00 CHF at 8.1% = 18.225 -> 18,23 CHF
    assert body["net_minor"] == 22500
    assert body["vat_minor"] == 1823
    assert body["gross_minor"] == 24323
