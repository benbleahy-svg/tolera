"""M4.4 — milling interrogation wiring: setups/runtime/confidence through the
job layer.

MILLING joined ``RECOGNIZED_FAMILIES``, so the M4.2 wiring applies unchanged:
assigning a Milling-family process to a component (re-)interrogates the part's
PRIMARY CAD with that family, and the result JSON carries ``setups[]`` with
per-setup runtime + confidence — the honest-ceiling signal the part view and
(later, M4.10) auto-routing read.

Runs against real Postgres (skips without ``TEST_DATABASE_URL``) with
in-memory storage + eager Celery, like tests/test_interrogation_m42.py.
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
MILLED_BLOCK = (CAD_DIR / "block-milled-80x50x20.step").read_bytes()

RTOL = 1e-3


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _step_upload(name: str, data: bytes) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, data, "application/step"))


def _new_line(client: TestClient) -> tuple[str, str]:
    quote_id = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
    return str(item["part_id"]), str(item["root_component_id"])


def _milling_process_id(client: TestClient) -> str:
    processes = client.get("/api/processes").json()
    return str(next(p for p in processes if p["name"] == "Milling")["id"])


def _close(measured: float | None, target: float) -> bool:
    return measured is not None and abs(measured - target) / target < RTOL


def test_manual_milling_interrogation_returns_setups(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "milling-manual")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = app_client.post("/api/parts").json()["id"]
        with eager_celery():
            app_client.post(
                f"/api/parts/{part_id}/files", files=[_step_upload("block.step", MILLED_BLOCK)]
            )
            res = app_client.post(f"/api/parts/{part_id}/interrogate", json={"family": "MILLING"})
            assert res.status_code == 202, res.text

        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "succeeded"
        result = status["run"]["result"]
        assert result["family"] == "MILLING"
        assert result["confidence"] == "High"
        scalars = result["family_scalars"]
        assert scalars["setup_count"] == 1
        [setup] = scalars["setups"]
        assert setup["direction"] == [0.0, 0.0, 1.0]
        assert setup["setup_time"] == 1.0  # hours — the spec/KB default
        assert setup["confidence"] == "High"
        # the analytic golden runtime (fixtures/cad/goldens.json → milling)
        assert _close(scalars["runtime"], 2.2533333333 / 60.0)
        names = sorted({f["name"] for f in result["features"]})
        assert names == ["hole", "machine_direction", "pocket"]
        assert len([f for f in result["features"] if f["name"] == "hole"]) == 3


def test_setting_milling_process_triggers_family_run(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "milling-process-set")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id, component_id = _new_line(app_client)
        with eager_celery():
            app_client.post(
                f"/api/parts/{part_id}/files", files=[_step_upload("block.step", MILLED_BLOCK)]
            )
        assert app_client.get(f"/api/parts/{part_id}/interrogation").json()["run"]["family"] is None

        with eager_celery():
            res = app_client.patch(
                f"/api/components/{component_id}/process",
                json={"process_id": _milling_process_id(app_client), "keep_operations": True},
            )
            assert res.status_code == 200, res.text

        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "succeeded"
        assert status["run"]["family"] == "MILLING"
        result = status["run"]["result"]
        assert result["confidence"] == "High"
        scalars = result["family_scalars"]
        assert scalars["setup_count"] == 1
        [setup] = scalars["setups"]
        assert setup["direction"] == [0.0, 0.0, 1.0]
        assert setup["setup_time"] == 1.0
        assert setup["confidence"] == "High"
        assert _close(scalars["runtime"], 2.2533333333 / 60.0)
        assert len([f for f in result["features"] if f["name"] == "hole"]) == 3
