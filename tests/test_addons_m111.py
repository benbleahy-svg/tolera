"""Tests for M1.11 — Add-Ons / Lead Times / Expedite + VAT lines.

Three layers:

* **Pure tax math** (`app.tax`): the spec `#dach-tax` rate table (DE 19 / AT
  20 / CH 8.1), 2-dp kaufmännische Rundung at the quote-total boundary, and
  the integer-minor-units conversion (CLAUDE.md §5 money invariant).
* **Behavior** (real RLS-bound Postgres, through the API): add-ons apply
  **after** discounts and never touch the unit price (KB
  `add-ons-p3l-cheat-sheet`); Kalk-priced add-ons per break; manual overrides
  survive reprice; per-qty lead times (Kalk DAYS roll-up + manual override);
  expedite tiers (days_faster + % markup) incl. quote-level APPLY TO ALL.
* **VAT lines** across DE/AT/CH (incl. the CH/CHF fixture) on
  `GET /api/quotes/{id}/totals` — net + MwSt/USt/MWST + gross, minor units +
  explicit currency.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient

from app.models import MembershipRole, OrgCountry
from app.tax import VAT_PROFILES, to_minor_units, vat_amount
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]


@contextmanager
def _as_admin(client: TestClient, org: uuid.UUID, user: uuid.UUID) -> Iterator[TestClient]:
    with authed(client, user_id=user, org_id=org, roles=ADMIN):
        yield client


# --------------------------------------------------------------------------- #
# Pure tax math
# --------------------------------------------------------------------------- #
def test_vat_rate_table_matches_dach_tax_spec() -> None:
    # spec #dach-tax: DE 19%/7% MwSt/USt · AT 20% USt · CH 8.1% MWST
    assert VAT_PROFILES[OrgCountry.DE].standard_pct == Decimal("19")
    assert VAT_PROFILES[OrgCountry.DE].label == "MwSt."
    assert VAT_PROFILES[OrgCountry.AT].standard_pct == Decimal("20")
    assert VAT_PROFILES[OrgCountry.AT].label == "USt."
    assert VAT_PROFILES[OrgCountry.CH].standard_pct == Decimal("8.1")
    assert VAT_PROFILES[OrgCountry.CH].label == "MWST"


def test_vat_amount_rounds_half_up_at_the_cent() -> None:
    assert vat_amount(Decimal("1000.00"), Decimal("19")) == Decimal("190.00")
    # 123.45 x 19% = 23.4555 → 23.46 (kaufmännische Rundung, never truncation)
    assert vat_amount(Decimal("123.45"), Decimal("19")) == Decimal("23.46")
    # 8.1% of 2100.00 = 170.10 exactly
    assert vat_amount(Decimal("2100.00"), Decimal("8.1")) == Decimal("170.10")
    # half-up on the sub-cent boundary: 0.50 x 19% = 0.095 → 0.10
    assert vat_amount(Decimal("0.50"), Decimal("19")) == Decimal("0.10")


def test_to_minor_units_is_exact_integer_cents() -> None:
    assert to_minor_units(Decimal("2100.00")) == 210000
    assert to_minor_units(Decimal("0.01")) == 1
    assert to_minor_units(Decimal("0")) == 0


# --------------------------------------------------------------------------- #
# API choreography helpers (test_pricing_m110 conventions)
# --------------------------------------------------------------------------- #
def _org_admin(
    seeder: Seeder, slug: str, *, country: str = "DE", currency: str = "EUR"
) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug, country=country, currency=currency)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_quote_item(
    client: TestClient, quantities: list[int] | None = None
) -> tuple[str, str, str]:
    """quote id, quote item id, root component id."""
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    if quantities:
        res = client.put(
            f"/api/quotes/{qid}/items/{item['id']}/quantities", json={"quantities": quantities}
        )
        assert res.status_code == 200, res.text
    return qid, str(item["id"]), str(item["root_component_id"])


def _add_manual_op(
    client: TestClient, component_id: str, name: str, cost: str, quantity: int = 1
) -> str:
    created = client.post(f"/api/components/{component_id}/operations", json={"name": name})
    assert created.status_code == 201, created.text
    op = next(o for o in created.json()["operations"] if o["name"] == name)
    res = client.patch(f"/api/operations/{op['id']}/cells/{quantity}", json={"manual_cost": cost})
    assert res.status_code == 200, res.text
    return str(op["id"])


def _add_markup(client: TestClient, component_id: str, pct: str) -> None:
    res = client.post(
        f"/api/components/{component_id}/pricing-items",
        json={
            "name": "Aufschlag",
            "calc_type": "markup",
            "category": "general",
            "default_pct": pct,
        },
    )
    assert res.status_code == 201, res.text


def _add_discount(client: TestClient, component_id: str, pct: str) -> None:
    res = client.post(
        f"/api/components/{component_id}/discounts",
        json={"name": "Rabatt", "default_pct": pct},
    )
    assert res.status_code == 201, res.text


def _pricing(client: TestClient, component_id: str) -> dict[str, Any]:
    res = client.get(f"/api/components/{component_id}/pricing")
    assert res.status_code == 200, res.text
    return cast(dict[str, Any], res.json())


def _add_add_on(client: TestClient, component_id: str, **payload: Any) -> dict[str, Any]:
    res = client.post(f"/api/components/{component_id}/add-ons", json=payload)
    assert res.status_code == 201, res.text
    return cast(dict[str, Any], res.json())


def _totals_row(summary: dict[str, Any], quantity: int) -> dict[str, Any]:
    return next(t for t in summary["totals"] if t["quantity"] == quantity)


# --------------------------------------------------------------------------- #
# Add-ons — flat, Kalk-priced, after discounts, overrides
# --------------------------------------------------------------------------- #
def test_flat_required_add_on_applies_after_discounts(
    seeder: Seeder, app_client: TestClient
) -> None:
    """Cost 1000 → +100% markup = 2000 → -10% discount = 1800 → +FAI 100
    = 1900. The add-on lands AFTER the discount (1900.00, not 1890.00) and
    never touches the unit price (KB add-ons-p3l-cheat-sheet)."""
    org, user = _org_admin(seeder, "addon-after-discount")
    with _as_admin(app_client, org, user) as client:
        _, _, component_id = _new_quote_item(client, [1])
        _add_manual_op(client, component_id, "Fräsen", "1000.0000")
        _add_markup(client, component_id, "100")
        _add_discount(client, component_id, "10")
        _add_add_on(
            client,
            component_id,
            name="First Article Inspection (FAI)",
            default_price="100",
            is_required=True,
        )
        summary = _pricing(client, component_id)
        row = _totals_row(summary, 1)
        assert Decimal(row["unit_price"]) == Decimal("1800.00")
        assert Decimal(row["total_price"]) == Decimal("1800.00")
        assert Decimal(row["total_required_add_ons"]) == Decimal("100.0000")
        assert Decimal(row["total_with_required_add_ons"]) == Decimal("1900.0000")

        add_on = summary["add_ons"][0]
        assert add_on["name"] == "First Article Inspection (FAI)"
        assert add_on["is_required"] is True
        cell = next(c for c in add_on["cells"] if c["quantity"] == 1)
        assert Decimal(cell["price"]) == Decimal("100.0000")


def test_non_required_add_on_stays_out_of_the_required_total(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "addon-optional")
    with _as_admin(app_client, org, user) as client:
        _, _, component_id = _new_quote_item(client, [1])
        _add_manual_op(client, component_id, "Fräsen", "500.0000")
        _add_add_on(
            client,
            component_id,
            name="Certificate of Conformance",
            default_price="25",
            is_required=False,
        )
        row = _totals_row(_pricing(client, component_id), 1)
        assert Decimal(row["total_required_add_ons"]) == Decimal("0.0000")


def test_kalk_priced_add_on_computes_per_break(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "addon-kalk")
    with _as_admin(app_client, org, user) as client:
        _, _, component_id = _new_quote_item(client, [1, 5])
        _add_manual_op(client, component_id, "Fräsen", "100.0000")
        _add_add_on(
            client,
            component_id,
            name="Verpackung",
            formula="PRICE = 20 + 2 * quantity",
            is_required=True,
        )
        summary = _pricing(client, component_id)
        cells = {c["quantity"]: c for c in summary["add_ons"][0]["cells"]}
        assert Decimal(cells[1]["calc_price"]) == Decimal("22.0000")
        assert Decimal(cells[5]["calc_price"]) == Decimal("30.0000")


def test_set_is_required_drives_the_calc_side_and_toggle_overrides(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "addon-required-calc")
    with _as_admin(app_client, org, user) as client:
        _, _, component_id = _new_quote_item(client, [1])
        _add_manual_op(client, component_id, "Fräsen", "100.0000")
        created = _add_add_on(
            client,
            component_id,
            name="NRE",
            formula="set_is_required(True)\nPRICE = 50",
            is_required=False,
        )
        assert created["calc_is_required"] is True
        assert created["is_required"] is True  # calc wins over the def default
        # the manual toggle outranks the formula (calc-vs-override, CLAUDE.md §5)
        res = client.patch(f"/api/add-ons/{created['id']}", json={"manual_is_required": False})
        assert res.status_code == 200, res.text
        assert res.json()["is_required"] is False


def test_manual_price_override_survives_reprice(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "addon-override")
    with _as_admin(app_client, org, user) as client:
        _, _, component_id = _new_quote_item(client, [1])
        op_id = _add_manual_op(client, component_id, "Fräsen", "100.0000")
        created = _add_add_on(client, component_id, name="Tooling Charge", default_price="250")
        res = client.patch(f"/api/add-ons/{created['id']}/cells/1", json={"manual_price": "199.99"})
        assert res.status_code == 200, res.text
        # reprice via a cost change — the override must survive, the calc refresh
        res = client.patch(f"/api/operations/{op_id}/cells/1", json={"manual_cost": "150.0000"})
        assert res.status_code == 200, res.text
        add_on = _pricing(client, component_id)["add_ons"][0]
        cell = next(c for c in add_on["cells"] if c["quantity"] == 1)
        assert Decimal(cell["manual_price"]) == Decimal("199.9900")
        assert Decimal(cell["price"]) == Decimal("199.9900")
        assert Decimal(cell["calc_price"]) == Decimal("250.0000")


def test_add_on_def_snapshot_on_attach(seeder: Seeder, app_client: TestClient) -> None:
    """E4-d: editing the def never touches an attached row (M1.10 posture)."""
    org, user = _org_admin(seeder, "addon-snapshot")
    with _as_admin(app_client, org, user) as client:
        res = client.post(
            "/api/add-on-defs",
            json={"name": "FAI", "default_price": "100", "default_is_required": True},
        )
        assert res.status_code == 201, res.text
        def_id = res.json()["id"]
        _, _, component_id = _new_quote_item(client, [1])
        _add_manual_op(client, component_id, "Fräsen", "100.0000")
        created = _add_add_on(client, component_id, source_def_id=def_id)
        assert created["name"] == "FAI"
        assert created["is_required"] is True
        # def edit after attach — the snapshot must not move
        res = client.patch(f"/api/add-on-defs/{def_id}", json={"default_price": "999"})
        assert res.status_code == 200, res.text
        add_on = _pricing(client, component_id)["add_ons"][0]
        cell = next(c for c in add_on["cells"] if c["quantity"] == 1)
        assert Decimal(cell["price"]) == Decimal("100.0000")


# --------------------------------------------------------------------------- #
# Lead times + expedite
# --------------------------------------------------------------------------- #
def test_lead_time_calc_from_kalk_days_and_manual_override(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "leadtime-days")
    with _as_admin(app_client, org, user) as client:
        _, _, component_id = _new_quote_item(client, [1, 5])
        created = client.post(f"/api/components/{component_id}/operations", json={"name": "Fräsen"})
        assert created.status_code == 201, created.text
        op = next(o for o in created.json()["operations"] if o["name"] == "Fräsen")
        # the formula lands via the drawer edit (M1.9 snapshot posture)
        res = client.patch(
            f"/api/operations/{op['id']}", json={"cost_formula": "COST = 100\nDAYS = 4"}
        )
        assert res.status_code == 200, res.text
        summary = _pricing(client, component_id)
        lead = {lt["quantity"]: lt for lt in summary["lead_times"]}
        assert lead[1]["calc_lead_time_days"] == 4
        assert lead[1]["lead_time_days"] == 4
        # the estimator's blue-text edit wins; the calc side stays visible
        res = client.patch(
            f"/api/components/{component_id}/lead-time/1", json={"manual_lead_time_days": 6}
        )
        assert res.status_code == 200, res.text
        lead = {lt["quantity"]: lt for lt in _pricing(client, component_id)["lead_times"]}
        assert lead[1]["manual_lead_time_days"] == 6
        assert lead[1]["lead_time_days"] == 6
        assert lead[1]["calc_lead_time_days"] == 4
        assert lead[5]["lead_time_days"] == 4  # other breaks untouched


def test_expedite_options_shorten_lead_and_markup_price(
    seeder: Seeder, app_client: TestClient
) -> None:
    """AC: expedite shortens the lead time and adjusts price per its rule
    (relative days faster + % markup on the discounted unit price)."""
    org, user = _org_admin(seeder, "expedite")
    with _as_admin(app_client, org, user) as client:
        _, _, component_id = _new_quote_item(client, [1])
        _add_manual_op(client, component_id, "Fräsen", "1000.0000")
        _add_markup(client, component_id, "80")  # unit 1800.00
        res = client.patch(
            f"/api/components/{component_id}/lead-time/1", json={"manual_lead_time_days": 10}
        )
        assert res.status_code == 200, res.text
        res = client.put(
            f"/api/components/{component_id}/expedite-options",
            json={"options": [{"days_faster": 3, "markup_pct": "10"}]},
        )
        assert res.status_code == 200, res.text
        lead = {lt["quantity"]: lt for lt in _pricing(client, component_id)["lead_times"]}
        expedite = lead[1]["expedites"][0]
        assert expedite["days_faster"] == 3
        assert expedite["lead_time_days"] == 7
        assert Decimal(expedite["unit_price"]) == Decimal("1980.00")
        assert Decimal(expedite["total_price"]) == Decimal("1980.00")


def test_apply_to_all_pushes_tiers_to_every_line(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "apply-to-all")
    with _as_admin(app_client, org, user) as client:
        qid, _, first = _new_quote_item(client, [1])
        second = str(
            client.post(f"/api/quotes/{qid}/items").json()["items"][1]["root_component_id"]
        )
        for cid in (first, second):
            _add_manual_op(client, cid, "Fräsen", "100.0000")
        res = client.post(
            f"/api/quotes/{qid}/lead-times/apply-to-all",
            json={
                "standard_lead_time_days": 12,
                "tiers": [
                    {"days_faster": 3, "markup_pct": "10"},
                    {"days_faster": 6, "markup_pct": "25"},
                ],
            },
        )
        assert res.status_code == 200, res.text
        for cid in (first, second):
            lead = {lt["quantity"]: lt for lt in _pricing(client, cid)["lead_times"]}
            assert lead[1]["lead_time_days"] == 12
            assert [e["days_faster"] for e in lead[1]["expedites"]] == [3, 6]
        # tiers staged on the quote for the editor
        quote = client.get(f"/api/quotes/{qid}").json()
        assert quote["expedite_tiers"]["tiers"][0]["days_faster"] == 3


# --------------------------------------------------------------------------- #
# VAT lines — DE / AT / CH (quote-level, never in Kalk)
# --------------------------------------------------------------------------- #
def _quote_with_net_2100(client: TestClient) -> str:
    """One item, qty 1: cost 1000 → +100% = 2000 unit + required FAI 100 = 2100 net."""
    qid, _, component_id = _new_quote_item(client, [1])
    _add_manual_op(client, component_id, "Fräsen", "1000.0000")
    _add_markup(client, component_id, "100")
    _add_add_on(client, component_id, name="FAI", default_price="100", is_required=True)
    return qid


def test_vat_line_de(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "vat-de", country="DE", currency="EUR")
    with _as_admin(app_client, org, user) as client:
        qid = _quote_with_net_2100(client)
        res = client.get(f"/api/quotes/{qid}/totals")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["currency"] == "EUR"
        assert body["vat_label"] == "MwSt."
        assert Decimal(body["vat_rate_pct"]) == Decimal("19")
        assert body["net_minor"] == 210000
        assert body["vat_minor"] == 39900
        assert body["gross_minor"] == 249900


def test_vat_line_at(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "vat-at", country="AT", currency="EUR")
    with _as_admin(app_client, org, user) as client:
        qid = _quote_with_net_2100(client)
        body = client.get(f"/api/quotes/{qid}/totals").json()
        assert body["vat_label"] == "USt."
        assert Decimal(body["vat_rate_pct"]) == Decimal("20")
        assert (body["net_minor"], body["vat_minor"], body["gross_minor"]) == (
            210000,
            42000,
            252000,
        )


def test_vat_line_ch_chf(seeder: Seeder, app_client: TestClient) -> None:
    # the CH/CHF fixture the block's test plan names: 8.1% MWST on CHF
    org, user = _org_admin(seeder, "vat-ch", country="CH", currency="CHF")
    with _as_admin(app_client, org, user) as client:
        qid = _quote_with_net_2100(client)
        body = client.get(f"/api/quotes/{qid}/totals").json()
        assert body["currency"] == "CHF"
        assert body["vat_label"] == "MWST"
        assert Decimal(body["vat_rate_pct"]) == Decimal("8.1")
        assert (body["net_minor"], body["vat_minor"], body["gross_minor"]) == (
            210000,
            17010,
            227010,
        )


def test_totals_selects_the_requested_break(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "vat-breaks")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, component_id = _new_quote_item(client, [1, 5])
        _add_manual_op(client, component_id, "Fräsen", "100.0000")
        for qty in (1, 5):
            if qty != 1:
                res = client.patch(
                    f"/api/operations/{_op_id(client, component_id)}/cells/{qty}",
                    json={"manual_cost": "400.0000"},
                )
                assert res.status_code == 200, res.text
        # default: the lowest break → net 100.00
        body = client.get(f"/api/quotes/{qid}/totals").json()
        assert body["net_minor"] == 10000
        assert body["items"][0]["quantity"] == 1
        # explicit selection: qty 5 → net 400.00
        body = client.get(f"/api/quotes/{qid}/totals", params={"item": f"{item_id}:5"}).json()
        assert body["net_minor"] == 40000
        assert body["items"][0]["quantity"] == 5


def _op_id(client: TestClient, component_id: str) -> str:
    ops = client.get(f"/api/components/{component_id}/costing").json()["operations"]
    return str(ops[0]["id"])
