"""M3.13 — the scan task and the quarantine gate, end to end.

The block's acceptance criteria (build-plan/M3-intelligence.md → M3.13):
  * the EICAR fixture uploads, is flagged ``infected``, and its download/forward
    return 409/403;
  * a clean fixture passes to ``clean`` and downloads;
  * an ingested email attachment is scanned via the same task;
  * a clamd outage yields ``error`` + retry, never a silent ``clean``;
  * the task is idempotent (a double-enqueue converges).

clamd itself is never needed: the scan task depends on the ``VirusScanner``
protocol, so a fake verdict source is substituted at the seam. The wire protocol
is covered separately in ``test_av_m313.py`` against a fake daemon.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from celery.exceptions import Retry
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.av import ScannerUnavailableError, ScanStatus, Verdict, eicar_bytes
from app.av_scan import scan_part_file_task
from app.config import Settings
from app.main import create_app
from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings, eager_celery, mailgun_fields

ADMIN = [MembershipRole.admin]
PDF_BYTES = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
EICAR_PDF = b"%PDF-1.7\n" + eicar_bytes()  # passes the PDF sniff, carries the signature


class FakeScanner:
    """A verdict source with no daemon behind it.

    ``verdicts`` is keyed by the payload's leading bytes so one scanner can serve
    a clean and an infected file in the same test; ``calls`` proves idempotency
    (a terminal row must not be re-scanned)."""

    def __init__(self, *, infected_marker: bytes = b"", unavailable: bool = False) -> None:
        self.infected_marker = infected_marker
        self.unavailable = unavailable
        self.calls = 0

    async def scan_chunks(self, chunks: AsyncIterator[bytes]) -> Verdict:
        self.calls += 1
        payload = b"".join([chunk async for chunk in chunks])
        if self.unavailable:
            raise ScannerUnavailableError("clamd unreachable: ConnectionRefusedError")
        if self.infected_marker and self.infected_marker in payload:
            return Verdict(ScanStatus.infected, "Eicar-Test-Signature")
        return Verdict(ScanStatus.clean)


@pytest.fixture
def scanner(monkeypatch: pytest.MonkeyPatch) -> FakeScanner:
    """Install a fake scanner behind the task's ``make_scanner`` seam."""
    fake = FakeScanner(infected_marker=eicar_bytes())
    monkeypatch.setattr("app.av_scan.make_scanner", lambda _settings: fake)
    return fake


def _settings(tenancy_db: str) -> Settings:
    """Test settings with scanning switched ON (the gate is inert without it)."""
    return build_settings(
        database_url=tenancy_db,
        app_database_url=app_role_url(tenancy_db),
        av_scanner="clamav",
        clamav_host="clamav-fake",
    )


@pytest.fixture
def av_client(tenancy_db: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tenancy_db))) as test_client:
        yield test_client


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _upload(client: TestClient, name: str, body: bytes) -> tuple[str, str]:
    """Create a part, upload one file, return (part_id, file_id)."""
    part_id = str(client.post("/api/parts").json()["id"])
    resp = client.post(
        f"/api/parts/{part_id}/files",
        files=[("files", (name, body, "application/pdf"))],
    )
    assert resp.status_code == 201, resp.text
    return part_id, str(resp.json()[0]["id"])


def _status(client: TestClient, part_id: str, file_id: str) -> str:
    listed = client.get(f"/api/parts/{part_id}/files").json()
    return str(next(f["scan_status"] for f in listed if f["id"] == file_id))


# --------------------------------------------------------------------------- #
# The headline: EICAR is quarantined, a clean file is not
# --------------------------------------------------------------------------- #
def test_eicar_upload_is_quarantined_and_download_is_blocked(
    av_client: TestClient, seeder: Seeder, scanner: FakeScanner
) -> None:
    org, admin = _org_with_admin(seeder, "org-av")
    with authed(av_client, user_id=admin, org_id=org, roles=ADMIN), eager_celery():
        part_id, file_id = _upload(av_client, "malware.pdf", EICAR_PDF)

        assert _status(av_client, part_id, file_id) == "infected"
        listed = av_client.get(f"/api/parts/{part_id}/files").json()
        # The signature is surfaced so staff can explain the quarantine…
        assert listed[0]["scan_signature"] == "Eicar-Test-Signature"
        # …while the bytes stay in.
        blocked = av_client.get(f"/api/parts/{part_id}/files/{file_id}/download")
        assert blocked.status_code == 403
        assert blocked.json()["code"] == "file_quarantined"


def test_clean_upload_passes_and_downloads(
    av_client: TestClient, seeder: Seeder, scanner: FakeScanner
) -> None:
    org, admin = _org_with_admin(seeder, "org-av")
    with authed(av_client, user_id=admin, org_id=org, roles=ADMIN), eager_celery():
        part_id, file_id = _upload(av_client, "drawing.pdf", PDF_BYTES)

        assert _status(av_client, part_id, file_id) == "clean"
        dl = av_client.get(f"/api/parts/{part_id}/files/{file_id}/download")
        assert dl.status_code == 200
        assert dl.content == PDF_BYTES  # still byte-identical (M1.2 holds)


def test_unscanned_file_is_visible_but_not_downloadable(
    av_client: TestClient, seeder: Seeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "pending = allow internal view-metadata, block download" (the charter).

    Celery is *not* eager here, so nothing scans the row — exactly the window
    between store and verdict."""
    org, admin = _org_with_admin(seeder, "org-av")
    monkeypatch.setattr("app.av_scan.scan_part_file_task.delay", lambda *_a: None)
    with authed(av_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id, file_id = _upload(av_client, "drawing.pdf", PDF_BYTES)

        assert _status(av_client, part_id, file_id) == "pending"  # metadata: fine
        blocked = av_client.get(f"/api/parts/{part_id}/files/{file_id}/download")
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "file_scan_pending"


def test_pending_downloads_when_no_scanner_is_configured(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The default deployment has no clamd; gating on ``pending`` there would block
    every download forever, so the gate stands down (``app_client`` = AV off)."""
    org, admin = _org_with_admin(seeder, "org-av")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id, file_id = _upload(app_client, "drawing.pdf", PDF_BYTES)
        assert _status(app_client, part_id, file_id) == "pending"
        assert app_client.get(f"/api/parts/{part_id}/files/{file_id}/download").status_code == 200


# --------------------------------------------------------------------------- #
# Outage + idempotency
# --------------------------------------------------------------------------- #
def test_clamd_outage_yields_error_and_retries_never_clean(
    av_client: TestClient, seeder: Seeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, admin = _org_with_admin(seeder, "org-av")
    down = FakeScanner(unavailable=True)
    monkeypatch.setattr("app.av_scan.make_scanner", lambda _settings: down)
    monkeypatch.setattr("app.av_scan.scan_part_file_task.delay", lambda *_a: None)
    with authed(av_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id, file_id = _upload(av_client, "drawing.pdf", PDF_BYTES)

        # The task re-raises, so ``BaseTask``'s ladder turns the outage into a
        # retry (``Retry`` is what that looks like from the caller's side) —
        # never a returned "clean".
        with eager_celery(), pytest.raises((ScannerUnavailableError, Retry)):
            scan_part_file_task.apply(args=[str(org), file_id], throw=True)

        # The verdict is recorded as ``error`` — never silently ``clean`` — and
        # the file stays undownloadable.
        assert _status(av_client, part_id, file_id) == "error"
        blocked = av_client.get(f"/api/parts/{part_id}/files/{file_id}/download")
        assert blocked.status_code == 409

        # A later run against a healthy daemon converges: ``error`` is retryable.
        healthy = FakeScanner()
        monkeypatch.setattr("app.av_scan.make_scanner", lambda _settings: healthy)
        with eager_celery():
            scan_part_file_task.apply(args=[str(org), file_id], throw=True)
        assert _status(av_client, part_id, file_id) == "clean"


def test_double_enqueue_converges_and_does_not_rescan(
    av_client: TestClient, seeder: Seeder, scanner: FakeScanner
) -> None:
    """Idempotency (CLAUDE.md §5): a redelivered task finds a terminal verdict and
    stops — one scan, one answer, no matter how often it runs."""
    org, admin = _org_with_admin(seeder, "org-av")
    with authed(av_client, user_id=admin, org_id=org, roles=ADMIN), eager_celery():
        part_id, file_id = _upload(av_client, "drawing.pdf", PDF_BYTES)
        assert scanner.calls == 1

        for _ in range(2):
            result = scan_part_file_task.apply(args=[str(org), file_id], throw=True).get()
            assert result["skipped"] is True
        assert scanner.calls == 1
        assert _status(av_client, part_id, file_id) == "clean"


def test_scan_of_a_deleted_file_is_a_no_op(
    av_client: TestClient, seeder: Seeder, scanner: FakeScanner
) -> None:
    """A file deleted between enqueue and run must not resurrect or crash the task."""
    org, admin = _org_with_admin(seeder, "org-av")
    with authed(av_client, user_id=admin, org_id=org, roles=ADMIN), eager_celery():
        result = scan_part_file_task.apply(args=[str(org), str(uuid.uuid4())], throw=True).get()
        assert result["status"] == "gone"


def test_task_is_a_no_op_when_scanning_is_disabled(app_client: TestClient, seeder: Seeder) -> None:
    org, _admin = _org_with_admin(seeder, "org-av")
    with eager_celery():
        result = scan_part_file_task.apply(args=[str(org), str(uuid.uuid4())], throw=True).get()
    assert result["reason"] == "scanning_disabled"


def test_infected_file_stays_blocked_even_with_scanning_switched_off(
    av_client: TestClient, tenancy_db: str, seeder: Seeder, scanner: FakeScanner
) -> None:
    """A known-malware verdict is terminal: turning clamd off must not release it."""
    org, admin = _org_with_admin(seeder, "org-av")
    with authed(av_client, user_id=admin, org_id=org, roles=ADMIN), eager_celery():
        part_id, file_id = _upload(av_client, "malware.pdf", EICAR_PDF)
        assert _status(av_client, part_id, file_id) == "infected"

    off = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    with (
        TestClient(create_app(off)) as scanner_less,
        authed(scanner_less, user_id=admin, org_id=org, roles=ADMIN),
    ):
        resp = scanner_less.get(f"/api/parts/{part_id}/files/{file_id}/download")
    assert resp.status_code == 403
    assert resp.json()["code"] == "file_quarantined"


# --------------------------------------------------------------------------- #
# Derived files inherit the verdict rather than sitting unscanned
# --------------------------------------------------------------------------- #
def test_redacted_copy_inherits_the_source_verdict(
    av_client: TestClient, seeder: Seeder, scanner: FakeScanner
) -> None:
    org, admin = _org_with_admin(seeder, "org-av")
    with authed(av_client, user_id=admin, org_id=org, roles=ADMIN), eager_celery():
        part_id, file_id = _upload(av_client, "drawing.pdf", PDF_BYTES)
        copy = av_client.post(
            f"/api/parts/{part_id}/files/{file_id}/redacted-copy",
            files=[("file", ("redacted.pdf", PDF_BYTES, "application/pdf"))],
        )
        assert copy.status_code == 201, copy.text
        # Rendered from a file already judged clean → downloadable immediately.
        copy_id = str(copy.json()["id"])
        assert _status(av_client, part_id, copy_id) == "clean"
        assert av_client.get(f"/api/parts/{part_id}/files/{copy_id}/download").status_code == 200


# --------------------------------------------------------------------------- #
# The ingested (untrusted) path — M3.3's attachments go through the same task
# --------------------------------------------------------------------------- #
def test_email_ingested_attachment_is_scanned_by_the_same_task(
    tenancy_db: str, seeder: Seeder
) -> None:
    """The condition behind the decision: the RFQ inbox is the untrusted door.

    An attachment that arrives by email is stored through the very same
    ``_store_files_on_part`` seam, so it gets the same verdict — proven here by
    driving a real Mailgun webhook and reading the resulting rows."""
    from tests.test_email_ingest_m33 import (
        RECIPIENT,
        SAMPLE_EML,
        SENDER,
        SIGNING_KEY,
        _seed_org_with_member,
    )

    settings = _settings(tenancy_db)
    settings.mailgun_webhook_signing_key = SIGNING_KEY
    scanned = FakeScanner()
    with TestClient(create_app(settings)) as client:
        org, _user = _seed_org_with_member(seeder)
        with (
            eager_celery(),
            pytest.MonkeyPatch.context() as mp,
        ):
            mp.setattr("app.av_scan.make_scanner", lambda _settings: scanned)
            mp.setattr("app.email_ingest._enqueue_lens_extract", lambda *_a: None)
            mp.setattr("app.email_ingest._enqueue_body_parse", lambda *_a: None)
            # The ingest task runs in a worker, where the AV config comes from the
            # process environment rather than an injected app.state — stand that
            # environment up for the duration of the call.
            mp.setattr("app.email_ingest.get_settings", lambda: settings)
            resp = client.post(
                "/webhooks/mailgun",
                data={
                    **mailgun_fields(SIGNING_KEY),
                    "recipient": RECIPIENT,
                    "sender": SENDER,
                    "body-mime": SAMPLE_EML.read_bytes().decode("utf-8"),
                },
            )
        assert resp.status_code == 200, resp.text

    statuses = _fetch(
        tenancy_db,
        "SELECT scan_status FROM part_file WHERE org_id = :org AND rfq_id IS NOT NULL",
        {"org": str(org)},
    )
    assert statuses, "the fixture RFQ carries attachments"
    assert {row[0] for row in statuses} == {"clean"}
    assert scanned.calls == len(statuses)


def _fetch(owner_url: str, sql: str, params: dict[str, object]) -> list[Any]:
    async def _run() -> list[Any]:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                return list((await conn.execute(text(sql), params)).all())
        finally:
            await engine.dispose()

    return asyncio.run(_run())
