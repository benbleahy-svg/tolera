"""M4.8 — custom interrogations: authoring API, seed variants, resolution.

The block's acceptance criteria (build-plan M4.8): a part whose material has
both a family-level and a material-level ``CustomInterrogation`` resolves the
**material-level** thresholds; an Aluminum part uses the Aluminum deep-hole
ratio (20x), a Stainless part the Stainless one (6x) — the spec
``#dfm-catalogue`` material tuning, seeded as milling variants linked to the
``Aluminium`` / ``Nichtrostender Stahl`` material families; re-resolution is
deterministic. Plus the Configure authoring surface: create (defaults
prefilled, unique name), material/op-def linking (org-pinned), the advisory
duplicate-dispatch ⚠️ (KB ``custom-interrogations`` "Be careful..."), and the
undeletable seeded default.

Runs against real Postgres (skips without ``TEST_DATABASE_URL``) with
in-memory storage + eager Celery, like tests/test_interrogation_m42.py.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.interrogation import inputs_fingerprint
from app.models import MembershipRole
from tests.conftest import Seeder, authed
from tests.support import eager_celery

ADMIN = [MembershipRole.admin]

CAD_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
#: 40x40x30 block, d3 through hole -> depth/dia ratio 10: fires at the seed
#: default 8.0, is suppressed by the Aluminium 20x, fires at the Stainless 6x.
DEEPHOLE = (CAD_DIR / "block-deephole-40x40x30.step").read_bytes()

ALUMINIUM_VARIANT = "CNC-Fräsen Aluminium"
STAINLESS_VARIANT = "CNC-Fräsen Nichtrostender Stahl"


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _create_part(client: TestClient) -> str:
    created = client.post("/api/parts")
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _profiles(client: TestClient) -> list[dict[str, Any]]:
    res = client.get("/api/configure/interrogations")
    assert res.status_code == 200, res.text
    return list(res.json()["profiles"])


def _profile_named(client: TestClient, name: str) -> dict[str, Any]:
    profile = next((p for p in _profiles(client) if p["name"] == name), None)
    assert profile is not None, f"profile {name!r} not seeded"
    return profile


def _material(client: TestClient, q: str) -> dict[str, Any]:
    return next(m for m in client.get("/api/materials", params={"q": q}).json())


def _interrogate(client: TestClient, part_id: str, material_id: str) -> dict[str, Any]:
    with eager_celery():
        res = client.post(
            f"/api/parts/{part_id}/interrogate",
            json={"family": "MILLING", "material_id": material_id},
        )
        assert res.status_code == 202, res.text
    status = client.get(f"/api/parts/{part_id}/interrogation").json()
    assert status["status"] == "succeeded", status
    return dict(status["run"])


def _warning(run: dict[str, Any], wtype: str) -> dict[str, Any] | None:
    feedback = run["result"].get("feedback") or []
    return next((w for w in feedback if w["type"] == wtype), None)


# --------------------------------------------------------------------------- #
# Seeded material variants (spec #dfm-catalogue material tuning)
# --------------------------------------------------------------------------- #
def test_seed_creates_milling_material_variants(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "m48-seed")
    result = seeder.configure_catalog(org)
    # 4 family defaults (M4.7) + 2 material variants (M4.8).
    assert result.interrogation_profiles_created == 6
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        alu = _profile_named(app_client, ALUMINIUM_VARIANT)
        inox = _profile_named(app_client, STAINLESS_VARIANT)
        alu_family = _material(app_client, "EN AW-6061")["family_id"]
        inox_family = _material(app_client, "1.4301")["family_id"]
        default_keys = _profile_named(app_client, "Standard CNC-Fräsen")["inputs"].keys()
    assert alu["family"] == "MILLING"
    assert not alu["is_default"]
    assert alu["material_family_id"] == str(alu_family)
    assert alu["inputs"]["deep_hole_ratio_threshold"] == 20.0
    assert alu["inputs"]["deep_cut_radiused_ratio_threshold"] == 6.0
    assert alu["inputs"]["deep_cut_planar_ratio_threshold"] == 8.0
    assert inox["material_family_id"] == str(inox_family)
    assert inox["inputs"]["deep_hole_ratio_threshold"] == 6.0
    assert inox["inputs"]["deep_cut_radiused_ratio_threshold"] == 2.0
    assert inox["inputs"]["deep_cut_planar_ratio_threshold"] == 3.0
    # A variant carries the full input set, not a sparse override (grill #10).
    assert alu["inputs"].keys() == default_keys


def test_reseed_is_idempotent_and_preserves_edits(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "m48-reseed")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        alu = _profile_named(app_client, ALUMINIUM_VARIANT)
        edited = {**alu["inputs"], "deep_hole_ratio_threshold": 22.0}
        res = app_client.put(f"/api/configure/interrogations/{alu['id']}", json={"inputs": edited})
        assert res.status_code == 200, res.text
    rerun = seeder.configure_catalog(org)
    assert rerun.interrogation_profiles_created == 0
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        assert (
            _profile_named(app_client, ALUMINIUM_VARIANT)["inputs"]["deep_hole_ratio_threshold"]
            == 22.0
        )


# --------------------------------------------------------------------------- #
# Acceptance: material tuning resolves per material family
# --------------------------------------------------------------------------- #
def test_aluminum_part_uses_aluminum_ratio_stainless_the_stainless_one(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "m48-tuning")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            up = app_client.post(
                f"/api/parts/{part_id}/files",
                files=[("files", ("dh.step", DEEPHOLE, "application/step"))],
            )
            assert up.status_code == 201, up.text
        alu = _material(app_client, "EN AW-6061")
        inox = _material(app_client, "1.4301")

        run = _interrogate(app_client, part_id, alu["id"])
        # ratio 10 < Aluminium 20x -> suppressed.
        assert _warning(run, "deep_hole") is None
        alu_profile = _profile_named(app_client, ALUMINIUM_VARIANT)
        assert run["inputs_hash"] == inputs_fingerprint(alu_profile["inputs"])

        run = _interrogate(app_client, part_id, inox["id"])
        # ratio 10 > Stainless 6x -> fires, carrying the firing threshold.
        fired = _warning(run, "deep_hole")
        assert fired is not None
        assert fired["threshold_used"]["deep_hole_ratio_threshold"] == 6.0


def test_material_level_profile_beats_family_level(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "m48-specificity")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            app_client.post(
                f"/api/parts/{part_id}/files",
                files=[("files", ("dh.step", DEEPHOLE, "application/step"))],
            )
        alu = _material(app_client, "EN AW-6061")
        # Family-level Aluminium (20x, seeded) would suppress; a material-level
        # profile for EN AW-6061 at 6x must win and fire.
        created = app_client.post(
            "/api/configure/interrogations",
            json={
                "name": "EN AW-6061 streng",
                "family": "MILLING",
                "inputs": {"deep_hole_ratio_threshold": 6.0},
            },
        )
        assert created.status_code == 201, created.text
        profile = created.json()
        linked = app_client.put(
            f"/api/configure/interrogations/{profile['id']}",
            json={"material_id": alu["id"]},
        )
        assert linked.status_code == 200, linked.text

        run = _interrogate(app_client, part_id, alu["id"])
        fired = _warning(run, "deep_hole")
        assert fired is not None
        assert fired["threshold_used"]["deep_hole_ratio_threshold"] == 6.0

        # Determinism: re-resolution lands on the same profile/inputs.
        rerun = _interrogate(app_client, part_id, alu["id"])
        assert rerun["inputs_hash"] == run["inputs_hash"]


# --------------------------------------------------------------------------- #
# Authoring API
# --------------------------------------------------------------------------- #
def test_create_prefills_engine_defaults_and_enforces_unique_name(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "m48-create")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        created = app_client.post(
            "/api/configure/interrogations",
            json={"name": "Laser fein", "family": "SHEET_METAL"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        # KB create flow: every task input present at its default.
        default = _profile_named(app_client, "Standard Blech (Laser)")
        assert body["inputs"].keys() == default["inputs"].keys()
        assert not body["is_default"]

        dup = app_client.post(
            "/api/configure/interrogations",
            json={"name": "Laser fein", "family": "SHEET_METAL"},
        )
        assert dup.status_code == 422
        assert dup.json()["code"] == "duplicate_interrogation_name"

        unknown = app_client.post(
            "/api/configure/interrogations",
            json={"name": "x", "family": "no-such-family"},
        )
        assert unknown.status_code == 422


def test_material_links_are_org_pinned(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "m48-pin-a")
    other_org, other_admin = _org_with_admin(seeder, "m48-pin-b")
    seeder.configure_catalog(org)
    seeder.configure_catalog(other_org)
    with authed(app_client, user_id=other_admin, org_id=other_org, roles=ADMIN):
        foreign_family = _material(app_client, "EN AW-6061")["family_id"]
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        profile = _profile_named(app_client, ALUMINIUM_VARIANT)
        res = app_client.put(
            f"/api/configure/interrogations/{profile['id']}",
            json={"material_family_id": str(foreign_family)},
        )
        assert res.status_code == 422
        assert res.json()["code"] == "unknown_material_link"
        # And a cross-org profile id 404s outright (RLS).
    with authed(app_client, user_id=other_admin, org_id=other_org, roles=ADMIN):
        res = app_client.put(
            f"/api/configure/interrogations/{profile['id']}", json={"name": "hijack"}
        )
        assert res.status_code == 404


def test_op_link_duplicate_dispatch_guard_warns(app_client: TestClient, seeder: Seeder) -> None:
    """KB "Be careful...": two same-family profiles linked into one process via
    different ops -> advisory ⚠️, never a hard block."""
    org, admin = _org_with_admin(seeder, "m48-guard")
    seeder.configure_catalog(org)
    process_ops = seeder.process_router_ops(org, family="MILLING")
    assert len(process_ops) >= 2, "seeded milling router needs >=2 ops for this test"
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        first = app_client.post(
            "/api/configure/interrogations", json={"name": "Fräsen A", "family": "MILLING"}
        ).json()
        second = app_client.post(
            "/api/configure/interrogations", json={"name": "Fräsen B", "family": "MILLING"}
        ).json()
        res = app_client.put(
            f"/api/configure/interrogations/{first['id']}",
            json={"operation_def_ids": [str(process_ops[0])]},
        )
        assert res.status_code == 200, res.text
        assert res.json()["warnings"] == []
        res = app_client.put(
            f"/api/configure/interrogations/{second['id']}",
            json={"operation_def_ids": [str(process_ops[1])]},
        )
        assert res.status_code == 200, res.text
        warnings = res.json()["warnings"]
        assert len(warnings) == 1
        assert warnings[0]["code"] == "duplicate_dispatch"
        assert warnings[0]["other_profile_id"] == first["id"]
        # The saved links round-trip on GET.
        assert _profile_named(app_client, "Fräsen B")["operation_def_ids"] == [str(process_ops[1])]


def test_default_profile_cannot_be_deleted_variants_can(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "m48-delete")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        default = _profile_named(app_client, "Standard CNC-Fräsen")
        res = app_client.delete(f"/api/configure/interrogations/{default['id']}")
        assert res.status_code == 422
        assert res.json()["code"] == "default_profile_undeletable"

        variant = _profile_named(app_client, ALUMINIUM_VARIANT)
        res = app_client.delete(f"/api/configure/interrogations/{variant['id']}")
        assert res.status_code == 204
        assert all(p["name"] != ALUMINIUM_VARIANT for p in _profiles(app_client))
