"""M4.10 — auto-routing: setting a process generates its default router.

Spec ``#assembly`` ("Setting a process generates its default router"; process
taxonomy) + KB ``custom-operation-generation``. Generic processes instantiate
their ``process_operation`` template rows honoring the §4 flags (per_setup /
is_assembly / root_component_only); a ``generation_formula`` process runs the
process-level Kalk instead. Generated rows carry ``origin='auto_routing'``
(block AC: imported/generated values carry their source) and per-setup rows
carry ``operation_properties.setup_index`` (the Kalk ``INDEX`` wiring).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import MembershipRole

from .conftest import Seeder, authed

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]


def _org_admin(seeder: Seeder, slug: str = "route-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_item(client: TestClient) -> dict[str, str]:
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    return {
        "quote_id": qid,
        "item_id": str(item["id"]),
        "part_id": str(item["part_id"]),
        "component_id": str(item["root_component_id"]),
    }


def _process_id(client: TestClient, name: str) -> str:
    processes = client.get("/api/processes").json()
    return str(next(p["id"] for p in processes if p["name"] == name))


def _ops(client: TestClient, component_id: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = client.get(f"/api/components/{component_id}/costing").json()[
        "operations"
    ]
    return ops


def _set_process(
    client: TestClient, component_id: str, process_id: str, *, keep: bool = False
) -> None:
    res = client.patch(
        f"/api/components/{component_id}/process",
        json={"process_id": process_id, "keep_operations": keep},
    )
    assert res.status_code == 200, res.text


# --------------------------------------------------------------------------- #
# Generic template instantiation
# --------------------------------------------------------------------------- #
def test_set_process_generates_default_router(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "route-generic")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        _set_process(app_client, ids["component_id"], _process_id(app_client, "Tube Laser"))
        ops = _ops(app_client, ids["component_id"])
    # the seeded Tube Laser router: material line + cut + deburr, in order
    assert [op["name"] for op in ops] == [
        "Material | Bar (Round)",
        "Laserschneiden Rohr",
        "Entgraten",
    ]


def test_generated_ops_carry_source(seeder: Seeder, app_client: TestClient) -> None:
    # block AC: generated values carry their source — origin='auto_routing',
    # while a manual add stays origin='manual'
    org, admin = _org_admin(seeder, "route-origin")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        _set_process(app_client, ids["component_id"], _process_id(app_client, "Tube Laser"))
        created = app_client.post(
            f"/api/components/{ids['component_id']}/operations", json={"name": "Handarbeit"}
        )
        assert created.status_code == 201, created.text
        ops = _ops(app_client, ids["component_id"])
    origins = {op["name"]: op["origin"] for op in ops}
    assert origins["Laserschneiden Rohr"] == "auto_routing"
    assert origins["Handarbeit"] == "manual"


def test_change_process_regenerates_router(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "route-change")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        _set_process(app_client, ids["component_id"], _process_id(app_client, "Tube Laser"))
        # UPDATE (keep_operations=False): deletes the old router, generates anew
        _set_process(app_client, ids["component_id"], _process_id(app_client, "Sheet Metal"))
        ops = _ops(app_client, ids["component_id"])
    assert [op["name"] for op in ops] == [
        "Material | Sheet (Nesting)",
        "Laserschneiden Blech",
        "Kanten",
        "Entgraten",
    ]


def test_keep_existing_ops_skips_generation(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "route-keep")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        created = app_client.post(
            f"/api/components/{ids['component_id']}/operations", json={"name": "Handarbeit"}
        )
        assert created.status_code == 201, created.text
        # UPDATE AND KEEP EXISTING OPS: process changes, router untouched
        _set_process(
            app_client, ids["component_id"], _process_id(app_client, "Tube Laser"), keep=True
        )
        ops = _ops(app_client, ids["component_id"])
    assert [op["name"] for op in ops] == ["Handarbeit"]


def test_root_only_and_assembly_flags(seeder: Seeder, app_client: TestClient) -> None:
    """Assembly | Parent-Level routes only on assembly roots: a plain child
    component with the same process generates nothing from flagged rows."""
    org, admin = _org_admin(seeder, "route-flags")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        # make the root an assembly (the BOM publish path does this for real)
        seeder.sql(
            "UPDATE component SET is_assembly = true WHERE id = :id",
            {"id": ids["component_id"]},
        )
        _set_process(
            app_client, ids["component_id"], _process_id(app_client, "Assembly | Parent-Level")
        )
        root_ops = _ops(app_client, ids["component_id"])

        # a non-root, non-assembly child published under the root part's tree
        child_part = seeder.part(org)
        child_component = uuid.uuid4()
        seeder.sql(
            """
            INSERT INTO component (id, org_id, part_id, is_root_component)
            VALUES (:id, :org, :part, false)
            """,
            {"id": child_component, "org": org, "part": child_part},
        )
        root_node = uuid.uuid4()
        seeder.sql(
            """
            INSERT INTO node (id, org_id, part_id, root_part_id, qty_relative_to_parent)
            VALUES (:id, :org, :part, :part, 1)
            """,
            {"id": root_node, "org": org, "part": uuid.UUID(ids["part_id"])},
        )
        seeder.sql(
            """
            INSERT INTO node
                (id, org_id, part_id, parent_node_id, root_part_id, qty_relative_to_parent)
            VALUES (:id, :org, :part, :parent, :root_part, 2)
            """,
            {
                "id": uuid.uuid4(),
                "org": org,
                "part": child_part,
                "parent": root_node,
                "root_part": uuid.UUID(ids["part_id"]),
            },
        )
        _set_process(
            app_client, str(child_component), _process_id(app_client, "Assembly | Parent-Level")
        )
        child_ops = _ops(app_client, str(child_component))

    # root assembly: both flagged template rows instantiate
    assert [op["name"] for op in root_ops] == ["Assembly | Manufactured", "Generic | Shipping Prep"]
    # non-root non-assembly: is_assembly row AND root_component_only row skip
    assert child_ops == []


def test_per_setup_row_instantiates_per_setup_count(seeder: Seeder, app_client: TestClient) -> None:
    """A per_setup template row (Fräsen) becomes one op per detected setup,
    each carrying its 0-based ``setup_index`` (the Kalk INDEX wiring)."""
    org, admin = _org_admin(seeder, "route-setups")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        file_id = seeder.part_file(org, uuid.UUID(ids["part_id"]), "block.step")
        seeder.sql(
            """
            INSERT INTO interrogation_run
                (id, org_id, part_id, file_id, family, status, result)
            VALUES
                (:id, :org, :part, :file, 'MILLING', 'succeeded', CAST(:result AS jsonb))
            """,
            {
                "id": uuid.uuid4(),
                "org": org,
                "part": uuid.UUID(ids["part_id"]),
                "file": file_id,
                "result": json.dumps({"family_scalars": {"setup_count": 3}}),
            },
        )
        _set_process(app_client, ids["component_id"], _process_id(app_client, "Milling"))
        ops = _ops(app_client, ids["component_id"])
    names = [op["name"] for op in ops]
    assert names.count("Fräsen") == 3
    # order holds: material first, the setup instances together, then the rest
    assert names[0] == "Material | Bar (Round)"
    assert names[-2:] == ["Entgraten", "Verpacken/Kontrollieren"]


def test_per_setup_defaults_to_one_without_interrogation(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, admin = _org_admin(seeder, "route-nosetup")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        _set_process(app_client, ids["component_id"], _process_id(app_client, "Milling"))
        ops = _ops(app_client, ids["component_id"])
    assert [op["name"] for op in ops].count("Fräsen") == 1


# --------------------------------------------------------------------------- #
# Custom process — generation_formula
# --------------------------------------------------------------------------- #
def test_generation_formula_routes_by_custom_attribute(
    seeder: Seeder, app_client: TestClient
) -> None:
    """The KB lathe example, non-geometric path: a custom attribute picks the
    workcenter; custom_name + operation_properties persist on the router row."""
    org, admin = _org_admin(seeder, "route-custom")
    seeder.configure_catalog(org)
    formula = (
        "generate_operation('Drehen', custom_name='Kleine Drehbank',"
        " operation_properties={'wc': 'DB-2'})\n"
        "generate_operation('Entgraten')\n"
    )
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        process_id = _process_id(app_client, "Lathe")
        seeder.sql(
            "UPDATE process SET generation_formula = :f WHERE id = :id",
            {"f": formula, "id": uuid.UUID(process_id)},
        )
        _set_process(app_client, ids["component_id"], process_id)
        ops = _ops(app_client, ids["component_id"])
    assert [op["name"] for op in ops] == ["Kleine Drehbank", "Entgraten"]


def test_generation_formula_error_surfaces(seeder: Seeder, app_client: TestClient) -> None:
    """A broken formula must fail the process change loudly — never publish a
    half-generated router."""
    org, admin = _org_admin(seeder, "route-broken")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        process_id = _process_id(app_client, "Lathe")
        seeder.sql(
            "UPDATE process SET generation_formula = :f WHERE id = :id",
            {"f": "generate_operation('Not In Library')\n", "id": uuid.UUID(process_id)},
        )
        res = app_client.patch(
            f"/api/components/{ids['component_id']}/process",
            json={"process_id": process_id, "keep_operations": False},
        )
        assert res.status_code == 422, res.text
        # the failed change kept the component un-routed (transaction rolled back)
        ops = _ops(app_client, ids["component_id"])
    assert ops == []
