"""M4.1 — the interrogation job: upload trigger, state, persistence, cache.

The async slice around the pure engine (tests/test_geometry_engine_m41.py):
a PRIMARY CAD upload auto-queues an ``interrogation_run`` (post-commit, the
pdf_text precedent), the Celery task fills ``part_geometry`` raw + effective
columns WITHOUT clobbering manual overrides (calc-vs-override, DECISIONS.md
2026-06-26), ``part.geom_hash`` gets the versioned signature, and the status
endpoint drives the viewer's ``interrogating…`` state
(INTERROGATION-ENGINE-SPEC §5.6).

Runs against real Postgres (``app_client``/``seeder`` skip without
``TEST_DATABASE_URL``) with in-memory storage + eager Celery.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed
from tests.support import eager_celery

ADMIN = [MembershipRole.admin]
VIEWER = [MembershipRole.viewer]

CAD_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
CUBE = (CAD_DIR / "cube-20mm.step").read_bytes()
ASSEMBLY = (CAD_DIR / "asm-plate-2pins.step").read_bytes()

RTOL = 1e-3  # the Part-2 geometry tolerance (M4.0 probe gate)


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _step_upload(name: str, data: bytes) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, data, "application/step"))


def _create_part(client: TestClient) -> str:
    created = client.post("/api/parts")
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _close(measured: float | None, target: float) -> bool:
    return measured is not None and abs(measured - target) / target < RTOL


# --------------------------------------------------------------------------- #
# Upload → auto-interrogation → dims + signature persisted
# --------------------------------------------------------------------------- #
def test_primary_cad_upload_interrogates(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "interrogate-auto")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            up = app_client.post(
                f"/api/parts/{part_id}/files", files=[_step_upload("cube.step", CUBE)]
            )
            assert up.status_code == 201, up.text

        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "succeeded"
        run = status["run"]
        assert run["geom_hash"].startswith("gs1:")
        assert run["error_code"] is None
        dims = run["result"]["dimensions"]
        assert _close(dims["volume"], 8000.0)

        # The effective PartGeometry now reads the extraction (raw path).
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        assert _close(geom["size_x"], 20.0)
        assert _close(geom["size_y"], 20.0)
        assert _close(geom["size_z"], 20.0)
        assert _close(geom["area"], 2400.0)
        assert _close(geom["volume"], 8000.0)
        assert geom["weight"] is None  # no material known — never invented
        assert geom["overrides"] == {}  # nothing here was human-set


def test_interrogation_never_clobbers_manual_override(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Calc-vs-override: a human-set dim survives interrogation; the raw
    extraction is still recorded so the precedence stays auditable."""
    org, admin = _org_with_admin(seeder, "interrogate-override")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        set_dim = app_client.patch(f"/api/parts/{part_id}/geometry", json={"size_x": "99"})
        assert set_dim.status_code == 200, set_dim.text

        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("cube.step", CUBE)])

        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        assert geom["size_x"] == 99.0  # the override wins
        assert "size_x" in geom["overrides"]
        assert _close(geom["size_y"], 20.0)  # non-overridden dims refresh
        assert _close(geom["volume"], 8000.0)


def test_clearing_override_restores_extraction(app_client: TestClient, seeder: Seeder) -> None:
    """COALESCE(override, raw): dropping a human override falls back to the
    interrogation extraction instead of discarding the machine's answer."""
    org, admin = _org_with_admin(seeder, "interrogate-clear-override")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("cube.step", CUBE)])
        app_client.patch(f"/api/parts/{part_id}/geometry", json={"size_x": "99"})
        assert app_client.get(f"/api/parts/{part_id}/geometry").json()["size_x"] == 99.0

        cleared = app_client.patch(f"/api/parts/{part_id}/geometry", json={"size_x": None})
        assert cleared.status_code == 200, cleared.text
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        assert _close(geom["size_x"], 20.0)  # back to the extraction
        assert "size_x" not in geom["overrides"]


def test_primary_swap_clears_stale_geometry(app_client: TestClient, seeder: Seeder) -> None:
    """Swapping PRIMARY invalidates the old file's extraction in the same
    transaction — a failing new body (assembly) must not leave the previous
    file's dims/signature live for matching or costing."""
    org, admin = _org_with_admin(seeder, "interrogate-swap-stale")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("cube.step", CUBE)])
        assert _close(app_client.get(f"/api/parts/{part_id}/geometry").json()["volume"], 8000.0)

        # Manual override set before the swap must survive the invalidation.
        app_client.patch(f"/api/parts/{part_id}/geometry", json={"weight": "42"})

        with eager_celery():
            up = app_client.post(
                f"/api/parts/{part_id}/files", files=[_step_upload("asm.step", ASSEMBLY)]
            )
            [asm_file] = up.json()
            swapped = app_client.post(f"/api/parts/{part_id}/files/{asm_file['id']}/primary")
            assert swapped.status_code == 200, swapped.text

        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "failed"
        assert status["run"]["error_code"] == "multi_body"
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        assert geom["volume"] is None  # stale extraction cleared
        assert geom["size_x"] is None
        assert geom["weight"] == 42.0  # the human's entry survives

        # Swapping back to the CAD body re-interrogates (cache) and refills.
        files = app_client.get(f"/api/parts/{part_id}/files").json()
        cube_file = next(f for f in files if f["filename"] == "cube.step")
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files/{cube_file['id']}/primary")
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        assert _close(geom["volume"], 8000.0)


def test_queued_state_before_worker_runs(app_client: TestClient, seeder: Seeder) -> None:
    """Without a worker the run stays ``queued`` — the ``interrogating…``
    state the part view shows (INTERROGATION-ENGINE-SPEC §5.6). (No broker in
    tests: the post-commit enqueue fails soft, exactly like pdf_text.)"""
    org, admin = _org_with_admin(seeder, "interrogate-queued")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("cube.step", CUBE)])
        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "queued"
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        assert geom["size_x"] is None  # nothing filled yet


def test_no_cad_part_has_no_interrogation(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "interrogate-none")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "none"
        assert status["run"] is None


# --------------------------------------------------------------------------- #
# Failure taxonomy
# --------------------------------------------------------------------------- #
def test_assembly_step_fails_with_multi_body(app_client: TestClient, seeder: Seeder) -> None:
    """Single-body invariant: the assembly fixture (3 solids) fails the run
    with a machine-readable code — decomposition is M4.9b, never a guess."""
    org, admin = _org_with_admin(seeder, "interrogate-multibody")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            files = [_step_upload("asm.step", ASSEMBLY)]
            app_client.post(f"/api/parts/{part_id}/files", files=files)
        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "failed"
        assert status["run"]["error_code"] == "multi_body"
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        assert geom["volume"] is None


def test_oversized_file_fails_gate(
    app_client: TestClient, seeder: Seeder, monkeypatch: object
) -> None:
    """The ingest size gate (spec §5.1; KB interrogations-basics limits table)
    fails the run as ``file_too_large`` instead of burning worker time."""
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    from app import interrogation

    monkeypatch.setattr(interrogation, "DEFAULT_SIZE_LIMIT_BYTES", 10)  # tiny for the test
    org, admin = _org_with_admin(seeder, "interrogate-oversize")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("cube.step", CUBE)])
        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "failed"
        assert status["run"]["error_code"] == "file_too_large"


# --------------------------------------------------------------------------- #
# Manual re-trigger (viewer path) + material → weight
# --------------------------------------------------------------------------- #
def test_retrigger_with_material_fills_weight(app_client: TestClient, seeder: Seeder) -> None:
    """POST /interrogate with a material: weight = volume x density
    (20 mm cube @ seeded 1.4301, 7.90 g/cm3 → 63.20 g)."""
    org, admin = _org_with_admin(seeder, "interrogate-material")
    seeder.configure_catalog(org)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("cube.step", CUBE)])

        material = app_client.get("/api/materials", params={"q": "1.4301"}).json()[0]
        with eager_celery():
            res = app_client.post(
                f"/api/parts/{part_id}/interrogate", json={"material_id": material["id"]}
            )
            assert res.status_code == 202, res.text

        status = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert status["status"] == "succeeded"
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        assert _close(geom["weight"], 63.2)


def test_retrigger_requires_primary_cad(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "interrogate-nocad")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        res = app_client.post(f"/api/parts/{part_id}/interrogate", json={})
        assert res.status_code == 422
        assert res.json()["code"] == "no_primary_cad"


def test_retrigger_requires_quote_edit(app_client: TestClient, seeder: Seeder) -> None:
    org = seeder.org("interrogate-rbac")
    viewer = seeder.user("viewer@interrogate-rbac.example")
    seeder.membership(viewer, org, VIEWER)
    with authed(app_client, user_id=viewer, org_id=org, roles=VIEWER):
        part_id_res = app_client.post("/api/parts")
        assert part_id_res.status_code == 403  # viewers can't even create parts
        # And the trigger itself is quote_edit-gated on someone else's part.
        res = app_client.post(f"/api/parts/{uuid.uuid4()}/interrogate", json={})
        assert res.status_code == 403


# --------------------------------------------------------------------------- #
# Result cache (§5.4) — same body, same org → reuse, never cross-org
# --------------------------------------------------------------------------- #
def test_identical_body_reuses_cached_result(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "interrogate-cache")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        first = _create_part(app_client)
        second = _create_part(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{first}/files", files=[_step_upload("a.step", CUBE)])
            app_client.post(f"/api/parts/{second}/files", files=[_step_upload("b.step", CUBE)])

        run_a = app_client.get(f"/api/parts/{first}/interrogation").json()["run"]
        run_b = app_client.get(f"/api/parts/{second}/interrogation").json()["run"]
        assert run_a["geom_hash"] == run_b["geom_hash"]
        assert run_b["result"]["cached_from"] == run_a["id"]
        # The cached copy fills PartGeometry identically.
        geom_b = app_client.get(f"/api/parts/{second}/geometry").json()
        assert _close(geom_b["volume"], 8000.0)


def test_duplicate_delivery_never_overwrites_success(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Celery acks late → the broker may deliver a run twice. A redelivery of
    an already-succeeded run must skip (row claimed FOR UPDATE), never re-run
    or downgrade the committed result."""
    from app.interrogation import interrogate_part_task

    org, admin = _org_with_admin(seeder, "interrogate-duplicate")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_id}/files", files=[_step_upload("cube.step", CUBE)])
        run = app_client.get(f"/api/parts/{part_id}/interrogation").json()["run"]
        assert run["status"] == "succeeded"

        # Second delivery of the SAME task message.
        out = interrogate_part_task.run(str(org), run["id"])
        # part_id rides along so the redelivery still chains the M4.12
        # requote-diff job (idempotent) even when the success already committed.
        assert out == {
            "skipped": "already_succeeded",
            "run_id": run["id"],
            "part_id": part_id,
        }
        after = app_client.get(f"/api/parts/{part_id}/interrogation").json()["run"]
        assert after["status"] == "succeeded"
        assert after["finished_at"] == run["finished_at"]  # untouched, not re-run


def test_interrogation_is_org_scoped(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_with_admin(seeder, "interrogate-org-a")
    org_b, admin_b = _org_with_admin(seeder, "interrogate-org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        part_a = _create_part(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_a}/files", files=[_step_upload("a.step", CUBE)])
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        # Foreign part: invisible (404) — RLS + org scoping.
        assert app_client.get(f"/api/parts/{part_a}/interrogation").status_code == 404
        # And a same-body upload in org B must NOT reuse org A's run.
        part_b = _create_part(app_client)
        with eager_celery():
            app_client.post(f"/api/parts/{part_b}/files", files=[_step_upload("b.step", CUBE)])
        run_b = app_client.get(f"/api/parts/{part_b}/interrogation").json()["run"]
        assert "cached_from" not in run_b["result"]
