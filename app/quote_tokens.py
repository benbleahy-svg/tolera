"""Quote tokens — mint + verify the Digital Quote buyer-portal credential (M5.1).

Spec ``#digitalquote``: the buyer opens ``/q/:token`` with no login. The token is
a **signed JWT** (HS256, the app both mints and verifies) whose ``exp`` claim is
**deliberately omitted** — expiry is a *soft* application-layer property (a passed
``expiration_date`` shows an EXPIRED badge but the portal stays reachable), so the
credential itself must never hard-expire.

The signature is the whole bearer secret; the persisted :class:`~app.models.QuoteToken`
row is the authority for **revocation** (which a stateless JWT cannot express). The
signed ``org`` claim is what lets the public endpoint open the org-scoped RLS session
*before* any DB read — an attacker cannot forge a token for an arbitrary org without
the HMAC secret.

This module is pure crypto + a thin persistence helper; the request handler lives in
:mod:`app.buyer_portal`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Quote, QuoteToken, QuoteTokenScope

_ALGORITHM = "HS256"


class InvalidToken(Exception):
    """The token string is malformed, wrongly signed, or missing required claims."""


@dataclass(frozen=True)
class TokenClaims:
    """The verified, parsed payload of a buyer-portal JWT."""

    token_id: uuid.UUID
    org_id: uuid.UUID
    quote_id: uuid.UUID
    scope: QuoteTokenScope


def mint_jwt(
    secret: str,
    *,
    token_id: uuid.UUID,
    org_id: uuid.UUID,
    quote_id: uuid.UUID,
    scope: QuoteTokenScope,
) -> str:
    """Sign a buyer-portal JWT. **No ``exp`` claim** (soft app-layer expiry)."""
    payload = {
        "jti": str(token_id),
        "org": str(org_id),
        "quote": str(quote_id),
        "scope": scope.value,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_jwt(secret: str, token: str) -> TokenClaims:
    """Verify the signature and parse the claims, or raise :class:`InvalidToken`.

    ``verify_exp`` is left at its default: since we never emit ``exp``, a token
    that lacks it is accepted (PyJWT only enforces ``exp`` when present) — expiry
    is enforced against ``quote.expiration_date`` at the app layer, not here."""
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc

    try:
        token_id = uuid.UUID(str(claims["jti"]))
        org_id = uuid.UUID(str(claims["org"]))
        quote_id = uuid.UUID(str(claims["quote"]))
        scope = QuoteTokenScope(claims["scope"])
    except (KeyError, ValueError) as exc:
        raise InvalidToken(f"malformed claims: {exc}") from exc

    return TokenClaims(token_id=token_id, org_id=org_id, quote_id=quote_id, scope=scope)


async def create_buyer_token(
    session: AsyncSession,
    secret: str,
    quote: Quote,
    *,
    recipient_email: str | None = None,
) -> tuple[QuoteToken, str]:
    """Mint a per-recipient ``buyer_portal`` token for ``quote`` and persist the row.

    Returns the row and its signed JWT string (also stored on the row so Settings
    can list/copy a recipient's link). The row's ``id`` is the JWT ``jti``."""
    row = QuoteToken(
        org_id=quote.org_id,
        scope=QuoteTokenScope.buyer_portal,
        quote_id=quote.id,
        recipient_email=recipient_email,
        token="",  # replaced below once the id is allocated
    )
    session.add(row)
    await session.flush()  # allocate row.id (the jti)
    row.token = mint_jwt(
        secret,
        token_id=row.id,
        org_id=quote.org_id,
        quote_id=quote.id,
        scope=QuoteTokenScope.buyer_portal,
    )
    await session.flush()
    return row, row.token
