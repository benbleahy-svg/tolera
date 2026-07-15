"""Email providers — send + incremental inbound sync (M3.5).

Spec ``#email-connectivity`` "Connection types (v1)":

* **Gmail** — send via ``users/me/messages/send`` (raw MIME), receive via
  ``history.list`` incremental from the stored ``historyId``.
* **Outlook / Microsoft 365** — send via Graph (draft → send, so the
  ``internetMessageId`` + ``conversationId`` are known), receive via
  ``messages/delta`` with a stored delta link.
* **Generic SMTP + IMAP** — ``smtplib`` over TLS out, ``imaplib`` UNSEEN poll
  in. The mailbox is opened READONLY: syncing must never mutate the user's
  own mailbox; idempotency comes from the Message-Id unique index instead.

Every provider speaks the same small contract (:class:`EmailProvider`), so the
send/sync layers — and the CI tests, which register a mock (build-plan M3.5:
"sends are mocked in CI") — never care which mailbox is behind a connection.
The outbound Message-ID is minted HERE (``make_msgid``) and placed in the MIME,
so threading never depends on a provider echoing headers back.

Credentials arrive as the decrypted bundle (``email_crypto``); this module
never logs them (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import email
import imaplib
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage as MimeMessage
from email.utils import make_msgid, parseaddr, parsedate_to_datetime
from typing import Any, Protocol

import httpx

from .errors import AppError
from .models import EmailConnectionType

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
GRAPH_API = "https://graph.microsoft.com/v1.0"


class ProviderError(AppError):
    """A provider call failed (auth revoked, API error). Message is safe to
    surface; details never include credentials."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=502)


# --------------------------------------------------------------------------- #
# The provider contract
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OutboundEmail:
    """One message to send from the user's own address."""

    to: list[str]
    subject: str
    body_text: str
    #: RFC 2822 threading headers for follow-ups on an existing thread.
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SendResult:
    message_id: str  #: the RFC 2822 Message-ID we minted into the MIME
    provider_thread_id: str | None  #: Gmail threadId / Outlook conversationId


@dataclass(frozen=True)
class InboundAttachment:
    filename: str
    content_type: str | None
    payload: bytes


@dataclass(frozen=True)
class InboundEmail:
    """One newly-synced message from the user's mailbox."""

    message_id: str
    in_reply_to: str | None
    references: list[str]
    provider_thread_id: str | None
    from_address: str
    to_addresses: list[str]
    subject: str
    body_text: str
    body_html: str | None
    sent_at: datetime | None
    attachments: list[InboundAttachment] = field(default_factory=list)


@dataclass(frozen=True)
class SyncResult:
    messages: list[InboundEmail]
    #: The next incremental cursor (historyId / delta link); ``None`` for IMAP,
    #: whose idempotency is the Message-Id unique index.
    cursor: str | None


class EmailProvider(Protocol):
    """What the send endpoint and the 5-minute sync task need from a mailbox."""

    async def send(
        self,
        credentials: dict[str, Any],
        *,
        from_address: str,
        from_name: str | None,
        message: OutboundEmail,
    ) -> SendResult: ...

    async def fetch_new(self, credentials: dict[str, Any], *, cursor: str | None) -> SyncResult: ...

    async def baseline_cursor(self, credentials: dict[str, Any]) -> str | None:
        """The cursor to store at connect time, so the first sync starts at
        "now" — never the mailbox's history (GDPR data-minimisation)."""
        ...


# --------------------------------------------------------------------------- #
# Shared MIME helpers
# --------------------------------------------------------------------------- #
def build_mime(
    *, from_address: str, from_name: str | None, message: OutboundEmail
) -> tuple[MimeMessage, str]:
    """The outbound RFC 5322 message + the Message-ID minted for it."""
    mime = MimeMessage()
    mime["From"] = f"{from_name} <{from_address}>" if from_name else from_address
    mime["To"] = ", ".join(message.to)
    mime["Subject"] = message.subject
    message_id = make_msgid(domain=from_address.partition("@")[2] or None)
    mime["Message-ID"] = message_id
    if message.in_reply_to:
        mime["In-Reply-To"] = message.in_reply_to
    if message.references:
        mime["References"] = " ".join(message.references)
    mime.set_content(message.body_text)
    return mime, message_id


def parse_inbound_mime(raw: bytes, *, provider_thread_id: str | None = None) -> InboundEmail:
    """Project a raw RFC 5322 message into the sync contract (Gmail ``raw``
    format and IMAP fetches share this path)."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    _, from_address = parseaddr(str(msg.get("From", "")))
    to_addresses = [addr for _, addr in (parseaddr(t) for t in str(msg.get("To", "")).split(","))]
    sent_at: datetime | None = None
    if msg.get("Date"):
        try:
            sent_at = parsedate_to_datetime(str(msg["Date"]))
        except ValueError:
            sent_at = None
        if sent_at is not None and sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=UTC)
    body_plain = msg.get_body(preferencelist=("plain",))
    body_html = msg.get_body(preferencelist=("html",))
    attachments: list[InboundAttachment] = []
    for part in msg.iter_attachments():
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        if not filename or not isinstance(payload, bytes):
            continue
        attachments.append(InboundAttachment(filename, part.get_content_type(), payload))
    return InboundEmail(
        message_id=(msg.get("Message-Id") or "").strip(),
        in_reply_to=(msg.get("In-Reply-To") or "").strip() or None,
        references=str(msg.get("References", "")).split(),
        provider_thread_id=provider_thread_id,
        from_address=from_address.lower(),
        to_addresses=[a.lower() for a in to_addresses if a],
        subject=str(msg.get("Subject", "")),
        body_text=str(body_plain.get_content()) if body_plain is not None else "",
        body_html=str(body_html.get_content()) if body_html is not None else None,
        sent_at=sent_at,
        attachments=attachments,
    )


async def _refresh_oauth_token(
    token_url: str, *, client_id: str, client_secret: str, refresh_token: str, scope: str | None
) -> str:
    """OAuth2 refresh-token grant → short-lived access token (never stored)."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        data["scope"] = scope
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(token_url, data=data)
    if resp.status_code != 200:
        # Token endpoint bodies can echo identifiers — log nothing from them.
        raise ProviderError("oauth_refresh_failed", "OAuth-Token konnte nicht erneuert werden.")
    token = resp.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise ProviderError("oauth_refresh_failed", "OAuth-Token konnte nicht erneuert werden.")
    return token


# --------------------------------------------------------------------------- #
# Gmail (Google OAuth2 — scopes gmail.send + gmail.readonly)
# --------------------------------------------------------------------------- #
class GmailProvider:
    """Gmail API: ``messages.send`` out, ``history.list`` (incremental from the
    stored ``historyId``) in — spec ``#email-connectivity`` v1 table."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    async def _access_token(self, credentials: dict[str, Any]) -> str:
        return await _refresh_oauth_token(
            GOOGLE_TOKEN_URL,
            client_id=self._client_id,
            client_secret=self._client_secret,
            refresh_token=str(credentials.get("refresh_token", "")),
            scope=None,
        )

    async def send(
        self,
        credentials: dict[str, Any],
        *,
        from_address: str,
        from_name: str | None,
        message: OutboundEmail,
    ) -> SendResult:
        mime, message_id = build_mime(
            from_address=from_address, from_name=from_name, message=message
        )
        token = await self._access_token(credentials)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GMAIL_API}/users/me/messages/send",
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": raw},
            )
        if resp.status_code not in (200, 202):
            raise ProviderError("gmail_send_failed", "Gmail-Versand fehlgeschlagen.")
        return SendResult(message_id=message_id, provider_thread_id=resp.json().get("threadId"))

    async def baseline_cursor(self, credentials: dict[str, Any]) -> str | None:
        token = await self._access_token(credentials)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GMAIL_API}/users/me/profile", headers={"Authorization": f"Bearer {token}"}
            )
        if resp.status_code != 200:
            raise ProviderError("gmail_profile_failed", "Gmail-Profil nicht lesbar.")
        history_id = resp.json().get("historyId")
        return str(history_id) if history_id is not None else None

    async def fetch_new(self, credentials: dict[str, Any], *, cursor: str | None) -> SyncResult:
        token = await self._access_token(credentials)
        headers = {"Authorization": f"Bearer {token}"}
        if not cursor:
            # No cursor stored (legacy row / cleared) — re-baseline, sync next poll.
            return SyncResult([], await self.baseline_cursor(credentials))
        message_ids: list[str] = []
        latest_cursor = cursor
        page_token: str | None = None
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params: dict[str, str] = {
                    "startHistoryId": cursor,
                    "historyTypes": "messageAdded",
                }
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(
                    f"{GMAIL_API}/users/me/history", headers=headers, params=params
                )
                if resp.status_code == 404:
                    # historyId expired (Gmail keeps ~a week) — re-baseline and
                    # resume next poll rather than crash-looping.
                    return SyncResult([], await self.baseline_cursor(credentials))
                if resp.status_code != 200:
                    raise ProviderError("gmail_sync_failed", "Gmail-Abgleich fehlgeschlagen.")
                data = resp.json()
                latest_cursor = str(data.get("historyId", latest_cursor))
                for entry in data.get("history", []):
                    for added in entry.get("messagesAdded", []):
                        msg = added.get("message", {})
                        if msg.get("id"):
                            message_ids.append(str(msg["id"]))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            messages: list[InboundEmail] = []
            for mid in message_ids:
                resp = await client.get(
                    f"{GMAIL_API}/users/me/messages/{mid}",
                    headers=headers,
                    params={"format": "raw"},
                )
                if resp.status_code != 200:
                    continue  # deleted between listing and fetch — skip
                data = resp.json()
                raw = base64.urlsafe_b64decode(str(data.get("raw", "")))
                messages.append(parse_inbound_mime(raw, provider_thread_id=data.get("threadId")))
        return SyncResult(messages, latest_cursor)


# --------------------------------------------------------------------------- #
# Outlook / Microsoft 365 (Graph — scopes Mail.Send + Mail.ReadWrite)
# --------------------------------------------------------------------------- #
class OutlookProvider:
    """Microsoft Graph: draft → send (so ``internetMessageId`` and
    ``conversationId`` are known), ``messages/delta`` in."""

    def __init__(self, client_id: str, client_secret: str, tenant: str = "common") -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    async def _access_token(self, credentials: dict[str, Any]) -> str:
        return await _refresh_oauth_token(
            self._token_url,
            client_id=self._client_id,
            client_secret=self._client_secret,
            refresh_token=str(credentials.get("refresh_token", "")),
            scope="https://graph.microsoft.com/.default offline_access",
        )

    async def send(
        self,
        credentials: dict[str, Any],
        *,
        from_address: str,
        from_name: str | None,
        message: OutboundEmail,
    ) -> SendResult:
        token = await self._access_token(credentials)
        headers = {"Authorization": f"Bearer {token}"}
        draft: dict[str, Any] = {
            "subject": message.subject,
            "body": {"contentType": "Text", "content": message.body_text},
            "toRecipients": [{"emailAddress": {"address": to}} for to in message.to],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{GRAPH_API}/me/messages", headers=headers, json=draft)
            if resp.status_code != 201:
                raise ProviderError("outlook_send_failed", "Outlook-Versand fehlgeschlagen.")
            created = resp.json()
            send_resp = await client.post(
                f"{GRAPH_API}/me/messages/{created['id']}/send", headers=headers
            )
            if send_resp.status_code != 202:
                raise ProviderError("outlook_send_failed", "Outlook-Versand fehlgeschlagen.")
        return SendResult(
            message_id=str(created.get("internetMessageId", "")),
            provider_thread_id=created.get("conversationId"),
        )

    async def baseline_cursor(self, credentials: dict[str, Any]) -> str | None:
        # Walk the delta to its end once; the returned deltaLink means
        # "everything after connect time".
        result = await self._delta(
            credentials, f"{GRAPH_API}/me/mailFolders/inbox/messages/delta", collect=False
        )
        return result.cursor

    async def fetch_new(self, credentials: dict[str, Any], *, cursor: str | None) -> SyncResult:
        if not cursor:
            return SyncResult([], await self.baseline_cursor(credentials))
        return await self._delta(credentials, cursor, collect=True)

    async def _delta(self, credentials: dict[str, Any], url: str, *, collect: bool) -> SyncResult:
        token = await self._access_token(credentials)
        headers = {"Authorization": f"Bearer {token}"}
        messages: list[InboundEmail] = []
        async with httpx.AsyncClient(timeout=30) as client:
            next_url: str | None = url
            delta_link: str | None = None
            while next_url:
                resp = await client.get(next_url, headers=headers)
                if resp.status_code == 410:
                    # Delta token expired — Graph's resync signal: re-baseline.
                    return SyncResult(
                        [], (await self.baseline_cursor(credentials)) if collect else None
                    )
                if resp.status_code != 200:
                    raise ProviderError("outlook_sync_failed", "Outlook-Abgleich fehlgeschlagen.")
                data = resp.json()
                if collect:
                    for item in data.get("value", []):
                        messages.append(await self._to_inbound(client, headers, item))
                next_url = data.get("@odata.nextLink")
                delta_link = data.get("@odata.deltaLink", delta_link)
        return SyncResult(messages, delta_link)

    async def _to_inbound(
        self, client: httpx.AsyncClient, headers: dict[str, str], item: dict[str, Any]
    ) -> InboundEmail:
        sent_at: datetime | None = None
        if item.get("receivedDateTime"):
            try:
                raw_ts = str(item["receivedDateTime"]).replace("Z", "+00:00")
                sent_at = datetime.fromisoformat(raw_ts)
            except ValueError:
                sent_at = None
        body = item.get("body") or {}
        attachments: list[InboundAttachment] = []
        if item.get("hasAttachments") and item.get("id"):
            resp = await client.get(
                f"{GRAPH_API}/me/messages/{item['id']}/attachments", headers=headers
            )
            if resp.status_code == 200:
                for att in resp.json().get("value", []):
                    content = att.get("contentBytes")
                    if att.get("name") and isinstance(content, str):
                        attachments.append(
                            InboundAttachment(
                                str(att["name"]),
                                att.get("contentType"),
                                base64.b64decode(content),
                            )
                        )
        return InboundEmail(
            message_id=str(item.get("internetMessageId", "")),
            in_reply_to=None,  # Graph doesn't expose it; conversationId matches instead
            references=[],
            provider_thread_id=item.get("conversationId"),
            from_address=str(
                ((item.get("from") or {}).get("emailAddress") or {}).get("address", "")
            ).lower(),
            to_addresses=[
                str((r.get("emailAddress") or {}).get("address", "")).lower()
                for r in item.get("toRecipients", [])
            ],
            subject=str(item.get("subject", "")),
            body_text=str(body.get("content", "")) if body.get("contentType") == "text" else "",
            body_html=str(body.get("content", "")) if body.get("contentType") == "html" else None,
            sent_at=sent_at,
            attachments=attachments,
        )


# --------------------------------------------------------------------------- #
# Generic SMTP + IMAP (app passwords; credentials encrypted at rest)
# --------------------------------------------------------------------------- #
class SmtpImapProvider:
    """SMTP with TLS out; IMAP UNSEEN poll in (spec v1 table). Blocking stdlib
    clients run in a worker thread. The IMAP mailbox is opened READONLY so the
    sync never flags the user's own mail; the Message-Id unique index makes
    re-reads idempotent."""

    async def send(
        self,
        credentials: dict[str, Any],
        *,
        from_address: str,
        from_name: str | None,
        message: OutboundEmail,
    ) -> SendResult:
        mime, message_id = build_mime(
            from_address=from_address, from_name=from_name, message=message
        )

        def _send() -> None:
            host = str(credentials.get("smtp_host", ""))
            port = int(credentials.get("smtp_port", 587))
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                # Explicit verified context: the stdlib default here skips
                # certificate/hostname checks (fresh-eyes review 🔴2) — an
                # on-path attacker must never harvest the mailbox password.
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(
                    str(credentials.get("username", "")), str(credentials.get("password", ""))
                )
                smtp.send_message(mime, from_addr=from_address, to_addrs=message.to)

        try:
            await asyncio.to_thread(_send)
        except (smtplib.SMTPException, OSError) as exc:
            raise ProviderError("smtp_send_failed", "SMTP-Versand fehlgeschlagen.") from exc
        return SendResult(message_id=message_id, provider_thread_id=None)

    async def baseline_cursor(self, credentials: dict[str, Any]) -> str | None:
        return None  # IMAP has no cursor; UNSEEN + Message-Id dedupe carry idempotency

    async def fetch_new(self, credentials: dict[str, Any], *, cursor: str | None) -> SyncResult:
        def _fetch() -> list[bytes]:
            host = str(credentials.get("imap_host", ""))
            port = int(credentials.get("imap_port", 993))
            raws: list[bytes] = []
            imap = imaplib.IMAP4_SSL(
                host, port, timeout=30, ssl_context=ssl.create_default_context()
            )
            try:
                imap.login(
                    str(credentials.get("username", "")), str(credentials.get("password", ""))
                )
                imap.select("INBOX", readonly=True)  # never mutate the user's mailbox
                status_, data = imap.search(None, "UNSEEN")
                if status_ != "OK":
                    return raws
                for num in data[0].split():
                    status_, msg_data = imap.fetch(num, "(RFC822)")
                    if status_ == "OK" and msg_data and isinstance(msg_data[0], tuple):
                        raws.append(msg_data[0][1])
            finally:
                with contextlib.suppress(OSError):  # best-effort close
                    imap.logout()
            return raws

        try:
            raws = await asyncio.to_thread(_fetch)
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ProviderError("imap_sync_failed", "IMAP-Abgleich fehlgeschlagen.") from exc
        return SyncResult([parse_inbound_mime(raw) for raw in raws], None)


# --------------------------------------------------------------------------- #
# Registry — the seam the send/sync layers resolve through (tests swap it)
# --------------------------------------------------------------------------- #
def get_provider(connection_type: EmailConnectionType) -> EmailProvider:
    """Provider for a connection, built from app settings on each call (cheap:
    providers hold two strings). Tests monkeypatch THIS function."""
    from .config import get_settings

    settings = get_settings()
    if connection_type is EmailConnectionType.gmail:
        return GmailProvider(settings.google_oauth_client_id, settings.google_oauth_client_secret)
    if connection_type is EmailConnectionType.outlook:
        return OutlookProvider(
            settings.ms_oauth_client_id,
            settings.ms_oauth_client_secret,
            settings.ms_oauth_tenant,
        )
    return SmtpImapProvider()
