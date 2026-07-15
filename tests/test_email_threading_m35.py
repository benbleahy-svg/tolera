"""M3.5 — send-from-user, inbound sync, reply matching, timeline.

The block's test plan: "reply round-trip test — outbound (mock provider) →
inbound reply with matching ``In-Reply-To`` → asserts it threads onto the
correct quote and lands on the timeline." Plus: matching via provider
``threadId`` and via the M3.3 ingest ``quote.email_thread_id``; non-matching
mail is NOT stored (data minimisation); idempotent re-polls; cursor + status
updates; permissions; 409 without a connection.

All provider traffic is mocked (build-plan M3.5: "sends are mocked in CI").
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.email_providers import InboundAttachment, InboundEmail, SendResult, SyncResult
from app.email_sync import run_email_sync_connection
from app.main import create_app
from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings

KEY = "cd" * 32

pytestmark = pytest.mark.usefixtures("tenancy_db")


class MockProvider:
    """Records sends; serves a scripted inbox for fetch_new."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbox: list[InboundEmail] = []
        self.next_cursor: str | None = "cursor-after-sync"
        self.thread_id: str | None = "prov-thread-1"

    async def send(
        self, credentials: Any, *, from_address: str, from_name: Any, message: Any
    ) -> SendResult:
        message_id = f"<out-{len(self.sent) + 1}@acme-machining.de>"
        self.sent.append(
            {
                "from_address": from_address,
                "to": message.to,
                "subject": message.subject,
                "in_reply_to": message.in_reply_to,
                "references": message.references,
                "message_id": message_id,
            }
        )
        return SendResult(message_id=message_id, provider_thread_id=self.thread_id)

    async def fetch_new(self, credentials: Any, *, cursor: str | None) -> SyncResult:
        return SyncResult(list(self.inbox), self.next_cursor)

    async def baseline_cursor(self, credentials: Any) -> str | None:
        return "baseline"


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> MockProvider:
    mock = MockProvider()
    monkeypatch.setattr("app.email_threads.get_provider", lambda _t: mock)
    monkeypatch.setattr("app.email_sync.get_provider", lambda _t: mock)
    return mock


@pytest.fixture
def client(tenancy_db: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.email_credentials_key = KEY
    monkeypatch.setattr("app.email_sync._task_settings", lambda: settings)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _fetch_rows(owner_url: str, sql: str, params: dict[str, object]) -> list[Any]:
    async def _run() -> list[Any]:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                return list((await conn.execute(text(sql), params)).all())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


SMTP_PAYLOAD = {
    "from_address": "jan@acme-machining.de",
    "from_name": "Jan Fechner",
    "smtp_host": "smtp.acme-machining.de",
    "imap_host": "imap.acme-machining.de",
    "username": "jan@acme-machining.de",
    "password": "app-password-secret",
}


def _seed_quote_org(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Org + admin member + draft quote."""
    org = seeder.org(slug, f"{slug.title()} GmbH")
    user = seeder.user(f"jan@{slug}.example")
    seeder.membership(user, org, [MembershipRole.admin])
    quote = seeder.quote(org, f"Q-{slug}-1")
    return org, user, quote


def _connect(client: TestClient) -> str:
    resp = client.post("/email-connections/smtp", json=SMTP_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def _send(client: TestClient, quote_id: uuid.UUID, **overrides: Any) -> Any:
    payload = {
        "to": ["einkauf@kunde-beispiel.de"],
        "subject": "Ihr Angebot Q-1",
        "body_text": "Sehr geehrte Damen und Herren, anbei unser Angebot.",
        **overrides,
    }
    return client.post(f"/quotes/{quote_id}/emails", json=payload)


def _reply(
    *,
    message_id: str = "<reply-1@kunde-beispiel.de>",
    in_reply_to: str | None = None,
    references: list[str] | None = None,
    provider_thread_id: str | None = None,
    attachments: list[InboundAttachment] | None = None,
) -> InboundEmail:
    return InboundEmail(
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=references or ([in_reply_to] if in_reply_to else []),
        provider_thread_id=provider_thread_id,
        from_address="einkauf@kunde-beispiel.de",
        to_addresses=["jan@acme-machining.de"],
        subject="AW: Ihr Angebot Q-1",
        body_text="Danke, wir bestellen 50 Stück.",
        body_html=None,
        sent_at=datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
        attachments=attachments or [],
    )


def _run_sync(org: uuid.UUID, connection_id: str) -> dict[str, Any]:
    return asyncio.run(_sync_via_task_resources(org_id=org, connection_id=uuid.UUID(connection_id)))


async def _sync_via_task_resources(
    *, org_id: uuid.UUID, connection_id: uuid.UUID
) -> dict[str, Any]:
    from app.task_resources import resolve

    db_url, storage = resolve()
    return await run_email_sync_connection(
        db_url, storage, org_id=org_id, connection_id=connection_id
    )


# --------------------------------------------------------------------------- #
# Outbound send-from-user
# --------------------------------------------------------------------------- #
def test_send_uses_connected_from_address_and_creates_thread(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    org, user, quote = _seed_quote_org(seeder, "acme-send")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        _connect(client)
        resp = _send(client, quote)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["direction"] == "outbound"
    assert body["from_address"] == "jan@acme-machining.de"  # the CONNECTED address
    assert provider.sent[0]["from_address"] == "jan@acme-machining.de"

    rows = _fetch_rows(
        tenancy_db,
        "SELECT sent_message_id, provider_thread_id FROM quote_email_thread "
        "WHERE org_id = :org AND quote_id = :quote",
        {"org": org, "quote": quote},
    )
    assert rows == [("<out-1@acme-machining.de>", "prov-thread-1")]


def test_send_without_connection_is_409(client: TestClient, seeder: Seeder) -> None:
    org, user, quote = _seed_quote_org(seeder, "acme-noconn")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        resp = _send(client, quote)
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_email_connection"


def test_send_requires_quote_edit(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    org, _user, quote = _seed_quote_org(seeder, "acme-perm")
    viewer = seeder.user("viewer@acme-perm.example")
    seeder.membership(viewer, org, [MembershipRole.viewer])
    with authed(client, user_id=viewer, org_id=org, roles=[MembershipRole.viewer]):
        assert _send(client, quote).status_code == 403


def test_follow_up_send_threads_with_rfc_headers(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    org, user, quote = _seed_quote_org(seeder, "acme-follow")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        _connect(client)
        _send(client, quote)
        _send(client, quote, subject="Nachtrag zum Angebot")
    follow_up = provider.sent[1]
    # RFC 2822 threading: the follow-up references the thread's first message.
    assert follow_up["references"] == ["<out-1@acme-machining.de>"]
    assert follow_up["in_reply_to"] == "<out-1@acme-machining.de>"


# --------------------------------------------------------------------------- #
# Inbound sync + reply matching
# --------------------------------------------------------------------------- #
def test_reply_round_trip_via_in_reply_to(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    """The block's acceptance path: outbound → customer reply → timeline."""
    org, user, quote = _seed_quote_org(seeder, "acme-round")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect(client)
        _send(client, quote)
        provider.inbox = [_reply(in_reply_to="<out-1@acme-machining.de>")]
        result = _run_sync(org, connection_id)
        assert result["matched"] == 1

        timeline = client.get(f"/quotes/{quote}/emails").json()
    assert [m["direction"] for m in timeline] == ["outbound", "inbound"]  # in order
    assert timeline[1]["from_address"] == "einkauf@kunde-beispiel.de"
    assert timeline[1]["body_text"] == "Danke, wir bestellen 50 Stück."

    # The estimator is notified of the reply.
    notes = _fetch_rows(
        tenancy_db,
        "SELECT kind, payload->>'quote_id' FROM notification "
        "WHERE org_id = :org AND user_id = :user AND kind = 'quote_email_reply'",
        {"org": org, "user": user},
    )
    assert notes == [("quote_email_reply", str(quote))]


def test_reply_matches_via_provider_thread_id(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    org, user, quote = _seed_quote_org(seeder, "acme-tid")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect(client)
        _send(client, quote)
        # Outlook path: no In-Reply-To exposed, only the conversationId.
        provider.inbox = [_reply(provider_thread_id="prov-thread-1")]
        assert _run_sync(org, connection_id)["matched"] == 1
        timeline = client.get(f"/quotes/{quote}/emails").json()
    assert [m["direction"] for m in timeline] == ["outbound", "inbound"]


def test_reply_matches_ingested_rfq_thread_id(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    """M3.3 hand-off: a reply whose References carries the ingested RFQ's
    Message-Id (quote.email_thread_id) threads onto that quote — even though
    no outbound was ever sent from the platform."""
    org, user, quote = _seed_quote_org(seeder, "acme-rfq")
    seeder.sql(
        "UPDATE quote SET email_thread_id = '<rfq-42@kunde-beispiel.de>' WHERE id = :id",
        {"id": quote},
    )
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect(client)
        provider.inbox = [_reply(references=["<rfq-42@kunde-beispiel.de>", "<other@x.example>"])]
        assert _run_sync(org, connection_id)["matched"] == 1
        timeline = client.get(f"/quotes/{quote}/emails").json()
    assert [m["direction"] for m in timeline] == ["inbound"]


def test_non_matching_mail_is_not_stored(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    """Data minimisation: the sync must never ingest the user's unrelated mail."""
    org, user, _quote = _seed_quote_org(seeder, "acme-nomatch")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect(client)
        provider.inbox = [
            _reply(message_id="<newsletter@spam.example>", references=["<unrelated@x>"])
        ]
        result = _run_sync(org, connection_id)
    assert result["matched"] == 0
    rows = _fetch_rows(
        tenancy_db, "SELECT count(*) FROM email_message WHERE org_id = :org", {"org": org}
    )
    assert rows == [(1,)] or rows == [(0,)]  # only ever the outbound (none here)
    assert rows == [(0,)]


def test_resync_is_idempotent(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    org, user, quote = _seed_quote_org(seeder, "acme-idem")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect(client)
        _send(client, quote)
        provider.inbox = [_reply(in_reply_to="<out-1@acme-machining.de>")]
        assert _run_sync(org, connection_id)["matched"] == 1
        # The same UNSEEN message comes back on the next poll (IMAP semantics).
        assert _run_sync(org, connection_id)["matched"] == 0
    rows = _fetch_rows(
        tenancy_db,
        "SELECT count(*) FROM email_message WHERE org_id = :org AND direction = 'inbound'",
        {"org": org},
    )
    assert rows == [(1,)]


def test_sync_updates_cursor_and_status(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    org, user, _quote = _seed_quote_org(seeder, "acme-cursor")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect(client)
    # SMTP/IMAP has no cursor; simulate the gmail cursor path directly.
    seeder.sql(
        "UPDATE user_email_connection SET connection_type = 'gmail', "
        "gmail_history_id = 'hist-1' WHERE id = :id",
        {"id": uuid.UUID(connection_id)},
    )
    provider.next_cursor = "hist-2"
    _run_sync(org, connection_id)
    [(history_id, synced_at, sync_error)] = _fetch_rows(
        tenancy_db,
        "SELECT gmail_history_id, last_synced_at, last_sync_error "
        "FROM user_email_connection WHERE id = :id",
        {"id": uuid.UUID(connection_id)},
    )
    assert history_id == "hist-2"
    assert synced_at is not None
    assert sync_error is None


def test_inbound_attachment_saved_and_linked(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    org, user, quote = _seed_quote_org(seeder, "acme-att")
    pdf = b"%PDF-1.4 fake print bytes"
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect(client)
        _send(client, quote)
        provider.inbox = [
            _reply(
                in_reply_to="<out-1@acme-machining.de>",
                attachments=[InboundAttachment("bestellung.pdf", "application/pdf", pdf)],
            )
        ]
        _run_sync(org, connection_id)
        timeline = client.get(f"/quotes/{quote}/emails").json()
    attachments = timeline[1]["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "bestellung.pdf"
    assert attachments[0]["size_bytes"] == len(pdf)
    assert "storage_key" in attachments[0]


def test_cross_org_reply_never_matches(
    client: TestClient, seeder: Seeder, provider: MockProvider, tenancy_db: str
) -> None:
    """A connection in org B must not thread onto org A's quote even when the
    Message-Id collides (org-scoped session + org-scoped matching)."""
    org_a, user_a, quote_a = _seed_quote_org(seeder, "acme-org-a")
    with authed(client, user_id=user_a, org_id=org_a, roles=[MembershipRole.admin]):
        _connect(client)
        _send(client, quote_a)

    org_b = seeder.org("acme-org-b", "Org B GmbH")
    user_b = seeder.user("jan@acme-org-b.example")
    seeder.membership(user_b, org_b, [MembershipRole.admin])
    with authed(client, user_id=user_b, org_id=org_b, roles=[MembershipRole.admin]):
        connection_b = _connect(client)
        provider.inbox = [_reply(in_reply_to="<out-1@acme-machining.de>")]
        result = _run_sync(org_b, connection_b)
    assert result["matched"] == 0
    rows = _fetch_rows(
        tenancy_db,
        "SELECT count(*) FROM email_message WHERE org_id = :org AND direction = 'inbound'",
        {"org": org_a},
    )
    assert rows == [(0,)]


# --------------------------------------------------------------------------- #
# Timeline permissions
# --------------------------------------------------------------------------- #
def test_timeline_readable_by_viewer(
    client: TestClient, seeder: Seeder, provider: MockProvider
) -> None:
    org, user, quote = _seed_quote_org(seeder, "acme-tlperm")
    viewer = seeder.user("viewer@acme-tlperm.example")
    seeder.membership(viewer, org, [MembershipRole.viewer])
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        _connect(client)
        _send(client, quote)
    with authed(client, user_id=viewer, org_id=org, roles=[MembershipRole.viewer]):
        resp = client.get(f"/quotes/{quote}/emails")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
