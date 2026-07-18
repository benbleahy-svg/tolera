"""Send-quote composer (M5.5) — the real draft→Sent send.

Block test plan: send the thread's quote (mock the mail provider); assert merge
resolution, the ``/q/:token`` link present, PDF attached when toggled, lifecycle =
Sent, and ``quote.sent`` fired; To/CC/BCC all receive. Plus the platform-address
fallback + the "connect your email" 409 when nothing is configured.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.email_providers import PlatformSender, SendResult, SyncResult
from app.main import create_app
from app.models import MembershipRole, QuoteStatus
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings

pytestmark = pytest.mark.usefixtures("tenancy_db")

KEY = "cd" * 32


class MockProvider:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(
        self, credentials: Any, *, from_address: str, from_name: Any, message: Any
    ) -> SendResult:
        self.sent.append(
            {
                "from_address": from_address,
                "to": list(message.to),
                "cc": list(message.cc),
                "bcc": list(message.bcc),
                "all": list(message.all_recipients),
                "subject": message.subject,
                "body_text": message.body_text,
                "body_html": message.body_html,
                "attachments": [a.filename for a in message.attachments],
            }
        )
        return SendResult(message_id=f"<out-{len(self.sent)}@acme.de>", provider_thread_id="t-1")

    async def fetch_new(self, credentials: Any, *, cursor: str | None) -> SyncResult:
        return SyncResult([], None)  # send-only mock; inbound is out of scope here

    async def baseline_cursor(self, credentials: Any) -> str | None:
        return None


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> MockProvider:
    mock = MockProvider()
    monkeypatch.setattr("app.quote_send.get_provider", lambda _t: mock)
    return mock


@pytest.fixture
def client(tenancy_db: str) -> Iterator[TestClient]:
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.email_credentials_key = KEY
    settings.quote_token_secret = "s" * 40
    settings.app_base_url = "https://app.tolera.eu"
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _fetch(owner_url: str, sql: str, params: dict[str, object]) -> list[Any]:
    async def _run() -> list[Any]:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                return list((await conn.execute(text(sql), params)).all())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


SMTP_PAYLOAD = {
    "from_address": "jan@acme.de",
    "from_name": "Jan Fechner",
    "smtp_host": "smtp.acme.de",
    "imap_host": "imap.acme.de",
    "username": "jan@acme.de",
    "password": "app-password",
}


def _setup(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org = seeder.org(slug, f"{slug.title()} GmbH")
    user = seeder.user(f"jan@{slug}.example")
    seeder.membership(user, org, [MembershipRole.admin])
    account = seeder.account(org, "Kunde GmbH")
    contact = seeder.contact(org, account, "chris@kunde.de")
    quote = seeder.quote(
        org, f"Q-{slug}-1", account_id=account, contact_id=contact, estimator_id=user
    )
    return org, user, quote


def _send_body(**overrides: Any) -> dict[str, Any]:
    return {
        "to": ["chris@kunde.de"],
        "subject": "Ihr Angebot %%QUOTE_NUMBER%%",
        "body_html": "<p>Guten Tag, Ihr Angebot: %%QUOTE_LINK%%</p>",
        "include_pdf": False,
        **overrides,
    }


def test_send_resolves_merge_and_link_and_flips_to_sent(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    org, user, quote = _setup(seeder, "send-happy")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        client.post("/email-connections/smtp", json=SMTP_PAYLOAD)
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body())
    assert resp.status_code == 200, resp.text

    sent = provider.sent[0]
    # Merge resolved: the quote number is substituted, no %% left.
    assert "Q-send-happy-1" in sent["subject"]
    assert "%%" not in sent["subject"] and "%%" not in sent["body_html"]
    # The secure portal link is present and points at /q/<token>.
    assert "https://app.tolera.eu/q/" in sent["body_html"]

    # Lifecycle flipped to Sent.
    rows = _fetch(tenancy_db, "SELECT status FROM quote WHERE id = :q", {"q": quote})
    assert rows[0][0] == QuoteStatus.sent.value

    # A per-recipient QuoteToken was minted.
    tokens = _fetch(
        tenancy_db,
        "SELECT recipient_email FROM quote_token WHERE quote_id = :q",
        {"q": quote},
    )
    assert ("chris@kunde.de",) in tokens

    # quote.sent fired onto the outbox.
    events = _fetch(
        tenancy_db,
        "SELECT event_type, payload FROM domain_event WHERE org_id = :o",
        {"o": org},
    )
    assert any(e[0] == "quote.sent" for e in events)


def test_send_reuses_existing_thread(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    # A draft may already have a QuoteEmailThread (an earlier M3.5 timeline message);
    # the composer must reuse it, not violate the per-quote unique index.
    org, user, quote = _setup(seeder, "send-thread")
    seeder.sql(
        "INSERT INTO quote_email_thread (org_id, quote_id, sent_message_id) "
        "VALUES (:o, :q, '<pre-existing@acme.de>')",
        {"o": org, "q": quote},
    )
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        client.post("/email-connections/smtp", json=SMTP_PAYLOAD)
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body())
    assert resp.status_code == 200, resp.text
    rows = _fetch(
        tenancy_db, "SELECT count(*) FROM quote_email_thread WHERE quote_id = :q", {"q": quote}
    )
    assert rows[0][0] == 1  # still exactly one thread


def test_to_cc_bcc_all_receive(client: TestClient, seeder: Seeder, provider: MockProvider) -> None:
    org, user, quote = _setup(seeder, "send-ccbcc")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        client.post("/email-connections/smtp", json=SMTP_PAYLOAD)
        resp = client.post(
            f"/api/quotes/{quote}/send",
            json=_send_body(cc=["cc@kunde.de"], bcc=["bcc@intern.de"]),
        )
    assert resp.status_code == 200, resp.text
    sent = provider.sent[0]
    assert set(sent["all"]) == {"chris@kunde.de", "cc@kunde.de", "bcc@intern.de"}


def test_include_pdf_attaches_snapshot(
    client: TestClient,
    seeder: Seeder,
    provider: MockProvider,
    monkeypatch: pytest.MonkeyPatch,
    tenancy_db: str,
) -> None:
    monkeypatch.setattr("app.quote_send.weasyprint_available", lambda: True)
    monkeypatch.setattr("app.quote_send.html_to_pdf", lambda _html: b"%PDF-1.4 fake")
    org, user, quote = _setup(seeder, "send-pdf")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        client.post("/email-connections/smtp", json=SMTP_PAYLOAD)
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body(include_pdf=True))
    assert resp.status_code == 200, resp.text
    assert provider.sent[0]["attachments"]  # a PDF was attached
    # The send-time snapshot key was persisted.
    rows = _fetch(tenancy_db, "SELECT pdf_object_key FROM quote WHERE id = :q", {"q": quote})
    assert rows[0][0] is not None


def test_fallback_to_platform_when_no_connection(
    client: TestClient, seeder: Seeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform_mock = MockProvider()
    monkeypatch.setattr(
        "app.quote_send.get_platform_sender",
        lambda _s: PlatformSender(platform_mock, "quotes@tolera.eu", "Tolera"),
    )
    org, user, quote = _setup(seeder, "send-fallback")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body())
    assert resp.status_code == 200, resp.text
    assert platform_mock.sent[0]["from_address"] == "quotes@tolera.eu"


def test_no_connection_and_no_platform_is_409(
    client: TestClient, seeder: Seeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.quote_send.get_platform_sender", lambda _s: None)
    org, user, quote = _setup(seeder, "send-noconn")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body())
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_email_connection"


def test_send_requires_contact(client: TestClient, seeder: Seeder, provider: MockProvider) -> None:
    org = seeder.org("send-nocontact", "NoContact GmbH")
    user = seeder.user("jan@send-nocontact.example")
    seeder.membership(user, org, [MembershipRole.admin])
    quote = seeder.quote(org, "Q-nc-1")  # no contact assigned
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        client.post("/email-connections/smtp", json=SMTP_PAYLOAD)
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body())
    assert resp.status_code == 422
    assert resp.json()["code"] == "missing_contact"


def test_preview_does_not_send_or_transition(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    org, user, quote = _setup(seeder, "send-preview")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        resp = client.post(f"/api/quotes/{quote}/send/preview", json=_send_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Q-send-preview-1" in body["subject"]
    assert not provider.sent  # nothing sent
    rows = _fetch(tenancy_db, "SELECT status FROM quote WHERE id = :q", {"q": quote})
    assert rows[0][0] == QuoteStatus.draft.value  # still draft


def test_quote_email_carries_impressum_footer(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    # M5.9 AC: customer-facing quote emails carry the legal Impressum + USt-IdNr,
    # appended server-side (not the editable template body).
    org = seeder.org(
        "send-impressum",
        "Send-Impressum GmbH",
        ust_id_nr="DE123456789",
        commercial_register="Amtsgericht München, HRB 123456",
        facility_address="Musterstraße 1\n80331 München",
    )
    user = seeder.user("jan@send-impressum.example")
    seeder.membership(user, org, [MembershipRole.admin])
    account = seeder.account(org, "Kunde GmbH")
    contact = seeder.contact(org, account, "chris@kunde.de")
    quote = seeder.quote(org, "Q-imp-1", account_id=account, contact_id=contact, estimator_id=user)
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        client.post("/email-connections/smtp", json=SMTP_PAYLOAD)
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body())
    assert resp.status_code == 200, resp.text
    body_html = provider.sent[0]["body_html"]
    assert "Impressum" in body_html
    assert "Handelsregister" in body_html
    assert "Amtsgericht München, HRB 123456" in body_html
    assert "USt-IdNr." in body_html and "DE123456789" in body_html


def test_quote_email_omits_impressum_when_org_has_no_legal_identity(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    # Never invent: a plain org (no register/VAT-ID) sends no Impressum block.
    org, user, quote = _setup(seeder, "send-no-imp")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        client.post("/email-connections/smtp", json=SMTP_PAYLOAD)
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body())
    assert resp.status_code == 200, resp.text
    assert "Impressum" not in provider.sent[0]["body_html"]


def test_send_requires_quote_finalize(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    org, _user, quote = _setup(seeder, "send-perm")
    viewer = seeder.user("viewer@send-perm.example")
    seeder.membership(viewer, org, [MembershipRole.viewer])
    with authed(client, user_id=viewer, org_id=org, roles=[MembershipRole.viewer]):
        resp = client.post(f"/api/quotes/{quote}/send", json=_send_body())
    assert resp.status_code == 403
