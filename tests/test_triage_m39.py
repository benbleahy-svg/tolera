"""M3.9 — RFQ Triage Brief.

Two tracks:

* Pure deterministic-core unit tests (no DB) — the machine-checkable acceptance:
  correct signals, deterministic est-time, never-suppressible compliance.
* DB integration — seed a draft quote + ingested RFQ, run the task, assert
  ``quote.triage_brief`` carries the signals; gating (AI-disabled) and the
  export-controlled AI-skip.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import triage
from app.models import MembershipRole
from app.triage import (
    customer_line,
    detect_missing_files,
    estimate_time_to_quote,
    need_by,
    run_generate_triage_brief,
    scan_compliance,
    summarize_files,
)
from tests.conftest import Seeder, app_role_url, authed

ADMIN = [MembershipRole.admin]

NOW = datetime(2026, 7, 16, 9, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Deterministic core — pure unit tests (no DB)
# --------------------------------------------------------------------------- #


def test_summarize_files_classes() -> None:
    files = summarize_files(["a.step", "b.STP", "c.pdf", "d.PDF", "e.dxf", "notes.txt"])
    assert files["step"] == 2
    assert files["pdf"] == 2
    assert files["dxf"] == 1
    assert files["other"] == 1
    assert files["total"] == 6
    assert "2 STEP" in files["summary"] and "2 PDF" in files["summary"]


def test_missing_files_flags_part_without_a_file() -> None:
    part_numbers = ["PP-2244", "PP-5531", "BR-100"]
    filenames = ["BR-100.step", "BR-100.pdf"]
    missing = detect_missing_files(part_numbers, filenames)
    assert missing == ["PP-2244", "PP-5531"]


def test_missing_files_matches_normalized_key_in_filename() -> None:
    assert detect_missing_files(["PP 2244"], ["pp_2244_rev_b.step"]) == []


def test_scan_compliance_keyword_and_flag_never_suppressed() -> None:
    flags = scan_compliance("Bitte ITAR beachten — Ausfuhr geprüft.", export_controlled=True)
    codes = {f["source"] for f in flags}
    assert "part_flag" in codes  # export_controlled bool
    assert "keyword" in codes  # ITAR / Ausfuhr keyword hit
    assert all(f["code"] == "export_control" for f in flags)


def test_scan_compliance_clean_text_no_flags() -> None:
    assert scan_compliance("Standard-Frästeil aus Aluminium.", export_controlled=False) == []


def test_scan_compliance_no_substring_false_positive() -> None:
    # "military" must not fire on an unrelated word embedded elsewhere.
    assert scan_compliance("Familienbetrieb seit 1980.", export_controlled=False) == []


def test_est_time_is_deterministic_and_monotonic() -> None:
    procs = [{"family": "machining"}]
    a = estimate_time_to_quote(7, procs)
    b = estimate_time_to_quote(7, procs)
    assert a == b  # identical across runs (no AI)
    assert a["deterministic"] is True
    more = estimate_time_to_quote(14, procs)
    assert more["low_min"] >= a["low_min"]  # monotonic in part count


def test_est_time_zero_parts_dash() -> None:
    assert estimate_time_to_quote(0, [])["display"] == "—"


def test_need_by_urgency_bands() -> None:
    assert need_by(None, NOW)["urgency"] == "keine"
    assert need_by(NOW.date() - timedelta(days=1), NOW)["urgency"] == "überfällig"
    assert need_by(NOW.date() + timedelta(days=2), NOW)["urgency"] == "hoch"
    assert need_by(NOW.date() + timedelta(days=7), NOW)["urgency"] == "mittel"
    far = need_by(NOW.date() + timedelta(days=30), NOW)
    assert far["urgency"] == "niedrig"
    assert far["days_until"] == 30


def test_customer_line_new_vs_known() -> None:
    assert customer_line(False, "Arch Medial", 0).startswith("Neukunde")
    known = customer_line(True, "Arch Medial", 8)
    assert known.startswith("Bestandskunde") and "8" in known


# --------------------------------------------------------------------------- #
# DB integration — the task caches the brief; gating; export-control AI-skip
# --------------------------------------------------------------------------- #


class _FakeEnricher:
    def __init__(self) -> None:
        self.calls = 0

    async def enrich(self, core: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {
            "detected_processes": [{"name": "CNC-Fräsen", "likelihood": "likely"}],
            "customer_one_liner": "KI-Zusammenfassung",
        }


@pytest.fixture
def fake_enricher() -> Iterator[_FakeEnricher]:
    enricher = _FakeEnricher()
    triage.register(enricher)
    try:
        yield enricher
    finally:
        triage.register(None)


def _seed_quote_with_rfq(
    seeder: Any,
    *,
    filenames: list[str],
    line_items: list[dict[str, Any]],
    body: str = "Anfrage für Frästeile.",
    subject: str = "RFQ",
    export_controlled: bool = False,
    requested_days: int | None = 6,
    account_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = seeder.org("fechner-triage")
    quote_id = seeder.quote(org_id, "Q-TRIAGE-1", account_id=account_id)
    rfq_id = uuid.uuid4()
    req_date: date | None = None
    if requested_days is not None:
        # UTC, matching the task's clock — date.today() is the local date and
        # drifts a day ahead of UTC between 22:00Z and midnight Z under CEST.
        req_date = datetime.now(UTC).date() + timedelta(days=requested_days)
    seeder.sql(
        "INSERT INTO request_for_quote "
        "(id, org_id, quote_id, subject, description, requested_delivery_date, "
        " export_controlled, suggested_line_items) "
        "VALUES (:id, :org, :q, :subj, :body, :rd, :ec, "
        "        CAST(:sli AS jsonb))",
        {
            "id": str(rfq_id),
            "org": str(org_id),
            "q": str(quote_id),
            "subj": subject,
            "body": body,
            "rd": req_date,
            "ec": export_controlled,
            "sli": _json({"status": "completed", "items": line_items}),
        },
    )
    for name in filenames:
        part_id = seeder.part(org_id)
        file_id = seeder.part_file(org_id, part_id, filename=name)
        seeder.sql(
            "UPDATE part_file SET rfq_id = :rfq WHERE id = :id",
            {"rfq": str(rfq_id), "id": str(file_id)},
        )
    return org_id, quote_id


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj)


def _fetch_brief(owner_url: str, quote_id: uuid.UUID) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT triage_brief FROM quote WHERE id = :id"), {"id": str(quote_id)}
                )
                return cast("dict[str, Any] | None", row.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _run_brief(tenancy_db: str, org_id: uuid.UUID, quote_id: uuid.UUID) -> Any:
    return asyncio.run(
        run_generate_triage_brief(app_role_url(tenancy_db), org_id=org_id, quote_id=quote_id)
    )


def test_task_caches_brief_with_signals(
    tenancy_db: str, seeder: Any, fake_enricher: _FakeEnricher
) -> None:
    org_id, quote_id = _seed_quote_with_rfq(
        seeder,
        filenames=["BR-100.step", "BR-100.pdf", "PP-2244.pdf"],
        line_items=[
            {"part_number": "BR-100"},
            {"part_number": "PP-2244"},
            {"part_number": "PP-5531"},
        ],
        body="Frästeile aus Aluminium, Ausfuhr beachten.",
    )
    out = _run_brief(tenancy_db, org_id, quote_id)
    assert out["ok"] is True
    brief = _fetch_brief(tenancy_db, quote_id)
    assert brief is not None
    assert brief["version"] == 1
    assert brief["ai"]["enabled"] is True and brief["ai"]["reason"] == "ok"
    assert fake_enricher.calls == 1
    # Signals (spec #ai-triage table):
    assert brief["parts"]["files"]["step"] == 1
    assert brief["parts"]["files"]["pdf"] == 2
    assert "PP-5531" in brief["missing_files"]  # expected, no file received
    assert brief["est_time_to_quote"]["deterministic"] is True
    assert brief["need_by"]["days_until"] == 6
    assert any(f["source"] == "keyword" for f in brief["compliance_flags"])  # Ausfuhr


def test_missing_file_blocker_present(
    tenancy_db: str, seeder: Any, fake_enricher: _FakeEnricher
) -> None:
    org_id, quote_id = _seed_quote_with_rfq(
        seeder,
        filenames=["BR-100.step"],
        line_items=[{"part_number": "BR-100"}, {"part_number": "NO-FILE-9"}],
    )
    _run_brief(tenancy_db, org_id, quote_id)
    brief = _fetch_brief(tenancy_db, quote_id)
    assert brief is not None
    assert brief["missing_files"] == ["NO-FILE-9"]


def test_ai_disabled_still_caches_core_but_skips_enrichment(
    tenancy_db: str, seeder: Any, fake_enricher: _FakeEnricher
) -> None:
    org_id, quote_id = _seed_quote_with_rfq(
        seeder,
        filenames=["BR-100.step"],
        line_items=[{"part_number": "BR-100"}],
        body="Ausfuhr beachten.",
    )
    seeder.sql(
        "INSERT INTO org_ai_settings (org_id, master_enabled) VALUES (:org, false) "
        "ON CONFLICT (org_id) DO UPDATE SET master_enabled = false",
        {"org": str(org_id)},
    )
    _run_brief(tenancy_db, org_id, quote_id)
    brief = _fetch_brief(tenancy_db, quote_id)
    assert brief is not None
    assert brief["ai"]["enabled"] is False
    assert brief["ai"]["reason"] == "master_disabled"
    assert fake_enricher.calls == 0  # no AI call when master off
    # …but deterministic signals + compliance are still present (never suppressed).
    assert any(f["source"] == "keyword" for f in brief["compliance_flags"])
    assert brief["est_time_to_quote"]["deterministic"] is True


def test_rerun_target_gated_on_unopened_quote(
    tenancy_db: str, seeder: Any, fake_enricher: _FakeEnricher
) -> None:
    from app.db import make_engine, make_sessionmaker, org_scoped_session
    from app.triage import find_rerun_target

    org_id, quote_id = _seed_quote_with_rfq(
        seeder, filenames=["BR-100.step"], line_items=[{"part_number": "BR-100"}]
    )

    async def _target() -> uuid.UUID | None:
        engine = make_engine(app_role_url(tenancy_db))
        try:
            sm = make_sessionmaker(engine)
            async with org_scoped_session(sm, org_id) as session:
                # Scope the lookup to this quote's RFQ so a stray part_file
                # from another seeded test can never be picked up.
                part_id = (
                    await session.scalars(
                        text(
                            "SELECT pf.part_id FROM part_file pf "
                            "JOIN request_for_quote rfq ON rfq.id = pf.rfq_id "
                            "WHERE rfq.quote_id = :quote LIMIT 1"
                        ),
                        {"quote": str(quote_id)},
                    )
                ).one()
                return await find_rerun_target(session, cast("uuid.UUID", part_id))
        finally:
            await engine.dispose()

    # Unopened draft → re-run targets the quote.
    assert asyncio.run(_target()) == quote_id
    # Once the estimator has started work (started_at set), the brief freezes.
    seeder.sql("UPDATE quote SET started_at = now() WHERE id = :id", {"id": str(quote_id)})
    assert asyncio.run(_target()) is None


def test_export_controlled_skips_ai_but_flags_compliance(
    tenancy_db: str, seeder: Any, fake_enricher: _FakeEnricher
) -> None:
    org_id, quote_id = _seed_quote_with_rfq(
        seeder,
        filenames=["BR-100.step"],
        line_items=[{"part_number": "BR-100"}],
        export_controlled=True,
    )
    _run_brief(tenancy_db, org_id, quote_id)
    brief = _fetch_brief(tenancy_db, quote_id)
    assert brief is not None
    assert brief["ai"]["reason"] == "export_controlled"
    assert fake_enricher.calls == 0  # dual-use content never reaches the provider
    assert any(f["source"] == "part_flag" for f in brief["compliance_flags"])


def test_ai_flags_absent_row_defaults_all_enabled(tenancy_db: str, seeder: Seeder) -> None:
    """An org with no ``org_ai_settings`` row behaves AI-fully-enabled — a
    missing row must never be a silent disable (the accessor invariant)."""
    from app.ai_settings import get_ai_flags
    from app.db import make_engine, make_sessionmaker, org_scoped_session

    org_id = seeder.org("no-ai-row")
    seeder.sql("DELETE FROM org_ai_settings WHERE org_id = :o", {"o": str(org_id)})

    async def _flags() -> Any:
        engine = make_engine(app_role_url(tenancy_db))
        try:
            sm = make_sessionmaker(engine)
            async with org_scoped_session(sm, org_id) as session:
                return await get_ai_flags(session, org_id)
        finally:
            await engine.dispose()

    flags = asyncio.run(_flags())
    assert flags.master_enabled is True
    assert flags.triage_brief_enabled is True  # the exact flag the gate reads
    assert flags.triage_enabled is True  # master AND triage_brief


# --------------------------------------------------------------------------- #
# API route — GET /api/quotes/{id}/triage-brief (org-scoped)
# --------------------------------------------------------------------------- #


def test_triage_brief_endpoint_returns_cached_brief(app_client: TestClient, seeder: Seeder) -> None:
    org_id = seeder.org("triage-api")
    user = seeder.user("u@triage-api.example")
    seeder.membership(user, org_id, ADMIN)
    quote_id = seeder.quote(org_id, "Q-API-1")
    seeder.sql(
        "UPDATE quote SET triage_brief = CAST(:b AS jsonb) WHERE id = :id",
        {"b": _json({"version": 1, "ai": {"enabled": True, "reason": "ok"}}), "id": str(quote_id)},
    )
    with authed(app_client, user_id=user, org_id=org_id, roles=ADMIN):
        res = app_client.get(f"/api/quotes/{quote_id}/triage-brief")
    assert res.status_code == 200
    assert res.json()["brief"]["ai"]["reason"] == "ok"


def test_triage_brief_endpoint_pending_when_absent(app_client: TestClient, seeder: Seeder) -> None:
    org_id = seeder.org("triage-api2")
    user = seeder.user("u@triage-api2.example")
    seeder.membership(user, org_id, ADMIN)
    quote_id = seeder.quote(org_id, "Q-API-2")
    with authed(app_client, user_id=user, org_id=org_id, roles=ADMIN):
        res = app_client.get(f"/api/quotes/{quote_id}/triage-brief")
    assert res.status_code == 200
    body = res.json()
    assert body["brief"] is None and body["ai"]["reason"] == "pending"


def test_triage_brief_endpoint_is_org_scoped(app_client: TestClient, seeder: Seeder) -> None:
    org_a = seeder.org("triage-a")
    org_b = seeder.org("triage-b")
    user_b = seeder.user("u@triage-b.example")
    seeder.membership(user_b, org_b, ADMIN)
    quote_a = seeder.quote(org_a, "Q-A")  # belongs to org A
    with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
        res = app_client.get(f"/api/quotes/{quote_a}/triage-brief")
    assert res.status_code == 404  # RLS hides org A's quote from org B
