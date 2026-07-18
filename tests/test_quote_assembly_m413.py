"""M4.13 — AI: Agentic Quote Assembly (spec ``#ai-quote-assembly``).

Two tracks (the M4.12 pattern):

* Pure unit tests — the deterministic server-side Accept-All gate
  (``accept_all_blockers``): significant geometry delta, material drawing
  changes, the conservative currency guard, stale cached entries.
* DB integration — the M4 exit criterion: the repeat-part fixture triggers
  the assembly banner and **Accept All imports the router + pricing in one
  atomic transaction with source tags** (``source = imported`` +
  ``source_quote_id``), backed by the 60-second undo (reverts to a blank
  line item); the material-change fixture gets Accept All suppressed
  **server-side** (only Review offered); the M4.12 import-router path stamps
  the same provenance.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import quote_assembly, requote_diff
from app.models import MembershipRole
from app.quote_assembly import UNDO_TTL_SECONDS, accept_all_blockers, undo_key
from tests.conftest import Seeder, authed
from tests.test_requote_diff_m412 import (
    _FakeSynthesizer,
    _org_with_admin,
    _plant_finding,
    _run_diff,
    _seed_requote_pair,
)

ADMIN = [MembershipRole.admin]


# --------------------------------------------------------------------------- #
# Accept-All gate — pure unit tests
# --------------------------------------------------------------------------- #


def _entry(
    *,
    significant: bool = False,
    material_changes: list[dict[str, Any]] | None = None,
    source_currency: str | None = "EUR",
) -> dict[str, Any]:
    matched: dict[str, Any] = {"quote_id": str(uuid.uuid4()), "quote_number": "Q-1"}
    if source_currency is not None:
        matched["currency"] = source_currency
    return {
        "matched": matched,
        "diff": {
            "geometry_delta": {"available": True, "significant": significant},
            "finding_diff": {
                "added": [],
                "removed": [],
                "changed": [],
                "material_changes": material_changes or [],
            },
        },
    }


def test_clean_diff_has_no_blockers() -> None:
    assert accept_all_blockers(_entry(), target_currency="EUR") == []


def test_significant_geometry_delta_blocks() -> None:
    blockers = accept_all_blockers(_entry(significant=True), target_currency="EUR")
    assert blockers == ["geometry_significant"]


def test_material_changes_block() -> None:
    blockers = accept_all_blockers(
        _entry(material_changes=[{"reason": "requirements_added"}]), target_currency="EUR"
    )
    assert blockers == ["material_changes"]


def test_both_signals_block_together() -> None:
    blockers = accept_all_blockers(
        _entry(significant=True, material_changes=[{"reason": "material_changed"}]),
        target_currency="EUR",
    )
    assert blockers == ["geometry_significant", "material_changes"]


def test_currency_mismatch_blocks() -> None:
    """Conservative guard (ASSUMED, DECISIONS 2026-07-18): CHF rates copied
    into a EUR quote would be silently-wrong money."""
    blockers = accept_all_blockers(_entry(source_currency="CHF"), target_currency="EUR")
    assert blockers == ["currency_mismatch"]


def test_stale_entry_without_currency_blocks() -> None:
    """A pre-M4.13 cached entry lacks ``matched.currency`` — never eligible
    until the diff is refreshed (fail-closed, not fail-open)."""
    blockers = accept_all_blockers(_entry(source_currency=None), target_currency="EUR")
    assert blockers == ["entry_stale"]


def test_undo_key_format() -> None:
    item_id = uuid.uuid4()
    assert undo_key(item_id) == f"undo:quote_assembly:{item_id}"


# --------------------------------------------------------------------------- #
# DB integration
# --------------------------------------------------------------------------- #


class _FakeUndoStore:
    """In-memory stand-in for the Redis TTL key (CI has no Redis broker)."""

    def __init__(self) -> None:
        self.data: dict[str, tuple[dict[str, Any], float]] = {}
        self.now = 0.0

    async def arm(self, key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
        self.data[key] = (value, self.now + ttl_seconds)
        return True

    async def take(self, key: str) -> dict[str, Any] | None:
        item = self.data.pop(key, None)
        if item is None:
            return None
        value, expires = item
        if self.now >= expires:
            return None
        return value


@pytest.fixture
def fake_synthesizer() -> Iterator[_FakeSynthesizer]:
    synth = _FakeSynthesizer()
    requote_diff.register(synth)
    yield synth
    requote_diff.register(None)


@pytest.fixture
def fake_undo_store() -> Iterator[_FakeUndoStore]:
    store = _FakeUndoStore()
    quote_assembly.register_undo_store(store)
    yield store
    quote_assembly.register_undo_store(None)


def _rows(
    owner_url: str, table: str, org_id: uuid.UUID, component_id: uuid.UUID
) -> list[dict[str, Any]]:
    async def _run() -> list[dict[str, Any]]:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(f"SELECT * FROM {table} WHERE component_id = :id AND org_id = :org"),
                    {"id": str(component_id), "org": str(org_id)},
                )
                return [dict(r._mapping) for r in result]
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _seed_source_router_and_pricing(seeder: Seeder, org: uuid.UUID, component_a: uuid.UUID) -> None:
    seeder.operation(org, component_a, "Sägen", position=0)
    seeder.operation(org, component_a, "CNC-Fräsen", position=1)
    seeder.sql(
        "INSERT INTO pricing_item (id, org_id, component_id, name, default_pct, position) "
        "VALUES (:id, :org, :c, 'Marge', 20.0, 0)",
        {"id": str(uuid.uuid4()), "org": str(org), "c": str(component_a)},
    )
    seeder.sql(
        "INSERT INTO add_on (id, org_id, component_id, name, default_price, position) "
        "VALUES (:id, :org, :c, 'Erstmusterprüfbericht', 150.0, 0)",
        {"id": str(uuid.uuid4()), "org": str(org), "c": str(component_a)},
    )


def _get_entries(client: TestClient, quote_id: uuid.UUID) -> list[dict[str, Any]]:
    res = client.get(f"/api/quotes/{quote_id}/requote-diff")
    assert res.status_code == 200
    return cast("list[dict[str, Any]]", res.json()["entries"])


def test_banner_state_and_accept_all_atomic_import(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
    fake_undo_store: _FakeUndoStore,
) -> None:
    """The M4 exit criterion: repeat-part fixture → banner offered + eligible;
    Accept All copies router + pricing atomically, every row stamped
    ``source = imported`` + ``source_quote_id``; the undo key is armed."""
    org, admin = _org_with_admin(seeder, "org-qa1")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
    _seed_source_router_and_pricing(seeder, org, ids["component_a"])

    out = _run_diff(tenancy_db, org, ids["part_b"])
    assert out["ok"] is True

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        entries = _get_entries(app_client, ids["new_quote"])
        assert len(entries) == 1
        state = entries[0]["assembly_state"]
        assert state["offered"] is True
        assert state["accept_all_eligible"] is True
        assert state["blockers"] == []
        assert state["quote_count"] >= 1

        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/import",
            json={"part_id": str(ids["part_b"]), "path": "accept_all"},
        )
        assert res.status_code == 200, res.text

    ops = _rows(tenancy_db, "operation", org, ids["component_b"])
    assert sorted(o["name"] for o in ops) == ["CNC-Fräsen", "Sägen"]
    assert all(o["source"] == "imported" for o in ops)
    assert all(str(o["source_quote_id"]) == str(ids["prior_quote"]) for o in ops)

    items = _rows(tenancy_db, "pricing_item", org, ids["component_b"])
    assert [i["name"] for i in items] == ["Marge"]
    assert items[0]["source"] == "imported"
    assert str(items[0]["source_quote_id"]) == str(ids["prior_quote"])
    addons = _rows(tenancy_db, "add_on", org, ids["component_b"])
    assert [a["name"] for a in addons] == ["Erstmusterprüfbericht"]
    assert addons[0]["source"] == "imported"
    assert str(addons[0]["source_quote_id"]) == str(ids["prior_quote"])

    # The source is never touched.
    src_ops = _rows(tenancy_db, "operation", org, ids["component_a"])
    assert all(o["source"] == "manual" for o in src_ops)

    # Undo armed for exactly this line item, and the record is in the entry.
    assert len(fake_undo_store.data) == 1
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        entries = _get_entries(app_client, ids["new_quote"])
    record = entries[0]["assembly"]
    assert record["path"] == "accept_all"
    assert str(record["source_quote_id"]) == str(ids["prior_quote"])


def test_undo_reverts_to_blank_line_item(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
    fake_undo_store: _FakeUndoStore,
) -> None:
    org, admin = _org_with_admin(seeder, "org-qa2")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
    _seed_source_router_and_pricing(seeder, org, ids["component_a"])
    assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True

    blank_pricing = len(_rows(tenancy_db, "pricing_item", org, ids["component_b"]))

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/import",
            json={"part_id": str(ids["part_b"]), "path": "accept_all"},
        )
        assert res.status_code == 200
        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/undo",
            json={"part_id": str(ids["part_b"])},
        )
        assert res.status_code == 200, res.text

    ops = _rows(tenancy_db, "operation", org, ids["component_b"])
    assert ops == []
    pricing = _rows(tenancy_db, "pricing_item", org, ids["component_b"])
    assert len(pricing) == blank_pricing
    assert all(p["source"] == "manual" for p in pricing)
    assert _rows(tenancy_db, "add_on", org, ids["component_b"]) == []

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        entries = _get_entries(app_client, ids["new_quote"])
        assert entries[0]["assembly"]["undone_at"] is not None
        # A second undo has nothing left to take: the key is single-use.
        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/undo",
            json={"part_id": str(ids["part_b"])},
        )
        assert res.status_code == 410


def test_undo_expires_after_ttl(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
    fake_undo_store: _FakeUndoStore,
) -> None:
    org, admin = _org_with_admin(seeder, "org-qa3")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
    seeder.operation(org, ids["component_a"], "Sägen")
    assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/import",
            json={"part_id": str(ids["part_b"]), "path": "accept_all"},
        )
        assert res.status_code == 200
        fake_undo_store.now += UNDO_TTL_SECONDS + 1
        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/undo",
            json={"part_id": str(ids["part_b"])},
        )
        assert res.status_code == 410
    # The import itself stands — undo expiring never rolls anything back.
    assert len(_rows(tenancy_db, "operation", org, ids["component_b"])) == 1


def test_accept_all_suppressed_on_material_change(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
    fake_undo_store: _FakeUndoStore,
) -> None:
    """Material-change fixture: Accept All is suppressed **server-side**; the
    Review path (individually chipped values) still imports."""
    org, admin = _org_with_admin(seeder, "org-qa4")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
    seeder.operation(org, ids["component_a"], "Sägen")
    # A new requirements callout on Rev B — deterministic material change.
    _plant_finding(seeder, org, ids["file_b"], value="FAI REQUIRED")
    assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        entries = _get_entries(app_client, ids["new_quote"])
        state = entries[0]["assembly_state"]
        assert state["offered"] is True
        assert state["accept_all_eligible"] is False
        assert "material_changes" in state["blockers"]

        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/import",
            json={"part_id": str(ids["part_b"]), "path": "accept_all"},
        )
        assert res.status_code == 409
        assert res.json()["code"] == "accept_all_suppressed"

        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/import",
            json={"part_id": str(ids["part_b"]), "path": "review"},
        )
        assert res.status_code == 200, res.text

    ops = _rows(tenancy_db, "operation", org, ids["component_b"])
    assert len(ops) == 1
    assert ops[0]["source"] == "imported"
    # Review path never arms an undo key — its safety net is per-value review.
    assert fake_undo_store.data == {}


def test_currency_mismatch_blocks_accept_all(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
    fake_undo_store: _FakeUndoStore,
) -> None:
    org, admin = _org_with_admin(seeder, "org-qa5")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
    seeder.operation(org, ids["component_a"], "Sägen")
    seeder.sql(
        "UPDATE quote SET currency = 'CHF' WHERE id = :id AND org_id = :org",
        {"id": str(ids["prior_quote"]), "org": str(org)},
    )
    assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        entries = _get_entries(app_client, ids["new_quote"])
        state = entries[0]["assembly_state"]
        assert state["accept_all_eligible"] is False
        assert state["blockers"] == ["currency_mismatch"]
        # BOTH paths are rejected (DECISIONS 2026-07-18, tightened in review):
        # CHF rates in a EUR quote are wrong money with or without review chips.
        for path in ("accept_all", "review"):
            res = app_client.post(
                f"/api/quotes/{ids['new_quote']}/assembly/import",
                json={"part_id": str(ids["part_b"]), "path": path},
            )
            assert res.status_code == 409
            assert res.json()["code"] == "currency_mismatch"
        # ... and so is the M4.12 import-router path (rates are currency-bearing).
        res = app_client.post(
            f"/api/components/{ids['component_b']}/import-router",
            json={"source_component_id": str(ids["component_a"])},
        )
        assert res.status_code == 409
        assert res.json()["code"] == "currency_mismatch"
    assert _rows(tenancy_db, "operation", org, ids["component_b"]) == []


def test_assembly_flag_off_hides_offer_and_blocks_import(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
    fake_undo_store: _FakeUndoStore,
) -> None:
    org, admin = _org_with_admin(seeder, "org-qa6")
    seeder.sql(
        "INSERT INTO org_ai_settings (org_id, quote_assembly_enabled) VALUES (:org, false)",
        {"org": str(org)},
    )
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
    seeder.operation(org, ids["component_a"], "Sägen")
    assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        entries = _get_entries(app_client, ids["new_quote"])
        state = entries[0]["assembly_state"]
        assert state["offered"] is False
        res = app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/import",
            json={"part_id": str(ids["part_b"]), "path": "accept_all"},
        )
        assert res.status_code == 409
        assert res.json()["code"] == "assembly_disabled"


def test_import_router_stamps_source_tags(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
) -> None:
    """The M4.12 'Import router from Rev A' path carries the same provenance:
    spec — "all imported values carry source = imported"."""
    org, admin = _org_with_admin(seeder, "org-qa7")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org)
    seeder.operation(org, ids["component_a"], "Sägen")

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = app_client.post(
            f"/api/components/{ids['component_b']}/import-router",
            json={"source_component_id": str(ids["component_a"])},
        )
        assert res.status_code == 200, res.text

    ops = _rows(tenancy_db, "operation", org, ids["component_b"])
    assert len(ops) == 1
    assert ops[0]["source"] == "imported"
    assert str(ops[0]["source_quote_id"]) == str(ids["prior_quote"])


def test_assembly_routes_are_org_scoped(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
    fake_undo_store: _FakeUndoStore,
) -> None:
    """RLS: another org's admin sees a 404, never the quote — and no rows move."""
    org, admin = _org_with_admin(seeder, "org-qa8")
    other_org, other_admin = _org_with_admin(seeder, "org-qa8-other")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
    seeder.operation(org, ids["component_a"], "Sägen")
    assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True

    with authed(app_client, user_id=other_admin, org_id=other_org, roles=ADMIN):
        for route in ("import", "undo"):
            body: dict[str, Any] = {"part_id": str(ids["part_b"])}
            if route == "import":
                body["path"] = "accept_all"
            res = app_client.post(f"/api/quotes/{ids['new_quote']}/assembly/{route}", json=body)
            assert res.status_code == 404, res.text
    assert _rows(tenancy_db, "operation", org, ids["component_b"]) == []


def test_accept_all_is_atomic_on_late_failure(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
    fake_undo_store: _FakeUndoStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One transaction (spec: "a single atomic endpoint"): a failure AFTER the
    router and pricing copies rolls everything back — no rows, no assembly
    record, no undo key."""
    org, admin = _org_with_admin(seeder, "org-qa9")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
    _seed_source_router_and_pricing(seeder, org, ids["component_a"])
    assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True

    blank_pricing = len(_rows(tenancy_db, "pricing_item", org, ids["component_b"]))

    async def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("recalc exploded")

    monkeypatch.setattr(quote_assembly, "recalculate_component", _boom)
    with (
        authed(app_client, user_id=admin, org_id=org, roles=ADMIN),
        pytest.raises(RuntimeError, match="recalc exploded"),
    ):
        app_client.post(
            f"/api/quotes/{ids['new_quote']}/assembly/import",
            json={"part_id": str(ids["part_b"]), "path": "accept_all"},
        )

    assert _rows(tenancy_db, "operation", org, ids["component_b"]) == []
    assert len(_rows(tenancy_db, "pricing_item", org, ids["component_b"])) == blank_pricing
    assert _rows(tenancy_db, "add_on", org, ids["component_b"]) == []
    assert fake_undo_store.data == {}
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        entries = _get_entries(app_client, ids["new_quote"])
        assert entries[0].get("assembly") is None


class _OutageStore:
    """Arms fine; the outage hits on take — the undo verdict is unknown."""

    async def arm(self, key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
        return True

    async def take(self, key: str) -> dict[str, Any] | None:
        raise quote_assembly.UndoStoreUnavailableError("redis down")


def test_undo_store_outage_returns_503_and_leaves_import(
    tenancy_db: str,
    app_client: TestClient,
    seeder: Seeder,
    fake_synthesizer: _FakeSynthesizer,
) -> None:
    """A Redis outage is not an expired window: 503 (retryable), the blanking
    rolls back, and the import stands untouched."""
    quote_assembly.register_undo_store(_OutageStore())
    try:
        org, admin = _org_with_admin(seeder, "org-qa10")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            ids = _seed_requote_pair(seeder, app_client, org, volume_b=100_000.0)
        seeder.operation(org, ids["component_a"], "Sägen")
        assert _run_diff(tenancy_db, org, ids["part_b"])["ok"] is True

        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            res = app_client.post(
                f"/api/quotes/{ids['new_quote']}/assembly/import",
                json={"part_id": str(ids["part_b"]), "path": "accept_all"},
            )
            assert res.status_code == 200, res.text
            res = app_client.post(
                f"/api/quotes/{ids['new_quote']}/assembly/undo",
                json={"part_id": str(ids["part_b"])},
            )
            assert res.status_code == 503
            assert res.json()["code"] == "undo_store_unavailable"
    finally:
        quote_assembly.register_undo_store(None)

    ops = _rows(tenancy_db, "operation", org, ids["component_b"])
    assert len(ops) == 1  # the 503 rolled the blanking back; the import stands
