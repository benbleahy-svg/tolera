"""``GET /api/me`` — the session bootstrap the app shell loads on startup.

Returns the caller's identity, the active org's config (name/locale/currency/
country — what the shell localises + formats money with), every org they belong
to (the org-switcher source), and their effective capabilities. The cross-org /
``app_user`` reads that the restricted role cannot perform directly go through
the audited ``app_current_identity`` SECURITY DEFINER function (migration 0004 /
DECISIONS.md 2026-06-24), called with the *verified* ``principal.user_id`` — so a
caller only ever reads their own identity. Capabilities come from ``app.authz``
(the single source of truth); the frontend gates nav on them and never
re-encodes the role→capability matrix.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal, get_principal
from .authz import permissions_for
from .deps import get_session
from .errors import AppError
from .models import MembershipRole, MembershipStatus

router = APIRouter(prefix="/api", tags=["session"])


class UserOut(BaseModel):
    """The authenticated user's identity (from the global ``app_user`` table)."""

    id: uuid.UUID
    email: str
    first_name: str | None = None
    last_name: str | None = None


class OrgOut(BaseModel):
    """An organization's display + DACH config (locale/currency drive the UI)."""

    id: uuid.UUID
    name: str
    slug: str
    country: str
    currency: str
    locale: str


class MembershipOut(BaseModel):
    """One of the caller's org memberships — the org-switcher renders this list."""

    org_id: uuid.UUID
    org_name: str
    org_slug: str
    country: str
    currency: str
    locale: str
    roles: list[str]
    status: str


class MeOut(BaseModel):
    """The session bootstrap payload."""

    user: UserOut
    active_org: OrgOut
    memberships: list[MembershipOut]
    effective_permissions: list[str]
    roles: list[str]


@router.get("/me")
async def get_me(
    principal: Annotated[Principal, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MeOut:
    """Resolve the caller's session bootstrap. The identity read is bound to the
    caller by the DB: ``app_current_identity()`` reads the ``app.current_user_id``
    GUC that ``get_session`` stamped from the verified principal — no user id is
    passed in, so the read cannot be aimed at another user."""
    raw = (await session.execute(text("SELECT app_current_identity()"))).scalar_one()
    # asyncpg may hand jsonb back as text or as a decoded object; accept both.
    identity = json.loads(raw) if isinstance(raw, str) else raw

    user = identity.get("user")
    if user is None:
        # The token authenticates a user with no identity row — fail closed.
        raise AppError(
            "unauthorized",
            "Authenticated user not found",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    memberships = identity.get("memberships") or []
    # Match the active org AND require the membership be active — a pending or
    # disabled membership must not grant roles/capabilities (fail closed).
    active = next(
        (
            m
            for m in memberships
            if m["org_id"] == str(principal.active_org_id)
            and m["status"] == MembershipStatus.active.value
        ),
        None,
    )
    if active is None:
        # The claim's active org isn't an active membership of the caller — fail closed.
        raise AppError(
            "forbidden",
            "You do not have an active membership in the active organization",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Report roles/capabilities from the **active membership row** (the DB, which
    # ``user_org_membership`` makes authoritative — see app.auth), NOT the JWT
    # ``principal.roles`` cache. If the claim is briefly stale (before the M5.12
    # claim↔membership sync catches up), the claim could overstate access and make
    # this payload self-contradictory (memberships[*].roles vs top-level roles).
    # Sourcing both from the active row keeps the response internally consistent
    # and DB-truthful. (API-layer enforcement via authz.require() still keys on the
    # claim in M0.3; M5.12 keeps the two in lockstep.)
    active_roles = tuple(MembershipRole(role) for role in active["roles"])

    return MeOut(
        user=UserOut(**user),
        active_org=OrgOut(
            id=active["org_id"],
            name=active["org_name"],
            slug=active["org_slug"],
            country=active["country"],
            currency=active["currency"],
            locale=active["locale"],
        ),
        memberships=[MembershipOut(**m) for m in memberships],
        effective_permissions=sorted(p.value for p in permissions_for(active_roles)),
        roles=[role.value for role in active_roles],
    )
