"""Tests for M1.7 — Manual Materials & Operations + Calculated/Override drawers.

Two layers:

* **Pure math** — the calculation-mode arithmetic (``app.costing.compute_calc_cost``)
  against hand-computed figures: machine+operator, labour-only, surcharge, flat vs
  time-based setup, override-time resolution, missing-rate → ``None``,
  outside-process / material lines → ``None``. Mandatory per CLAUDE.md §9 (pricing
  math is test-first).
* **API/DB round-trips** (real RLS-bound Postgres): catalog seed idempotency +
  Werkstoffnummer type-ahead; the nested-picker tree; Edit Material Properties;
  attach-from-library with config copy (config freeze); inline add auto-saving to
  the library; per-break cells materialised and reshaped with "Change quantities";
  the acceptance case — **an override persists and survives a recalculation** (calc
  retained underneath); roll-up input bucketing (material/inside/outside); Change
  Process UPDATE vs KEEP-OPS; draft-only locking; permission gates; org isolation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.costing import compute_calc_cost
from app.models import (
    CalculationMode,
    MembershipRole,
    OpCategory,
    Operation,
    SetupBasis,
)
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
ENGINEER = [MembershipRole.engineer]  # no quote_edit (M0.3 matrix)


# --------------------------------------------------------------------------- #
# Pure math — the calculation-mode arithmetic
# --------------------------------------------------------------------------- #
def _op(**kwargs: Any) -> Operation:
    defaults: dict[str, Any] = {
        "category": OpCategory.operation,
        "calculation_mode": CalculationMode.machine_plus_operator,
        "setup_basis": SetupBasis.flat,
        "setup_cost": None,
        "run_rate": None,
        "labour_rate": None,
        "calc_setup_mins": None,
        "manual_setup_mins": None,
        "calc_runtime_mins": None,
        "manual_runtime_mins": None,
        "calc_attend_mins": None,
        "manual_attend_mins": None,
        "surcharge_pct": Decimal(0),
        "yield_factor": Decimal(1),
    }
    defaults.update(kwargs)
    return Operation(**defaults)


def test_machine_plus_operator_hand_calc() -> None:
    # setup 30 € + (12 min/60 x 90 €/hr + 6 min/60 x 45 €/hr) x Losgröße 10
    # = 30 + (18.0 + 4.5) x 10 = 255.00
    op = _op(
        setup_cost=Decimal(30),
        run_rate=Decimal(90),
        labour_rate=Decimal(45),
        calc_runtime_mins=Decimal(12),
        calc_attend_mins=Decimal(6),
    )
    assert compute_calc_cost(op, 10) == Decimal("255.0000")


def test_labour_only_hand_calc() -> None:
    # setup 10 € + (15 min/60 x 60 €/hr) x 4 = 10 + 15 x 4 = 70.00 ; labour_rate unused
    op = _op(
        calculation_mode=CalculationMode.labour_only,
        setup_cost=Decimal(10),
        run_rate=Decimal(60),
        calc_runtime_mins=Decimal(15),
    )
    assert compute_calc_cost(op, 4) == Decimal("70.0000")


def test_surcharge_applies_on_computed_cost() -> None:
    # (#oplibrary Operation surcharge): x(1 + 10/100) on the full computed cost.
    op = _op(
        calculation_mode=CalculationMode.labour_only,
        setup_cost=Decimal(10),
        run_rate=Decimal(60),
        calc_runtime_mins=Decimal(15),
        surcharge_pct=Decimal(10),
    )
    assert compute_calc_cost(op, 4) == Decimal("77.0000")


def test_time_based_setup_uses_run_rate() -> None:
    # Advanced toggle: setup 30 min/60 x 90 €/hr = 45 €, plus runtime.
    # (Setup rate = run_rate — DECISIONS.md 2026-07-07 OPEN default.)
    op = _op(
        setup_basis=SetupBasis.time,
        calc_setup_mins=Decimal(30),
        run_rate=Decimal(90),
        calc_runtime_mins=Decimal(2),
    )
    # 45 + (2/60 x 90) x 5 = 45 + 15 = 60
    assert compute_calc_cost(op, 5) == Decimal("60.0000")


def test_manual_time_overrides_calc_time() -> None:
    # The estimator's override wins over the calculated time (COALESCE order).
    op = _op(
        calculation_mode=CalculationMode.labour_only,
        run_rate=Decimal(60),
        calc_runtime_mins=Decimal(15),
        manual_runtime_mins=Decimal(30),
    )
    # (30/60 x 60) x 2 = 60
    assert compute_calc_cost(op, 2) == Decimal("60.0000")


def test_missing_rate_yields_none_not_zero() -> None:
    # A rate a non-zero term needs but is unset → unpriceable (M1.14 signal), not 0 €.
    op = _op(calc_runtime_mins=Decimal(10))
    assert compute_calc_cost(op, 1) is None
    # Nebenzeit present but labour_rate missing → also unpriceable.
    op2 = _op(run_rate=Decimal(90), calc_runtime_mins=Decimal(10), calc_attend_mins=Decimal(5))
    assert compute_calc_cost(op2, 1) is None


def test_flat_setup_alone_needs_no_rate() -> None:
    op = _op(setup_cost=Decimal(50))
    assert compute_calc_cost(op, 100) == Decimal("50.0000")


def test_outside_process_and_material_have_no_calc() -> None:
    outside = _op(calculation_mode=CalculationMode.outside_process, setup_cost=Decimal(10))
    assert compute_calc_cost(outside, 1) is None
    material = _op(category=OpCategory.material, setup_cost=Decimal(10))
    assert compute_calc_cost(material, 1) is None


# --------------------------------------------------------------------------- #
# API helpers
# --------------------------------------------------------------------------- #
def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_line(client: TestClient, quantities: list[int] | None = None) -> tuple[str, str, str]:
    """Create a draft quote + line item; return (quote_id, item_id, root component id)."""
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    if quantities:
        res = client.put(
            f"/api/quotes/{qid}/items/{item['id']}/quantities", json={"quantities": quantities}
        )
        assert res.status_code == 200, res.text
    return qid, str(item["id"]), str(item["root_component_id"])


def _new_component(client: TestClient, quantities: list[int] | None = None) -> str:
    """Create a draft quote + line item; return its root component id."""
    return _new_line(client, quantities)[2]


def _add_op(client: TestClient, component_id: str, **body: Any) -> dict[str, Any]:
    res = client.post(f"/api/components/{component_id}/operations", json=body)
    assert res.status_code == 201, res.text
    payload: dict[str, Any] = res.json()
    return payload


def _op_row(costing: dict[str, Any], name: str) -> dict[str, Any]:
    return next(op for op in costing["operations"] if op["name"] == name)


# --------------------------------------------------------------------------- #
# Catalog seed + picker
# --------------------------------------------------------------------------- #
def test_catalog_seed_idempotent(app_client: TestClient, seeder: Seeder) -> None:
    org, _ = _org_admin(seeder)
    first = seeder.catalog(org)
    assert first.classes_created == 1
    assert first.families_created == 11  # the hubs.com metal families
    assert first.materials_created > 0
    assert first.processes_created == 4  # Core-4
    again = seeder.catalog(org)
    assert (
        again.classes_created,
        again.families_created,
        again.materials_created,
        again.processes_created,
    ) == (0, 0, 0, 0)


def test_material_tree_and_werkstoffnummer_search(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    seeder.catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        tree = app_client.get("/api/materials/tree").json()
        hits = app_client.get("/api/materials", params={"q": "1.4301"}).json()
        by_alias = app_client.get("/api/materials", params={"q": "304"}).json()
        by_family_alias = app_client.get("/api/materials", params={"q": "stainless"}).json()
    assert [cls["name"] for cls in tree] == ["Metall"]
    families = {f["name"] for f in tree[0]["families"]}
    assert {"Aluminium", "Nichtrostender Stahl", "Werkzeugstahl", "Invar"} <= families
    # Werkstoffnummer lookup resolves 1.4301 → X5CrNi18-10 / 304 (DACH keying).
    assert hits[0]["en_name"] == "X5CrNi18-10"
    assert hits[0]["aisi_alias"] == "304"
    assert hits[0]["path"] == "Metall / Nichtrostender Stahl / 1.4301"
    assert any(hit["werkstoffnummer"] == "1.4301" for hit in by_alias)
    # The English family alias still finds the German-named family's materials.
    assert {hit["family_name"] for hit in by_family_alias} == {"Nichtrostender Stahl"}


def test_edit_material_properties(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    seeder.catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        material = app_client.get("/api/materials", params={"q": "1.4301"}).json()[0]
        res = app_client.patch(
            f"/api/materials/{material['id']}",
            json={"cost_per_volume": "0.000012", "added_lead_time_days": 3},
        )
        assert res.status_code == 200, res.text
        assert Decimal(res.json()["cost_per_volume"]) == Decimal("0.000012")
        assert res.json()["added_lead_time_days"] == 3


def test_materials_org_isolated(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b = seeder.org("org-b")
    user_b = seeder.user("admin@org-b.example")
    seeder.membership(user_b, org_b, ADMIN)
    seeder.catalog(org_a)  # only org A gets the catalog
    with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
        assert app_client.get("/api/materials/tree").json() == []
        assert app_client.get("/api/materials", params={"q": "1.4301"}).json() == []
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        material_id = app_client.get("/api/materials", params={"q": "1.4301"}).json()[0]["id"]
    with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
        # Cross-org edit is a 404 (RLS: the row does not exist for org B).
        assert app_client.patch(f"/api/materials/{material_id}", json={}).status_code == 404


# --------------------------------------------------------------------------- #
# Component material / process assignment
# --------------------------------------------------------------------------- #
def test_assign_and_clear_component_material(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    seeder.catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client)
        material_id = app_client.get("/api/materials", params={"q": "42CrMo4"}).json()[0]["id"]
        res = app_client.patch(
            f"/api/components/{component_id}/material", json={"material_id": material_id}
        )
        assert res.status_code == 200, res.text
        assert res.json()["material_id"] == material_id
        cleared = app_client.patch(
            f"/api/components/{component_id}/material", json={"material_id": None}
        )
        assert cleared.json()["material_id"] is None


def test_change_process_update_deletes_ops_keep_preserves(
    app_client: TestClient, seeder: Seeder
) -> None:
    # The modal's two commits: UPDATE ("This action will delete all existing
    # operations.") vs UPDATE AND KEEP EXISTING OPS (DECISIONS.md 2026-07-07).
    org, admin = _org_admin(seeder)
    seeder.catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client)
        _add_op(app_client, component_id, name="Entgraten", calculation_mode="labour_only")
        processes = app_client.get("/api/processes").json()
        milling = next(p for p in processes if p["name"] == "Milling")
        lathe = next(p for p in processes if p["name"] == "Lathe")
        kept = app_client.patch(
            f"/api/components/{component_id}/process",
            json={"process_id": milling["id"], "keep_operations": True},
        ).json()
        assert kept["process_id"] == milling["id"]
        assert [op["name"] for op in kept["operations"]] == ["Entgraten"]
        wiped = app_client.patch(
            f"/api/components/{component_id}/process",
            json={"process_id": lathe["id"], "keep_operations": False},
        ).json()
        assert wiped["process_id"] == lathe["id"]
        assert wiped["operations"] == []


# --------------------------------------------------------------------------- #
# Operations: attach, auto-save, cells, override persistence, roll-up
# --------------------------------------------------------------------------- #
def test_inline_add_auto_saves_to_library(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client)
        costing = _add_op(
            app_client,
            component_id,
            name="Laserschneiden Blech",
            calculation_mode="machine_plus_operator",
            run_rate="120",
            labour_rate="45",
            setup_cost="40",
        )
        # ... the def is now in the library (typeahead finds it) ...
        defs = app_client.get("/api/operation-defs", params={"q": "laser"}).json()
        assert [d["name"] for d in defs] == ["Laserschneiden Blech"]
        assert defs[0]["is_pre_installed"] is False
        # ... and a second inline add with the same name reuses it (no duplicate).
        _add_op(app_client, component_id, name="Laserschneiden Blech")
        defs_again = app_client.get("/api/operation-defs", params={"q": "laser"}).json()
        assert len(defs_again) == 1
    row = _op_row(costing, "Laserschneiden Blech")
    assert row["operation_def_id"] == defs[0]["id"]


def test_operation_defs_filter_by_is_finish(app_client: TestClient, seeder: Seeder) -> None:
    """M5.0 #partview: the REQUESTED FINISHES multi-select lists ``is_finish`` defs
    only — ``GET /api/operation-defs?is_finish=true`` narrows to finish operations."""
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        app_client.post(
            "/api/operation-defs",
            json={"name": "Eloxieren", "calculation_mode": "labour_only", "is_finish": True},
        )
        app_client.post(
            "/api/operation-defs",
            json={"name": "CNC Fräsen", "calculation_mode": "labour_only", "run_rate": "80"},
        )
        finishes = app_client.get("/api/operation-defs", params={"is_finish": "true"}).json()
        non_finishes = app_client.get("/api/operation-defs", params={"is_finish": "false"}).json()
    finish_names = {d["name"] for d in finishes}
    non_finish_names = {d["name"] for d in non_finishes}
    assert "Eloxieren" in finish_names
    assert "CNC Fräsen" not in finish_names
    # ...and the non-finish query returns the non-finish def (not an empty list,
    # which would let an always-empty implementation pass).
    assert "CNC Fräsen" in non_finish_names
    assert "Eloxieren" not in non_finish_names
    assert all(d["is_finish"] for d in finishes)
    assert all(not d["is_finish"] for d in non_finishes)


def test_attach_copies_def_config_config_freeze(app_client: TestClient, seeder: Seeder) -> None:
    # Library edits after attach must not reprice the quote: config is copied.
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        op_def = app_client.post(
            "/api/operation-defs",
            json={"name": "Kanten", "calculation_mode": "labour_only", "run_rate": "80"},
        ).json()
        component_id = _new_component(app_client)
        costing = _add_op(app_client, component_id, operation_def_id=op_def["id"])
        row = _op_row(costing, "Kanten")
        assert Decimal(row["run_rate"]) == Decimal(80)


def test_cells_per_break_and_reshaping(app_client: TestClient, seeder: Seeder) -> None:
    # Acceptance: adding/removing breaks reshapes the per-qty cost cells.
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item_id, component_id = _new_line(app_client, quantities=[1, 5, 20])
        costing = _add_op(
            app_client,
            component_id,
            name="Fräsen",
            run_rate="90",
            labour_rate="45",
            setup_cost="30",
        )
        row = _op_row(costing, "Fräsen")
        assert [cell["quantity"] for cell in row["cells"]] == [1, 5, 20]
        # Reshape the breaks: cells follow (5 gone; 50 appears with a fresh calc).
        res = app_client.put(
            f"/api/quotes/{qid}/items/{item_id}/quantities",
            json={"quantities": [1, 50]},
        )
        assert res.status_code == 200, res.text
        after = app_client.get(f"/api/components/{component_id}/costing").json()
        assert [cell["quantity"] for cell in _op_row(after, "Fräsen")["cells"]] == [1, 50]


def test_override_persists_and_survives_recalculation(
    app_client: TestClient, seeder: Seeder
) -> None:
    """THE acceptance case: an override persists and survives a recalculation —
    the calc value is retained underneath and comes back when the override clears."""
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client, quantities=[1, 10])
        costing = _add_op(
            app_client,
            component_id,
            name="Drehen",
            calculation_mode="labour_only",
            run_rate="60",
            setup_cost="10",
        )
        op = _op_row(costing, "Drehen")
        # Give it a runtime so calc is real: 15 min → qty1: 10+15=25; qty10: 10+150=160.
        updated = app_client.patch(
            f"/api/operations/{op['id']}", json={"manual_runtime_mins": "15"}
        ).json()
        cells = {c["quantity"]: c for c in _op_row(updated, "Drehen")["cells"]}
        assert Decimal(cells[1]["calc_cost"]) == Decimal("25.0000")
        assert Decimal(cells[10]["calc_cost"]) == Decimal("160.0000")
        # Override qty 10 to a hand price.
        overridden = app_client.patch(
            f"/api/operations/{op['id']}/cells/10", json={"manual_cost": "140"}
        ).json()
        cell10 = {c["quantity"]: c for c in _op_row(overridden, "Drehen")["cells"]}[10]
        assert Decimal(cell10["manual_cost"]) == Decimal(140)
        assert Decimal(cell10["effective_cost"]) == Decimal(140)
        # RECALCULATE: change the op's rate — calc moves, the override survives.
        recosted = app_client.patch(f"/api/operations/{op['id']}", json={"run_rate": "80"}).json()
        cell10 = {c["quantity"]: c for c in _op_row(recosted, "Drehen")["cells"]}[10]
        assert Decimal(cell10["calc_cost"]) == Decimal("210.0000")  # 10 + 200
        assert Decimal(cell10["manual_cost"]) == Decimal(140)  # untouched
        assert Decimal(cell10["effective_cost"]) == Decimal(140)  # override wins
        # Clear the override → falls back to the retained calc.
        cleared = app_client.patch(
            f"/api/operations/{op['id']}/cells/10", json={"manual_cost": None}
        ).json()
        cell10 = {c["quantity"]: c for c in _op_row(cleared, "Drehen")["cells"]}[10]
        assert cell10["manual_cost"] is None
        assert Decimal(cell10["effective_cost"]) == Decimal("210.0000")


def test_rollup_buckets_material_inside_outside(app_client: TestClient, seeder: Seeder) -> None:
    # Roll-up inputs (#costing): each row lands in exactly one bucket.
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client)  # single qty=1 break
        _add_op(
            app_client,
            component_id,
            name="Fräsen",
            calculation_mode="labour_only",
            run_rate="60",
            setup_cost="10",
        )
        costing = _add_op(app_client, component_id, name="Material | Blech", category="material")
        material_row = _op_row(costing, "Material | Blech")
        # Material lines have no calc source in M1.7 → manual cost cell.
        costing = app_client.patch(
            f"/api/operations/{material_row['id']}/cells/1", json={"manual_cost": "55.5"}
        ).json()
        costing = _add_op(
            app_client,
            component_id,
            name="Anodisieren",
            calculation_mode="outside_process",
        )
        anodize = _op_row(costing, "Anodisieren")
        assert anodize["is_outside_service"] is True  # implied by outside_process
        costing = app_client.patch(
            f"/api/operations/{anodize['id']}/cells/1", json={"manual_cost": "20"}
        ).json()
        fraesen = _op_row(costing, "Fräsen")
        costing = app_client.patch(
            f"/api/operations/{fraesen['id']}", json={"manual_runtime_mins": "30"}
        ).json()
    bucket = costing["buckets"][0]
    assert bucket["quantity"] == 1
    assert Decimal(bucket["material_total"]) == Decimal("55.5000")
    assert Decimal(bucket["inside_total"]) == Decimal("40.0000")  # 10 + 30/60x60
    assert Decimal(bucket["outside_total"]) == Decimal("20.0000")
    assert Decimal(bucket["total"]) == Decimal("115.5000")
    assert bucket["has_unpriced_rows"] is False


def test_unpriced_row_flagged_not_zero_priced(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client)
        # Runtime present but no rate configured → unpriceable, flagged for M1.14.
        costing = _add_op(app_client, component_id, name="Schleifen 1")
        op = _op_row(costing, "Schleifen 1")
        costing = app_client.patch(
            f"/api/operations/{op['id']}", json={"manual_runtime_mins": "10"}
        ).json()
    assert costing["buckets"][0]["has_unpriced_rows"] is True
    assert Decimal(costing["buckets"][0]["total"]) == Decimal(0)


def test_duplicate_and_remove_and_reorder(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client)
        costing = _add_op(
            app_client, component_id, name="Schleifen", calculation_mode="labour_only"
        )
        first = _op_row(costing, "Schleifen")
        dup = app_client.post(f"/api/operations/{first['id']}/duplicate")
        assert dup.status_code == 200, dup.text
        ops = dup.json()["operations"]
        assert [op["name"] for op in ops] == ["Schleifen", "Schleifen"]
        # Library gained exactly one def (duplicate copies the row, not the def).
        assert len(app_client.get("/api/operation-defs", params={"q": "schleifen"}).json()) == 1
        # Reorder: swap the two rows.
        reordered = app_client.put(
            f"/api/components/{component_id}/operations/order",
            json={"operation_ids": [ops[1]["id"], ops[0]["id"]]},
        ).json()
        assert [op["id"] for op in reordered["operations"]] == [ops[1]["id"], ops[0]["id"]]
        # Remove one — the other and the library def stay.
        assert app_client.delete(f"/api/operations/{ops[0]['id']}").status_code == 204
        remaining = app_client.get(f"/api/components/{component_id}/costing").json()
        assert [op["id"] for op in remaining["operations"]] == [ops[1]["id"]]
        assert len(app_client.get("/api/operation-defs", params={"q": "schleifen"}).json()) == 1


def test_explicit_null_on_not_null_fields_is_422_not_500(
    app_client: TestClient, seeder: Seeder
) -> None:
    # surcharge_pct / yield_factor / name are NOT NULL columns: an external client
    # sending an explicit null must get the clean validation envelope, never a DB
    # IntegrityError 500 (Greptile M1.7 review). Reset = send the default value.
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client)
        costing = _add_op(app_client, component_id, name="Fräsen", calculation_mode="labour_only")
        op = _op_row(costing, "Fräsen")
        for field in ("surcharge_pct", "yield_factor", "name"):
            res = app_client.patch(f"/api/operations/{op['id']}", json={field: None})
            assert res.status_code == 422, f"{field}: {res.status_code} {res.text}"
            assert res.json()["code"] == "validation_error"
        # Reset semantics: the DB defaults are accepted values.
        ok = app_client.patch(
            f"/api/operations/{op['id']}", json={"surcharge_pct": "0", "yield_factor": "1"}
        )
        assert ok.status_code == 200, ok.text


# --------------------------------------------------------------------------- #
# Gates: permissions, draft-only lock, org isolation
# --------------------------------------------------------------------------- #
def test_engineer_cannot_edit_operations(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    engineer = seeder.user("engineer@org-a.example")
    seeder.membership(engineer, org, ENGINEER)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        component_id = _new_component(app_client)
    with authed(app_client, user_id=engineer, org_id=org, roles=ENGINEER):
        res = app_client.post(f"/api/components/{component_id}/operations", json={"name": "Fräsen"})
        assert res.status_code == 403
        # Reads are fine (view + annotate).
        assert app_client.get(f"/api/components/{component_id}/costing").status_code == 200


def test_locked_quote_blocks_materials_and_operations(
    app_client: TestClient, seeder: Seeder
) -> None:
    # A trashed quote is never editable (the draft-only gate); "sent" behaves the
    # same via _quote_is_editable — trash avoids the send-precondition setup.
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, _, component_id = _new_line(app_client)
        costing = _add_op(app_client, component_id, name="Fräsen", calculation_mode="labour_only")
        trashed = app_client.post(f"/api/quotes/{qid}/trash")
        assert trashed.status_code == 200, trashed.text
        op = _op_row(costing, "Fräsen")
        assert (
            app_client.post(
                f"/api/components/{component_id}/operations", json={"name": "Drehen"}
            ).status_code
            == 409
        )
        assert (
            app_client.patch(
                f"/api/operations/{op['id']}", json={"manual_runtime_mins": "5"}
            ).status_code
            == 409
        )
        assert (
            app_client.patch(
                f"/api/operations/{op['id']}/cells/1", json={"manual_cost": "10"}
            ).status_code
            == 409
        )


def test_operations_org_isolated(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b = seeder.org("org-b")
    admin_b = seeder.user("admin@org-b.example")
    seeder.membership(admin_b, org_b, ADMIN)
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        component_id = _new_component(app_client)
        costing = _add_op(app_client, component_id, name="Fräsen", calculation_mode="labour_only")
        op = _op_row(costing, "Fräsen")
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        # Org B sees neither the component, the operation, nor org A's library.
        assert app_client.get(f"/api/components/{component_id}/costing").status_code == 404
        assert app_client.patch(f"/api/operations/{op['id']}", json={}).status_code == 404
        assert app_client.get("/api/operation-defs", params={"q": "Fräsen"}).json() == []
