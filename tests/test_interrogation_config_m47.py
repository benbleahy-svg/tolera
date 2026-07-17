"""M4.7 — Configure -> Interrogations: seed + profile API.

* **Seed** — one default ``CustomInterrogation`` per Core-4 family with the
  DFM-WARNINGS catalogue defaults (metric); a re-seed creates nothing and
  never overwrites an edited threshold (the configure_seed rule).
* **API** — GET serves catalogue + org profiles; PUT validates against the
  family's allowed-input set. An always-on warning has no toggle key, so a
  disable attempt is rejected server-side (the block's acceptance).
* **Tenancy** — profiles are org-scoped via RLS; another org's profile is
  invisible (404 on update).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.interrogation import inputs_fingerprint
from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]


@contextmanager
def _as_admin(client: TestClient, org: uuid.UUID, user: uuid.UUID) -> Iterator[TestClient]:
    with authed(client, user_id=user, org_id=org, roles=ADMIN):
        yield client


def _org_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def test_seed_creates_core4_default_profiles(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "dfm-seed")
    result = seeder.configure_catalog(org)
    assert result.interrogation_profiles_created == 4

    with _as_admin(app_client, org, user) as client:
        payload = client.get("/api/configure/interrogations").json()
    profiles = {p["family"]: p for p in payload["profiles"]}
    assert set(profiles) == {"SHEET_METAL", "MILLING", "LATHE", "TUBE_LASER"}
    # DFM-WARNINGS §Implementation 1 name, verbatim
    assert profiles["SHEET_METAL"]["name"] == "Default Sheet Metal (Laser)"
    # catalogue defaults, metric-native (240 in -> 6096 mm; 8.0 ratio)
    assert profiles["SHEET_METAL"]["inputs"]["press_length"] == pytest.approx(6096.0)
    assert profiles["MILLING"]["inputs"]["deep_hole_ratio_threshold"] == 8.0
    assert profiles["SHEET_METAL"]["inputs"]["should_detect_tight_corners"] is False

    # catalogue rides along: v2/Spatial rows are marked, always-on rows flagged
    catalog = {c["family"]: c for c in payload["catalog"]}
    milling = {w["type"]: w for w in catalog["MILLING"]["warnings"]}
    assert milling["uncut_faces"]["always_on"] is True
    assert milling["uncut_faces"]["toggle"] is None
    assert milling["tapered_walls"]["v1_supported"] is False


def test_reseed_is_idempotent_and_preserves_edits(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "dfm-reseed")
    seeder.configure_catalog(org)

    with _as_admin(app_client, org, user) as client:
        payload = client.get("/api/configure/interrogations").json()
        mill = next(p for p in payload["profiles"] if p["family"] == "MILLING")
        edited = {**mill["inputs"], "deep_hole_ratio_threshold": 12.5}
        resp = client.put(f"/api/configure/interrogations/{mill['id']}", json={"inputs": edited})
        assert resp.status_code == 200

    result = seeder.configure_catalog(org)
    assert result.interrogation_profiles_created == 0

    with _as_admin(app_client, org, user) as client:
        payload = client.get("/api/configure/interrogations").json()
        mill = next(p for p in payload["profiles"] if p["family"] == "MILLING")
    assert mill["inputs"]["deep_hole_ratio_threshold"] == 12.5


def test_always_on_disable_is_rejected_server_side(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "dfm-alwayson")
    seeder.configure_catalog(org)
    with _as_admin(app_client, org, user) as client:
        payload = client.get("/api/configure/interrogations").json()
        mill = next(p for p in payload["profiles"] if p["family"] == "MILLING")
        resp = client.put(
            f"/api/configure/interrogations/{mill['id']}",
            json={"inputs": {**mill["inputs"], "should_detect_uncut_faces": False}},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "unknown_interrogation_input"


def test_input_validation_rejects_bad_values(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "dfm-validate")
    seeder.configure_catalog(org)
    with _as_admin(app_client, org, user) as client:
        payload = client.get("/api/configure/interrogations").json()
        mill = next(p for p in payload["profiles"] if p["family"] == "MILLING")
        url = f"/api/configure/interrogations/{mill['id']}"
        for bad in (
            {"deep_hole_ratio_threshold": -1},
            {"deep_hole_ratio_threshold": True},
            {"should_detect_deep_hole": "yes"},
            {"totally_made_up": 1.0},
        ):
            resp = client.put(url, json={"inputs": {**mill["inputs"], **bad}})
            assert resp.status_code == 422, bad


def test_profiles_are_org_scoped(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_admin(seeder, "dfm-org-a")
    org_b, user_b = _org_admin(seeder, "dfm-org-b")
    seeder.configure_catalog(org_a)
    seeder.configure_catalog(org_b)

    with _as_admin(app_client, org_a, user_a) as client:
        a_profile = client.get("/api/configure/interrogations").json()["profiles"][0]

    with _as_admin(app_client, org_b, user_b) as client:
        listed = client.get("/api/configure/interrogations").json()["profiles"]
        assert a_profile["id"] not in {p["id"] for p in listed}
        resp = client.put(
            f"/api/configure/interrogations/{a_profile['id']}",
            json={"inputs": a_profile["inputs"]},
        )
        assert resp.status_code == 404


def test_inputs_fingerprint_is_canonical() -> None:
    """Key order must not change the cache key; empty means engine defaults."""
    assert inputs_fingerprint(None) == ""
    assert inputs_fingerprint({}) == ""
    a = inputs_fingerprint({"x": 1.0, "y": True})
    b = inputs_fingerprint({"y": True, "x": 1.0})
    assert a == b and len(a) == 64
    assert inputs_fingerprint({"x": 2.0, "y": True}) != a


# --------------------------------------------------------------------------- #
# End-to-end: the org profile drives the worker run (toggle + cache key)
# --------------------------------------------------------------------------- #
from pathlib import Path  # noqa: E402

from tests.support import eager_celery  # noqa: E402

_TIGHTBEND = (
    Path(__file__).resolve().parent.parent / "fixtures" / "cad" / "bracket-tightbend-t2-r1.step"
).read_bytes()


def _interrogate(client: TestClient, blob: bytes) -> dict[str, Any]:
    part_id = client.post("/api/parts").json()["id"]
    with eager_celery():
        client.post(
            f"/api/parts/{part_id}/files",
            files=[("files", ("tb.step", blob, "application/step"))],
        )
        res = client.post(f"/api/parts/{part_id}/interrogate", json={"family": "SHEET_METAL"})
        assert res.status_code == 202, res.text
    status = client.get(f"/api/parts/{part_id}/interrogation").json()
    assert status["status"] == "succeeded"
    return cast(dict[str, Any], status["run"])


def test_org_profile_toggle_suppresses_warning_in_worker_run(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "dfm-worker")
    seeder.configure_catalog(org)

    with _as_admin(app_client, org, user) as client:
        run = _interrogate(client, _TIGHTBEND)
        # seeded defaults: the 0.5xt bend fires, run carries the profile hash
        assert run["inputs_hash"] != ""
        fired = {w["type"] for w in run["result"]["feedback"]}
        assert "small_bend_radius" in fired
        for w in run["result"]["feedback"]:
            if w["type"] == "small_bend_radius":
                assert w["threshold_used"] == {"min_bend_radius": 0.75}

        # toggle off -> a fresh run under the edited profile suppresses it
        payload = client.get("/api/configure/interrogations").json()
        sm = next(p for p in payload["profiles"] if p["family"] == "SHEET_METAL")
        client.put(
            f"/api/configure/interrogations/{sm['id']}",
            json={"inputs": {**sm["inputs"], "should_detect_small_bend_radius": False}},
        )
        run2 = _interrogate(client, _TIGHTBEND)
        assert run2["inputs_hash"] not in ("", run["inputs_hash"])
        assert "small_bend_radius" not in {w["type"] for w in run2["result"]["feedback"]}
