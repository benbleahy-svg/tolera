"""Credentials-at-rest crypto for email connections (M3.5).

Spec ``#email-connectivity`` build notes: "Encrypt all refresh tokens with
AES-256-GCM, key from Infisical." The key reaches the app as the
``EMAIL_CREDENTIALS_KEY`` env setting (64 hex chars = 32 bytes); Infisical is
the delivery mechanism in production, not a runtime dependency. Fails closed:
no key (or a malformed one) refuses to encrypt OR decrypt, so a
misconfiguration can never persist credentials in the clear — the M3.3
fail-closed posture.

Blob layout: ``nonce (12 bytes) || AES-GCM ciphertext+tag``. The payload is the
JSON credential bundle — an OAuth refresh token (gmail/outlook) or the
SMTP/IMAP host/port/username/password bundle. Never logged (CLAUDE.md §5).
"""

from __future__ import annotations

import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import AppError

_NONCE_BYTES = 12
_KEY_BYTES = 32


class CredentialsKeyMissing(AppError):
    """The encryption key is unset or malformed — the feature is unavailable
    (503), never degraded to plaintext."""

    def __init__(self) -> None:
        super().__init__(
            "email_crypto_not_configured",
            "E-Mail-Verschlüsselung ist nicht konfiguriert.",
            status_code=503,
        )


def _key_bytes(key_hex: str) -> bytes:
    try:
        key = bytes.fromhex(key_hex or "")
    except ValueError as exc:
        raise CredentialsKeyMissing from exc
    if len(key) != _KEY_BYTES:
        raise CredentialsKeyMissing
    return key


def encrypt_credentials(key_hex: str, bundle: dict[str, Any]) -> bytes:
    """JSON-encode and seal the credential bundle (fresh nonce per call)."""
    key = _key_bytes(key_hex)
    nonce = os.urandom(_NONCE_BYTES)
    sealed = AESGCM(key).encrypt(nonce, json.dumps(bundle).encode(), None)
    return nonce + sealed


def decrypt_credentials(key_hex: str, blob: bytes) -> dict[str, Any]:
    """Open a sealed bundle; raises ``ValueError`` on tamper or wrong key."""
    key = _key_bytes(key_hex)
    if len(blob) <= _NONCE_BYTES:
        raise ValueError("ciphertext too short")
    try:
        plain = AESGCM(key).decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], None)
    except InvalidTag as exc:
        raise ValueError("credential blob failed authentication") from exc
    out = json.loads(plain)
    if not isinstance(out, dict):  # pragma: no cover — we only ever seal dicts
        raise ValueError("credential blob is not an object")
    return out
