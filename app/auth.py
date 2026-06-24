"""Authentication: resolve the caller into a :class:`Principal`.

The wire format is a Clerk session JWT (RS256, verified against Clerk's JWKS —
DECISIONS.md "Login type / auth flow"). Clerk's native Organizations carry the
active org, and our webhook sync stamps our *internal* ids + roles into the
session-token template as the ``tolera_*`` claims this module reads (DECISIONS.md
2026-06-24 "Org identity model"). Roles in the token are a synced cache; the
``user_org_membership`` table remains authoritative (written in M5.12).

``get_principal`` is a FastAPI dependency, so tests inject a principal via
``app.dependency_overrides`` and never touch Clerk — the cross-org/role gates
exercise the *tenancy* boundary, not the IdP.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import anyio
import jwt
from fastapi import Request, status

from .config import Settings
from .errors import AppError
from .models import MembershipRole

# Custom claims emitted by the Clerk JWT template (fed by webhook sync).
CLAIM_USER_ID = "tolera_user_id"
CLAIM_ORG_ID = "tolera_org_id"
CLAIM_ROLES = "tolera_roles"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, resolved to internal ids within their active org."""

    user_id: uuid.UUID
    active_org_id: uuid.UUID
    roles: tuple[MembershipRole, ...]


def _unauthorized(message: str = "Authentication required") -> AppError:
    return AppError("unauthorized", message, status_code=status.HTTP_401_UNAUTHORIZED)


def _bearer_token(request: Request) -> str:
    """Extract the bearer token, or raise 401."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    return token


def _verify_clerk_jwt(token: str, settings: Settings) -> dict[str, object]:
    """Verify a Clerk session JWT against the configured JWKS, or raise 401.

    ``verify_aud=False`` is intentional: Clerk session tokens are audience-less.
    The authorized-party (``azp``) claim is the equivalent guard and is enforced
    when ``clerk_authorized_parties`` is configured. The JWKS fetch is bounded by
    a timeout so a slow/unreachable Clerk can't hang the request indefinitely.
    """
    if not settings.clerk_jwks_url or not settings.clerk_jwt_issuer:
        # No IdP configured: there is no way to authenticate a real request.
        raise _unauthorized("Authentication is not configured")
    try:
        client = jwt.PyJWKClient(settings.clerk_jwks_url, timeout=5)
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_jwt_issuer,
            options={"verify_aud": False, "require": ["exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid session token") from exc

    allowed_parties = settings.clerk_authorized_party_set
    if allowed_parties and claims.get("azp") not in allowed_parties:
        raise _unauthorized("Session token from an unrecognised party")
    return claims


def _parse_uuid_claim(claims: dict[str, object], key: str) -> uuid.UUID:
    raw = claims.get(key)
    if not isinstance(raw, str):
        raise _unauthorized("Session token missing identity claims")
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise _unauthorized("Session token has malformed identity claims") from exc


def _parse_roles_claim(claims: dict[str, object]) -> tuple[MembershipRole, ...]:
    raw = claims.get(CLAIM_ROLES)
    values = raw if isinstance(raw, list) else []
    roles = tuple(MembershipRole(v) for v in values if v in MembershipRole.__members__.values())
    if not roles:
        raise _unauthorized("Session token carries no org role")
    return roles


async def get_principal(request: Request) -> Principal:
    """Resolve the caller from their Clerk session JWT. Overridden in tests."""
    settings: Settings = request.app.state.settings
    token = _bearer_token(request)
    # JWKS resolution + decode can do blocking network I/O; keep it off the loop.
    claims = await anyio.to_thread.run_sync(_verify_clerk_jwt, token, settings)
    return Principal(
        user_id=_parse_uuid_claim(claims, CLAIM_USER_ID),
        active_org_id=_parse_uuid_claim(claims, CLAIM_ORG_ID),
        roles=_parse_roles_claim(claims),
    )
