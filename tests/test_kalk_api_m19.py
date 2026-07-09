"""Tests for M1.9 — Kalk variable system + contexts + editor + Custom Tables,
API/DB layer (real RLS-bound Postgres; the evaluator itself is covered by
``test_kalk_m19_*``).

Covers: custom-table CRUD + typed cell validation + CSV import (German decimal
commas, ja/nein booleans) + org isolation; the editor CHECK endpoint; formula
save validation (def + quote-side snapshot, config-freeze semantics);
formula-driven ``calc_cost`` cells (4-dp half-up money boundary, per-break
values, table lookups); variable overrides (plain + per-quantity) surviving
recalculation; the runtime/setup_time manual-minutes boundary; workpiece +
cost-dictionary threading across router order; ``no_quote``; the drawer's
evaluation report.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
ENGINEER = [MembershipRole.engineer]  # view-only for quoting/config (M0.3 matrix)


def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_component(client: TestClient, quantities: list[int] | None = None) -> str:
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    if quantities:
        res = client.put(
            f"/api/quotes/{qid}/items/{item['id']}/quantities", json={"quantities": quantities}
        )
        assert res.status_code == 200, res.text
    return str(item["root_component_id"])


def _add_formula_op(
    client: TestClient, component_id: str, name: str, formula: str, **extra: Any
) -> dict[str, Any]:
    created = client.post(
        f"/api/components/{component_id}/operations", json={"name": name, **extra}
    )
    assert created.status_code == 201, created.text
    op = next(o for o in created.json()["operations"] if o["name"] == name)
    res = client.patch(f"/api/operations/{op['id']}", json={"cost_formula": formula})
    assert res.status_code == 200, res.text
    return next(o for o in res.json()["operations"] if o["name"] == name)


def _op_row(costing: dict[str, Any], name: str) -> dict[str, Any]:
    return next(op for op in costing["operations"] if op["name"] == name)


def _cell(op: dict[str, Any], quantity: int) -> dict[str, Any]:
    return next(c for c in op["cells"] if c["quantity"] == quantity)


MATERIALS_TABLE = {
    "name": "materialpreise",
    "columns": [
        {"name": "material", "type": "string"},
        {"name": "preis", "type": "numeric"},
        {"name": "schwierig", "type": "boolean"},
    ],
}
MATERIALS_ROWS = [
    {"material": "Aluminium 6061", "preis": 10.5, "schwierig": False},
    {"material": "Titan Grade 5", "preis": 80, "schwierig": True},
]


def _make_table(client: TestClient) -> str:
    res = client.post("/api/custom-tables", json=MATERIALS_TABLE)
    assert res.status_code == 201, res.text
    table_id = str(res.json()["id"])
    rows = client.put(f"/api/custom-tables/{table_id}/rows", json={"rows": MATERIALS_ROWS})
    assert rows.status_code == 200, rows.text
    return table_id


# --------------------------------------------------------------------------- #
# Custom tables CRUD
# --------------------------------------------------------------------------- #
def test_custom_table_crud_round_trip(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        table_id = _make_table(app_client)
        detail = app_client.get(f"/api/custom-tables/{table_id}").json()
        assert detail["row_count"] == 2
        assert detail["rows"][0] == {
            "row_number": 1,
            "material": "Aluminium 6061",
            "preis": 10.5,
            "schwierig": False,
        }
        listing = app_client.get("/api/custom-tables").json()
        assert [(t["name"], t["row_count"]) for t in listing] == [("materialpreise", 2)]
        assert app_client.delete(f"/api/custom-tables/{table_id}").status_code == 204
        assert app_client.get(f"/api/custom-tables/{table_id}").status_code == 404


def test_custom_table_validation(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        bad_name = app_client.post(
            "/api/custom-tables",
            json={"name": "t", "columns": [{"name": "1preis", "type": "numeric"}]},
        )
        assert bad_name.status_code == 422
        assert bad_name.json()["code"] == "invalid_column_name"

        bad_type = app_client.post(
            "/api/custom-tables",
            json={"name": "t", "columns": [{"name": "preis", "type": "date"}]},
        )
        assert bad_type.status_code == 422

        table_id = _make_table(app_client)
        duplicate = app_client.post("/api/custom-tables", json=MATERIALS_TABLE)
        assert duplicate.status_code == 409

        wrong_cell = app_client.put(
            f"/api/custom-tables/{table_id}/rows",
            json={"rows": [{"material": "X", "preis": "teuer", "schwierig": False}]},
        )
        assert wrong_cell.status_code == 422
        assert wrong_cell.json()["code"] == "invalid_cell"

        unknown_column = app_client.put(
            f"/api/custom-tables/{table_id}/rows", json={"rows": [{"farbe": "rot"}]}
        )
        assert unknown_column.status_code == 422
        assert unknown_column.json()["code"] == "unknown_column"


def test_column_edit_coerces_rows(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        table_id = _make_table(app_client)
        res = app_client.patch(
            f"/api/custom-tables/{table_id}",
            json={
                "columns": [
                    {"name": "material", "type": "string"},
                    {"name": "preis", "type": "string"},  # numeric → string: values null
                    {"name": "lieferzeit", "type": "numeric"},  # new: null
                ]
            },
        )
        assert res.status_code == 200, res.text
        rows = app_client.get(f"/api/custom-tables/{table_id}").json()["rows"]
        assert rows[0] == {
            "row_number": 1,
            "material": "Aluminium 6061",
            "preis": None,
            "lieferzeit": None,
        }


def test_csv_import_german_locale(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        table_id = _make_table(app_client)
        csv_body = 'material,preis,schwierig\nStahl S235,4,\nTitan Grade 5,"80,5",ja\n'
        res = app_client.post(
            f"/api/custom-tables/{table_id}/import",
            files={"file": ("preise.csv", csv_body.encode(), "text/csv")},
        )
        assert res.status_code == 200, res.text
        rows = app_client.get(f"/api/custom-tables/{table_id}").json()["rows"]
        assert rows == [
            {"row_number": 1, "material": "Stahl S235", "preis": 4, "schwierig": None},
            {"row_number": 2, "material": "Titan Grade 5", "preis": 80.5, "schwierig": True},
        ]

        mismatch = app_client.post(
            f"/api/custom-tables/{table_id}/import",
            files={"file": ("bad.csv", b"material,kosten\na,1\n", "text/csv")},
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["code"] == "csv_header_mismatch"

        # float() accepts "inf"/"nan"/huge exponents — JSONB cannot store them,
        # so the parser must reject non-finite numerics with a clean 422
        for bad_number in ("inf", "nan", "1e400"):
            res = app_client.post(
                f"/api/custom-tables/{table_id}/import",
                files={
                    "file": (
                        "inf.csv",
                        f"material,preis,schwierig\nStahl,{bad_number},\n".encode(),
                        "text/csv",
                    )
                },
            )
            assert res.status_code == 422, bad_number
            assert res.json()["code"] == "invalid_cell"


def test_custom_tables_org_isolated(app_client: TestClient, seeder: Seeder) -> None:
    org_a, user_a = _org_admin(seeder, "org-a")
    org_b, user_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=user_a, org_id=org_a, roles=ADMIN):
        table_id = _make_table(app_client)
    with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
        assert app_client.get("/api/custom-tables").json() == []
        assert app_client.get(f"/api/custom-tables/{table_id}").status_code == 404
        assert (
            app_client.put(f"/api/custom-tables/{table_id}/rows", json={"rows": []}).status_code
            == 404
        )


def test_engineer_cannot_edit_custom_tables(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    engineer = seeder.user("engineer@org-a.example")
    seeder.membership(engineer, org, ENGINEER)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        table_id = _make_table(app_client)
    with authed(app_client, user_id=engineer, org_id=org, roles=ENGINEER):
        assert app_client.get(f"/api/custom-tables/{table_id}").status_code == 200
        assert app_client.post("/api/custom-tables", json=MATERIALS_TABLE).status_code == 403
        assert app_client.delete(f"/api/custom-tables/{table_id}").status_code == 403


# --------------------------------------------------------------------------- #
# Editor CHECK + formula save validation
# --------------------------------------------------------------------------- #
def test_kalk_check_endpoint(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        ok = app_client.post(
            "/api/kalk/check", json={"formula": "COST = part.volume * 2\nDAYS = 1"}
        ).json()
        assert ok == {"ok": True, "errors": []}

        bad = app_client.post("/api/kalk/check", json={"formula": "COST = import os"}).json()
        assert bad["ok"] is False
        assert bad["errors"][0]["line"] == 1


def test_saving_invalid_formula_is_422(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/operation-defs",
            json={"name": "Bohren", "cost_formula": "COST = nonsense_name"},
        )
        assert res.status_code == 422
        assert res.json()["code"] == "invalid_formula"
        assert res.json()["details"][0]["code"] == "unknown_name"

        component = _new_component(app_client, [1])
        created = app_client.post(
            f"/api/components/{component}/operations", json={"name": "Fräsen"}
        )
        op = next(o for o in created.json()["operations"] if o["name"] == "Fräsen")
        bad_patch = app_client.patch(
            f"/api/operations/{op['id']}", json={"cost_formula": "COST = ("}
        )
        assert bad_patch.status_code == 422
        assert bad_patch.json()["code"] == "invalid_formula"


def test_formula_snapshot_on_attach_config_freeze(app_client: TestClient, seeder: Seeder) -> None:
    """E4-d: the operation copies the def's formula at attach; a later def edit
    never reprices the existing draft (DECISIONS.md 2026-07-08)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        created = app_client.post(
            "/api/operation-defs",
            json={"name": "Sägen", "cost_formula": "COST = 10 * quantity"},
        )
        assert created.status_code == 201, created.text
        def_id = created.json()["id"]

        component = _new_component(app_client, [2])
        attached = app_client.post(
            f"/api/components/{component}/operations", json={"operation_def_id": def_id}
        ).json()
        op = _op_row(attached, "Sägen")
        assert op["cost_formula"] == "COST = 10 * quantity"
        assert _cell(op, 2)["calc_cost"] == "20.0000"

        # def edit → snapshot (and cell) unchanged
        patched = app_client.patch(
            f"/api/operation-defs/{def_id}", json={"cost_formula": "COST = 99 * quantity"}
        )
        assert patched.status_code == 200
        costing = app_client.get(f"/api/components/{component}/costing").json()
        assert _op_row(costing, "Sägen")["cost_formula"] == "COST = 10 * quantity"
        assert _cell(_op_row(costing, "Sägen"), 2)["calc_cost"] == "20.0000"


# --------------------------------------------------------------------------- #
# Formula-driven calc cells
# --------------------------------------------------------------------------- #
def test_formula_drives_per_break_calc_with_table(app_client: TestClient, seeder: Seeder) -> None:
    """The acceptance case: a formula reading a table_var + variables produces
    the expected per-qty value, quantized 4-dp half-up into calc_cost."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        _make_table(app_client)
        component = _new_component(app_client, [1, 5])
        formula = """
row = table_var('Werkstoff', 'stock', 'materialpreise',
                create_filter(filter('material', 'contains', 'titan')), None, 'material')
einrichten = var('Einrichten', 30.0, 'EUR', currency)
COST = einrichten + row.preis * quantity * 1.001
"""
        op = _add_formula_op(app_client, component, "Material Titan", formula)
        # qty 1: 30 + 80*1*1.001 = 110.08 ; qty 5: 30 + 80*5*1.001 = 430.40
        assert _cell(op, 1)["calc_cost"] == "110.0800"
        assert _cell(op, 5)["calc_cost"] == "430.4000"


def test_formula_error_blanks_cell_and_reports(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1])
        # references a table that doesn't exist → runtime error → unpriceable
        op = _add_formula_op(
            app_client,
            component,
            "Kaputt",
            "row = table_var('R', '', 'gibtsnicht', None, None, None)\nCOST = 1",
        )
        assert _cell(op, 1)["calc_cost"] is None
        report = app_client.get(f"/api/operations/{op['id']}/kalk").json()
        assert report[0]["errors"][0]["code"] == "runtime_error"
        assert "gibtsnicht" in report[0]["errors"][0]["message"]


def test_no_quote_blanks_cell(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1])
        op = _add_formula_op(app_client, component, "NoQuote", "no_quote()\nCOST = 5")
        assert _cell(op, 1)["calc_cost"] is None


def test_surcharge_applies_on_kalk_output(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1])
        op = _add_formula_op(app_client, component, "Zuschlag", "COST = 100", surcharge_pct="10")
        assert _cell(op, 1)["calc_cost"] == "110.0000"


def test_manual_cost_override_survives_formula_recalc(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1])
        op = _add_formula_op(app_client, component, "Fräsen", "COST = 50")
        res = app_client.patch(f"/api/operations/{op['id']}/cells/1", json={"manual_cost": "42"})
        cell = _cell(_op_row(res.json(), "Fräsen"), 1)
        # scale varies pre/post DB round-trip ("42" vs "42.0000") — compare numerically
        assert float(cell["manual_cost"]) == 42.0
        assert cell["calc_cost"] == "50.0000"  # calc retained underneath
        assert float(cell["effective_cost"]) == 42.0


# --------------------------------------------------------------------------- #
# Variable overrides
# --------------------------------------------------------------------------- #
def test_variable_overrides_apply_and_survive_recalc(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1, 5])
        formula = "rate = var('Stundensatz', 60.0, 'EUR/hr', currency)\nCOST = rate * quantity"
        op = _add_formula_op(app_client, component, "Drehen", formula)
        assert _cell(op, 1)["calc_cost"] == "60.0000"

        res = app_client.put(
            f"/api/operations/{op['id']}/variables",
            json={"overrides": {"Stundensatz": 90.0}},
        )
        assert res.status_code == 200, res.text
        row = _op_row(res.json(), "Drehen")
        assert _cell(row, 1)["calc_cost"] == "90.0000"
        assert _cell(row, 5)["calc_cost"] == "450.0000"
        assert row["variable_overrides"] == {"Stundensatz": 90.0}

        # a per-quantity override on a quantity_specific var hits only its break
        formula_qs = (
            "menge = var('Minuten pro Teil', 6.0, 'min', number, True, True, True)\n"
            "COST = menge * quantity"
        )
        op2 = _add_formula_op(app_client, component, "Entgraten", formula_qs)
        res2 = app_client.put(
            f"/api/operations/{op2['id']}/variables",
            json={"overrides": {"Minuten pro Teil": {"5": 4.0}}},
        )
        row2 = _op_row(res2.json(), "Entgraten")
        assert _cell(row2, 1)["calc_cost"] == "6.0000"
        assert _cell(row2, 5)["calc_cost"] == "20.0000"


def test_runtime_setup_overrides_rejected_in_variables(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1])
        op = _add_formula_op(app_client, component, "Fräsen", "COST = 1")
        res = app_client.put(
            f"/api/operations/{op['id']}/variables", json={"overrides": {"runtime": 2.0}}
        )
        assert res.status_code == 422


def test_manual_runtime_mins_feeds_runtime_var(app_client: TestClient, seeder: Seeder) -> None:
    """The M1.7↔M1.9 time boundary: manual minutes → formula hours, and the
    formula's frozen runtime writes calc_runtime_mins back."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1])
        formula = """
runtime = var('runtime', 0.5, 'hours', number)
COST = runtime * 100
"""
        op = _add_formula_op(app_client, component, "Schleifen", formula)
        assert _cell(op, 1)["calc_cost"] == "50.0000"
        assert op["calc_runtime_mins"] == "30.0000"

        # manual 15 min = 0.25 h → COST 25; the manual pair stays authoritative
        res = app_client.patch(f"/api/operations/{op['id']}", json={"manual_runtime_mins": "15"})
        row = _op_row(res.json(), "Schleifen")
        assert _cell(row, 1)["calc_cost"] == "25.0000"
        # …and the manual value must NOT contaminate the calc side of the pair
        # (M1.9 review finding): the formula's own runtime stays underneath.
        assert row["calc_runtime_mins"] == "30.0000"

        # a formula that no longer declares runtime clears the stale calc time
        res2 = app_client.patch(f"/api/operations/{op['id']}", json={"cost_formula": "COST = 7"})
        row2 = _op_row(res2.json(), "Schleifen")
        assert row2["calc_runtime_mins"] is None


# --------------------------------------------------------------------------- #
# Router-order data flow (workpiece + cost dictionary)
# --------------------------------------------------------------------------- #
def test_workpiece_and_cost_dictionary_thread_in_router_order(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1])
        _add_formula_op(
            app_client,
            component,
            "Gewinde",
            "set_workpiece_value('gewinde', 8)\nCOST = 40",
        )
        op2 = _add_formula_op(
            app_client,
            component,
            "Eloxieren",
            "COST = get_workpiece_value('gewinde', 0) * 2 + get_cost_value('Gewinde') * 0.5",
        )
        # 8*2 + 40*0.5 = 36
        assert _cell(op2, 1)["calc_cost"] == "36.0000"


# --------------------------------------------------------------------------- #
# Drawer report
# --------------------------------------------------------------------------- #
def test_kalk_report_declares_variables_and_groups(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, [1, 5])
        formula = """
rate = var('Stundensatz', 60.0, 'EUR/hr', currency)
finish = drop_down_var('Finish', 'roh', create_list('roh', 'eloxiert'), '', string)
g = variable_group('Preise')
g.add_by_name('Stundensatz')
COST = rate * quantity
"""
        op = _add_formula_op(app_client, component, "Drehen", formula)
        report = app_client.get(f"/api/operations/{op['id']}/kalk").json()
        assert [r["quantity"] for r in report] == [1, 5]
        by_name = {d["name"]: d for d in report[0]["declared_variables"]}
        assert by_name["Stundensatz"]["value"] == 60.0
        assert by_name["Finish"]["options"] == ["roh", "eloxiert"]
        assert report[0]["variable_groups"] == [
            {"name": "Preise", "default_collapsed": False, "members": ["Stundensatz"]}
        ]
        assert report[0]["output"]["COST"] == 60.0
        assert report[1]["output"]["COST"] == 300.0

        # formula-less op → empty report
        created = app_client.post(
            f"/api/components/{component}/operations", json={"name": "Manuell"}
        )
        plain = next(o for o in created.json()["operations"] if o["name"] == "Manuell")
        assert app_client.get(f"/api/operations/{plain['id']}/kalk").json() == []
