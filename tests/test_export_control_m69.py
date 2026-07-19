"""Export-control (EU dual-use) compliance audit — M6.9 pilot hardening.

Pins the posture the spec ``#authz`` decided: **flag + audit, no hard block** —
a flagged record stays readable by any internal user, but every touch is logged.
The one refusal is AI ("CUI/ITAR-flagged files are always skipped regardless of
the toggle"), and these tests assert the skip is *recorded*, not merely asserted.

The database-level guarantees (append-only grants, RLS) are exercised through the
restricted ``tolera_app`` role, because a compliance log that the app role can
rewrite is not a compliance log.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.export_control import (
    CSV_COLUMNS,
    ForbiddenAuditDetailError,
    _check_detail,
    to_csv,
)
from app.models import (
    ExportControlAccess,
    ExportControlAction,
    ExportControlSubject,
    ExportRegime,
    MembershipRole,
)
from tests.conftest import Seeder, app_role_url, authed

pytestmark = pytest.mark.usefixtures("tenancy_db")


# --------------------------------------------------------------------------- #
# Pure helpers (no DB)
# --------------------------------------------------------------------------- #
def test_detail_guard_rejects_content_and_pii_keys() -> None:
    """``detail`` is identifiers + reasons only (CLAUDE.md §5: never log print
    contents or customer PII)."""
    for forbidden in ({"text": "..."}, {"email": "a@b.de"}, {"prompt": "..."}):
        with pytest.raises(ForbiddenAuditDetailError):
            _check_detail(forbidden)


def test_detail_guard_allows_identifiers_and_reasons() -> None:
    ok = {"reason": "export_controlled", "route": "lens_extract", "file_id": "abc"}
    assert _check_detail(ok) == ok


def test_csv_header_is_the_stable_column_order() -> None:
    """Compliance officers diff these files — the header must not drift."""
    assert to_csv([]).splitlines()[0] == ",".join(CSV_COLUMNS)


def test_csv_renders_iso_utc_and_compact_detail() -> None:
    from datetime import UTC, datetime

    entry = ExportControlAccess(
        org_id=uuid.uuid4(),
        actor_user_id=None,
        subject_type=ExportControlSubject.part,
        subject_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        action=ExportControlAction.ai_skip,
        regime=ExportRegime.eu_dual_use,
        detail={"reason": "export_controlled"},
        ip_address=None,
        user_agent=None,
    )
    entry.occurred_at = datetime(2026, 7, 19, 12, 30, tzinfo=UTC)
    row = to_csv([entry]).splitlines()[1]
    # ISO-8601 UTC, not a de-DE display format: this is a machine artefact.
    assert row.startswith("2026-07-19T12:30:00+00:00,ai_skip,part,")
    assert '{""reason"":""export_controlled""}' in row
    # A NULL actor (worker/system action) renders empty, never "None".
    assert ",None," not in row


# --------------------------------------------------------------------------- #
# Database guarantees
# --------------------------------------------------------------------------- #
def _seed_entry(seeder: Seeder, org_id: uuid.UUID) -> uuid.UUID:
    entry_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO export_control_access "
        "(id, org_id, subject_type, subject_id, action, regime, detail) VALUES "
        "(:id, :org, 'part', :subject, 'view', 'eu_dual_use', '{}'::jsonb)",
        {"id": entry_id, "org": org_id, "subject": uuid.uuid4()},
    )
    return entry_id


def test_org_defaults_to_eu_dual_use_regime(seeder: Seeder) -> None:
    """DACH-DELTA §5 re-bases the regime on Reg (EU) 2021/821 for DE/AT/CH, and
    ``organization.country`` admits nothing else — so that is the default."""
    org_id = seeder.org("fechner")
    [(regime,)] = seeder.fetch(
        "SELECT export_regime FROM organization WHERE id = :id", {"id": org_id}
    )
    assert regime == "eu_dual_use"


async def _as_app_role(dsn: str, org_id: uuid.UUID, statement: str) -> list[Any]:
    """Run one statement as the restricted, RLS-bound role with the org GUC set —
    the same boundary production serves requests on."""
    engine = create_async_engine(app_role_url(dsn))
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(org_id)},
            )
            result = await conn.execute(text(statement))
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE export_control_access SET action = 'download'",
        "DELETE FROM export_control_access",
    ],
)
def test_compliance_log_is_append_only_for_the_app_role(
    tenancy_db: str, seeder: Seeder, statement: str
) -> None:
    """The restricted role may SELECT + INSERT and nothing else — the
    ``quote_status_event`` precedent (M1.4). A code slip, or a compromised app
    role, must not be able to rewrite or erase the compliance trail."""
    org_id = seeder.org("fechner")
    _seed_entry(seeder, org_id)

    with pytest.raises(Exception, match=r"(?i)permission denied"):
        asyncio.run(_as_app_role(tenancy_db, org_id, statement))


def test_compliance_log_is_org_isolated(tenancy_db: str, seeder: Seeder) -> None:
    """RLS: an org never sees another org's compliance entries."""
    fechner = seeder.org("fechner")
    other = seeder.org("other")
    _seed_entry(seeder, other)
    mine = _seed_entry(seeder, fechner)

    rows = asyncio.run(_as_app_role(tenancy_db, fechner, "SELECT id FROM export_control_access"))
    assert [row[0] for row in rows] == [mine]


# --------------------------------------------------------------------------- #
# Settings API — regime config + the spec's "CUI Audit: download CSV"
# --------------------------------------------------------------------------- #
def _org_with(
    seeder: Seeder, slug: str, roles: list[MembershipRole]
) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = seeder.org(slug)
    user_id = seeder.user(f"{slug}@example.de")
    seeder.membership(user_id, org_id, roles)
    return org_id, user_id


ADMIN = [MembershipRole.admin]
MANAGER = [MembershipRole.manager]


def test_compliance_surfaces_are_admin_only_not_manager(
    app_client: TestClient, seeder: Seeder
) -> None:
    """``compliance_manage`` must NOT flow to manager. The audit names every actor
    who touched a flagged record, and ``settings_edit``/``users_manage`` — the
    obvious gates to reuse — both reach managers (``app.authz._MANAGER``)."""
    org_id, manager = _org_with(seeder, "fechner", MANAGER)
    with authed(app_client, user_id=manager, org_id=org_id, roles=MANAGER):
        for path in ("", "/audit", "/audit.csv"):
            resp = app_client.get(f"/api/settings/export-control{path}")
            assert resp.status_code == 403, path


def test_admin_reads_regime_and_can_change_it(app_client: TestClient, seeder: Seeder) -> None:
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        assert app_client.get("/api/settings/export-control").json() == {
            "export_regime": "eu_dual_use"
        }
        resp = app_client.put("/api/settings/export-control", json={"export_regime": "none"})
        assert resp.status_code == 200
        assert resp.json()["export_regime"] == "none"


def test_changing_the_regime_never_rewrites_past_entries(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Each entry denormalises the regime in force when it was written, so a
    later Settings change cannot retroactively relabel the compliance log."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    _seed_entry(seeder, org_id)  # written under eu_dual_use
    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        app_client.put("/api/settings/export-control", json={"export_regime": "itar"})
        [entry] = app_client.get("/api/settings/export-control/audit").json()["entries"]
        assert entry["regime"] == "eu_dual_use"


def test_audit_csv_downloads_with_stable_header(app_client: TestClient, seeder: Seeder) -> None:
    """Spec Settings → Company Settings → "CUI Audit: download CSV (compliance log)"."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    _seed_entry(seeder, org_id)
    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.get("/api/settings/export-control/audit.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    # Never a silent cap — a complete download says so explicitly.
    assert resp.headers["X-Audit-Truncated"] == "false"
    lines = resp.text.splitlines()
    assert lines[0] == ",".join(CSV_COLUMNS)
    assert len(lines) == 2


def test_audit_is_org_isolated_through_the_api(app_client: TestClient, seeder: Seeder) -> None:
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    other = seeder.org("other")
    _seed_entry(seeder, other)
    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        assert app_client.get("/api/settings/export-control/audit").json()["entries"] == []


# --------------------------------------------------------------------------- #
# AI refusals are recorded, not merely asserted
#
# Spec (AI architecture): "CUI/ITAR-flagged files are always skipped regardless
# of the toggle." M6.9's job is to make that provable — every refusing path
# writes an ``ai_skip`` entry naming the route.
# --------------------------------------------------------------------------- #
def _skips(seeder: Seeder, org_id: uuid.UUID) -> list[tuple[str, str]]:
    """(route, subject_type) of every recorded AI refusal for the org."""
    rows = seeder.fetch(
        "SELECT detail->>'route', subject_type::text FROM export_control_access "
        "WHERE org_id = :org AND action = 'ai_skip' ORDER BY occurred_at",
        {"org": org_id},
    )
    return [(row[0], row[1]) for row in rows]


def test_triage_records_its_ai_refusal(tenancy_db: str, seeder: Seeder) -> None:
    """The triage brief already refused a flagged RFQ (M3.9); M6.9 makes the
    refusal evidential."""
    from tests.test_triage_m39 import _run_brief, _seed_quote_with_rfq

    org_id, quote_id = _seed_quote_with_rfq(
        seeder,
        filenames=["BR-100.step"],
        line_items=[{"part_number": "BR-100"}],
        export_controlled=True,
    )
    _run_brief(tenancy_db, org_id, quote_id)
    assert ("triage.brief", "request_for_quote") in _skips(seeder, org_id)


def test_email_parts_parse_refuses_a_flagged_rfq_and_records_it(
    tenancy_db: str, seeder: Seeder
) -> None:
    """The gap M6.9 closed: this path ships the customer's email body + filenames
    to the provider and had no export-control gate at all."""
    from app.email_parts import run_email_parts_parse

    org_id = seeder.org("fechner")
    quote_id = seeder.quote(org_id, "Q-EC-1")
    rfq_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO request_for_quote (id, org_id, quote_id, description, export_controlled) "
        "VALUES (:id, :org, :q, :body, true)",
        {
            "id": rfq_id,
            "org": org_id,
            "q": quote_id,
            "body": "Bitte 10 Stk. Teil BR-100 anfragen.",
        },
    )

    result = asyncio.run(run_email_parts_parse(tenancy_db, org_id=org_id, rfq_id=rfq_id))

    assert result["skipped"] is True
    assert result["reason"] == "export_controlled"
    assert ("email_parts.parse", "request_for_quote") in _skips(seeder, org_id)
    # The refusal must not have written a suggestions payload — a flagged RFQ
    # simply has no AI-derived parts list.
    [(payload,)] = seeder.fetch(
        "SELECT suggested_line_items FROM request_for_quote WHERE id = :id", {"id": rfq_id}
    )
    assert payload is None


# --------------------------------------------------------------------------- #
# Internal access is logged — "flag + audit, no hard block" (spec #authz)
# --------------------------------------------------------------------------- #
def _flagged_part(seeder: Seeder, org_id: uuid.UUID) -> uuid.UUID:
    part_id = seeder.part(org_id)
    seeder.sql("UPDATE part SET export_controlled = true WHERE id = :id", {"id": part_id})
    return part_id


def _entries(seeder: Seeder, org_id: uuid.UUID, action: str) -> list[Any]:
    return seeder.fetch(
        "SELECT subject_type::text, subject_id, actor_user_id FROM export_control_access "
        "WHERE org_id = :org AND action = :action",
        {"org": org_id, "action": action},
    )


def test_viewing_a_flagged_part_is_allowed_and_logged(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The decided posture in one test: the read succeeds (no hard block) AND an
    entry naming the actor lands in the compliance log."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    part_id = _flagged_part(seeder, org_id)

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.get(f"/api/parts/{part_id}")

    assert resp.status_code == 200  # never blocked
    assert _entries(seeder, org_id, "view") == [("part", part_id, admin)]


def test_viewing_an_unflagged_part_writes_nothing(app_client: TestClient, seeder: Seeder) -> None:
    """The log is for flagged records only — otherwise it is a traffic log, and
    the compliance signal drowns."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    part_id = seeder.part(org_id)
    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        assert app_client.get(f"/api/parts/{part_id}").status_code == 200
    assert _entries(seeder, org_id, "view") == []


def test_downloading_a_flagged_parts_file_is_allowed_and_logged(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The flag lives on Part, not PartFile, so the download seam has to reach the
    parent to know it is controlled."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    part_id = _flagged_part(seeder, org_id)

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        # Upload through the API so a real blob backs the stream.
        upload = app_client.post(
            f"/api/parts/{part_id}/files",
            files=[("files", ("BR-100.step", b"ISO-10303-21;", "application/step"))],
        )
        assert upload.status_code in (200, 201), upload.text
        file_id = uuid.UUID(upload.json()[0]["id"])
        resp = app_client.get(f"/api/parts/{part_id}/files/{file_id}/download")

    assert resp.status_code == 200
    assert _entries(seeder, org_id, "download") == [("part_file", file_id, admin)]


# --------------------------------------------------------------------------- #
# Restricted-party screening — the OPTIONAL hook (DACH-DELTA §5)
# --------------------------------------------------------------------------- #
def test_null_provider_answers_not_screened_never_clear() -> None:
    """The distinction is the whole point: an org that has not configured
    screening has not been screened, and must not be recorded as passing."""
    from app.services.screening import NullScreeningProvider, ScreeningStatus

    result = asyncio.run(NullScreeningProvider().screen("Beispiel GmbH"))
    assert result.status is ScreeningStatus.not_screened
    # not_screened is not a review trigger by itself — it means "opted out".
    assert result.needs_review is False


def test_fixture_provider_surfaces_a_hit_for_a_human() -> None:
    from app.services.screening import FixtureScreeningProvider, ScreeningStatus

    provider = FixtureScreeningProvider({"Sanktioniert AG": "EU-2026-001"})
    hit = asyncio.run(provider.screen("Sanktioniert AG"))
    assert hit.status is ScreeningStatus.potential_match
    assert hit.needs_review is True  # a finding, never an automatic refusal
    assert hit.matches[0].reference == "EU-2026-001"

    clear = asyncio.run(provider.screen("Fechner Zerspanung GmbH"))
    assert clear.status is ScreeningStatus.clear
    assert clear.needs_review is False


def test_every_screening_outcome_is_recorded_without_naming_the_match(
    tenancy_db: str, seeder: Seeder
) -> None:
    """A log holding only the hits cannot answer "was this ever checked?". And the
    matched names are third-party personal data — the count and list go in, the
    names stay out."""
    from app.db import make_engine, make_sessionmaker, org_scoped_session
    from app.export_control import screen_and_record
    from app.services.screening import FixtureScreeningProvider, register

    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    vendor_rfq_id = uuid.uuid4()
    register(FixtureScreeningProvider({"Sanktioniert AG": "EU-2026-001"}))

    async def _run() -> None:
        engine = make_engine(tenancy_db)
        try:
            sm = make_sessionmaker(engine)
            async with org_scoped_session(sm, org_id) as session:
                await screen_and_record(
                    session,
                    org_id=org_id,
                    subject_type=ExportControlSubject.vendor_rfq,
                    subject_id=vendor_rfq_id,
                    party_name="Sanktioniert AG",
                    actor_user_id=admin,
                )
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        register(None)  # restore the null default for every later test

    [(detail,)] = seeder.fetch(
        "SELECT detail FROM export_control_access WHERE org_id = :org AND action = 'screening'",
        {"org": org_id},
    )
    assert detail["status"] == "potential_match"
    assert detail["match_count"] == 1
    assert detail["lists"] == ["eu-consolidated"]
    # The matched party's name is third-party PII — it must not be in the log.
    assert "Sanktioniert AG" not in str(detail)
