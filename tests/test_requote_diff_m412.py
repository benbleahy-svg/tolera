"""M4.12 — AI: Requote Diff Assistant.

Two tracks (the M3.9 pattern):

* Pure unit tests (no DB) — the machine-checkable diff math: geometry delta
  (volume / bbox / feature counts + the deterministic ``significant`` flag)
  and the ``ExtractionFinding`` set-diff (added / removed / changed + the
  deterministic ``material_changes`` M4.13's server-side gate will consume).
* DB integration — seed a Rev-A part with a prior quote and a Rev-B part on a
  new draft quote (exact-geometric match), run the task, assert the diff is
  cached as ``quote.requote_diff`` JSONB; AI gating (master off / export
  control / provider error); the read + choice endpoints; and the explicit-
  selection invariant: computing a diff never copies a single operation.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import requote_diff
from app.models import MembershipRole
from app.requote_diff import (
    finding_diff,
    geometry_delta,
    run_generate_requote_diff,
)
from tests.conftest import Seeder, app_role_url, authed

ADMIN = [MembershipRole.admin]


# --------------------------------------------------------------------------- #
# Geometry delta — pure unit tests
# --------------------------------------------------------------------------- #


def _raw(
    *,
    volume: float = 100_000.0,
    size: tuple[float, float, float] = (120.0, 80.0, 10.0),
    features: list[dict[str, Any]] | None = None,
    scalars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A minimal persisted ``AnalysisResult`` dict (the ``PartGeometry.raw`` shape)."""
    return {
        "family": "milling",
        "dimensions": {
            "size_x": size[0],
            "size_y": size[1],
            "size_z": size[2],
            "volume": volume,
            "area": 25_000.0,
        },
        "features": features or [],
        "family_scalars": scalars or {},
    }


def test_geometry_delta_volume_bbox_and_feature_counts() -> None:
    a = _raw(volume=100_000.0, features=[{"name": "hole"}] * 12)
    b = _raw(volume=97_700.0, features=[{"name": "hole"}] * 12 + [{"name": "pocket"}])
    delta = geometry_delta(a, b)
    assert delta["available"] is True
    assert delta["volume"]["a"] == 100_000.0
    assert delta["volume"]["b"] == 97_700.0
    assert delta["volume"]["delta_pct"] == pytest.approx(-2.3)
    assert delta["bbox"]["size_x"]["delta"] == 0.0
    assert delta["features"]["hole"] == {"a": 12, "b": 12, "delta": 0}
    assert delta["features"]["pocket"] == {"a": 0, "b": 1, "delta": 1}


def test_geometry_delta_scalar_counts_merge_into_features() -> None:
    a = _raw(scalars={"bend_count": 4, "pierce_count": 10})
    b = _raw(scalars={"bend_count": 5, "pierce_count": 10})
    delta = geometry_delta(a, b)
    assert delta["features"]["bend_count"] == {"a": 4, "b": 5, "delta": 1}
    assert delta["features"]["pierce_count"]["delta"] == 0


def test_geometry_delta_insignificant_when_within_thresholds() -> None:
    # -2.3 % volume, no feature change, bbox identical → cosmetic.
    a = _raw(volume=100_000.0)
    b = _raw(volume=97_700.0)
    assert geometry_delta(a, b)["significant"] is False


def test_geometry_delta_significant_on_volume() -> None:
    a = _raw(volume=100_000.0)
    b = _raw(volume=94_000.0)  # -6 % > the 5 % threshold
    assert geometry_delta(a, b)["significant"] is True


def test_geometry_delta_significant_on_feature_count_change() -> None:
    a = _raw(features=[{"name": "hole"}] * 12)
    b = _raw(features=[{"name": "hole"}] * 12 + [{"name": "pocket"}])
    assert geometry_delta(a, b)["significant"] is True


def test_geometry_delta_significant_on_bbox_dim() -> None:
    a = _raw(size=(120.0, 80.0, 10.0))
    b = _raw(size=(120.0, 80.0, 11.5))  # +1.5 mm > the 1.0 mm threshold
    assert geometry_delta(a, b)["significant"] is True


def test_geometry_delta_unavailable_without_raw() -> None:
    # PDF-only parts carry no interrogation result: nothing to subtract. The
    # flag stays False — an exact-file match means byte-identical inputs.
    delta = geometry_delta(None, _raw())
    assert delta["available"] is False
    assert delta["significant"] is False


# --------------------------------------------------------------------------- #
# Finding set-diff — pure unit tests
# --------------------------------------------------------------------------- #


def _finding(
    *,
    type_: str = "linear_dimension",
    category: str = "dimensions",
    role: str | None = None,
    value: str | None = None,
    normalized: str | None = None,
    tolerance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": type_,
        "category": category,
        "role": role,
        "value": value,
        "normalized_value": normalized,
        "units": "mm",
        "tolerance": tolerance,
        "gdt": None,
    }


def test_finding_diff_added_removed_changed() -> None:
    bore_a = _finding(
        type_="diameter",
        role="bore_3",
        normalized="12.5",
        tolerance={"kind": "bilateral", "upper": 0.010, "lower": -0.010},
    )
    bore_b = {**bore_a, "tolerance": {"kind": "bilateral", "upper": 0.005, "lower": -0.005}}
    fai = _finding(
        type_="note", category="requirements", role=None, value="FIRST ARTICLE INSPECTION REQUIRED"
    )
    dropped = _finding(type_="note", category="requirements", role=None, value="Entgraten")
    diff = finding_diff([bore_a, dropped], [bore_b, fai])
    assert [f["value"] for f in diff["added"]] == ["FIRST ARTICLE INSPECTION REQUIRED"]
    assert [f["value"] for f in diff["removed"]] == ["Entgraten"]
    [changed] = diff["changed"]
    assert changed["a"]["tolerance"]["upper"] == 0.010
    assert changed["b"]["tolerance"]["upper"] == 0.005
    assert "tolerance" in changed["changes"]


def test_finding_diff_identical_sets_are_empty() -> None:
    f = _finding(role="bore_1", normalized="8.0")
    diff = finding_diff([f], [dict(f)])
    assert diff == {"added": [], "removed": [], "changed": [], "material_changes": []}


def test_finding_diff_material_changes_deterministic() -> None:
    """M4.13's Accept-All suppression reads ``material_changes`` server-side —
    it must come from the deterministic classifier, never the LLM."""
    bore_a = _finding(
        type_="diameter",
        role="bore_3",
        normalized="12.5",
        tolerance={"kind": "bilateral", "upper": 0.010, "lower": -0.010},
    )
    bore_b = {**bore_a, "tolerance": {"kind": "bilateral", "upper": 0.005, "lower": -0.005}}
    fai = _finding(type_="note", category="requirements", value="FAI REQUIRED")
    diff = finding_diff([bore_a], [bore_b, fai])
    reasons = {m["reason"] for m in diff["material_changes"]}
    assert reasons == {"tolerance_changed", "requirements_added"}


def test_finding_diff_material_on_material_type_change() -> None:
    mat_a = _finding(type_="material", category="quote_setup", normalized="1.4301")
    mat_b = _finding(type_="material", category="quote_setup", normalized="1.4404")
    diff = finding_diff([mat_a], [mat_b])
    assert any(m["reason"] == "material_changed" for m in diff["material_changes"])


def test_finding_diff_cosmetic_value_change_not_material() -> None:
    # A re-worded title-block note (category ``regions``) is cosmetic.
    a = _finding(type_="note", category="regions", role="title_block", value="Zeichnung Rev A")
    b = _finding(type_="note", category="regions", role="title_block", value="Zeichnung Rev B")
    diff = finding_diff([a], [b])
    assert len(diff["changed"]) == 1
    assert diff["material_changes"] == []


# --------------------------------------------------------------------------- #
# DB integration — task, gating, endpoints, explicit-selection invariant
# --------------------------------------------------------------------------- #


class _FakeSynthesizer:
    def __init__(self) -> None:
        self.calls = 0
        self.last_diff: dict[str, Any] | None = None

    async def synthesize(self, diff: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.last_diff = diff
        return {"synthesis": "Geringfügige Änderung — engere Bohrungstoleranz."}


@pytest.fixture
def fake_synthesizer() -> Iterator[_FakeSynthesizer]:
    synth = _FakeSynthesizer()
    requote_diff.register(synth)
    try:
        yield synth
    finally:
        requote_diff.register(None)


GEOM_HASH = "gs1:deadbeefdeadbeefdeadbeefdeadbeef"


def _plant_geometry(
    seeder: Seeder, org_id: uuid.UUID, part_id: uuid.UUID, raw: dict[str, Any]
) -> None:
    dims = raw["dimensions"]
    seeder.sql(
        "INSERT INTO part_geometry (id, org_id, part_id, size_x, size_y, size_z, volume, raw) "
        "VALUES (:id, :org, :part, :sx, :sy, :sz, :vol, CAST(:raw AS jsonb))",
        {
            "id": str(uuid.uuid4()),
            "org": str(org_id),
            "part": str(part_id),
            "sx": dims["size_x"],
            "sy": dims["size_y"],
            "sz": dims["size_z"],
            "vol": dims["volume"],
            "raw": json.dumps(raw),
        },
    )


def _plant_finding(
    seeder: Seeder,
    org_id: uuid.UUID,
    file_id: uuid.UUID,
    *,
    type_: str = "note",
    category: str = "requirements",
    value: str | None = None,
    normalized: str | None = None,
    role: str | None = None,
    tolerance: dict[str, Any] | None = None,
    status: str = "accepted",
) -> None:
    seeder.sql(
        "INSERT INTO extraction_finding "
        "(id, org_id, source_file_id, category, type, value, normalized_value, role, "
        " tolerance, confidence, status) "
        "VALUES (:id, :org, :file, :cat, :type, :val, :norm, :role, "
        "        CAST(:tol AS jsonb), 0.9, :status)",
        {
            "id": str(uuid.uuid4()),
            "org": str(org_id),
            "file": str(file_id),
            "cat": category,
            "type": type_,
            "val": value,
            "norm": normalized,
            "role": role,
            "tol": json.dumps(tolerance) if tolerance is not None else None,
            "status": status,
        },
    )


def _quote_item(client: TestClient, quote_id: uuid.UUID) -> dict[str, Any]:
    detail = client.post(f"/api/quotes/{quote_id}/items")
    assert detail.status_code in (200, 201)
    return cast("dict[str, Any]", detail.json()["items"][-1])


def _seed_requote_pair(
    seeder: Seeder,
    client: TestClient,
    org_id: uuid.UUID,
    *,
    volume_b: float = 97_700.0,
) -> dict[str, Any]:
    """Rev A on a prior quote + Rev B on a new draft quote, same ``geom_hash``.

    Returns ids: prior/new quote, part and component for each, file ids."""
    prior_quote = seeder.quote(org_id, "Q-2026-1000")
    prior_item = _quote_item(client, prior_quote)
    new_quote = seeder.quote(org_id, "Q-2026-2000")
    new_item = _quote_item(client, new_quote)
    part_a = uuid.UUID(prior_item["part_id"])
    part_b = uuid.UUID(new_item["part_id"])
    for pid in (part_a, part_b):
        seeder.sql(
            "UPDATE part SET geom_hash = :h WHERE id = :id",
            {"h": GEOM_HASH, "id": str(pid)},
        )
    _plant_geometry(seeder, org_id, part_a, _raw(volume=100_000.0))
    _plant_geometry(seeder, org_id, part_b, _raw(volume=volume_b))
    file_a = seeder.part_file(org_id, part_a, filename="halter-rev-a.step")
    file_b = seeder.part_file(org_id, part_b, filename="halter-rev-b.step")
    return {
        "prior_quote": prior_quote,
        "new_quote": new_quote,
        "part_a": part_a,
        "part_b": part_b,
        "component_a": uuid.UUID(prior_item["root_component_id"]),
        "component_b": uuid.UUID(new_item["root_component_id"]),
        "file_a": file_a,
        "file_b": file_b,
    }


def _run_diff(tenancy_db: str, org_id: uuid.UUID, part_id: uuid.UUID) -> dict[str, Any]:
    return asyncio.run(
        run_generate_requote_diff(app_role_url(tenancy_db), org_id=org_id, part_id=part_id)
    )


def _fetch_requote_diff(owner_url: str, quote_id: uuid.UUID) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT requote_diff FROM quote WHERE id = :id"), {"id": str(quote_id)}
                )
                return cast("dict[str, Any] | None", row.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _count_ops(owner_url: str, component_id: uuid.UUID) -> int:
    async def _run() -> int:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT count(*) FROM operation WHERE component_id = :id"),
                    {"id": str(component_id)},
                )
                return int(row.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"{slug}-admin@example.test")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def test_task_caches_diff_with_synthesis(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
) -> None:
    org, admin = _org_with_admin(seeder, "org-rqd1")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org)
    _plant_finding(
        seeder,
        org,
        ids["file_a"],
        type_="diameter",
        category="dimensions",
        role="bore_3",
        normalized="12.5",
        tolerance={"kind": "bilateral", "upper": 0.010, "lower": -0.010},
    )
    _plant_finding(
        seeder,
        org,
        ids["file_b"],
        type_="diameter",
        category="dimensions",
        role="bore_3",
        normalized="12.5",
        tolerance={"kind": "bilateral", "upper": 0.005, "lower": -0.005},
    )
    _plant_finding(seeder, org, ids["file_b"], value="FAI REQUIRED", status="suggested")
    # A rejected finding never enters the diff.
    _plant_finding(seeder, org, ids["file_b"], value="Geisterwert", status="rejected")

    out = _run_diff(tenancy_db, org, ids["part_b"])
    assert out["ok"] is True

    cached = _fetch_requote_diff(tenancy_db, ids["new_quote"])
    assert cached is not None
    entry = cached["entries"][str(ids["part_b"])]
    assert entry["match_type"] == "exact_geometric"
    assert entry["matched"]["quote_number"] == "Q-2026-1000"
    assert entry["matched"]["part_id"] == str(ids["part_a"])
    assert entry["matched"]["component_id"] == str(ids["component_a"])
    assert entry["target_component_id"] == str(ids["component_b"])
    assert entry["diff"]["geometry_delta"]["volume"]["delta_pct"] == pytest.approx(-2.3)
    added_values = [f["value"] for f in entry["diff"]["finding_diff"]["added"]]
    assert added_values == ["FAI REQUIRED"]
    assert "Geisterwert" not in json.dumps(entry)
    assert len(entry["diff"]["finding_diff"]["changed"]) == 1
    assert entry["ai"] == {"enabled": True, "reason": "ok"}
    assert entry["synthesis"] == "Geringfügige Änderung — engere Bohrungstoleranz."
    assert entry["choice"] is None
    assert fake_synthesizer.calls == 1
    # The synthesizer receives the structured diff JSON — never file bytes.
    assert fake_synthesizer.last_diff is not None
    assert set(fake_synthesizer.last_diff) >= {"geometry_delta", "finding_diff"}


def test_task_skips_without_baseline(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
) -> None:
    org, admin = _org_with_admin(seeder, "org-rqd2")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote = seeder.quote(org, "Q-2026-3000")
        item = _quote_item(app_client, quote)
    out = _run_diff(tenancy_db, org, uuid.UUID(item["part_id"]))
    assert out.get("skipped") == "no_baseline"
    assert _fetch_requote_diff(tenancy_db, quote) is None
    assert fake_synthesizer.calls == 0


def test_ai_master_off_still_caches_deterministic_diff(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
) -> None:
    org, admin = _org_with_admin(seeder, "org-rqd3")
    seeder.sql(
        "INSERT INTO org_ai_settings (org_id, master_enabled) VALUES (:org, FALSE)",
        {"org": str(org)},
    )
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org)
    out = _run_diff(tenancy_db, org, ids["part_b"])
    assert out["ok"] is True
    cached = _fetch_requote_diff(tenancy_db, ids["new_quote"])
    assert cached is not None
    entry = cached["entries"][str(ids["part_b"])]
    assert entry["ai"] == {"enabled": False, "reason": "master_disabled"}
    assert entry["synthesis"] is None
    assert entry["diff"]["geometry_delta"]["available"] is True
    assert fake_synthesizer.calls == 0


def test_export_controlled_skips_synthesis(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
) -> None:
    org, admin = _org_with_admin(seeder, "org-rqd4")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org)
    seeder.sql(
        "INSERT INTO request_for_quote (id, org_id, quote_id, subject, export_controlled) "
        "VALUES (:id, :org, :q, 'RFQ', TRUE)",
        {"id": str(uuid.uuid4()), "org": str(org), "q": str(ids["new_quote"])},
    )
    out = _run_diff(tenancy_db, org, ids["part_b"])
    assert out["ok"] is True
    cached = _fetch_requote_diff(tenancy_db, ids["new_quote"])
    assert cached is not None
    entry = cached["entries"][str(ids["part_b"])]
    assert entry["ai"] == {"enabled": False, "reason": "export_controlled"}
    assert fake_synthesizer.calls == 0


def test_provider_error_degrades_to_deterministic_diff(
    tenancy_db: str, app_client: TestClient, seeder: Seeder
) -> None:
    class _Boom:
        async def synthesize(self, diff: dict[str, Any]) -> dict[str, Any]:
            from app.lens_provider import LensProviderError

            raise LensProviderError("provider_unavailable")

    requote_diff.register(_Boom())
    try:
        org, admin = _org_with_admin(seeder, "org-rqd5")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            ids = _seed_requote_pair(seeder, app_client, org)
        out = _run_diff(tenancy_db, org, ids["part_b"])
        assert out["ok"] is True
        cached = _fetch_requote_diff(tenancy_db, ids["new_quote"])
        assert cached is not None
        entry = cached["entries"][str(ids["part_b"])]
        assert entry["ai"]["enabled"] is False
        assert entry["ai"]["reason"] == "error:provider_unavailable"
        assert entry["synthesis"] is None
        assert entry["diff"]["geometry_delta"]["available"] is True
    finally:
        requote_diff.register(None)


def test_diff_never_copies_operations(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
) -> None:
    """The human gate: computing + caching the diff is read-only on the router —
    nothing lands on the new component without the explicit import click."""
    org, admin = _org_with_admin(seeder, "org-rqd6")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org)
        seeder.operation(org, ids["component_a"], name="Fräsen")
        assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True
    assert _count_ops(tenancy_db, ids["component_b"]) == 0


def test_endpoints_pending_entries_and_choice(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
) -> None:
    org, admin = _org_with_admin(seeder, "org-rqd7")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org)
        # Pending shell before the task ran.
        resp = app_client.get(f"/api/quotes/{ids['new_quote']}/requote-diff")
        assert resp.status_code == 200
        assert resp.json() == {"entries": []}

        assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True
        resp = app_client.get(f"/api/quotes/{ids['new_quote']}/requote-diff")
        [entry] = resp.json()["entries"]
        assert entry["part_id"] == str(ids["part_b"])
        assert entry["choice"] is None

        # Unknown part → 404; unknown choice → 422.
        bad = app_client.post(
            f"/api/quotes/{ids['new_quote']}/requote-diff/choice",
            json={"part_id": str(uuid.uuid4()), "choice": "start_fresh"},
        )
        assert bad.status_code == 404
        bad = app_client.post(
            f"/api/quotes/{ids['new_quote']}/requote-diff/choice",
            json={"part_id": str(ids["part_b"]), "choice": "yolo"},
        )
        assert bad.status_code == 422

        ok = app_client.post(
            f"/api/quotes/{ids['new_quote']}/requote-diff/choice",
            json={"part_id": str(ids["part_b"]), "choice": "start_fresh"},
        )
        assert ok.status_code == 200
        [entry] = ok.json()["entries"]
        assert entry["choice"]["choice"] == "start_fresh"
        assert entry["choice"]["at"]  # audit timestamp


def test_refresh_endpoint_enqueues(
    app_client: TestClient, seeder: Seeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, admin = _org_with_admin(seeder, "org-rqd8")
    queued: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(
        requote_diff,
        "enqueue_requote_diff",
        lambda org_id, part_id: queued.append((org_id, part_id)),
    )
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote = seeder.quote(org, "Q-2026-4000")
        item = _quote_item(app_client, quote)
        resp = app_client.post(f"/api/quotes/{quote}/requote-diff/refresh")
        assert resp.status_code == 202
        assert resp.json() == {"queued": 1}
    assert queued == [(org, uuid.UUID(item["part_id"]))]


def test_not_draft_quote_never_overwritten(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
) -> None:
    org, admin = _org_with_admin(seeder, "org-rqd9")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org)
    seeder.sql("UPDATE quote SET status = 'sent' WHERE id = :id", {"id": str(ids["new_quote"])})
    out = _run_diff(tenancy_db, org, ids["part_b"])
    assert out.get("skipped") == "not_draft"
    assert _fetch_requote_diff(tenancy_db, ids["new_quote"]) is None
