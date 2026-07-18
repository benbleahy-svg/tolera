"""Customer Intelligence Brief endpoint (M5.10; spec ``#ai-customer-brief``).

The send-quote composer calls this on mount. It returns the on-demand brief
(``brief`` non-null) or a "no card" response (``brief`` null + a ``reason``);
either way the response is 200 — omission is the normal, expected outcome, not
an error. Nothing is persisted. Org-scoping is enforced by the RLS session; a
cross-org quote id is unknown to the session and 404s via the read.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .customer_brief import generate_customer_brief
from .deps import get_session

customer_brief_router = APIRouter(prefix="/api/quotes/{quote_id}", tags=["customer-brief"])


@customer_brief_router.get("/customer-brief")
async def get_customer_brief(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> dict[str, Any]:
    """The "About this customer" card payload, or an omission reason.

    Runs the deterministic per-account aggregate + a single Claude call (spec:
    generated on demand, not stored). Never blocks the send: any gate failure
    (no account, AI off, < 3 prior quotes, model error) returns
    ``{"brief": null, "reason": ...}`` and the composer shows nothing."""
    return await generate_customer_brief(session, org_id=principal.active_org_id, quote_id=quote_id)
