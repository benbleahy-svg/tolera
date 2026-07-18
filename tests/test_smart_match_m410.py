"""M4.10 — PC library, Smart Match, convert-to-purchased, geometry memory.

Spec ``#assembly`` (Convert to Purchased Component / Persistent geometry
memory) + DOMAIN-MODEL §5 ``PurchasedComponent`` + KB ``purchased-components``.
The match tiers mirror DemoL/03: OEM Part Number Match · OEM Geometric Match ·
Historical Geometric Match (N). Convert freezes ``piece_price`` onto the
component (E4-d) and records the org-level geometry→PC memory; the same
signature auto-tags on the next interrogation (block AC: "no re-convert").
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

GEOM = "gs1:" + "ab" * 32


def _org_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
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


def _child_component(
    seeder: Seeder,
    org: uuid.UUID,
    root_part_id: str,
    *,
    part_number: str | None = None,
    geom_hash: str | None = None,
    qty: int = 1,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Plant a published manufactured child (part + component + node) under
    the root part — the M4.9 publish shape."""
    part = seeder.part(org)
    if part_number or geom_hash:
        seeder.sql(
            "UPDATE part SET part_number = :pn, geom_hash = :gh WHERE id = :id",
            {"pn": part_number, "gh": geom_hash, "id": part},
        )
    component = uuid.uuid4()
    seeder.sql(
        """
        INSERT INTO component (id, org_id, part_id, is_root_component)
        VALUES (:id, :org, :part, false)
        """,
        {"id": component, "org": org, "part": part},
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
    seeder.sql(
        """
        INSERT INTO node
            (id, org_id, part_id, parent_node_id, root_part_id, qty_relative_to_parent)
        SELECT :id, :org, :part,
               (SELECT id FROM node WHERE part_id = :root_part AND parent_node_id IS NULL),
               :root_part, :qty
        """,
        {
            "id": uuid.uuid4(),
            "org": org,
            "part": part,
            "root_part": uuid.UUID(root_part_id),
            "qty": qty,
        },
    )
    return part, component


def _create_pc(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload = {
        "oem_part_number": "F-440-1",
        "internal_part_number": "f-440-1",
        "piece_price": "0.1250",
        "description": "PEM Einpressmutter F-440",
        "brand": "PEM",
        **overrides,
    }
    res = client.post("/api/purchased-components", json=payload)
    assert res.status_code == 201, res.text
    out: dict[str, Any] = res.json()
    return out


# --------------------------------------------------------------------------- #
# Library CRUD + tenancy
# --------------------------------------------------------------------------- #
def test_library_create_and_list(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "pc-crud")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        created = _create_pc(app_client)
        assert created["piece_price"] == "0.1250"
        assert created["currency"] == "EUR"
        listed = app_client.get("/api/purchased-components").json()
        assert [pc["oem_part_number"] for pc in listed] == ["F-440-1"]
        # search hits OEM + internal part numbers
        assert app_client.get("/api/purchased-components", params={"q": "f-440"}).json()
        assert app_client.get("/api/purchased-components", params={"q": "zzz"}).json() == []


def test_library_is_org_scoped(seeder: Seeder, app_client: TestClient) -> None:
    org_a, admin_a = _org_admin(seeder, "pc-org-a")
    org_b, admin_b = _org_admin(seeder, "pc-org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        _create_pc(app_client)
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        assert app_client.get("/api/purchased-components").json() == []


# --------------------------------------------------------------------------- #
# Smart Match indicators (DemoL/03)
# --------------------------------------------------------------------------- #
def test_purchase_matches_part_number_tier(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "pc-match-pn")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pc = _create_pc(app_client)
        _create_pc(
            app_client,
            oem_part_number="CLS-440-2",
            internal_part_number="cls-440-2",
            description="andere",
        )
        ids = _new_item(app_client)
        _part, component = _child_component(seeder, org, ids["part_id"], part_number="F-440-1")
        matches = app_client.get(f"/api/components/{component}/purchase-matches").json()
    smart = matches["smart"]
    assert [m["purchased_component"]["id"] for m in smart] == [pc["id"]]
    assert smart[0]["oem_part_number_match"] is True
    assert smart[0]["oem_geometric_match"] is False
    assert smart[0]["historical_geometric_matches"] == 0
    # the All tab carries the whole library
    assert len(matches["all"]) == 2


def test_purchase_matches_historical_and_unlinked_oem(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, admin = _org_admin(seeder, "pc-match-geo")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pc = _create_pc(app_client)
        ids = _new_item(app_client)
        _part, component = _child_component(seeder, org, ids["part_id"], geom_hash=GEOM)
        # planted history: this geometry was matched to the PC 21 times before
        seeder.sql(
            """
            INSERT INTO pc_geometry_memory
                (id, org_id, geom_hash, purchased_component_id, match_count)
            VALUES (:id, :org, :gh, :pc, 21)
            """,
            {"id": uuid.uuid4(), "org": org, "gh": GEOM, "pc": uuid.UUID(pc["id"])},
        )
        # an OEM-catalog product with the same geometry, not yet in the library
        seeder.sql(
            """
            INSERT INTO oem_product (id, org_id, brand, oem_part_number, geom_hash)
            VALUES (:id, :org, 'PEM', 'F4-440-1', :gh)
            """,
            {"id": uuid.uuid4(), "org": org, "gh": GEOM},
        )
        matches = app_client.get(f"/api/components/{component}/purchase-matches").json()
    smart = matches["smart"]
    assert smart[0]["purchased_component"]["id"] == pc["id"]
    assert smart[0]["historical_geometric_matches"] == 21
    assert [p["oem_part_number"] for p in matches["unlinked_oem"]] == ["F4-440-1"]


# --------------------------------------------------------------------------- #
# Convert
# --------------------------------------------------------------------------- #
def test_convert_links_freezes_price_and_records_memory(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, admin = _org_admin(seeder, "pc-convert")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pc = _create_pc(app_client)
        ids = _new_item(app_client)
        _part, component = _child_component(seeder, org, ids["part_id"], geom_hash=GEOM, qty=4)
        res = app_client.post(
            f"/api/components/{component}/convert-to-purchased",
            json={"purchased_component_id": pc["id"]},
        )
        assert res.status_code == 200, res.text
        out = res.json()
        assert out["obtain_method"] == "PURCHASED"
        assert out["purchased_component_id"] == pc["id"]
        assert out["piece_price"] == "0.1250"

        # library price edits later never touch the frozen component price
        # (E4-d config-freeze) — asserted via a re-read after a library PATCH
        patched = app_client.patch(
            f"/api/purchased-components/{pc['id']}", json={"piece_price": "9.9900"}
        )
        assert patched.status_code == 200, patched.text
        matches = app_client.get(f"/api/components/{component}/purchase-matches").json()
        assert matches["component"]["piece_price"] == "0.1250"

        # memory: converting again from a second component increments the count
        _part2, component2 = _child_component(seeder, org, ids["part_id"], geom_hash=GEOM)
        res2 = app_client.post(
            f"/api/components/{component2}/convert-to-purchased",
            json={"purchased_component_id": pc["id"]},
        )
        assert res2.status_code == 200, res2.text
        matches2 = app_client.get(f"/api/components/{component2}/purchase-matches").json()
    assert matches2["smart"][0]["historical_geometric_matches"] == 2


def test_convert_with_create_new_fallback(seeder: Seeder, app_client: TestClient) -> None:
    # DemoL/03 "Create New Component": no match → create the library entry
    # inline and convert in one act
    org, admin = _org_admin(seeder, "pc-create-new")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        _part, component = _child_component(seeder, org, ids["part_id"])
        res = app_client.post(
            f"/api/components/{component}/convert-to-purchased",
            json={
                "create": {
                    "oem_part_number": "DIN-912-M4x10",
                    "piece_price": "0.0500",
                    "description": "Zylinderschraube",
                }
            },
        )
        assert res.status_code == 200, res.text
        listed = app_client.get("/api/purchased-components").json()
    assert [pc["oem_part_number"] for pc in listed] == ["DIN-912-M4x10"]
    assert res.json()["piece_price"] == "0.0500"


def test_convert_rejects_assembly_and_cross_org(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "pc-convert-guards")
    org_b, admin_b = _org_admin(seeder, "pc-convert-other")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pc = _create_pc(app_client)
        ids = _new_item(app_client)
        _part, component = _child_component(seeder, org, ids["part_id"])
        seeder.sql("UPDATE component SET is_assembly = true WHERE id = :id", {"id": component})
        res = app_client.post(
            f"/api/components/{component}/convert-to-purchased",
            json={"purchased_component_id": pc["id"]},
        )
        assert res.status_code == 422
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        res = app_client.post(
            f"/api/components/{component}/convert-to-purchased",
            json={"purchased_component_id": pc["id"]},
        )
        assert res.status_code == 404


# --------------------------------------------------------------------------- #
# Persistent auto-tag (block AC: second quote, no re-convert)
# --------------------------------------------------------------------------- #
def test_memory_auto_tags_on_interrogation(seeder: Seeder, app_client: TestClient) -> None:
    """The acceptance path: once a geometry is converted, a NEW part with the
    same signature is auto-tagged purchased when its signature lands (the
    interrogation-success hook) — the estimator never re-converts."""
    from app.purchased_components import apply_purchased_memory_by_hash

    org, admin = _org_admin(seeder, "pc-auto-tag")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pc = _create_pc(app_client)
        ids = _new_item(app_client)
        _part, component = _child_component(seeder, org, ids["part_id"], geom_hash=GEOM)
        assert (
            app_client.post(
                f"/api/components/{component}/convert-to-purchased",
                json={"purchased_component_id": pc["id"]},
            ).status_code
            == 200
        )

        # a second quote: same fastener geometry arrives as a manufactured child
        ids2 = _new_item(app_client)
        part2, component2 = _child_component(seeder, org, ids2["part_id"], geom_hash=GEOM)
        # the interrogation-success hook fires with the computed signature
        from sqlalchemy.ext.asyncio import AsyncSession

        async def hook() -> None:
            engine = seeder._engine
            async with AsyncSession(engine) as session, session.begin():
                await apply_purchased_memory_by_hash(
                    session, org_id=org, part_id=part2, geom_hash=GEOM
                )

        seeder._loop.run_until_complete(hook())

        matches = app_client.get(f"/api/components/{component2}/purchase-matches").json()
    assert matches["component"]["obtain_method"] == "PURCHASED"
    assert matches["component"]["purchased_component_id"] == pc["id"]
    assert matches["component"]["piece_price"] == "0.1250"
    # the auto-tag itself counted as a historical match
    assert matches["smart"][0]["historical_geometric_matches"] >= 2


# --------------------------------------------------------------------------- #
# BOM-Builder publish tightening (D34: purchased rows tie to the library)
# --------------------------------------------------------------------------- #
def _bom_doc(*children: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "root": {
            "row_id": "root",
            "row_type": "assembly_root",
            "part_number": "ASM-1",
            "qty": 1,
            "children": list(children),
        },
    }


def test_publish_auto_links_and_blocks_unassigned(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_admin(seeder, "pc-publish-tight")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pc = _create_pc(app_client)
        ids = _new_item(app_client)

        # unassigned + no name match → blocking error (the library has records)
        res = app_client.post(
            f"/api/quote-items/{ids['item_id']}/bom-builder/publish",
            json={
                "payload": _bom_doc(
                    {"row_id": "r1", "row_type": "purchased", "part_number": "UNKNOWN-9", "qty": 2}
                )
            },
        )
        assert res.status_code == 409, res.text
        codes = {e["code"] for e in res.json()["details"]["errors"]}
        assert "purchased_unassigned" in codes

        # exact part-number match auto-links (KB purchased-components note)
        res = app_client.post(
            f"/api/quote-items/{ids['item_id']}/bom-builder/publish",
            json={
                "payload": _bom_doc(
                    {"row_id": "r1", "row_type": "purchased", "part_number": "F-440-1", "qty": 2}
                )
            },
        )
        assert res.status_code == 200, res.text
        child = res.json()["tree"]["children"][0]
        matches = app_client.get(f"/api/components/{child['component_id']}/purchase-matches").json()
    assert matches["component"]["purchased_component_id"] == pc["id"]
    assert matches["component"]["piece_price"] == "0.1250"


def test_publish_unassigned_stays_notice_while_library_empty(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, admin = _org_admin(seeder, "pc-publish-loose")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _new_item(app_client)
        doc = _bom_doc(
            {"row_id": "r1", "row_type": "purchased", "part_number": "UNKNOWN-9", "qty": 2}
        )
        check = app_client.post(
            f"/api/quote-items/{ids['item_id']}/bom-builder/check", json={"payload": doc}
        )
        assert check.status_code == 200, check.text
        assert "purchased_unassigned" in {n["code"] for n in check.json()["notices"]}
        assert check.json()["errors"] == []
        res = app_client.post(
            f"/api/quote-items/{ids['item_id']}/bom-builder/publish", json={"payload": doc}
        )
        assert res.status_code == 200, res.text
