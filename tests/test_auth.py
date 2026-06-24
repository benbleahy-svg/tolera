"""Unit tests for the Clerk session-JWT path in ``app.auth``.

The cross-org/role gates in ``test_tenancy`` override ``get_principal``; these
tests exercise the *real* verification logic with locally-minted RS256 tokens,
stubbing only the JWKS fetch (the network seam) with a known public key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import CLAIM_ORG_ID, CLAIM_ROLES, CLAIM_USER_ID, get_principal
from app.config import Settings
from app.errors import AppError

ISSUER = "https://clerk.example/issuer"
JWKS_URL = "https://clerk.example/.well-known/jwks.json"


def _settings(**overrides: Any) -> Settings:
    base = {
        "environment": "test",
        "clerk_jwks_url": JWKS_URL,
        "clerk_jwt_issuer": ISSUER,
    }
    return Settings(**{**base, **overrides})


def _mint(key: rsa.RSAPrivateKey, claims: dict[str, Any], *, issuer: str = ISSUER) -> str:
    payload = {"iss": issuer, "exp": datetime.now(UTC) + timedelta(hours=1), **claims}
    return jwt.encode(payload, key, algorithm="RS256")


def _request(settings: Settings, token: str | None = None) -> Any:
    headers = {"authorization": f"Bearer {token}"} if token else {}
    state = SimpleNamespace(settings=settings)
    return SimpleNamespace(headers=headers, app=SimpleNamespace(state=state))


def _patch_jwks(monkeypatch: pytest.MonkeyPatch, public_key: Any) -> None:
    class _FakeClient:
        def __init__(self, _url: str, **_kwargs: Any) -> None: ...  # accepts timeout=

        def get_signing_key_from_jwt(self, _token: str) -> Any:
            return SimpleNamespace(key=public_key)

    # auth.py does ``import jwt``; patching the module reaches its call site.
    monkeypatch.setattr(jwt, "PyJWKClient", _FakeClient)


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


async def test_valid_token_resolves_principal(
    monkeypatch: pytest.MonkeyPatch, signing_key: rsa.RSAPrivateKey
) -> None:
    _patch_jwks(monkeypatch, signing_key.public_key())
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    token = _mint(
        signing_key,
        {
            CLAIM_USER_ID: str(user_id),
            CLAIM_ORG_ID: str(org_id),
            CLAIM_ROLES: ["admin", "estimator", "bogus"],
        },
    )

    principal = await get_principal(_request(_settings(), token))

    assert principal.user_id == user_id
    assert principal.active_org_id == org_id
    # Unknown role strings are dropped; known ones are kept.
    assert [r.value for r in principal.roles] == ["admin", "estimator"]


async def test_missing_bearer_is_rejected() -> None:
    with pytest.raises(AppError) as exc:
        await get_principal(_request(_settings(), token=None))
    assert exc.value.status_code == 401


async def test_unconfigured_clerk_is_rejected(signing_key: rsa.RSAPrivateKey) -> None:
    token = _mint(signing_key, {CLAIM_USER_ID: str(uuid.uuid4())})
    settings = _settings(clerk_jwks_url="", clerk_jwt_issuer="")
    with pytest.raises(AppError) as exc:
        await get_principal(_request(settings, token))
    assert exc.value.status_code == 401


async def test_bad_signature_is_rejected(
    monkeypatch: pytest.MonkeyPatch, signing_key: rsa.RSAPrivateKey
) -> None:
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _patch_jwks(monkeypatch, other_key.public_key())  # wrong key → signature fails
    token = _mint(signing_key, {CLAIM_USER_ID: str(uuid.uuid4()), CLAIM_ORG_ID: str(uuid.uuid4())})
    with pytest.raises(AppError) as exc:
        await get_principal(_request(_settings(), token))
    assert exc.value.status_code == 401


async def test_missing_identity_claims_are_rejected(
    monkeypatch: pytest.MonkeyPatch, signing_key: rsa.RSAPrivateKey
) -> None:
    _patch_jwks(monkeypatch, signing_key.public_key())
    token = _mint(signing_key, {CLAIM_ROLES: ["admin"]})  # no user/org id
    with pytest.raises(AppError) as exc:
        await get_principal(_request(_settings(), token))
    assert exc.value.status_code == 401


async def test_token_without_a_known_role_is_rejected(
    monkeypatch: pytest.MonkeyPatch, signing_key: rsa.RSAPrivateKey
) -> None:
    _patch_jwks(monkeypatch, signing_key.public_key())
    token = _mint(
        signing_key,
        {CLAIM_USER_ID: str(uuid.uuid4()), CLAIM_ORG_ID: str(uuid.uuid4()), CLAIM_ROLES: ["bogus"]},
    )
    with pytest.raises(AppError) as exc:
        await get_principal(_request(_settings(), token))
    assert exc.value.status_code == 401
