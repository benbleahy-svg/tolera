"""M6.7 — Würth ("Tolera Source") material adapter.

Acceptance criteria under test (build-plan/M6-differentiators-hardening.md §M6.7):

  1. the adapter returns availability + price-by-qty from the fixture;
  2. swapping the fixture for a (future) live client requires only config;
  3. timeouts/errors degrade gracefully (no broken costing);
  4. an RFQ-send through the adapter produces the documented request shape;
  5. no code path hardcodes credentials.

Two layers, the ``test_vendor_rfq_m64`` shape: pure adapter units first (no DB,
no network), then the API surface against real RLS.
"""

from __future__ import annotations

import inspect
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import MembershipRole
from app.services.suppliers import wuerth as wuerth_module
from app.services.suppliers.base import (
    AvailabilityStatus,
    SourcingRfqLine,
    SourcingRfqRequest,
    SupplierUnavailable,
)
from app.services.suppliers.wuerth import (
    FixtureWuerthClient,
    LiveWuerthClient,
    WuerthMaterialPricingAdapter,
    build_wuerth_adapter,
)
from tests.conftest import Seeder, authed
from tests.support import build_settings

ADMIN = [MembershipRole.admin]


def _adapter() -> WuerthMaterialPricingAdapter:
    return WuerthMaterialPricingAdapter(FixtureWuerthClient())


class _BoomClient:
    """A client whose every call fails — the timeout/outage path."""

    async def fetch_catalog(self) -> dict[str, Any]:
        raise TimeoutError("wuerth timed out")

    async def send_rfq(self, request: dict[str, Any]) -> dict[str, Any]:
        raise TimeoutError("wuerth timed out")


# --------------------------------------------------------------------------- #
# 1 · Availability + price-by-quantity (pure)
# --------------------------------------------------------------------------- #
async def test_price_break_resolves_to_the_highest_break_at_or_below_quantity() -> None:
    result = await _adapter().availability(["0057 8 30"], quantities=[1, 100, 500, 5000])

    item = result.items[0]
    assert item.found is True
    assert item.currency == "EUR"
    # fixture breaks: 1 -> 24, 100 -> 19, 500 -> 16, 2000 -> 13
    assert [(q.quantity, q.unit_price_minor) for q in item.quotes] == [
        (1, 24),
        (100, 19),
        (500, 16),
        (5000, 13),
    ]


async def test_extended_price_is_unit_price_times_quantity_in_minor_units() -> None:
    result = await _adapter().availability(["0057 8 30"], quantities=[500])

    quote = result.items[0].quotes[0]
    assert quote.unit_price_minor == 16
    assert quote.extended_price_minor == 16 * 500
    assert isinstance(quote.unit_price_minor, int)
    assert isinstance(quote.extended_price_minor, int)


async def test_availability_status_follows_the_200_percent_stock_rule() -> None:
    """spec #collab inventory dots: >=200 % of the break = available, >=100 % = at risk."""
    # fixture stock for 0384 06 is 400 pieces
    result = await _adapter().availability(["0384 06"], quantities=[100, 250, 400, 900])

    assert [q.status for q in result.items[0].quotes] == [
        AvailabilityStatus.available,  # 400 >= 2 * 100
        AvailabilityStatus.at_risk,  # 400 >= 250 but < 500
        AvailabilityStatus.at_risk,  # 400 >= 400 but < 800
        AvailabilityStatus.insufficient,  # 400 < 900
    ]


async def test_zero_stock_is_insufficient_but_still_priced() -> None:
    result = await _adapter().availability(["0300 5 12"], quantities=[10])

    item = result.items[0]
    assert item.found is True
    assert item.quantity_available == 0
    assert item.lead_time_days == 21
    assert item.quotes[0].status is AvailabilityStatus.insufficient
    assert item.quotes[0].unit_price_minor == 31


async def test_unknown_part_number_is_not_found_not_an_error() -> None:
    result = await _adapter().availability(["NICHT-IM-KATALOG"], quantities=[10])

    item = result.items[0]
    assert item.found is False
    assert item.quotes == ()
    assert item.description is None


async def test_lookup_is_whitespace_and_case_insensitive() -> None:
    result = await _adapter().availability(["pem-cls-m4-2"], quantities=[1])
    assert result.items[0].found is True

    spaced = await _adapter().availability(["005783 0"], quantities=[1])
    assert spaced.items[0].found is True  # "0057 8 30" ignoring whitespace


async def test_quantities_are_deduplicated_and_sorted() -> None:
    result = await _adapter().availability(["0057 8 30"], quantities=[100, 1, 100])
    assert [q.quantity for q in result.items[0].quotes] == [1, 100]


async def test_echoes_back_one_item_per_requested_part_in_order() -> None:
    result = await _adapter().availability(["0384 06", "UNBEKANNT"], quantities=[1])

    assert [item.oem_part_number for item in result.items] == ["0384 06", "UNBEKANNT"]


# --------------------------------------------------------------------------- #
# 2 · Graceful degradation (AC 3)
# --------------------------------------------------------------------------- #
async def test_client_failure_raises_supplier_unavailable_not_the_raw_error() -> None:
    adapter = WuerthMaterialPricingAdapter(_BoomClient())

    with pytest.raises(SupplierUnavailable) as excinfo:
        await adapter.availability(["0057 8 30"], quantities=[1])

    assert excinfo.value.supplier == "wuerth"


class _MalformedClient:
    """A supplier that answers 200 with drifted/garbage content."""

    def __init__(self, document: Any, ack: Any = None) -> None:
        self._document = document
        self._ack = ack

    async def fetch_catalog(self) -> Any:
        return self._document

    async def send_rfq(self, request: Any) -> Any:
        return self._ack


@pytest.mark.parametrize(
    "document",
    [
        pytest.param({"items": []}, id="no-currency"),
        pytest.param({"currency": "EUR", "items": [{"brand": "W"}]}, id="item-without-part-number"),
        pytest.param(
            {
                "currency": "EUR",
                "items": [{"oem_part_number": "X", "price_breaks": [{"min_quantity": 1}]}],
            },
            id="break-without-price",
        ),
        pytest.param(
            {
                "currency": "EUR",
                "items": [{"oem_part_number": "X", "quantity_available": "n/a"}],
            },
            id="stock-not-a-number",
        ),
        pytest.param("not a document at all", id="not-an-object"),
    ],
)
async def test_drifted_supplier_payloads_degrade_rather_than_crash(document: Any) -> None:
    """Live-API drift is likelier than an outage and must degrade identically —
    a 500 on the estimating page is exactly what "never blocks costing" forbids."""
    adapter = WuerthMaterialPricingAdapter(_MalformedClient(document))

    with pytest.raises(SupplierUnavailable):
        await adapter.availability(["X"], quantities=[1])


async def test_unusable_rfq_acknowledgement_is_a_failed_send_not_a_crash() -> None:
    adapter = WuerthMaterialPricingAdapter(_MalformedClient({}, ack=["unexpected", "list"]))

    with pytest.raises(SupplierUnavailable):
        await adapter.send_rfq(
            SourcingRfqRequest(
                reference="TS-RFQ-9",
                requested_by="Fechner GmbH",
                lines=[SourcingRfqLine(oem_part_number="0384 06", quantities=[10])],
            )
        )


async def test_quantity_below_the_lowest_break_is_reported_unpriced_not_dropped() -> None:
    """A missing row would silently lose one of the estimator's make quantities."""
    client = _MalformedClient(
        {
            "currency": "EUR",
            "items": [
                {
                    "oem_part_number": "X",
                    "quantity_available": 100,
                    "price_breaks": [{"min_quantity": 5, "unit_price_minor": 40}],
                }
            ],
        }
    )
    result = await WuerthMaterialPricingAdapter(client).availability(["X"], quantities=[1, 10])

    quotes = result.items[0].quotes
    assert [q.quantity for q in quotes] == [1, 10]
    assert quotes[0].unit_price_minor is None
    assert quotes[0].extended_price_minor is None
    assert quotes[1].unit_price_minor == 40


# --------------------------------------------------------------------------- #
# 3 · RFQ-send request shape (AC 4)
# --------------------------------------------------------------------------- #
async def test_rfq_send_produces_the_documented_request_shape() -> None:
    client = FixtureWuerthClient()
    adapter = WuerthMaterialPricingAdapter(client)

    result = await adapter.send_rfq(
        SourcingRfqRequest(
            reference="TS-RFQ-1234",
            requested_by="Fechner GmbH",
            reply_to="einkauf@fechner.example",
            message="Bitte Preis für Serie 2026",
            lines=[
                SourcingRfqLine(
                    oem_part_number="0057 8 30",
                    description="Sechskantschraube DIN 933 M8x30",
                    quantities=[100, 500],
                )
            ],
        )
    )

    assert client.last_rfq_request == {
        "schema_version": "1.0",
        "supplier": "wuerth",
        "reference": "TS-RFQ-1234",
        "requested_by": "Fechner GmbH",
        "reply_to": "einkauf@fechner.example",
        "message": "Bitte Preis für Serie 2026",
        "lines": [
            {
                "oem_part_number": "0057 8 30",
                "description": "Sechskantschraube DIN 933 M8x30",
                "quantities": [100, 500],
            }
        ],
    }
    assert result.accepted is True
    assert result.reference == "TS-RFQ-1234"
    assert result.supplier_reference
    # Fixture mode must announce itself — a mock send is not a send.
    assert result.mode == "fixture"


async def test_rfq_request_omits_optional_keys_and_never_attaches_files() -> None:
    client = FixtureWuerthClient()
    adapter = WuerthMaterialPricingAdapter(client)

    await adapter.send_rfq(
        SourcingRfqRequest(
            reference="TS-RFQ-9",
            requested_by="Fechner GmbH",
            lines=[SourcingRfqLine(oem_part_number="0384 06", quantities=[10])],
        )
    )

    sent = client.last_rfq_request
    assert sent is not None
    assert "reply_to" not in sent
    assert "message" not in sent
    assert "description" not in sent["lines"][0]
    # No file/CAD key may ever appear — the external-send gate lane is M6.7c.
    assert not {"files", "file_ids", "attachments", "step"} & set(sent)


async def test_rfq_send_failure_raises_supplier_unavailable() -> None:
    adapter = WuerthMaterialPricingAdapter(_BoomClient())

    with pytest.raises(SupplierUnavailable):
        await adapter.send_rfq(
            SourcingRfqRequest(
                reference="TS-RFQ-9",
                requested_by="Fechner GmbH",
                lines=[SourcingRfqLine(oem_part_number="0384 06", quantities=[10])],
            )
        )


# --------------------------------------------------------------------------- #
# 4 · Config-only fixture→live swap + no hardcoded credentials (AC 2, 5)
# --------------------------------------------------------------------------- #
def test_fixture_mode_builds_a_fixture_client_and_needs_no_credentials() -> None:
    adapter = build_wuerth_adapter(build_settings(wuerth_mode="fixture"))

    assert isinstance(adapter.client, FixtureWuerthClient)
    assert adapter.mode == "fixture"


def test_fixture_mode_fails_closed_when_the_recorded_response_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deploy that forgot to ship fixtures/wuerth would degrade every lookup
    and read as a supplier outage — boot loudly instead."""
    monkeypatch.setattr(wuerth_module, "FIXTURE_PATH", Path("/nonexistent/catalog.json"))

    with pytest.raises(ValueError, match="WUERTH_MODE=fixture"):
        build_settings(wuerth_mode="fixture").validate_wuerth()


def test_live_mode_builds_the_http_client_from_settings_only() -> None:
    settings = build_settings(
        wuerth_mode="live",
        wuerth_base_url="https://api.example-wuerth.test",
        wuerth_api_key="sekret-from-env",
    )

    adapter = build_wuerth_adapter(settings)

    assert isinstance(adapter.client, LiveWuerthClient)
    assert adapter.mode == "live"


def test_live_mode_without_a_key_fails_closed_at_validation() -> None:
    settings = build_settings(wuerth_mode="live", wuerth_base_url="https://x.test")

    with pytest.raises(ValueError, match="WUERTH_API_KEY"):
        settings.validate_wuerth()


def test_live_mode_without_a_base_url_fails_closed_at_validation() -> None:
    settings = build_settings(wuerth_mode="live", wuerth_api_key="k")

    with pytest.raises(ValueError, match="WUERTH_BASE_URL"):
        settings.validate_wuerth()


def test_unknown_mode_fails_validation() -> None:
    with pytest.raises(ValueError, match="WUERTH_MODE"):
        build_settings(wuerth_mode="hybrid").validate_wuerth()


def test_no_credential_or_endpoint_literal_lives_in_the_adapter_module() -> None:
    """AC 5 — credentials and the endpoint come from settings, never the source."""
    lowered = inspect.getsource(wuerth_module).lower()

    for marker in ('api_key = "', "api_key = '", "bearer ey", "wuerth.de", "https://"):
        assert marker not in lowered, f"credential/endpoint literal {marker!r} in adapter source"


# --------------------------------------------------------------------------- #
# 5 · API surface (org-scoped, RLS)
# --------------------------------------------------------------------------- #
def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _plant_pc(seeder: Seeder, org_id: uuid.UUID, oem_part_number: str) -> uuid.UUID:
    pc_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO purchased_component (id, org_id, oem_part_number, description)"
        " VALUES (:id, :org_id, :pn, :descr)",
        {"id": pc_id, "org_id": org_id, "pn": oem_part_number, "descr": "Schraube"},
    )
    return pc_id


def test_availability_endpoint_returns_breaks_for_a_purchased_component(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "src-a")
    pc_id = _plant_pc(seeder, org, "0057 8 30")

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        resp = app_client.get(
            f"/api/sourcing/purchased-components/{pc_id}/availability",
            params={"quantities": "1,100"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["degraded"] is False
    assert body["supplier"] == "wuerth"
    assert body["item"]["found"] is True
    assert [q["unit_price_minor"] for q in body["item"]["quotes"]] == [24, 19]
    assert body["item"]["currency"] == "EUR"
    assert body["item"]["quotes"][0]["status"] == "available"


def test_availability_for_another_orgs_component_is_404(
    app_client: TestClient, seeder: Seeder
) -> None:
    org_a, admin_a = _org_with_admin(seeder, "src-b")
    org_b = seeder.org("src-c")
    foreign_pc = _plant_pc(seeder, org_b, "0057 8 30")

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        resp = app_client.get(
            f"/api/sourcing/purchased-components/{foreign_pc}/availability",
            params={"quantities": "1"},
        )

    assert resp.status_code == 404


def test_supplier_outage_degrades_to_200_and_never_breaks_costing(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "src-d")
    pc_id = _plant_pc(seeder, org, "0057 8 30")

    app = cast(FastAPI, app_client.app)
    app.dependency_overrides[wuerth_module.get_sourcing_adapter] = lambda: (
        WuerthMaterialPricingAdapter(_BoomClient())
    )
    try:
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.get(
                f"/api/sourcing/purchased-components/{pc_id}/availability",
                params={"quantities": "1"},
            )
    finally:
        app.dependency_overrides.pop(wuerth_module.get_sourcing_adapter, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is True
    assert body["item"]["quotes"] == []


def test_rfq_send_records_an_org_scoped_audit_event(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "src-e")
    pc_id = _plant_pc(seeder, org, "0057 8 30")

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        resp = app_client.post(
            "/api/sourcing/rfq",
            json={
                "purchased_component_ids": [str(pc_id)],
                "quantities": [100, 500],
                "message": "Bitte Preis für Serie 2026",
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["reference"].startswith("TS-RFQ-")
    assert body["mode"] == "fixture"

    assert (
        seeder.count(
            "domain_event",
            "org_id = :org AND event_type = 'sourcing.rfq_sent' AND payload->>'mode' = 'fixture'",
            {"org": org},
        )
        == 1
    )


def test_rfq_send_rejects_another_orgs_component(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_with_admin(seeder, "src-g")
    org_b = seeder.org("src-h")
    foreign_pc = _plant_pc(seeder, org_b, "0057 8 30")

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        resp = app_client.post(
            "/api/sourcing/rfq",
            json={"purchased_component_ids": [str(foreign_pc)], "quantities": [10]},
        )

    assert resp.status_code == 404
    assert seeder.count("domain_event", "event_type = 'sourcing.rfq_sent'") == 0


def test_supplier_price_never_writes_into_the_library(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Tier-1: a supplier price is a suggestion — it never silently reprices."""
    org, admin = _org_with_admin(seeder, "src-f")
    pc_id = _plant_pc(seeder, org, "0057 8 30")

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        app_client.get(
            f"/api/sourcing/purchased-components/{pc_id}/availability",
            params={"quantities": "1,100"},
        )
        app_client.post(
            "/api/sourcing/rfq",
            json={"purchased_component_ids": [str(pc_id)], "quantities": [100]},
        )

    assert (
        seeder.count(
            "purchased_component",
            "id = :id AND piece_price IS NULL",
            {"id": pc_id},
        )
        == 1
    )
