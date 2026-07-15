"""M3.5 — credentials-at-rest crypto (spec #email-connectivity build notes).

AES-256-GCM over the JSON credential bundle; the key is a 64-hex-char (32-byte)
env-injected secret (Infisical delivers it as env in prod). Fails closed when
unset — a connection must never be persisted in the clear.
"""

from __future__ import annotations

import pytest

from app.email_crypto import (
    CredentialsKeyMissing,
    decrypt_credentials,
    encrypt_credentials,
)

KEY = "0f" * 32  # 32 bytes hex — deterministic test key


def test_round_trip() -> None:
    bundle = {"refresh_token": "1//abc-secret", "provider": "gmail"}
    blob = encrypt_credentials(KEY, bundle)
    assert isinstance(blob, bytes)
    assert b"1//abc-secret" not in blob  # ciphertext, not plaintext-in-a-coat
    assert decrypt_credentials(KEY, blob) == bundle


def test_fresh_nonce_per_call() -> None:
    bundle = {"password": "p"}
    assert encrypt_credentials(KEY, bundle) != encrypt_credentials(KEY, bundle)


def test_tamper_detected() -> None:
    blob = bytearray(encrypt_credentials(KEY, {"password": "p"}))
    blob[-1] ^= 0x01
    with pytest.raises(ValueError):
        decrypt_credentials(KEY, bytes(blob))


def test_wrong_key_rejected() -> None:
    blob = encrypt_credentials(KEY, {"password": "p"})
    with pytest.raises(ValueError):
        decrypt_credentials("ab" * 32, blob)


@pytest.mark.parametrize("bad", ["", "zz" * 32, "0f" * 16])
def test_missing_or_malformed_key_fails_closed(bad: str) -> None:
    with pytest.raises(CredentialsKeyMissing):
        encrypt_credentials(bad, {"password": "p"})
    with pytest.raises(CredentialsKeyMissing):
        decrypt_credentials(bad, b"\x00" * 32)
