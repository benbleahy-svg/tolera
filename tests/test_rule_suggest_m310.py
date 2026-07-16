"""M3.10 — Rule Auto-Suggestion (AI Feature 2, human-gated).

Acceptance (build-plan M3.10):
* adding the same op to a 3rd qualifying part surfaces a non-blocking chip;
* clicking it opens the Create Rule dialog **pre-seeded** with the pattern;
* **no rule is created by AI** — the dialog requires an explicit CREATE RULE;
* the suggestion is suppressed when ``rule_suggest_enabled`` is off;
* the pattern query (not Claude) decides eligibility.

These drive the real manual-add path (``POST /components/{id}/operations`` sets
``added_manually=True``) so the detector is exercised end-to-end.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import rule_suggest
from app.models import MembershipRole
from tests.conftest import authed

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]


# --------------------------------------------------------------------------- #
# Helpers — drive the real API so added_manually is set by the manual-add path
# --------------------------------------------------------------------------- #
def _op_def_id(client: TestClient) -> str:
    return str(client.get("/api/operation-defs").json()[0]["id"])


def _process_id(client: TestClient) -> str:
    return str(client.get("/api/processes").json()[0]["id"])


def _materials_by_class(client: TestClient) -> dict[str, list[str]]:
    """Class name -> material ids, read off the picker tree."""
    out: dict[str, list[str]] = {}
    for cls in client.get("/api/materials/tree").json():
        ids = [str(m["id"]) for fam in cls["families"] for m in fam["materials"]]
        if ids:
            out[cls["name"]] = ids
    return out


def _new_component(client: TestClient) -> str:
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    return str(item["root_component_id"])


def _manual_add(
    client: TestClient, component_id: str, *, process_id: str, material_id: str, op_def_id: str
) -> None:
    assert (
        client.patch(f"/api/components/{component_id}/process", json={"process_id": process_id})
    ).status_code == 200
    assert (
        client.patch(f"/api/components/{component_id}/material", json={"material_id": material_id})
    ).status_code == 200
    res = client.post(
        f"/api/components/{component_id}/operations", json={"operation_def_id": op_def_id}
    )
    assert res.status_code in (200, 201), res.text


def _drawer(client: TestClient, component_id: str) -> dict[str, Any] | None:
    res = client.get(f"/api/components/{component_id}/rule-suggestion")
    assert res.status_code == 200, res.text
    suggestion: dict[str, Any] | None = res.json()["suggestion"]
    return suggestion


def _seed_second_class(seeder: Any, org_id: uuid.UUID) -> str:
    """Plant a material in a distinct class (so the catalog's default class is
    not the only one) — returns the new material id."""
    cid, fid, mid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    seeder.sql(
        "INSERT INTO material_class (id, org_id, name, position) "
        "VALUES (:cid, :org, 'Kunststoff-M310', 99)",
        {"cid": cid, "org": org_id},
    )
    seeder.sql(
        "INSERT INTO material_family (id, org_id, class_id, name) "
        "VALUES (:fid, :org, :cid, 'PA-M310')",
        {"fid": fid, "cid": cid, "org": org_id},
    )
    seeder.sql(
        "INSERT INTO material (id, org_id, family_id, display_name) "
        "VALUES (:mid, :org, :fid, 'PA6-M310')",
        {"mid": mid, "fid": fid, "org": org_id},
    )
    return str(mid)


def _setup(seeder: Any) -> tuple[uuid.UUID, uuid.UUID]:
    user = seeder.user("m310@example.com")
    org = seeder.org("m310", "M310 GmbH")
    seeder.membership(user, org, ADMIN)
    seeder.configure_catalog(org)
    return user, org


# --------------------------------------------------------------------------- #
# The threshold: 3 manual adds fire, 2 do not
# --------------------------------------------------------------------------- #
def test_third_manual_add_surfaces_a_suggestion(app_client: TestClient, seeder: Any) -> None:
    user, org = _setup(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc = _process_id(app_client)
        op = _op_def_id(app_client)
        mats = next(ids for ids in _materials_by_class(app_client).values() if len(ids) >= 1)
        material = mats[0]

        comps = [_new_component(app_client) for _ in range(3)]
        for c in comps[:2]:
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)
            assert _drawer(app_client, c) is None  # only 1st/2nd — below threshold

        # The third qualifying part crosses the threshold.
        _manual_add(app_client, comps[2], process_id=proc, material_id=material, op_def_id=op)
        suggestion = _drawer(app_client, comps[2])

        assert suggestion is not None
        assert suggestion["pattern"]["part_count"] == 3
        assert suggestion["pattern"]["operation_def_id"] == op
        # The drawer carries the persisted row id so the chip can consume it.
        assert suggestion["suggested_action_id"]
        # Pre-seed for the Create Rule dialog is present (spec: signal name,
        # operation, likely condition).
        draft = suggestion["rule_draft"]
        assert draft["operation_def_id"] == op
        assert draft["name"] and draft["keyword"]
        assert suggestion["sentence"]


def test_no_rule_is_created_by_the_ai(app_client: TestClient, seeder: Any) -> None:
    """The suggestion never authors a rule — the human clicks CREATE RULE."""
    user, org = _setup(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc, op = _process_id(app_client), _op_def_id(app_client)
        material = next(iter(_materials_by_class(app_client).values()))[0]
        for _ in range(3):
            c = _new_component(app_client)
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)
        before = len(app_client.get("/api/rules").json())  # the seeded starter library
        assert _drawer(app_client, c) is not None
        # The suggestion authors NO rule — the count is unchanged; only the human
        # clicking CREATE RULE (M3.8) ever adds one.
        assert len(app_client.get("/api/rules").json()) == before


# --------------------------------------------------------------------------- #
# Eligibility is the pattern query, not Claude
# --------------------------------------------------------------------------- #
def test_rule_added_operations_do_not_count(app_client: TestClient, seeder: Any) -> None:
    """Only ``added_manually`` ops feed the detector: 2 manual + 1 rule-added
    (added_manually=False) stays below threshold."""
    user, org = _setup(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc, op = _process_id(app_client), _op_def_id(app_client)
        material = next(iter(_materials_by_class(app_client).values()))[0]
        comps = [_new_component(app_client) for _ in range(3)]
        for c in comps[:2]:
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)
        # Third component gets the same op, same family/class, but marked as a
        # rule/import add (the ADD_OPERATION / part-library posture).
        _manual_add(app_client, comps[2], process_id=proc, material_id=material, op_def_id=op)
        seeder.sql(
            "UPDATE operation SET added_manually = false "
            "WHERE component_id = :cid AND operation_def_id = :op",
            {"cid": uuid.UUID(comps[2]), "op": uuid.UUID(op)},
        )
        assert _drawer(app_client, comps[2]) is None


def test_material_class_separates_patterns(app_client: TestClient, seeder: Any) -> None:
    """ "Same process family + material class": 2 parts in each of two classes is
    2-and-2, so neither class reaches the threshold."""
    user, org = _setup(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc, op = _process_id(app_client), _op_def_id(app_client)
        class_a = next(iter(_materials_by_class(app_client).values()))[0]
        class_b = _seed_second_class(seeder, org)
        for material in (class_a, class_a, class_b, class_b):
            c = _new_component(app_client)
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)
        assert _drawer(app_client, c) is None  # class_b has only 2


def test_ninety_day_window(app_client: TestClient, seeder: Any) -> None:
    """Manual adds older than 90 days are outside the window."""
    user, org = _setup(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc, op = _process_id(app_client), _op_def_id(app_client)
        material = next(iter(_materials_by_class(app_client).values()))[0]
        comps = [_new_component(app_client) for _ in range(3)]
        for c in comps:
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)
        assert _drawer(app_client, comps[-1]) is not None  # within window: fires
        # Age every manual add past the window.
        seeder.sql(
            "UPDATE operation SET created_at = now() - interval '100 days' "
            "WHERE org_id = :org AND added_manually = true",
            {"org": org},
        )
        assert _drawer(app_client, comps[-1]) is None


# --------------------------------------------------------------------------- #
# Gating + lifecycle
# --------------------------------------------------------------------------- #
def _set_ai_flag(seeder: Any, org: uuid.UUID, column: str, value: bool) -> None:
    """Upsert the org's AI settings (the ORM-seeded org has no row, so
    get_ai_flags would otherwise return the all-enabled default)."""
    seeder.sql(
        f"INSERT INTO org_ai_settings (org_id, {column}) VALUES (:org, :val) "
        f"ON CONFLICT (org_id) DO UPDATE SET {column} = :val",
        {"org": org, "val": value},
    )


def test_suppressed_when_flag_off(app_client: TestClient, seeder: Any) -> None:
    user, org = _setup(seeder)
    _set_ai_flag(seeder, org, "rule_suggest_enabled", False)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc, op = _process_id(app_client), _op_def_id(app_client)
        material = next(iter(_materials_by_class(app_client).values()))[0]
        for _ in range(3):
            c = _new_component(app_client)
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)
        assert _drawer(app_client, c) is None
        assert app_client.get("/api/suggested-actions").json() == []


def test_master_flag_off_suppresses(app_client: TestClient, seeder: Any) -> None:
    user, org = _setup(seeder)
    _set_ai_flag(seeder, org, "master_enabled", False)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc, op = _process_id(app_client), _op_def_id(app_client)
        material = next(iter(_materials_by_class(app_client).values()))[0]
        for _ in range(3):
            c = _new_component(app_client)
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)
        assert _drawer(app_client, c) is None


def test_dismiss_hides_and_does_not_resurface(app_client: TestClient, seeder: Any) -> None:
    user, org = _setup(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc, op = _process_id(app_client), _op_def_id(app_client)
        material = next(iter(_materials_by_class(app_client).values()))[0]
        for _ in range(3):
            c = _new_component(app_client)
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)
        _drawer(app_client, c)  # persist it
        strip = app_client.get("/api/suggested-actions").json()
        assert len(strip) == 1
        action_id = strip[0]["id"]

        res = app_client.post(f"/api/suggested-actions/{action_id}/dismiss")
        assert res.status_code == 200
        assert res.json()["status"] == "dismissed"
        assert app_client.get("/api/suggested-actions").json() == []

        # A later detection must NOT resurrect the dismissed row.
        assert _drawer(app_client, c) is None
        assert app_client.get("/api/suggested-actions").json() == []


# --------------------------------------------------------------------------- #
# The nightly scan + Claude-writes-the-sentence
# --------------------------------------------------------------------------- #
class _StubEnricher:
    async def suggest(self, facts: dict[str, Any]) -> dict[str, Any]:
        return {"sentence": f"KI: {facts['operation']} als Regel für {facts['material_class']}?"}


def test_nightly_scan_populates_strip_with_ai_sentence(
    app_client: TestClient, seeder: Any, eager_celery: None
) -> None:
    user, org = _setup(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        proc, op = _process_id(app_client), _op_def_id(app_client)
        material = next(iter(_materials_by_class(app_client).values()))[0]
        for _ in range(3):
            c = _new_component(app_client)
            _manual_add(app_client, c, process_id=proc, material_id=material, op_def_id=op)

        rule_suggest.register(_StubEnricher())
        try:
            from app.rule_suggest import scan_rule_suggestions_task

            scan_rule_suggestions_task.delay()
        finally:
            rule_suggest.register(None)

        strip = app_client.get("/api/suggested-actions").json()
        assert len(strip) == 1
        # Claude wrote the sentence; the pattern/pre-seed stay deterministic.
        assert strip[0]["payload"]["sentence"].startswith("KI:")
        assert strip[0]["payload"]["pattern"]["part_count"] == 3
