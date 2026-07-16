"""M4.2 — family interrogation wiring: sheet-metal runs through the job layer.

The spec's trigger sentence — "When a sheet-metal process is set, an
interrogation block shows the auto-detected flat pattern + attributes"
(spec ``#sheetmetal``): assigning a SHEET_METAL-family process to a component
enqueues a family interrogation of the part's PRIMARY CAD, and a PRIMARY
upload resolves the family from the component's process (the M4.1
material-resolution precedent). The result JSON carries the recognizer's
``family_scalars``/``features`` to the part view.

Runs against real Postgres (skips without ``TEST_DATABASE_URL``) with
in-memory storage + eager Celery, like tests/test_interrogation_m41.py.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed
from tests.support import eager_celery

ADMIN = [MembershipRole.admin]

CAD_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
BRACKET = (CAD_DIR / "bracket-L-60x40x2-r3.step").read_bytes()

RTOL = 1e-3


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _step_upload(name: str, data: bytes) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, data, "application/step"))


def _new_line(client: TestClient) -> tuple[str, str]:
    """Draft quote + line item → (part_id, root component_id)."""
    quote_id = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
    return str(item["part_id"]), str(item["root_component_id"])


def _sheet_metal_process_id(client: TestClient) -> str:
    processes = client.get("/api/processes").json()
    return str(next(p for p in processes if p["name"] == "Sheet Metal")["id"])


def _close(measured: float | None, target: float) -> bool:
    return measured is not None and abs(measured - target) / target < RTOL


# --------------------------------------------------------------------------- #
# Manual family trigger (viewer path) → scalars in the result JSON
# --------------------------------------------------------------------------- #
def test_manual_sheet_metal_interrogation_returns_scalars(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "sheetmetal-manual")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = app_client.post("/api/parts").json()["id"]
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("br.step", BRACKET)])
            res = app_client.post(
                f"/api/parts/{part_id}/interrogate", json={"family": "SHEET_METAL"}
            )
            assert res.status_code == 202, res.text

        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "succeeded"
        result = status["run"]["result"]
        assert status["run"]["family"] == "SHEET_METAL"
        assert result["family"] == "SHEET_METAL"
        scalars = result["family_scalars"]
        assert scalars["bend_count"] == 1
        assert _close(scalars["thickness"], 2.0)
        assert _close(scalars["size_x"], 95.8717)  # k-factor developed length
        assert _close(scalars["size_y"], 50.0)
        assert _close(scalars["flat_area"], 4814.16)
        [bend] = result["features"]
        assert bend["name"] == "bend"
        assert _close(bend["properties"]["radius"], 3.0)
        assert _close(bend["properties"]["angle"], 90.0)


# --------------------------------------------------------------------------- #
# "When a sheet-metal process is set …" (spec #sheetmetal)
# --------------------------------------------------------------------------- #
def test_setting_sheet_metal_process_triggers_family_run(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "sheetmetal-process-set")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id, component_id = _new_line(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("br.step", BRACKET)])
        # The dims-only upload run exists; family is not yet known.
        assert app_client.get(f"/api/parts/{part_id}/interrogation").json()["run"]["family"] is None

        with eager_celery():
            res = app_client.patch(
                f"/api/components/{component_id}/process",
                json={"process_id": _sheet_metal_process_id(app_client), "keep_operations": True},
            )
            assert res.status_code == 200, res.text

        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "succeeded"
        assert status["run"]["family"] == "SHEET_METAL"
        assert status["run"]["result"]["family_scalars"]["bend_count"] == 1


def test_setting_process_without_cad_enqueues_nothing(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "sheetmetal-process-nocad")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id, component_id = _new_line(app_client)
        with eager_celery():
            res = app_client.patch(
                f"/api/components/{component_id}/process",
                json={"process_id": _sheet_metal_process_id(app_client), "keep_operations": True},
            )
            assert res.status_code == 200, res.text
        assert app_client.get(f"/api/parts/{part_id}/interrogation").json()["status"] == "none"


def test_upload_resolves_family_from_component_process(
    app_client: TestClient, seeder: Seeder
) -> None:
    """PRIMARY upload AFTER the process is set: the auto-run carries the
    component's unambiguous family (the resolve_part_material_id precedent)."""
    org, admin = _org_with_admin(seeder, "sheetmetal-upload-family")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id, component_id = _new_line(app_client)
        res = app_client.patch(
            f"/api/components/{component_id}/process",
            json={"process_id": _sheet_metal_process_id(app_client), "keep_operations": True},
        )
        assert res.status_code == 200, res.text

        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("br.step", BRACKET)])

        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "succeeded"
        assert status["run"]["family"] == "SHEET_METAL"
        scalars = status["run"]["result"]["family_scalars"]
        assert scalars["bend_count"] == 1
        assert "flat_pattern" in scalars  # the thumbnail contract rides along


def test_repeated_process_set_reuses_existing_run(app_client: TestClient, seeder: Seeder) -> None:
    """Re-assigning the same family must not pile up duplicate runs — the
    existing (part, file, family) run is the answer."""
    org, admin = _org_with_admin(seeder, "sheetmetal-process-idem")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id, component_id = _new_line(app_client)
        process_id = _sheet_metal_process_id(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("br.step", BRACKET)])
            for _ in range(2):
                app_client.patch(
                    f"/api/components/{component_id}/process",
                    json={"process_id": process_id, "keep_operations": True},
                )
        first = app_client.get(f"/api/parts/{part_id}/interrogation").json()["run"]

        with eager_celery():
            app_client.patch(
                f"/api/components/{component_id}/process",
                json={"process_id": process_id, "keep_operations": True},
            )
        after = app_client.get(f"/api/parts/{part_id}/interrogation").json()["run"]
        assert after["id"] == first["id"]  # no new run created
