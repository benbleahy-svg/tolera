"""M4.10 — Assembly Components API: listing + rollup, bulk edit, reorder,
copy pricing, delete, add-purchased.

Spec ``#assembly`` + ``#assemblies-model``: CHILD BOM shows rollup cost to
parent (subtree), FLAT BOM shows cost without rollup + derived Flat Qty;
child costs roll up to the root component per break (block AC 1). Bulk
Update deletes existing operations and regenerates the router from the new
process (DemoM/15). Reorder is single-level only (DemoM/04).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import MembershipRole

from .conftest import Seeder, authed

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]


def _org_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_item(client: TestClient, quantities: list[int] | None = None) -> dict[str, str]:
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    if quantities:
        res = client.put(
            f"/api/quotes/{qid}/items/{item['id']}/quantities", json={"quantities": quantities}
        )
        assert res.status_code == 200, res.text
    return {
        "quote_id": qid,
        "item_id": str(item["id"]),
        "part_id": str(item["part_id"]),
        "component_id": str(item["root_component_id"]),
    }


def _plant_child(
    seeder: Seeder,
    org: uuid.UUID,
    root_part_id: str,
    *,
    parent_node_id: uuid.UUID | None = None,
    part_number: str | None = None,
    qty: int = 1,
    position: int = 0,
    is_assembly: bool = False,
    obtain_method: str = "MANUFACTURED",
    piece_price: str | None = None,
    manual_override_cost: str | None = None,
) -> dict[str, uuid.UUID]:
    """Plant part + component + node (the published M4.9 shape)."""
    part = seeder.part(org)
    if part_number:
        seeder.sql(
            "UPDATE part SET part_number = :pn, is_assembly = :asm WHERE id = :id",
            {"pn": part_number, "asm": is_assembly, "id": part},
        )
    component = uuid.uuid4()
    seeder.sql(
        """
        INSERT INTO component
            (id, org_id, part_id, is_root_component, is_assembly, obtain_method,
             piece_price, manual_override_cost)
        VALUES
            (:id, :org, :part, false, :asm, :obtain,
             CAST(:pp AS numeric), CAST(:moc AS numeric))
        """,
        {
            "id": component,
            "org": org,
            "part": part,
            "asm": is_assembly,
            "obtain": obtain_method,
            "pp": piece_price,
            "moc": manual_override_cost,
        },
    )
    root_node = uuid.uuid4()
    seeder.sql(
        """
        INSERT INTO node (id, org_id, part_id, root_part_id, qty_relative_to_parent)
        SELECT :id, :org, :part, :part, 1
        WHERE NOT EXISTS (
            SELECT 1 FROM node WHERE part_id = :part AND parent_node_id IS NULL
        )
        """,
        {"id": root_node, "org": org, "part": uuid.UUID(root_part_id)},
    )
    node = uuid.uuid4()
    seeder.sql(
        """
        INSERT INTO node
            (id, org_id, part_id, parent_node_id, root_part_id,
             qty_relative_to_parent, position)
        SELECT :id, :org, :part,
               COALESCE(
                   CAST(:parent AS uuid),
                   (SELECT id FROM node WHERE part_id = :root_part AND parent_node_id IS NULL)
               ),
               :root_part, :qty, :position
        """,
        {
            "id": node,
            "org": org,
            "part": part,
            "parent": parent_node_id,
            "root_part": uuid.UUID(root_part_id),
            "qty": qty,
            "position": position,
        },
    )
    return {"part": part, "component": component, "node": node}


def _listing(client: TestClient, item_id: str) -> dict[str, Any]:
    res = client.get(f"/api/quote-items/{item_id}/assembly-components")
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()
    return out


# --------------------------------------------------------------------------- #
# Listing + rollup (block AC 1)
# --------------------------------------------------------------------------- #
def test_listing_groups_quantities_and_rollup(seeder: Seeder, app_client: TestClient) -> None:
    """Root breaks [1, 5]; child A (manufactured, override 2.00/unit, node qty
    2); sub-assembly S (node qty 1) holding purchased B (0.10, node qty 4).

    Rollup (CHILD BOM, per break): A = 2.00 x 2 x q; S = 0.10 x 4 x q.
    Component Summary total @1 = 4.40, @5 = 22.00 — child costs roll up to
    the root per quantity (the acceptance criterion)."""
    org, admin = _org_admin(seeder, "asm-listing")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client, quantities=[1, 5])
        _plant_child(
            seeder,
            org,
            ids["part_id"],
            part_number="A-1",
            qty=2,
            position=0,
            manual_override_cost="2.0000",
        )
        s = _plant_child(
            seeder,
            org,
            ids["part_id"],
            part_number="S-1",
            qty=1,
            position=1,
            is_assembly=True,
        )
        _plant_child(
            seeder,
            org,
            ids["part_id"],
            parent_node_id=s["node"],
            part_number="B-1",
            qty=4,
            obtain_method="PURCHASED",
            piece_price="0.1000",
        )
        out = _listing(app_client, ids["item_id"])

    assert out["quantities"] == [1, 5]
    rows = {r["part_number"]: r for r in out["tree"]}
    assert rows["A-1"]["group"] == "manufactured"
    assert rows["A-1"]["node_qty"] == 2
    assert rows["A-1"]["flat_qty"] == 2
    assert rows["A-1"]["rollup_costs"] == ["4.00", "20.00"]
    assert rows["S-1"]["group"] == "subassembly"
    assert rows["S-1"]["rollup_costs"] == ["0.40", "2.00"]
    b_row = rows["S-1"]["children"][0]
    assert b_row["group"] == "purchased"
    assert b_row["flat_qty"] == 4
    assert b_row["rollup_costs"] == ["0.40", "2.00"]
    assert out["summary"]["flat_qty_total"] == 7  # 2 + 1 + 4
    assert out["summary"]["totals"] == ["4.40", "22.00"]


# --------------------------------------------------------------------------- #
# Bulk Update Components (DemoM/15)
# --------------------------------------------------------------------------- #
def test_bulk_update_regenerates_routers(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "asm-bulk")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        a = _plant_child(seeder, org, ids["part_id"], part_number="A-1", position=0)
        b = _plant_child(seeder, org, ids["part_id"], part_number="B-1", position=1)
        # a pre-existing manual op on A that the bulk update must delete
        created = app_client.post(
            f"/api/components/{a['component']}/operations", json={"name": "Handarbeit"}
        )
        assert created.status_code == 201, created.text
        process_id = next(
            p["id"] for p in app_client.get("/api/processes").json() if p["name"] == "Tube Laser"
        )
        res = app_client.post(
            "/api/components/bulk-update",
            json={
                "component_ids": [str(a["component"]), str(b["component"])],
                "process_id": process_id,
            },
        )
        assert res.status_code == 200, res.text
        assert res.json()["updated"] == 2
        for cid in (a["component"], b["component"]):
            ops = app_client.get(f"/api/components/{cid}/costing").json()["operations"]
            assert [op["name"] for op in ops] == [
                "Material | Bar (Round)",
                "Laserschneiden Rohr",
                "Entgraten",
            ]
            assert {op["origin"] for op in ops} == {"auto_routing"}


# --------------------------------------------------------------------------- #
# Reorder (single level)
# --------------------------------------------------------------------------- #
def test_reorder_single_level(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "asm-reorder")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        a = _plant_child(seeder, org, ids["part_id"], part_number="A-1", position=0)
        b = _plant_child(seeder, org, ids["part_id"], part_number="B-1", position=1)
        c = _plant_child(seeder, org, ids["part_id"], part_number="C-1", position=2)
        out = _listing(app_client, ids["item_id"])
        res = app_client.post(
            f"/api/quote-items/{ids['item_id']}/assembly-components/reorder",
            json={
                "parent_node_id": _root_node_id(seeder, out),
                "ordered_node_ids": [str(c["node"]), str(a["node"]), str(b["node"])],
            },
        )
        assert res.status_code == 200, res.text
        after = _listing(app_client, ids["item_id"])
    assert [r["part_number"] for r in after["tree"]] == ["C-1", "A-1", "B-1"]

    # a partial list (cross-level or missing sibling) is rejected
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = app_client.post(
            f"/api/quote-items/{ids['item_id']}/assembly-components/reorder",
            json={
                "parent_node_id": _root_node_id(seeder, after),
                "ordered_node_ids": [str(a["node"])],
            },
        )
        assert res.status_code == 422


def _root_node_id(seeder: Seeder, listing: dict[str, Any]) -> str:
    del seeder
    # every top-level row shares the same parent: derive from any child row by
    # convention — the reorder API wants the parent node id, which the listing
    # doesn't carry per row; the root node's id equals the parent of tree[0].
    return listing["root_node_id"]  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- #
# Copy pricing (one source → one target)
# --------------------------------------------------------------------------- #
def test_copy_pricing_material_and_operations(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "asm-copy")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        src = _plant_child(seeder, org, ids["part_id"], part_number="L-1", position=0)
        dst = _plant_child(seeder, org, ids["part_id"], part_number="R-1", position=1)
        created = app_client.post(
            f"/api/components/{src['component']}/operations", json={"name": "Fräsen links"}
        )
        assert created.status_code == 201, created.text
        res = app_client.post(
            f"/api/components/{src['component']}/copy-pricing",
            json={"target_component_id": str(dst["component"])},
        )
        assert res.status_code == 200, res.text
        assert res.json()["copied_operations"] == 1
        ops = app_client.get(f"/api/components/{dst['component']}/costing").json()["operations"]
    assert [op["name"] for op in ops] == ["Fräsen links"]


# --------------------------------------------------------------------------- #
# Delete component
# --------------------------------------------------------------------------- #
def test_delete_component_removes_subtree(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "asm-delete")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client, quantities=[1])
        s = _plant_child(
            seeder, org, ids["part_id"], part_number="S-1", position=0, is_assembly=True
        )
        _plant_child(
            seeder,
            org,
            ids["part_id"],
            parent_node_id=s["node"],
            part_number="B-1",
            qty=4,
            obtain_method="PURCHASED",
            piece_price="0.1000",
        )
        # reprice once so the planted children land in the persisted cells
        res = app_client.put(
            f"/api/quotes/{ids['quote_id']}/items/{ids['item_id']}/quantities",
            json={"quantities": [1]},
        )
        assert res.status_code == 200, res.text
        # the purchased grandchild prices into the root before the delete
        pricing = app_client.get(f"/api/components/{ids['component_id']}/pricing").json()
        before = next(c for c in pricing["costing"] if c["quantity"] == 1)
        assert before["purchased_component"] == "0.4000"
        res = app_client.delete(f"/api/components/{s['component']}")
        assert res.status_code == 200, res.text
        after = _listing(app_client, ids["item_id"])
        # review fix: the delete itself reprices the root — no stale cost
        pricing = app_client.get(f"/api/components/{ids['component_id']}/pricing").json()
        emptied = next(c for c in pricing["costing"] if c["quantity"] == 1)
        assert emptied["purchased_component"] in ("0.0000", "0")
    assert after["tree"] == []

    # the root component itself is not deletable here
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = app_client.delete(f"/api/components/{ids['component_id']}")
        assert res.status_code == 422


# --------------------------------------------------------------------------- #
# ADD PURCHASED COMPONENTS
# --------------------------------------------------------------------------- #
def test_add_purchased_components_from_library(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "asm-add-pc")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pc = app_client.post(
            "/api/purchased-components",
            json={"oem_part_number": "F-440-1", "piece_price": "0.1250", "brand": "PEM"},
        ).json()
        ids = _new_item(app_client, quantities=[10])
        res = app_client.post(
            f"/api/quote-items/{ids['item_id']}/purchased-components",
            json={"items": [{"purchased_component_id": pc["id"], "node_qty": 6}]},
        )
        assert res.status_code == 200, res.text
        out = _listing(app_client, ids["item_id"])
    row = out["tree"][0]
    assert row["group"] == "purchased"
    assert row["part_number"] == "F-440-1"
    assert row["brand"] == "PEM"
    assert row["node_qty"] == 6
    assert row["piece_price"] == "0.1250"
    # 0.125 x 6 x 10 = 7.50 rolled up at the break
    assert row["rollup_costs"] == ["7.50"]


# --------------------------------------------------------------------------- #
# Assembly | Parent-Level auto-assignment on publish (spec #assembly)
# --------------------------------------------------------------------------- #
def test_publish_assigns_parent_level_process(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "asm-parent-level")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        res = app_client.post(
            f"/api/quote-items/{ids['item_id']}/bom-builder/publish",
            json={
                "payload": {
                    "schema_version": 1,
                    "root": {
                        "row_id": "root",
                        "row_type": "assembly_root",
                        "part_number": "ASM-9",
                        "qty": 1,
                        "children": [
                            {
                                "row_id": "r1",
                                "row_type": "manufactured",
                                "part_number": "M-1",
                                "qty": 2,
                            }
                        ],
                    },
                }
            },
        )
        assert res.status_code == 200, res.text
        ops = app_client.get(f"/api/components/{ids['component_id']}/costing").json()["operations"]
    # the flagged template rows instantiate on the assembly root
    assert [op["name"] for op in ops] == ["Assembly | Manufactured", "Generic | Shipping Prep"]
    assert {op["origin"] for op in ops} == {"auto_routing"}
