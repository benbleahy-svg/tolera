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
from collections.abc import Sequence
from dataclasses import dataclass

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Quote, QuoteToken, QuoteTokenScope, VendorRfqRecipient

_ALGORITHM = "HS256"


class InvalidToken(Exception):
    """The token string is malformed, wrongly signed, or missing required claims."""


@dataclass(frozen=True)
class TokenClaims:
    """The verified, parsed payload of an external-access JWT.

    Exactly one *subject* claim is meaningful per scope: ``buyer_portal`` carries
    ``quote_id`` (the quote the buyer opens), ``vendor_rfq`` carries
    ``rfq_recipient_id`` (the one vendor + one batch the portal link unlocks, M6.2).
    Both are optional here so one claims type serves every scope; each handler asserts
    the one it needs — a token without the right subject is rejected, never coerced."""

    token_id: uuid.UUID
    org_id: uuid.UUID
    quote_id: uuid.UUID | None
    scope: QuoteTokenScope
    rfq_recipient_id: uuid.UUID | None = None


def mint_jwt(
    secret: str,
    *,
    token_id: uuid.UUID,
    org_id: uuid.UUID,
    scope: QuoteTokenScope,
    quote_id: uuid.UUID | None = None,
    rfq_recipient_id: uuid.UUID | None = None,
) -> str:
    """Sign an external-access JWT. **No ``exp`` claim** (soft app-layer expiry).

    A subject claim is emitted only when supplied, so a ``vendor_rfq`` token carries
    ``rfq`` and no ``quote`` — the buyer endpoint therefore cannot be opened with it
    even before the scope check."""
    payload: dict[str, str] = {
        "jti": str(token_id),
        "org": str(org_id),
        "scope": scope.value,
    }
    if quote_id is not None:
        payload["quote"] = str(quote_id)
    if rfq_recipient_id is not None:
        payload["rfq"] = str(rfq_recipient_id)
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
        scope = QuoteTokenScope(claims["scope"])
        raw_quote = claims.get("quote")
        raw_rfq = claims.get("rfq")
        quote_id = uuid.UUID(str(raw_quote)) if raw_quote is not None else None
        rfq_recipient_id = uuid.UUID(str(raw_rfq)) if raw_rfq is not None else None
    except (KeyError, ValueError) as exc:
        raise InvalidToken(f"malformed claims: {exc}") from exc

    return TokenClaims(
        token_id=token_id,
        org_id=org_id,
        quote_id=quote_id,
        scope=scope,
        rfq_recipient_id=rfq_recipient_id,
    )


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


async def create_vendor_rfq_token(
    session: AsyncSession,
    secret: str,
    recipient: VendorRfqRecipient,
    *,
    part_file_ids: Sequence[uuid.UUID] | None = None,
) -> tuple[QuoteToken, str]:
    """Mint the ``vendor_rfq`` portal credential for one recipient (M6.2).

    The token is scoped to the **recipient**, not the quote (``quote_id`` stays NULL):
    one vendor, one batch, blind to every other vendor on the same RFQ. ``part_file_ids``
    is the vendor's file allowlist, persisted on the row as ``file_permissions`` — the
    download route consults it, so a per-vendor redacted-variant choice (M6.4) is
    enforced by the token rather than by whatever the UI happened to render. ``None``
    means "no files yet"; an explicit empty list means "this vendor gets no files"."""
    row = QuoteToken(
        org_id=recipient.org_id,
        scope=QuoteTokenScope.vendor_rfq,
        quote_id=None,
        vendor_rfq_recipient_id=recipient.id,
        recipient_email=recipient.contact_email,
        file_permissions=(
            None if part_file_ids is None else {"part_file_ids": [str(f) for f in part_file_ids]}
        ),
        token="",  # replaced below once the id is allocated
    )
    session.add(row)
    await session.flush()  # allocate row.id (the jti)
    row.token = mint_jwt(
        secret,
        token_id=row.id,
        org_id=recipient.org_id,
        rfq_recipient_id=recipient.id,
        scope=QuoteTokenScope.vendor_rfq,
    )
    await session.flush()
    return row, row.token
