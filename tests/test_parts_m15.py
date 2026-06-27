"""API/DB tests for the M1.5 4-layer model — part identity, manual geometry
(math/unit auto-eval, metric storage), the BOM tree query, the export-controlled
flag, and org isolation. Runs against a real RLS-bound Postgres (``app_client``);
the dimension parser itself is unit-tested in ``test_dimensions.py``.

Acceptance (build-plan M1.5): a quote item maps to a root component; the BOM tree
query returns the hierarchy; manual dims persist with units; ``2.27 + .359`` and
``1 meter`` auto-evaluate; the ITAR/EU-dual-use flag persists.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
ENGINEER = [MembershipRole.engineer]  # has no quote_edit (read+annotate only, M0.3)


def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _create_part(client: TestClient) -> Any:
    res = client.post("/api/parts")
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# Part creation → 4-layer defaults + root node
# --------------------------------------------------------------------------- #
def test_create_part_defaults_and_root_node(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part = _create_part(app_client)
        pid = part["id"]
        bom = app_client.get(f"/api/parts/{pid}/bom").json()
    assert part["obtain_method"] == "MANUFACTURED"
    assert part["is_assembly"] is False
    assert part["export_controlled"] is False
    assert part["part_number"] is None
    # BOM tree: a single root node for the new part.
    assert bom["part_id"] == pid
    assert bom["is_root"] is True
    assert bom["qty_relative_to_parent"] == 1
    assert bom["children"] == []


# --------------------------------------------------------------------------- #
# Identity + flags persist
# --------------------------------------------------------------------------- #
def test_patch_part_identity_persists(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        res = app_client.patch(
            f"/api/parts/{pid}",
            json={
                "name": "Halterung",
                "part_number": "BR-1001",
                "revision": "C",
                "description": "Edelstahl-Halter",
                "is_assembly": True,
                "obtain_method": "PURCHASED",
            },
        )
        assert res.status_code == 200, res.text
        got = app_client.get(f"/api/parts/{pid}").json()
    assert got["name"] == "Halterung"
    assert got["part_number"] == "BR-1001"
    assert got["revision"] == "C"
    assert got["description"] == "Edelstahl-Halter"
    assert got["is_assembly"] is True
    assert got["obtain_method"] == "PURCHASED"


def test_export_controlled_flag_persists(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        app_client.patch(f"/api/parts/{pid}", json={"export_controlled": True})
        got = app_client.get(f"/api/parts/{pid}").json()
    assert got["export_controlled"] is True


def test_patch_rejects_unknown_field(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        res = app_client.patch(f"/api/parts/{pid}", json={"bogus": 1})
    assert res.status_code == 422


def test_patch_rejects_null_on_not_null_flag(app_client: TestClient, seeder: Seeder) -> None:
    # is_assembly/obtain_method/export_controlled are NOT NULL — an explicit null is a
    # clean 422, not a leaked 500 (clearing identity fields with null is still allowed).
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        res = app_client.patch(f"/api/parts/{pid}", json={"is_assembly": None})
        cleared = app_client.patch(f"/api/parts/{pid}", json={"part_number": None})
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_value"
    assert cleared.status_code == 200  # nullable identity field clears fine


# --------------------------------------------------------------------------- #
# Manual geometry — metric storage + math/unit auto-evaluation
# --------------------------------------------------------------------------- #
def _set_geom(client: TestClient, pid: str, **body: Any) -> Any:
    return client.patch(f"/api/parts/{pid}/geometry", json=body)


def test_manual_dims_persist_as_metric(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        res = _set_geom(app_client, pid, size_x=10, size_y=20, size_z=5)
        assert res.status_code == 200, res.text
        geom = app_client.get(f"/api/parts/{pid}/geometry").json()
    assert geom["size_x"] == 10.0
    assert geom["size_y"] == 20.0
    assert geom["size_z"] == 5.0
    # overrides records which dims a human set (calc-vs-override provenance).
    assert set(geom["overrides"]) == {"size_x", "size_y", "size_z"}


def test_math_expression_auto_evaluates(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        _set_geom(app_client, pid, size_x="2.27 + .359")
        geom = app_client.get(f"/api/parts/{pid}/geometry").json()
    assert abs(geom["size_x"] - 2.629) < 1e-6


def test_typed_units_auto_evaluate(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        _set_geom(app_client, pid, size_x="1 meter", size_y="1 in")
        geom = app_client.get(f"/api/parts/{pid}/geometry").json()
    assert geom["size_x"] == 1000.0
    assert geom["size_y"] == 25.4


def test_in_toggle_stores_metric(app_client: TestClient, seeder: Seeder) -> None:
    # The IN/MM toggle is presentation-only: a bare "2" under the IN toggle is inches,
    # but storage is always metric (the geometry↔Kalk contract).
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        _set_geom(app_client, pid, unit="in", size_x="2")
        geom = app_client.get(f"/api/parts/{pid}/geometry").json()
    assert geom["size_x"] == 50.8


def test_area_volume_weight(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        _set_geom(app_client, pid, area="2 * 3", volume="1 cm", weight="1 kg")
        geom = app_client.get(f"/api/parts/{pid}/geometry").json()
    assert geom["area"] == 6.0  # mm²
    assert geom["volume"] == 1000.0  # mm³ (1 cm cubed)
    assert geom["weight"] == 1000.0  # g (1 kg)


def test_partial_update_preserves_and_clears(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        _set_geom(app_client, pid, size_x=10, size_y=20)
        _set_geom(app_client, pid, size_y=30)  # touch only y
        after_touch = app_client.get(f"/api/parts/{pid}/geometry").json()
        _set_geom(app_client, pid, size_x=None)  # explicit clear
        after_clear = app_client.get(f"/api/parts/{pid}/geometry").json()
    assert after_touch["size_x"] == 10.0  # preserved
    assert after_touch["size_y"] == 30.0  # updated
    assert after_clear["size_x"] is None
    assert "size_x" not in after_clear["overrides"]


def test_geometry_rejects_unsafe_input(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        res = _set_geom(app_client, pid, size_x="__import__('os').system('id')")
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_dimension"


def test_geometry_rejects_negative(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        res = _set_geom(app_client, pid, size_x="2 - 5")
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_dimension"


def test_geometry_empty_before_set(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        geom = app_client.get(f"/api/parts/{pid}/geometry").json()
    assert geom["size_x"] is None
    assert geom["overrides"] == {}


# --------------------------------------------------------------------------- #
# The 4-layer chain: quote item → root component → part → root node
# --------------------------------------------------------------------------- #
def test_quote_item_part_has_bom_and_geometry(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = app_client.post("/api/quotes", json={}).json()["id"]
        item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][0]
        part_id = item["part_id"]
        # The line item's part resolves to a queryable single-node BOM…
        bom = app_client.get(f"/api/parts/{part_id}/bom").json()
        # …and can carry manual dims (the golden-thread role; real interrogation at M4).
        _set_geom(app_client, part_id, size_x="120.5")
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
    assert bom["part_id"] == part_id
    assert bom["is_root"] is True
    assert geom["size_x"] == 120.5


# --------------------------------------------------------------------------- #
# Permissions + org isolation (RLS)
# --------------------------------------------------------------------------- #
def test_part_writes_require_quote_edit(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    eng = seeder.user("eng@org-a.example")
    seeder.membership(eng, org, ENGINEER)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        pid = _create_part(app_client)["id"]
    with authed(app_client, user_id=eng, org_id=org, roles=ENGINEER):
        patch = app_client.patch(f"/api/parts/{pid}", json={"part_number": "X"})
        geom = _set_geom(app_client, pid, size_x=1)
    assert patch.status_code == 403
    assert geom.status_code == 403


def test_part_and_geometry_org_isolation(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b, admin_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        pid = _create_part(app_client)["id"]
        _set_geom(app_client, pid, size_x=42)
    # Org B cannot see org A's part, its geometry, or its BOM (RLS).
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        assert app_client.get(f"/api/parts/{pid}").status_code == 404
        assert app_client.get(f"/api/parts/{pid}/geometry").status_code == 404
        assert app_client.get(f"/api/parts/{pid}/bom").status_code == 404
        assert _set_geom(app_client, pid, size_x=1).status_code == 404
