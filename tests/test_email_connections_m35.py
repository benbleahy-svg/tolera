"""M3.5 — user email connections (spec #email-connectivity settings page).

Covers: SMTP/IMAP manual connect, credentials AES-256-GCM at rest (raw column
inspected via the owner engine), never-in-responses, one-primary-per-user,
own-connections-only visibility, fail-closed without the crypto key, the OAuth
start/callback flow (token exchange mocked), and the test-send button.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.email_crypto import decrypt_credentials
from app.main import create_app
from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings

KEY = "ab" * 32

pytestmark = pytest.mark.usefixtures("tenancy_db")


@pytest.fixture
def email_client(tenancy_db: str) -> Iterator[TestClient]:
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.email_credentials_key = KEY
    settings.google_oauth_client_id = "google-client-id"
    settings.google_oauth_client_secret = "google-client-secret"
    with TestClient(create_app(settings)) as client:
        yield client


def _seed_member(
    seeder: Seeder, slug: str = "fechner", email: str = "jan@fechner.example"
) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug, f"{slug.title()} GmbH")
    user = seeder.user(email)
    seeder.membership(user, org, [MembershipRole.admin])
    return org, user


SMTP_PAYLOAD = {
    "from_address": "jan@acme-machining.de",
    "from_name": "Jan Fechner",
    "smtp_host": "smtp.acme-machining.de",
    "smtp_port": 587,
    "imap_host": "imap.acme-machining.de",
    "imap_port": 993,
    "username": "jan@acme-machining.de",
    "password": "app-password-secret",
}


def _connect_smtp(client: TestClient, payload: dict[str, Any] | None = None) -> Any:
    return client.post("/email-connections/smtp", json=payload or SMTP_PAYLOAD)


def _fetch_rows(owner_url: str, sql: str, params: dict[str, object]) -> list[Any]:
    async def _run() -> list[Any]:
        engine = create_async_engine(owner_url)
        try:
            async with engine.connect() as conn:
                return list((await conn.execute(text(sql), params)).all())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


# --------------------------------------------------------------------------- #
# Manual SMTP/IMAP connect
# --------------------------------------------------------------------------- #
def test_smtp_connect_creates_primary_connection(email_client: TestClient, seeder: Seeder) -> None:
    org, user = _seed_member(seeder)
    with authed(email_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        resp = _connect_smtp(email_client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["connection_type"] == "smtp_imap"
    assert body["from_address"] == "jan@acme-machining.de"
    assert body["is_primary"] is True  # first connection auto-primary
    # Credentials never serialize into a response, under any key name.
    assert "app-password-secret" not in resp.text
    assert "encrypted_credentials" not in body
    assert "password" not in body


def test_credentials_encrypted_at_rest(
    email_client: TestClient, seeder: Seeder, tenancy_db: str
) -> None:
    org, user = _seed_member(seeder, slug="fechner-rest")
    with authed(email_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect_smtp(email_client).json()["id"]
    [(blob,)] = _fetch_rows(
        tenancy_db,
        "SELECT encrypted_credentials FROM user_email_connection WHERE id = :id",
        {"id": uuid.UUID(connection_id)},
    )
    raw = bytes(blob)
    assert b"app-password-secret" not in raw  # ciphertext, not plaintext
    bundle = decrypt_credentials(KEY, raw)
    assert bundle["password"] == "app-password-secret"
    assert bundle["smtp_host"] == "smtp.acme-machining.de"


def test_one_primary_per_user_and_switch(email_client: TestClient, seeder: Seeder) -> None:
    org, user = _seed_member(seeder, slug="fechner-primary")
    with authed(email_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        first = _connect_smtp(email_client).json()
        second = _connect_smtp(
            email_client, {**SMTP_PAYLOAD, "from_address": "verkauf@acme-machining.de"}
        ).json()
        assert second["is_primary"] is False
        resp = email_client.put(f"/email-connections/{second['id']}/primary")
        assert resp.status_code == 200
        listed = email_client.get("/email-connections").json()
    primaries = [c for c in listed if c["is_primary"]]
    assert [c["id"] for c in primaries] == [second["id"]]
    assert first["id"] in [c["id"] for c in listed]


def test_connections_visible_to_owner_only(email_client: TestClient, seeder: Seeder) -> None:
    org, user = _seed_member(seeder, slug="fechner-vis")
    other = seeder.user("other@fechner-vis.example")
    seeder.membership(other, org, [MembershipRole.admin])
    with authed(email_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect_smtp(email_client).json()["id"]
    with authed(email_client, user_id=other, org_id=org, roles=[MembershipRole.admin]):
        assert email_client.get("/email-connections").json() == []
        # Nor deletable / switchable by another user.
        assert email_client.delete(f"/email-connections/{connection_id}").status_code == 404
        assert email_client.put(f"/email-connections/{connection_id}/primary").status_code == 404


def test_delete_disconnects(email_client: TestClient, seeder: Seeder) -> None:
    org, user = _seed_member(seeder, slug="fechner-del")
    with authed(email_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect_smtp(email_client).json()["id"]
        assert email_client.delete(f"/email-connections/{connection_id}").status_code == 204
        assert email_client.get("/email-connections").json() == []


def test_fails_closed_without_crypto_key(tenancy_db: str, seeder: Seeder) -> None:
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.email_credentials_key = ""  # unset → 503, never plaintext storage
    org, user = _seed_member(seeder, slug="fechner-nokey")
    with (
        TestClient(create_app(settings)) as client,
        authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]),
    ):
        resp = _connect_smtp(client)
    assert resp.status_code == 503
    assert resp.json()["code"] == "email_crypto_not_configured"


# --------------------------------------------------------------------------- #
# OAuth connect (Gmail wired; token exchange mocked — DECISIONS.md 2026-06-14)
# --------------------------------------------------------------------------- #
def test_oauth_start_returns_authorize_url_with_signed_state(
    email_client: TestClient, seeder: Seeder
) -> None:
    org, user = _seed_member(seeder, slug="fechner-oauth")
    with authed(email_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        resp = email_client.get("/email-connections/oauth/gmail/start")
    assert resp.status_code == 200
    url = resp.json()["authorize_url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "client_id=google-client-id" in url
    assert "gmail.send" in url
    assert "state=" in url


def test_oauth_start_not_configured(tenancy_db: str, seeder: Seeder) -> None:
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.email_credentials_key = KEY  # crypto fine — the CLIENT ID is missing
    org, user = _seed_member(seeder, slug="fechner-nooauth")
    with (
        TestClient(create_app(settings)) as client,
        authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]),
    ):
        resp = client.get("/email-connections/oauth/gmail/start")
    assert resp.status_code == 503
    assert resp.json()["code"] == "oauth_not_configured"


def test_oauth_callback_stores_encrypted_refresh_token(
    email_client: TestClient,
    seeder: Seeder,
    tenancy_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, user = _seed_member(seeder, slug="fechner-cb")

    async def fake_exchange(provider: Any, code: str, settings: Any) -> dict[str, Any]:
        assert code == "auth-code-123"
        return {
            "refresh_token": "1//refresh-secret",
            "email": "jan@gmail-connected.example",
            "name": "Jan F",
        }

    async def fake_baseline(connection_type: Any, credentials: dict[str, Any]) -> str | None:
        return "hist-1000"

    monkeypatch.setattr("app.email_connections._exchange_code", fake_exchange)
    monkeypatch.setattr("app.email_connections._initial_cursor", fake_baseline)

    with authed(email_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        state = email_client.get("/email-connections/oauth/gmail/start").json()["state"]
    resp = email_client.get(
        "/email-connections/oauth/gmail/callback",
        params={"code": "auth-code-123", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/settings/email" in resp.headers["location"]

    rows = _fetch_rows(
        tenancy_db,
        "SELECT connection_type, from_address, encrypted_credentials, gmail_history_id "
        "FROM user_email_connection WHERE org_id = :org AND user_id = :user",
        {"org": org, "user": user},
    )
    assert len(rows) == 1
    connection_type, from_address, blob, history_id = rows[0]
    assert connection_type == "gmail"
    assert from_address == "jan@gmail-connected.example"
    assert history_id == "hist-1000"  # baseline cursor: first sync starts at connect time
    assert decrypt_credentials(KEY, bytes(blob))["refresh_token"] == "1//refresh-secret"


def test_oauth_callback_rejects_tampered_state(email_client: TestClient) -> None:
    bogus = base64.urlsafe_b64encode(json.dumps({"user_id": str(uuid.uuid4())}).encode()).decode()
    resp = email_client.get(
        "/email-connections/oauth/gmail/callback",
        params={"code": "x", "state": bogus},
        follow_redirects=False,
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Test-send ("Test connection" button — spec settings page)
# --------------------------------------------------------------------------- #
def test_connection_test_sends_to_own_address(
    email_client: TestClient, seeder: Seeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, user = _seed_member(seeder, slug="fechner-test")
    sent: list[dict[str, Any]] = []

    class MockProvider:
        async def send(
            self, credentials: Any, *, from_address: str, from_name: Any, message: Any
        ) -> Any:
            from app.email_providers import SendResult

            sent.append({"from": from_address, "to": message.to, "subject": message.subject})
            return SendResult(message_id="<test@mock>", provider_thread_id=None)

    monkeypatch.setattr("app.email_connections.get_provider", lambda _t: MockProvider())

    with authed(email_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        connection_id = _connect_smtp(email_client).json()["id"]
        resp = email_client.post(f"/email-connections/{connection_id}/test")
    assert resp.status_code == 200
    assert sent == [
        {
            "from": "jan@acme-machining.de",
            "to": ["jan@acme-machining.de"],  # to the user's own address (spec)
            "subject": resp.json()["subject"],
        }
    ]
