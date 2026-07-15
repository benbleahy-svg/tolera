"""User email connections — settings-page API (M3.5, spec #email-connectivity).

Settings → User Profile → Email Connection: one-click Gmail / Outlook OAuth,
a manual SMTP/IMAP form, current status, and a "Test connection" button that
sends to the user's own address. Connections are per (org, user) and
self-service — every route operates on the caller's OWN rows only; there is no
cross-user management surface.

Credentials (OAuth refresh token / SMTP+IMAP bundle) are sealed with
AES-256-GCM (``email_crypto``) before they touch the database and are NEVER
serialized into a response or a log line (CLAUDE.md §5).

The OAuth dance: ``…/oauth/{provider}/start`` (authenticated) returns the
provider's authorize URL carrying an encrypted ``state`` that binds
(user, org, provider, expiry). The browser lands back on
``…/oauth/{provider}/callback`` WITHOUT a session (it's a top-level redirect
from Google/Microsoft), so the state token IS the authentication — sealed with
the same AES-GCM key, 10-minute expiry, single audience. Gmail ships behind
Google's pending-verification warning (DECISIONS.md 2026-06-14).
"""

from __future__ import annotations

import base64
import binascii
import time
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, cast
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .accounts import _normalize_email
from .auth import Principal, get_principal
from .config import Settings
from .db import org_scoped_session
from .deps import get_app_settings, get_session
from .email_crypto import decrypt_credentials, encrypt_credentials
from .email_providers import OutboundEmail, get_provider
from .errors import AppError
from .models import EmailConnectionType, UserEmailConnection

router = APIRouter(prefix="/email-connections", tags=["email-connections"])

STATE_TTL_SECONDS = 600

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"
)
MS_SCOPES = "offline_access https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Mail.ReadWrite"

OAuthProvider = Literal["gmail", "outlook"]


class EmailConnectionOut(BaseModel):
    """A connection as shown on the settings page — status only, no secrets."""

    id: uuid.UUID
    connection_type: EmailConnectionType
    from_address: str
    from_name: str | None
    is_primary: bool
    last_synced_at: datetime | None
    last_sync_error: str | None
    created_at: datetime


class SmtpConnectionIn(BaseModel):
    """The manual SMTP/IMAP form (spec settings page)."""

    from_address: str = Field(max_length=320)
    from_name: str | None = Field(default=None, max_length=200)
    smtp_host: str = Field(min_length=1, max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    imap_host: str = Field(min_length=1, max_length=253)
    imap_port: int = Field(default=993, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("from_address")
    @classmethod
    def _norm_from_address(cls, value: str) -> str:
        return _normalize_email(value)


def _out(row: UserEmailConnection) -> EmailConnectionOut:
    return EmailConnectionOut(
        id=row.id,
        connection_type=row.connection_type,
        from_address=row.from_address,
        from_name=row.from_name,
        is_primary=row.is_primary,
        last_synced_at=row.last_synced_at,
        last_sync_error=row.last_sync_error,
        created_at=row.created_at,
    )


async def _own_connection(
    session: AsyncSession, principal: Principal, connection_id: uuid.UUID
) -> UserEmailConnection:
    """The caller's own connection or 404 — another user's row is invisible,
    not forbidden (no existence oracle)."""
    row = await session.scalar(
        select(UserEmailConnection).where(
            UserEmailConnection.id == connection_id,
            UserEmailConnection.user_id == principal.user_id,
        )
    )
    if row is None:
        raise AppError(
            "connection_not_found",
            "E-Mail-Verbindung nicht gefunden.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row


async def _has_any_connection(session: AsyncSession, principal: Principal) -> bool:
    existing = await session.scalar(
        select(UserEmailConnection.id)
        .where(UserEmailConnection.user_id == principal.user_id)
        .limit(1)
    )
    return existing is not None


# --------------------------------------------------------------------------- #
# CRUD + primary + test
# --------------------------------------------------------------------------- #
@router.get("")
async def list_connections(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> list[EmailConnectionOut]:
    rows = await session.scalars(
        select(UserEmailConnection)
        .where(UserEmailConnection.user_id == principal.user_id)
        .order_by(UserEmailConnection.created_at)
    )
    return [_out(row) for row in rows]


@router.post("/smtp", status_code=status.HTTP_201_CREATED)
async def connect_smtp(
    payload: SmtpConnectionIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> EmailConnectionOut:
    bundle = {
        "smtp_host": payload.smtp_host,
        "smtp_port": payload.smtp_port,
        "imap_host": payload.imap_host,
        "imap_port": payload.imap_port,
        "username": payload.username,
        "password": payload.password,
    }
    row = UserEmailConnection(
        org_id=principal.active_org_id,
        user_id=principal.user_id,
        connection_type=EmailConnectionType.smtp_imap,
        from_address=payload.from_address,
        from_name=payload.from_name,
        encrypted_credentials=encrypt_credentials(settings.email_credentials_key, bundle),
        is_primary=not await _has_any_connection(session, principal),
    )
    session.add(row)
    await session.flush()
    return _out(row)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    connection_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> None:
    row = await _own_connection(session, principal, connection_id)
    await session.delete(row)
    await session.flush()


@router.put("/{connection_id}/primary")
async def set_primary(
    connection_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> EmailConnectionOut:
    row = await _own_connection(session, principal, connection_id)
    # Clear-then-set inside one transaction; the partial unique index
    # (uq_email_connection_primary) backstops any race.
    await session.execute(
        update(UserEmailConnection)
        .where(UserEmailConnection.user_id == principal.user_id, UserEmailConnection.is_primary)
        .values(is_primary=False)
    )
    row.is_primary = True
    await session.flush()
    return _out(row)


class TestSendOut(BaseModel):
    status: str
    subject: str


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> TestSendOut:
    """The settings page's "Test connection" — sends to the user's OWN address
    (spec #email-connectivity), so a typo'd credential can't spam a customer."""
    row = await _own_connection(session, principal, connection_id)
    credentials = decrypt_credentials(settings.email_credentials_key, row.encrypted_credentials)
    subject = "Tolera Testnachricht — E-Mail-Verbindung aktiv"
    await get_provider(row.connection_type).send(
        credentials,
        from_address=row.from_address,
        from_name=row.from_name,
        message=OutboundEmail(
            to=[row.from_address],
            subject=subject,
            body_text=(
                "Diese Testnachricht bestätigt, dass Ihre E-Mail-Verbindung "
                "korrekt eingerichtet ist."
            ),
        ),
    )
    return TestSendOut(status="sent", subject=subject)


# --------------------------------------------------------------------------- #
# OAuth (Gmail / Outlook)
# --------------------------------------------------------------------------- #
def _oauth_config(provider: OAuthProvider, settings: Settings) -> tuple[str, str]:
    client_id, client_secret = (
        (settings.google_oauth_client_id, settings.google_oauth_client_secret)
        if provider == "gmail"
        else (settings.ms_oauth_client_id, settings.ms_oauth_client_secret)
    )
    if not client_id or not client_secret:
        raise AppError(
            "oauth_not_configured",
            "OAuth ist für diesen Anbieter nicht konfiguriert.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return client_id, client_secret


def _redirect_uri(provider: OAuthProvider, settings: Settings) -> str:
    return f"{settings.api_base_url}/email-connections/oauth/{provider}/callback"


def _seal_state(settings: Settings, principal: Principal, provider: OAuthProvider) -> str:
    payload = {
        "user_id": str(principal.user_id),
        "org_id": str(principal.active_org_id),
        "provider": provider,
        "exp": time.time() + STATE_TTL_SECONDS,
    }
    blob = encrypt_credentials(settings.email_credentials_key, payload)
    return base64.urlsafe_b64encode(blob).decode()


def _open_state(settings: Settings, state: str, provider: OAuthProvider) -> dict[str, Any]:
    try:
        payload = decrypt_credentials(
            settings.email_credentials_key, base64.urlsafe_b64decode(state.encode())
        )
    except (ValueError, binascii.Error) as exc:
        raise AppError(
            "invalid_oauth_state",
            "Ungültiger oder abgelaufener OAuth-Status.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if payload.get("provider") != provider or float(payload.get("exp", 0)) < time.time():
        raise AppError(
            "invalid_oauth_state",
            "Ungültiger oder abgelaufener OAuth-Status.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return payload


class OAuthStartOut(BaseModel):
    authorize_url: str
    state: str


@router.get("/oauth/{provider}/start")
async def oauth_start(
    provider: OAuthProvider,
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> OAuthStartOut:
    client_id, _ = _oauth_config(provider, settings)
    state = _seal_state(settings, principal, provider)
    if provider == "gmail":
        params = {
            "client_id": client_id,
            "redirect_uri": _redirect_uri(provider, settings),
            "response_type": "code",
            "scope": GOOGLE_SCOPES,
            "access_type": "offline",  # refresh token
            "prompt": "consent",  # re-consent re-issues the refresh token
            "state": state,
        }
        url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    else:
        params = {
            "client_id": client_id,
            "redirect_uri": _redirect_uri(provider, settings),
            "response_type": "code",
            "scope": MS_SCOPES,
            "response_mode": "query",
            "state": state,
        }
        url = (
            f"https://login.microsoftonline.com/{settings.ms_oauth_tenant}"
            f"/oauth2/v2.0/authorize?{urlencode(params)}"
        )
    return OAuthStartOut(authorize_url=url, state=state)


async def _exchange_code(provider: OAuthProvider, code: str, settings: Settings) -> dict[str, Any]:
    """Authorization code → {refresh_token, email, name}. Live network call —
    tests monkeypatch this seam."""
    client_id, client_secret = _oauth_config(provider, settings)
    redirect_uri = _redirect_uri(provider, settings)
    if provider == "gmail":
        token_url = GOOGLE_TOKEN_URL
        profile_url = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
    else:
        token_url = (
            f"https://login.microsoftonline.com/{settings.ms_oauth_tenant}/oauth2/v2.0/token"
        )
        profile_url = "https://graph.microsoft.com/v1.0/me"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
        )
        if resp.status_code != 200:
            raise AppError(
                "oauth_exchange_failed",
                "OAuth-Autorisierung fehlgeschlagen.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        tokens = resp.json()
        refresh_token = tokens.get("refresh_token")
        access_token = tokens.get("access_token")
        if not refresh_token or not access_token:
            raise AppError(
                "oauth_exchange_failed",
                "OAuth-Autorisierung lieferte kein Refresh-Token.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        prof = await client.get(profile_url, headers={"Authorization": f"Bearer {access_token}"})
        profile = prof.json() if prof.status_code == 200 else {}
    email_addr = profile.get("emailAddress") or profile.get("mail") or ""
    name = profile.get("displayName")
    return {"refresh_token": refresh_token, "email": str(email_addr).lower(), "name": name}


async def _initial_cursor(
    connection_type: EmailConnectionType, credentials: dict[str, Any]
) -> str | None:
    """Baseline the sync cursor at connect time so the first poll starts at
    "now" — never the mailbox history (GDPR data-minimisation)."""
    return await get_provider(connection_type).baseline_cursor(credentials)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: OAuthProvider,
    code: str,
    state: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RedirectResponse:
    """The browser lands here from Google/Microsoft — no session, so the sealed
    ``state`` is the authentication (10-min expiry). On success: encrypted
    connection row + redirect to the settings page."""
    payload = _open_state(settings, state, provider)
    user_id = uuid.UUID(str(payload["user_id"]))
    org_id = uuid.UUID(str(payload["org_id"]))
    exchanged = await _exchange_code(provider, code, settings)
    if not exchanged.get("email"):
        raise AppError(
            "oauth_exchange_failed",
            "Die verbundene E-Mail-Adresse konnte nicht ermittelt werden.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    connection_type = (
        EmailConnectionType.gmail if provider == "gmail" else EmailConnectionType.outlook
    )
    credentials = {"refresh_token": exchanged["refresh_token"]}
    cursor = await _initial_cursor(connection_type, credentials)

    sessionmaker = cast("async_sessionmaker[AsyncSession]", request.app.state.sessionmaker)
    async with org_scoped_session(sessionmaker, org_id) as session:
        existing = await session.scalar(
            select(UserEmailConnection.id).where(UserEmailConnection.user_id == user_id).limit(1)
        )
        row = UserEmailConnection(
            org_id=org_id,
            user_id=user_id,
            connection_type=connection_type,
            from_address=exchanged["email"],
            from_name=exchanged.get("name"),
            encrypted_credentials=encrypt_credentials(settings.email_credentials_key, credentials),
            is_primary=existing is None,
            gmail_history_id=cursor if connection_type is EmailConnectionType.gmail else None,
            outlook_delta_link=(cursor if connection_type is EmailConnectionType.outlook else None),
        )
        session.add(row)
        await session.flush()
    return RedirectResponse(
        f"{settings.app_base_url}/settings/email?connected={provider}",
        status_code=status.HTTP_302_FOUND,
    )
