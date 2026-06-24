"""FastAPI request dependencies that tie auth to the org-scoped DB session.

``get_session`` is the seam every org-scoped route uses: it resolves the caller
(``get_principal``) and hands back a session pinned to their active org, so a
handler physically cannot read or write another org's rows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .auth import Principal, get_principal
from .db import USER_ID_GUC, org_scoped_session


async def get_session(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> AsyncIterator[AsyncSession]:
    """Yield a transaction-scoped session pinned to the caller's active org.

    Also stamps the authenticated user into a transaction-local GUC so the
    ``app_current_identity()`` SECURITY DEFINER read is bound to *this* caller by
    the database, not by a trusted function argument (migration 0004)."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with org_scoped_session(sessionmaker, principal.active_org_id) as session:
        await session.execute(
            text(f"SELECT set_config('{USER_ID_GUC}', :uid, true)"),
            {"uid": str(principal.user_id)},
        )
        yield session
