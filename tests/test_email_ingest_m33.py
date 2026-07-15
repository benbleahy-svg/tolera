"""M3.3 — Email ingest → auto-quote (Mailgun EU webhook).

Two layers, per the block's test plan:

* **Pure parsing/auth units** — recipient→slug, Mailgun signature verification,
  `.eml` MIME parsing incl. ZIP recursion with its safety caps. No DB.
* **Webhook integration** (real Postgres, eager Celery) — the Fechner `.eml`
  fixture → one draft Quote + matched/created Contact + files filed (`.eml` as
  ORIGINAL RFQ on the request_for_quote row, attachments as parts' files with
  RFQ provenance) + extraction queued + dashboard notification; idempotent on
  Message-Id; org-scoped (RLS).

The Lens enqueue is recorded via a monkeypatched seam (`_enqueue_lens_extract`)
— the acceptance is "extraction *queued*", and M3.1's own suite covers the task.
"""

from __future__ import annotations

import asyncio
import email
import hashlib
import hmac
import io
import time
import uuid
import zipfile
from collections.abc import Iterator
from email import policy
from email.message import EmailMessage
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.celery_app import celery_app
from app.email_ingest import (
    parse_rfq_email,
    slug_from_recipient,
    verify_mailgun_signature,
)
from app.main import create_app
from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "email"
SAMPLE_EML = FIXTURES / "rfq-sample.eml"
ZIP_EML = FIXTURES / "rfq-with-zip.eml"

SIGNING_KEY = "test-signing-key"
RECIPIENT = "fechner@rfq.tolera.eu"
SENDER = "einkauf@kunde-beispiel.de"


# --------------------------------------------------------------------------- #
# Recipient → org slug
# --------------------------------------------------------------------------- #
def test_slug_from_recipient() -> None:
    assert slug_from_recipient("fechner@rfq.tolera.eu") == "fechner"
    # Angle-bracket + case forms tolerated; slug comes back lowercased.
    assert slug_from_recipient("RFQ <Fechner@RFQ.tolera.eu>") == "fechner"


def test_slug_from_recipient_rejects_foreign_domain() -> None:
    assert slug_from_recipient("fechner@example.com") is None
    assert slug_from_recipient("not-an-address") is None
    assert slug_from_recipient("") is None


# --------------------------------------------------------------------------- #
# Mailgun webhook signature (HMAC-SHA256 over timestamp+token)
# --------------------------------------------------------------------------- #
def _sign(key: str, *, timestamp: str | None = None) -> dict[str, str]:
    ts = timestamp if timestamp is not None else str(int(time.time()))
    token = uuid.uuid4().hex
    sig = hmac.new(key.encode(), (ts + token).encode(), hashlib.sha256).hexdigest()
    return {"timestamp": ts, "token": token, "signature": sig}


def test_signature_roundtrip() -> None:
    fields = _sign(SIGNING_KEY)
    assert verify_mailgun_signature(SIGNING_KEY, **fields)


def test_signature_rejects_wrong_key() -> None:
    fields = _sign("some-other-key")
    assert not verify_mailgun_signature(SIGNING_KEY, **fields)


def test_signature_rejects_stale_timestamp() -> None:
    fields = _sign(SIGNING_KEY, timestamp=str(int(time.time()) - 3600))
    assert not verify_mailgun_signature(SIGNING_KEY, **fields)


def test_signature_rejects_garbage_timestamp() -> None:
    fields = _sign(SIGNING_KEY, timestamp="not-a-number")
    assert not verify_mailgun_signature(SIGNING_KEY, **fields)


# --------------------------------------------------------------------------- #
# .eml parsing (stdlib email) + ZIP recursion
# --------------------------------------------------------------------------- #
def test_parse_sample_eml() -> None:
    parsed = parse_rfq_email(SAMPLE_EML.read_bytes())
    assert parsed.message_id == "<rfq-fixture-0001@kunde-beispiel.de>"
    assert parsed.sender_email == SENDER
    assert parsed.sender_name == "Einkauf Kunde Beispiel GmbH"
    assert parsed.subject.startswith("Anfrage: Fraesteil 1.4301")
    assert parsed.sent_at is not None and parsed.sent_at.year == 2026
    assert "Losgroessen 1, 5 und 20" in parsed.body_text
    assert [a.filename for a in parsed.attachments] == ["cube-20mm-print.pdf"]
    assert parsed.attachments[0].payload.startswith(b"%PDF")


def test_parse_zip_eml_recurses_members() -> None:
    parsed = parse_rfq_email(ZIP_EML.read_bytes())
    names = sorted(a.filename for a in parsed.attachments)
    # Members are extracted (basenames — no zip paths); the container itself is
    # not filed as its own part-file once its members were extracted.
    assert names == ["wuerfel-20mm-zeichnung.pdf", "wuerfel-20mm.step"]
    by_name = {a.filename: a for a in parsed.attachments}
    assert by_name["wuerfel-20mm.step"].payload.startswith(b"ISO-10303-21")
    assert by_name["wuerfel-20mm-zeichnung.pdf"].payload.startswith(b"%PDF")
    assert all(a.origin == "fraesteil-paket.zip" for a in parsed.attachments)


def _eml_with_zip(zip_bytes: bytes, *, filename: str = "paket.zip") -> bytes:
    msg = EmailMessage()
    msg["From"] = f"Einkauf <{SENDER}>"
    msg["To"] = RECIPIENT
    msg["Subject"] = "Anfrage (ZIP)"
    msg["Message-Id"] = f"<{uuid.uuid4().hex}@kunde-beispiel.de>"
    msg.set_content("Anbei.")
    msg.add_attachment(zip_bytes, maintype="application", subtype="zip", filename=filename)
    return msg.as_bytes()


def _zip_of(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    # Deflate (like real packers): the member-size-cap test needs a container
    # that stays under the cap while a member decompresses past it.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _step_bytes() -> bytes:
    return (FIXTURES.parent / "cad" / "cube-20mm.step").read_bytes()


def test_parse_corrupt_zip_kept_opaque() -> None:
    raw = _eml_with_zip(b"PK\x03\x04 this is not a real zip archive")
    parsed = parse_rfq_email(raw)
    # Un-unpackable ZIP: the container is kept (stored opaque) so nothing is lost.
    assert [a.filename for a in parsed.attachments] == ["paket.zip"]
    assert parsed.attachments[0].origin is None


def test_parse_zip_skips_disallowed_members() -> None:
    raw = _eml_with_zip(
        _zip_of({"teil.step": _step_bytes(), "malware.exe": b"MZ\x90\x00", "notes.txt": b"hi"})
    )
    parsed = parse_rfq_email(raw)
    names = sorted(a.filename for a in parsed.attachments)
    # .exe is not on the allow-list; .txt and .step are.
    assert names == ["notes.txt", "teil.step"]


def test_parse_zip_skips_members_failing_magic_sniff() -> None:
    raw = _eml_with_zip(_zip_of({"fake.pdf": b"this is not a pdf"}))
    parsed = parse_rfq_email(raw)
    assert parsed.attachments == []


def test_parse_nested_zip_recurses_one_level_down() -> None:
    inner = _zip_of({"innen.step": _step_bytes()})
    raw = _eml_with_zip(_zip_of({"inner.zip": inner}))
    parsed = parse_rfq_email(raw)
    assert [a.filename for a in parsed.attachments] == ["innen.step"]


def test_parse_zip_member_count_capped() -> None:
    step = _step_bytes()
    many = _zip_of({f"teil-{i:03d}.step": step for i in range(250)})
    parsed = parse_rfq_email(_eml_with_zip(many))
    # Capped, not crashed — and the cap is logged, not silent (code comment).
    assert 0 < len(parsed.attachments) <= 200


def test_parse_zip_member_size_capped() -> None:
    big = b"ISO-10303-21;" + b"\x00" * (2 * 1024 * 1024)
    parsed = parse_rfq_email(
        _eml_with_zip(_zip_of({"big.step": big, "ok.step": _step_bytes()})),
        max_member_bytes=1024 * 1024,
    )
    assert [a.filename for a in parsed.attachments] == ["ok.step"]


def test_parse_zip_with_excessive_entry_count_kept_opaque() -> None:
    """ZipFile parses the central directory eagerly, so an entry-count bomb is
    refused BEFORE parsing and the container stored opaque (CodeRabbit major)."""
    many = _zip_of({f"n{i}.txt": b"x" for i in range(2001)})
    parsed = parse_rfq_email(_eml_with_zip(many))
    assert [a.filename for a in parsed.attachments] == ["paket.zip"]
    assert parsed.attachments[0].origin is None


def test_parse_zip_aggregate_budget_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """One email may not accumulate more decompressed bytes than the aggregate
    budget, however many members stay under the per-member cap (review 🔴1)."""
    import app.email_ingest as ingest_mod

    member = b"ISO-10303-21;" + b"\x00" * (60 * 1024)
    monkeypatch.setattr(ingest_mod, "MAX_TOTAL_ATTACHMENT_BYTES", 100 * 1024)
    parsed = parse_rfq_email(_eml_with_zip(_zip_of({f"teil-{i}.step": member for i in range(3)})))
    assert len(parsed.attachments) == 1  # second member would exceed the budget


def test_parse_overlong_message_id_falls_back_to_surrogate() -> None:
    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = RECIPIENT
    msg["Subject"] = "Anfrage"
    msg["Message-Id"] = f"<{'x' * 4000}@kunde-beispiel.de>"
    msg.set_content("Hallo.")
    parsed = parse_rfq_email(msg.as_bytes())
    # An index-row-busting header never reaches the unique index (review 🟡6).
    assert parsed.message_id.startswith("sha256:")


def test_parse_missing_message_id_gets_content_hash_surrogate() -> None:
    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = RECIPIENT
    msg["Subject"] = "Anfrage ohne Message-Id"
    msg.set_content("Hallo.")
    raw = msg.as_bytes()
    assert email.message_from_bytes(raw, policy=policy.default)["Message-Id"] is None
    first = parse_rfq_email(raw)
    second = parse_rfq_email(raw)
    assert first.message_id.startswith("sha256:")
    assert first.message_id == second.message_id  # deterministic → idempotency holds


# --------------------------------------------------------------------------- #
# Webhook integration (real Postgres + eager Celery)
# --------------------------------------------------------------------------- #
@pytest.fixture
def eager_celery() -> Iterator[None]:
    """Run tasks inline (M2.5/M3.1 precedent) so the webhook's enqueue executes."""
    previous = {
        key: celery_app.conf[key]
        for key in ("task_always_eager", "task_store_eager_result", "task_eager_propagates")
    }
    celery_app.conf.update(
        task_always_eager=True,
        task_store_eager_result=True,
        task_eager_propagates=True,
    )
    try:
        yield
    finally:
        celery_app.conf.update(**previous)


@pytest.fixture
def lens_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Record Lens-extraction enqueues instead of running the vision pipeline."""
    calls: list[tuple[str, str, str]] = []

    def record(org_id: uuid.UUID, part_id: uuid.UUID, file_id: uuid.UUID) -> None:
        calls.append((str(org_id), str(part_id), str(file_id)))

    monkeypatch.setattr("app.email_ingest._enqueue_lens_extract", record)
    return calls


@pytest.fixture
def ingest_client(tenancy_db: str) -> Iterator[TestClient]:
    """App served as the restricted RLS role, with the Mailgun key configured."""
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.mailgun_webhook_signing_key = SIGNING_KEY
    with TestClient(create_app(settings)) as client:
        yield client


def _post_webhook(
    client: TestClient,
    raw_eml: bytes,
    *,
    recipient: str = RECIPIENT,
    key: str = SIGNING_KEY,
    fields: dict[str, str] | None = None,
) -> Any:
    data = {
        **(fields or _sign(key)),
        "recipient": recipient,
        "sender": SENDER,
        "body-mime": raw_eml.decode("utf-8"),
    }
    return client.post("/webhooks/mailgun", data=data)


def _fetch_rows(owner_url: str, sql: str, params: dict[str, object]) -> list[Any]:
    async def _run() -> list[Any]:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                return list((await conn.execute(text(sql), params)).all())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _seed_org_with_member(seeder: Seeder, slug: str = "fechner") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug, f"{slug.title()} GmbH")
    user = seeder.user(f"estimator@{slug}.example")
    seeder.membership(user, org, [MembershipRole.admin])
    return org, user


def test_webhook_ingests_sample_eml_end_to_end(
    ingest_client: TestClient,
    seeder: Seeder,
    tenancy_db: str,
    eager_celery: None,
    lens_calls: list[tuple[str, str, str]],
) -> None:
    org, user = _seed_org_with_member(seeder)
    raw = SAMPLE_EML.read_bytes()

    resp = _post_webhook(ingest_client, raw)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "created"
    quote_id = body["quote_id"]

    # Draft quote, org currency, thread id + received date set.
    rows = _fetch_rows(
        tenancy_db,
        "SELECT status, currency, email_thread_id, rfq_received_date, contact_id "
        "FROM quote WHERE id = :id AND org_id = :org",
        {"id": quote_id, "org": str(org)},
    )
    assert len(rows) == 1
    status_, currency, thread_id, received, contact_id = rows[0]
    assert status_ == "draft"
    assert currency == "EUR"
    assert thread_id == "<rfq-fixture-0001@kunde-beispiel.de>"
    assert received is not None and contact_id is not None

    # Contact created account-less (the held-for-review intake state).
    contacts = _fetch_rows(
        tenancy_db,
        "SELECT account_id, first_name, last_name FROM contact "
        "WHERE org_id = :org AND email = :email AND deleted_at IS NULL",
        {"org": str(org), "email": SENDER},
    )
    assert len(contacts) == 1
    assert contacts[0][0] is None  # no Account invented

    # RFQ row: .eml stored as ORIGINAL RFQ + linked to the quote.
    rfqs = _fetch_rows(
        tenancy_db,
        "SELECT id, email_message_id, eml_storage_key, eml_filename, quote_id, processed_on, "
        "description FROM request_for_quote WHERE org_id = :org",
        {"org": str(org)},
    )
    assert len(rfqs) == 1
    rfq = rfqs[0]
    assert rfq[1] == "<rfq-fixture-0001@kunde-beispiel.de>"
    assert rfq[2] and rfq[3] == "original-rfq.eml"
    assert str(rfq[4]) == quote_id and rfq[5] is not None
    assert "Losgroessen" in (rfq[6] or "")

    # The ORIGINAL RFQ blob round-trips byte-faithfully (ASCII fixture).
    app = cast("Any", ingest_client.app)  # TestClient types .app as a bare ASGI callable

    async def _read_back(key: str) -> bytes:
        return b"".join([chunk async for chunk in app.state.storage.stream(key)])

    assert asyncio.run(_read_back(rfq[2])) == raw

    # Attachment filed: one part + one primary file, RFQ provenance kept.
    files = _fetch_rows(
        tenancy_db,
        "SELECT pf.filename, pf.role, pf.rfq_id, p.name FROM part_file pf "
        "JOIN part p ON p.id = pf.part_id WHERE pf.org_id = :org",
        {"org": str(org)},
    )
    assert [(f[0], f[1]) for f in files] == [("cube-20mm-print.pdf", "primary")]
    assert str(files[0][2]) == str(rfq[0])
    assert files[0][3] == "cube-20mm-print"

    # Extraction queued for the PDF print (recorded, not run).
    assert len(lens_calls) == 1
    assert lens_calls[0][0] == str(org)

    # Dashboard notification for the org's active member.
    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        notes = ingest_client.get("/api/notifications").json()
    kinds = [n["kind"] for n in notes]
    assert "quote_email_ingested" in kinds
    payload = next(n["payload"] for n in notes if n["kind"] == "quote_email_ingested")
    assert payload["quote_id"] == quote_id
    assert payload["quote_number"]


def test_webhook_matches_existing_contact_and_account(
    ingest_client: TestClient,
    seeder: Seeder,
    tenancy_db: str,
    eager_celery: None,
    lens_calls: list[tuple[str, str, str]],
) -> None:
    org, _ = _seed_org_with_member(seeder)
    account = seeder.account(org, "Kunde Beispiel GmbH")
    contact = seeder.contact(org, account, SENDER)

    resp = _post_webhook(ingest_client, SAMPLE_EML.read_bytes())
    assert resp.status_code == 200
    quote_id = resp.json()["quote_id"]

    rows = _fetch_rows(
        tenancy_db,
        "SELECT contact_id, account_id FROM quote WHERE id = :id",
        {"id": quote_id},
    )
    assert rows[0][0] == contact and rows[0][1] == account
    # No duplicate contact minted for a known sender.
    count = _fetch_rows(
        tenancy_db,
        "SELECT count(*) FROM contact WHERE org_id = :org AND email = :email",
        {"org": str(org), "email": SENDER},
    )
    assert count[0][0] == 1


def test_webhook_is_idempotent_on_message_id(
    ingest_client: TestClient,
    seeder: Seeder,
    tenancy_db: str,
    eager_celery: None,
    lens_calls: list[tuple[str, str, str]],
) -> None:
    org, _ = _seed_org_with_member(seeder)
    raw = SAMPLE_EML.read_bytes()

    first = _post_webhook(ingest_client, raw)
    second = _post_webhook(ingest_client, raw)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["status"] == "created"
    assert second.json()["status"] == "duplicate"
    assert second.json()["quote_id"] == first.json()["quote_id"]

    for table in ("quote", "request_for_quote"):
        count = _fetch_rows(
            tenancy_db,
            f"SELECT count(*) FROM {table} WHERE org_id = :org",
            {"org": str(org)},
        )
        assert count[0][0] == 1, table


def test_webhook_zip_attachments_create_parts_and_queue_pdf_extraction(
    ingest_client: TestClient,
    seeder: Seeder,
    tenancy_db: str,
    eager_celery: None,
    lens_calls: list[tuple[str, str, str]],
) -> None:
    org, _ = _seed_org_with_member(seeder)

    resp = _post_webhook(ingest_client, ZIP_EML.read_bytes())
    assert resp.status_code == 200, resp.text

    files = _fetch_rows(
        tenancy_db,
        "SELECT filename, file_type FROM part_file WHERE org_id = :org",
        {"org": str(org)},
    )
    assert sorted(tuple(f) for f in files) == [
        ("wuerfel-20mm-zeichnung.pdf", "document"),
        ("wuerfel-20mm.step", "brep_cad"),
    ]
    # Lens runs on PDF/TIFF prints only — the STEP goes to geometry (M4).
    assert len(lens_calls) == 1


def test_webhook_unknown_slug_is_permanent_reject(
    ingest_client: TestClient, seeder: Seeder, eager_celery: None
) -> None:
    _seed_org_with_member(seeder, slug="fechner")
    resp = _post_webhook(ingest_client, SAMPLE_EML.read_bytes(), recipient="nobody@rfq.tolera.eu")
    # 406 tells Mailgun to stop retrying (permanent failure).
    assert resp.status_code == 406


def test_webhook_rejects_bad_signature(
    ingest_client: TestClient, seeder: Seeder, eager_celery: None
) -> None:
    _seed_org_with_member(seeder)
    resp = _post_webhook(ingest_client, SAMPLE_EML.read_bytes(), key="wrong-key")
    assert resp.status_code == 401


def test_webhook_rejects_replayed_token(
    ingest_client: TestClient,
    seeder: Seeder,
    eager_celery: None,
    lens_calls: list[tuple[str, str, str]],
) -> None:
    """The HMAC doesn't bind the payload, so a captured (timestamp, token,
    signature) must be single-use (review 🟡4)."""
    _seed_org_with_member(seeder)
    fields = _sign(SIGNING_KEY)
    first = _post_webhook(ingest_client, SAMPLE_EML.read_bytes(), fields=fields)
    replay = _post_webhook(ingest_client, ZIP_EML.read_bytes(), fields=fields)
    assert first.status_code == 200
    assert replay.status_code == 401


def test_webhook_fails_closed_when_unconfigured(tenancy_db: str, seeder: Seeder) -> None:
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.mailgun_webhook_signing_key = ""
    _seed_org_with_member(seeder)
    with TestClient(create_app(settings)) as client:
        resp = _post_webhook(client, SAMPLE_EML.read_bytes())
    assert resp.status_code == 503


def test_ingested_rows_are_org_scoped(
    ingest_client: TestClient,
    seeder: Seeder,
    tenancy_db: str,
    eager_celery: None,
    lens_calls: list[tuple[str, str, str]],
) -> None:
    _seed_org_with_member(seeder, slug="fechner")
    org_b = seeder.org("acme", "Acme GmbH")
    intruder = seeder.user("intruder@acme.example")
    seeder.membership(intruder, org_b, [MembershipRole.admin])

    resp = _post_webhook(ingest_client, SAMPLE_EML.read_bytes())
    assert resp.status_code == 200

    with authed(ingest_client, user_id=intruder, org_id=org_b, roles=[MembershipRole.admin]):
        quotes = ingest_client.post("/api/quotes/search", json={}).json()
        notes = ingest_client.get("/api/notifications").json()
    assert quotes["total"] == 0 and quotes["rows"] == []
    assert notes == []
