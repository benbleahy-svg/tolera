"""M4.3 — multi-component sheet-metal nesting: API, locking, Kalk drawer feed.

Spec ``#nesting``: select sheet-metal components of like material/thickness
across line items → an estimation-grade area-packing nest yields # of sheets
per quantity break and the allocated material cost, feeding the material
drawer's Calculated/Override variables (Net Sheet Used, Sheet Cost, Parts Per
Sheet, # Of Sheets) via Kalk ``manual_nest()``.

End-to-end against real Postgres + real OCCT interrogation (the M4.2 bracket
fixture: thickness 2.0 mm, unfolded 95.8717 x 50.0 mm, flat area 4814.16 mm²).
The API's numbers are asserted against ``app.nesting_math.compute_nest`` run
on the same inputs — the pure module carries the hand-calc golden.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole
from app.nesting_math import NestComponent, NestSettings, NestStock, compute_nest
from tests.conftest import Seeder, authed
from tests.support import eager_celery

ADMIN = [MembershipRole.admin]

CAD_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
BRACKET = (CAD_DIR / "bracket-L-60x40x2-r3.step").read_bytes()

STOCK = {"length_mm": 3000.0, "width_mm": 1500.0, "erp_code": "", "sheet_cost": "250.00"}
SETTINGS = {
    "edge_buffer_mm": 3.0,
    "clearance_mm": 3.0,
    "kerf_mm": 0.25,
    "drop_threshold_pct": 25.0,
    "distribution_method": "area_of_parts",
    "allow_mixed_thickness": False,
}

# The drawer formula (Sheet Metal material op): the four spec-named variables,
# defaults fed by manual_nest(), cost recomputed FROM the variables so an
# override flows into COST.
DRAWER_FORMULA = """nest = manual_nest()
sheet_cost = var("Sheet Cost", nest.sheet_cost, "Kosten/Tafel", currency, quantity_specific=True)
num_sheets = var("# Of Sheets", nest.number_of_sheets, "", number, quantity_specific=True)
parts_per_sheet = var("Parts Per Sheet", nest.parts_per_sheet, "", number, quantity_specific=True)
net_sheet_used = var("Net Sheet Used", nest.net_sheet_used, "", number, quantity_specific=True)
COST = num_sheets * sheet_cost * nest.cost_share_pct / 100.0
DAYS = 0
"""


def _material_cell(
    client: TestClient, component_id: str, op_id: str, quantity: int
) -> dict[str, Any]:
    costing = client.get(f"/api/components/{component_id}/costing").json()
    op = next(o for o in costing["operations"] if o["id"] == op_id)
    return next(c for c in op["cells"] if c["quantity"] == quantity)


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _sheet_metal_process_id(client: TestClient) -> str:
    processes = client.get("/api/processes").json()
    return str(next(p for p in processes if p["name"] == "Sheet Metal")["id"])


def _material_id(client: TestClient) -> str:
    """One leaf material every nested component shares."""
    tree = client.get("/api/materials/tree").json()
    cls = tree[0]
    family = cls["families"][0]
    created = client.post(
        "/api/materials",
        json={"family_id": family["id"], "display_name": "1.4301 Blech"},
    )
    if created.status_code == 201:
        return str(created.json()["id"])
    materials = client.get("/api/materials").json()
    return str(next(m for m in materials if m["display_name"] == "1.4301 Blech")["id"])


def _sheet_line(
    client: TestClient,
    quote_id: str,
    material_id: str,
    *,
    quantities: list[int] | None = None,
) -> dict[str, str]:
    """Line item with bracket CAD, Sheet Metal process (triggers the M4.2
    interrogation), a shared material, and a formula-driven material op."""
    item = client.post(f"/api/quotes/{quote_id}/items").json()["items"][-1]
    part_id, component_id = str(item["part_id"]), str(item["root_component_id"])
    with eager_celery():
        client.post(
            f"/api/parts/{part_id}/files",
            files=[("files", ("bracket.step", BRACKET, "application/step"))],
        )
        res = client.patch(
            f"/api/components/{component_id}/process",
            json={"process_id": _sheet_metal_process_id(client), "keep_operations": True},
        )
        assert res.status_code == 200, res.text
    assert (
        client.patch(
            f"/api/components/{component_id}/material", json={"material_id": material_id}
        ).status_code
        == 200
    )
    created = client.post(
        f"/api/components/{component_id}/operations",
        json={"name": "Material | Sheet (Nesting)", "category": "material"},
    )
    assert created.status_code == 201, created.text
    op = next(o for o in created.json()["operations"] if o["name"] == "Material | Sheet (Nesting)")
    assert (
        client.patch(
            f"/api/operations/{op['id']}", json={"cost_formula": DRAWER_FORMULA}
        ).status_code
        == 200
    )
    if quantities is not None:
        assert (
            client.put(
                f"/api/quotes/{quote_id}/items/{item['id']}/quantities",
                json={"quantities": quantities},
            ).status_code
            == 200
        )
    return {
        "item_id": str(item["id"]),
        "part_id": part_id,
        "component_id": component_id,
        "material_op_id": str(op["id"]),
    }


def _expected(rows: list[dict[str, Any]], make_qtys: dict[str, int]) -> Any:
    """The pure-math expectation from the overview rows the API itself served."""
    return compute_nest(
        [
            NestComponent(
                key=row["component_id"],
                flat_x_mm=row["flat_x_mm"],
                flat_y_mm=row["flat_y_mm"],
                flat_area_mm2=row["flat_area_mm2"],
                contour_length_mm=row["contour_length_mm"] or 0.0,
                make_qty=make_qtys[row["component_id"]],
            )
            for row in rows
        ],
        NestStock(length_mm=3000.0, width_mm=1500.0, sheet_cost=Decimal("250.00")),
        NestSettings(edge_buffer_mm=3.0, clearance_mm=3.0, kerf_mm=0.25, drop_threshold_pct=25.0),
    )


def _create_nest(
    client: TestClient,
    quote_id: str,
    component_ids: list[str],
    stock: list[dict[str, Any]],
    **settings_overrides: Any,
) -> Any:
    return client.post(
        f"/api/quotes/{quote_id}/nests",
        json={
            "component_ids": component_ids,
            "stock": stock,
            "settings": {**SETTINGS, **settings_overrides},
            "component_settings": [],
        },
    )


# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #
def test_overview_lists_interrogated_sheet_metal_components(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "nest-overview")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material)
        b = _sheet_line(app_client, quote_id, material)

        overview = app_client.get(f"/api/quotes/{quote_id}/nesting").json()
        rows = overview["sheet_metal"]
        assert {r["component_id"] for r in rows} == {a["component_id"], b["component_id"]}
        for row in rows:
            assert row["thickness_mm"] is not None and abs(row["thickness_mm"] - 2.0) < 0.01
            assert abs(row["flat_area_mm2"] - 4814.16) / 4814.16 < 1e-3
            assert row["eligible"] is True
            assert row["nest_id"] is None
            assert row["material_id"] == material
        assert overview["linear_metal"] == []  # 1D analog is a stub (spec #nesting)
        assert overview["nests"] == []


# --------------------------------------------------------------------------- #
# Create — across quote items, single break each (the DemoA case)
# --------------------------------------------------------------------------- #
def test_create_nest_across_items_matches_pure_math(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "nest-create")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10])
        b = _sheet_line(app_client, quote_id, material, quantities=[10])

        rows = app_client.get(f"/api/quotes/{quote_id}/nesting").json()["sheet_metal"]
        res = _create_nest(
            app_client,
            quote_id,
            [a["component_id"], b["component_id"]],
            [{**STOCK, "quantity": 10}],
        )
        assert res.status_code == 201, res.text
        [nest] = res.json()["nests"]
        assert nest["label"] == "Nest #1"
        assert nest["kind"] == "sheet"
        assert nest["quantity"] == 10

        expected = _expected(rows, {r["component_id"]: 10 for r in rows})
        result = nest["result"]
        assert abs(result["net_sheet_used"] - expected.net_sheet_used) < 1e-9
        assert abs(result["charged_sheets"] - expected.charged_sheets) < 1e-9
        assert result["material_cost"] == str(expected.material_cost)
        assert result["currency"] == "EUR"
        by_component = {c["component_id"]: c for c in result["components"]}
        for comp in expected.components:
            got = by_component[comp.key]
            assert got["parts_per_sheet"] == comp.parts_per_sheet
            assert got["allocated_cost"] == str(comp.allocated_cost)
        # the overview now shows both components as nested
        rows_after = app_client.get(f"/api/quotes/{quote_id}/nesting").json()["sheet_metal"]
        assert all(r["nest_id"] == nest["id"] for r in rows_after)


def test_across_items_multi_break_rejected(app_client: TestClient, seeder: Seeder) -> None:
    """KB: across quote items every component needs a single make quantity."""
    org, admin = _org_with_admin(seeder, "nest-multibreak")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10, 20])
        b = _sheet_line(app_client, quote_id, material, quantities=[10, 20])
        res = _create_nest(
            app_client,
            quote_id,
            [a["component_id"], b["component_id"]],
            [{**STOCK, "quantity": 10}, {**STOCK, "quantity": 20}],
        )
        assert res.status_code == 422
        assert "single make quantity" in res.json()["message"].lower()


def test_mismatched_material_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "nest-material-mix")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10])
        b = _sheet_line(app_client, quote_id, material, quantities=[10])
        # move B onto a different material
        tree = app_client.get("/api/materials/tree").json()
        other = app_client.post(
            "/api/materials",
            json={"family_id": tree[0]["families"][0]["id"], "display_name": "1.0038 Blech"},
        ).json()["id"]
        app_client.patch(
            f"/api/components/{b['component_id']}/material", json={"material_id": other}
        )
        res = _create_nest(
            app_client,
            quote_id,
            [a["component_id"], b["component_id"]],
            [{**STOCK, "quantity": 10}],
        )
        assert res.status_code == 422
        assert "material" in res.json()["message"].lower()


def test_already_nested_component_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "nest-twice")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10])
        assert (
            _create_nest(
                app_client, quote_id, [a["component_id"]], [{**STOCK, "quantity": 10}]
            ).status_code
            == 201
        )
        res = _create_nest(app_client, quote_id, [a["component_id"]], [{**STOCK, "quantity": 10}])
        assert res.status_code == 409


# --------------------------------------------------------------------------- #
# Same quote item, multiple make quantities → one nest per break, one set
# --------------------------------------------------------------------------- #
def test_multi_break_same_item_creates_associated_set(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "nest-set")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10, 25])
        res = _create_nest(
            app_client,
            quote_id,
            [a["component_id"]],
            [{**STOCK, "quantity": 10}, {**STOCK, "quantity": 25}],
        )
        assert res.status_code == 201, res.text
        nests = res.json()["nests"]
        assert [n["quantity"] for n in nests] == [10, 25]
        assert len({n["set_id"] for n in nests}) == 1
        assert [n["label"] for n in nests] == ["Nest #1", "Nest #2"]

        # deleting one nest of the set deletes the associated nests too (KB)
        assert (
            app_client.delete(f"/api/quotes/{quote_id}/nests/{nests[0]['id']}").status_code == 204
        )
        assert app_client.get(f"/api/quotes/{quote_id}/nesting").json()["nests"] == []


def test_stock_breaks_must_match_component_breaks(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "nest-break-mismatch")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10, 25])
        res = _create_nest(app_client, quote_id, [a["component_id"]], [{**STOCK, "quantity": 10}])
        assert res.status_code == 422


# --------------------------------------------------------------------------- #
# Locking (spec dialog warning; KB FAQ)
# --------------------------------------------------------------------------- #
def test_nested_component_locks_quantities_and_material_op(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "nest-locks")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10])
        assert (
            _create_nest(
                app_client, quote_id, [a["component_id"]], [{**STOCK, "quantity": 10}]
            ).status_code
            == 201
        )

        res = app_client.put(
            f"/api/quotes/{quote_id}/items/{a['item_id']}/quantities",
            json={"quantities": [10, 20]},
        )
        assert res.status_code == 409
        assert res.json()["code"] == "nest_locked"

        res = app_client.delete(f"/api/operations/{a['material_op_id']}")
        assert res.status_code == 409
        assert res.json()["code"] == "nest_locked"

        # Change Process would delete/orphan the nested router either way —
        # locked in both variants (fresh-eyes review)
        other_process = app_client.get("/api/processes").json()[0]["id"]
        for keep in (True, False):
            res = app_client.patch(
                f"/api/components/{a['component_id']}/process",
                json={"process_id": other_process, "keep_operations": keep},
            )
            assert res.status_code == 409
            assert res.json()["code"] == "nest_locked"

        # reassigning the material breaks the nest's same-material premise
        res = app_client.patch(
            f"/api/components/{a['component_id']}/material", json={"material_id": None}
        )
        assert res.status_code == 409
        assert res.json()["code"] == "nest_locked"

        # deleting the nest unlocks both
        nest_id = app_client.get(f"/api/quotes/{quote_id}/nesting").json()["nests"][0]["id"]
        app_client.delete(f"/api/quotes/{quote_id}/nests/{nest_id}")
        assert (
            app_client.put(
                f"/api/quotes/{quote_id}/items/{a['item_id']}/quantities",
                json={"quantities": [10, 20]},
            ).status_code
            == 200
        )


def test_partial_cost_distribution_rejected(app_client: TestClient, seeder: Seeder) -> None:
    """Explicit distribution percentages are all-or-none — a partial set would
    silently zero the unlisted components' material cost."""
    org, admin = _org_with_admin(seeder, "nest-partial-pct")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10])
        b = _sheet_line(app_client, quote_id, material, quantities=[10])
        res = app_client.post(
            f"/api/quotes/{quote_id}/nests",
            json={
                "component_ids": [a["component_id"], b["component_id"]],
                "stock": [{**STOCK, "quantity": 10}],
                "settings": SETTINGS,
                "component_settings": [
                    {"component_id": a["component_id"], "cost_distribution_pct": "60"}
                ],
            },
        )
        assert res.status_code == 422
        assert "percentage" in res.json()["message"].lower()


# --------------------------------------------------------------------------- #
# Kalk drawer feed — manual_nest() → the four Calculated/Override variables
# --------------------------------------------------------------------------- #
def test_manual_nest_feeds_drawer_variables_and_cost(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "nest-kalk")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10])
        create = _create_nest(
            app_client, quote_id, [a["component_id"]], [{**STOCK, "quantity": 10}]
        )
        assert create.status_code == 201
        [nest] = create.json()["nests"]
        allocated = Decimal(nest["result"]["components"][0]["allocated_cost"])

        # the drawer report carries the four variables with nest-fed values
        [report] = app_client.get(f"/api/operations/{a['material_op_id']}/kalk").json()
        declared = {v["name"]: v for v in report["declared_variables"]}
        assert set(declared) >= {"Sheet Cost", "# Of Sheets", "Parts Per Sheet", "Net Sheet Used"}
        assert declared["Sheet Cost"]["value"] == 250.0
        assert declared["# Of Sheets"]["value"] == nest["result"]["charged_sheets"]
        assert declared["Net Sheet Used"]["value"] == nest["result"]["net_sheet_used"]

        # the calc cell carries the allocated material cost (single component
        # -> 100 % share; float recomputation stays within a tenth of a cent)
        cell = _material_cell(app_client, a["component_id"], a["material_op_id"], 10)
        assert abs(Decimal(cell["calc_cost"]) - allocated) <= Decimal("0.001")

        # an override on "# Of Sheets" flows into COST (Calculated/Override)
        assert (
            app_client.put(
                f"/api/operations/{a['material_op_id']}/variables",
                json={"overrides": {"# Of Sheets": {"10": 2}}},
            ).status_code
            == 200
        )
        cell = _material_cell(app_client, a["component_id"], a["material_op_id"], 10)
        assert abs(Decimal(cell["calc_cost"]) - Decimal("500.00")) <= Decimal("0.001")


def test_manual_nest_without_nest_reports_not_nested(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "nest-kalk-none")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10])
        # no nest: the formula still evaluates — zero defaults, COST 0
        cell = _material_cell(app_client, a["component_id"], a["material_op_id"], 10)
        assert Decimal(cell["calc_cost"]) == Decimal("0")


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #
def test_nests_are_org_isolated(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_with_admin(seeder, "nest-org-a")
    seeder.configure_catalog(org_a)
    org_b, admin_b = _org_with_admin(seeder, "nest-org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        material = _material_id(app_client)
        a = _sheet_line(app_client, quote_id, material, quantities=[10])
        assert (
            _create_nest(
                app_client, quote_id, [a["component_id"]], [{**STOCK, "quantity": 10}]
            ).status_code
            == 201
        )
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        assert app_client.get(f"/api/quotes/{quote_id}/nesting").status_code == 404
