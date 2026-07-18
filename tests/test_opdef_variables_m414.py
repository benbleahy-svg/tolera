"""Tests for M4.14 — op-def formula-evaluation endpoint + Variables table,
API/DB layer (real RLS-bound Postgres; the synthetic evaluation itself is
covered by ``test_kalk_m414_def_eval``).

Covers: the def-level report (declared variables + defaults + visibility,
no quote operation needed); the visibility PUT (eye toggles) persisting and
overlaying; snapshot-on-attach carrying the eyes to the quote side (E4-d) so
the Show-hidden filter honours them; Refresh Pricing re-copying the snapshot;
formula errors as report errors (never a 500); permissions + org isolation.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
ENGINEER = [MembershipRole.engineer]

FORMULA = (
    "rate = var('Stundensatz', 60, 'EUR/hr')\n"
    "hidden = var('Ruestfaktor', 1.5, '', default_visible=False)\n"
    "per_qty = var('Minuten pro Teil', 6, '', quantity_specific=True)\n"
    "COST = rate * per_qty / 60 * quantity\n"
    "DAYS = 0\n"
)


def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _create_def(client: TestClient, name: str, formula: str | None = FORMULA) -> dict[str, Any]:
    res = client.post(
        "/api/operation-defs", json={"name": name, "cost_formula": formula, "run_rate": "80"}
    )
    assert res.status_code == 201, res.text
    created: dict[str, Any] = res.json()
    return created


def _new_component(client: TestClient) -> str:
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    return str(item["root_component_id"])


def _by_name(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {v["name"]: v for v in report["declared_variables"]}


class TestDefKalkReport:
    def test_report_returns_variables_without_a_quote(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def = _create_def(app_client, "Fräsen")
            report = app_client.get(f"/api/operation-defs/{op_def['id']}/kalk")
            assert report.status_code == 200, report.text
            variables = _by_name(report.json())
        assert variables["Stundensatz"]["default"] == 60
        assert variables["Stundensatz"]["default_visible"] is True
        assert variables["Ruestfaktor"]["default_visible"] is False
        assert variables["Minuten pro Teil"]["quantity_specific"] is True
        assert report.json()["errors"] == []

    def test_def_without_formula_reports_empty(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def = _create_def(app_client, "Entgraten", formula=None)
            report = app_client.get(f"/api/operation-defs/{op_def['id']}/kalk").json()
        assert report == {
            "declared_variables": [],
            "variable_groups": [],
            "errors": [],
            "variable_visibility": {},
        }

    def test_runtime_error_is_a_report_error_not_a_500(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        # statically valid (passes the save-time CHECK), fails at evaluation
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            failing = "x = var('x', 1)\nCOST = 1 / 0\nDAYS = 0"
            op_def = _create_def(app_client, "Sägen", formula=failing)
            res = app_client.get(f"/api/operation-defs/{op_def['id']}/kalk")
        assert res.status_code == 200, res.text
        report = res.json()
        assert report["errors"][0]["code"] == "runtime_error"
        assert report["errors"][0]["line"] is not None
        assert "x" in _by_name(report)

    def test_unknown_def_404(self, app_client: TestClient, seeder: Seeder) -> None:
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            res = app_client.get(f"/api/operation-defs/{uuid.uuid4()}/kalk")
        assert res.status_code == 404

    def test_org_isolation(self, app_client: TestClient, seeder: Seeder) -> None:
        org_a, user_a = _org_admin(seeder, "org-a")
        org_b, user_b = _org_admin(seeder, "org-b")
        with authed(app_client, user_id=user_a, org_id=org_a, roles=ADMIN):
            op_def = _create_def(app_client, "Fräsen")
        with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
            # cross-org read AND write are both invisible (RLS)
            assert app_client.get(f"/api/operation-defs/{op_def['id']}/kalk").status_code == 404
            res = app_client.put(
                f"/api/operation-defs/{op_def['id']}/variable-visibility",
                json={"visibility": {"Stundensatz": False}},
            )
            assert res.status_code == 404
        with authed(app_client, user_id=user_a, org_id=org_a, roles=ADMIN):
            defs = app_client.get("/api/operation-defs?q=Fräsen").json()
        assert defs[0]["variable_visibility"] == {}  # the foreign PUT changed nothing


class TestVariableVisibility:
    def test_eye_toggle_persists_and_overlays(self, app_client: TestClient, seeder: Seeder) -> None:
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def = _create_def(app_client, "Fräsen")
            res = app_client.put(
                f"/api/operation-defs/{op_def['id']}/variable-visibility",
                json={"visibility": {"Stundensatz": False, "Ruestfaktor": True}},
            )
            assert res.status_code == 200, res.text
            variables = _by_name(res.json())
            assert variables["Stundensatz"]["default_visible"] is False
            assert variables["Ruestfaktor"]["default_visible"] is True
            # the report carries the stored map — the client's PUT base
            assert res.json()["variable_visibility"] == {
                "Stundensatz": False,
                "Ruestfaktor": True,
            }
            # the stored map is on the def resource for the next toggle
            defs = app_client.get("/api/operation-defs?q=Fräsen").json()
            assert defs[0]["variable_visibility"] == {
                "Stundensatz": False,
                "Ruestfaktor": True,
            }

    def test_visibility_write_needs_config_edit(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org = seeder.org("org-a")
        admin = seeder.user("admin@org-a.example")
        seeder.membership(admin, org, ADMIN)
        engineer = seeder.user("eng@org-a.example")
        seeder.membership(engineer, org, ENGINEER)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            op_def = _create_def(app_client, "Fräsen")
        with authed(app_client, user_id=engineer, org_id=org, roles=ENGINEER):
            # read is view-level…
            assert app_client.get(f"/api/operation-defs/{op_def['id']}/kalk").status_code == 200
            # …the eye is config-level
            res = app_client.put(
                f"/api/operation-defs/{op_def['id']}/variable-visibility",
                json={"visibility": {"Stundensatz": False}},
            )
        assert res.status_code == 403


class TestQuoteSideHonoursSnapshot:
    def test_attach_snapshots_visibility_and_report_overlays(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def = _create_def(app_client, "Fräsen")
            toggled = app_client.put(
                f"/api/operation-defs/{op_def['id']}/variable-visibility",
                json={"visibility": {"Stundensatz": False}},
            )
            assert toggled.status_code == 200, toggled.text
            assert _by_name(toggled.json())["Stundensatz"]["default_visible"] is False
            component_id = _new_component(app_client)
            created = app_client.post(
                f"/api/components/{component_id}/operations",
                json={"operation_def_id": op_def["id"]},
            )
            assert created.status_code == 201, created.text
            op = created.json()["operations"][0]
            report = app_client.get(f"/api/operations/{op['id']}/kalk").json()
        by_name = {d["name"]: d for d in report[0]["declared_variables"]}
        assert by_name["Stundensatz"]["default_visible"] is False

    def test_def_toggle_after_attach_does_not_reach_the_frozen_op(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def = _create_def(app_client, "Fräsen")
            component_id = _new_component(app_client)
            op = app_client.post(
                f"/api/components/{component_id}/operations",
                json={"operation_def_id": op_def["id"]},
            ).json()["operations"][0]
            app_client.put(
                f"/api/operation-defs/{op_def['id']}/variable-visibility",
                json={"visibility": {"Stundensatz": False}},
            )
            report = app_client.get(f"/api/operations/{op['id']}/kalk").json()
        by_name = {d["name"]: d for d in report[0]["declared_variables"]}
        # E4-d freeze: the attached op keeps its snapshot (visible)
        assert by_name["Stundensatz"]["default_visible"] is True

    def test_refresh_pricing_recopies_the_visibility_snapshot(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def = _create_def(app_client, "Fräsen")
            qid = app_client.post("/api/quotes", json={}).json()["id"]
            item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][0]
            component_id = str(item["root_component_id"])
            op = app_client.post(
                f"/api/components/{component_id}/operations",
                json={"operation_def_id": op_def["id"]},
            ).json()["operations"][0]
            app_client.put(
                f"/api/operation-defs/{op_def['id']}/variable-visibility",
                json={"visibility": {"Stundensatz": False}},
            )
            refreshed = app_client.post(f"/api/quotes/{qid}/refresh-pricing")
            assert refreshed.status_code == 200, refreshed.text
            report = app_client.get(f"/api/operations/{op['id']}/kalk").json()
        by_name = {d["name"]: d for d in report[0]["declared_variables"]}
        assert by_name["Stundensatz"]["default_visible"] is False

    def test_refresh_pricing_ignores_soft_deleted_defs(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        # a hidden (deleted_at) def must never push its formula/visibility
        # back onto an attached operation — the frozen snapshot stays
        org, user = _org_admin(seeder)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def = _create_def(app_client, "Fräsen")
            qid = app_client.post("/api/quotes", json={}).json()["id"]
            item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][0]
            component_id = str(item["root_component_id"])
            op = app_client.post(
                f"/api/components/{component_id}/operations",
                json={"operation_def_id": op_def["id"]},
            ).json()["operations"][0]
            app_client.put(
                f"/api/operation-defs/{op_def['id']}/variable-visibility",
                json={"visibility": {"Stundensatz": False}},
            )
            seeder.sql(
                "UPDATE operation_def SET deleted_at = now() WHERE id = :id",
                {"id": str(op_def["id"])},
            )
            refreshed = app_client.post(f"/api/quotes/{qid}/refresh-pricing")
            assert refreshed.status_code == 200, refreshed.text
            report = app_client.get(f"/api/operations/{op['id']}/kalk").json()
        by_name = {d["name"]: d for d in report[0]["declared_variables"]}
        # the deleted def's toggle did NOT reach the frozen op
        assert by_name["Stundensatz"]["default_visible"] is True
