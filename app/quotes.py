"""Quotes list — the read side of the quotes screen (M1.3, spec ``#quoteslist``).

One endpoint: ``POST /api/quotes/search``. It is a **read** (no side effects) but
takes a structured, persistable filter/sort body, so a POST is the right tool — and
crucially the body shape is **identical** to a saved view's stored ``filters``/``sort``
(DECISIONS.md 2026-06-25 "M1.3 build path"), so applying a saved view is just POSTing
its stored clauses back. The list is **read-only** in M1.3: quotes are created by the
seeder/owner (for this list) and by M1.4's create flow thereafter — the app role has
SELECT-only on ``quote``.

Results are org-scoped by RLS via ``get_session``; a request either selects a computed
``system_view`` (All Quotes / My Quotes / Drafts / Outstanding / Overdue) **or** an
ad-hoc ``filters``/``sort`` set — never both.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import Quote, QuoteStatus
from .quote_filters import (
    FilterClause,
    SortClause,
    apply_filters,
    apply_sort,
    apply_system_view,
    is_system_view,
)

quotes_router = APIRouter(prefix="/api/quotes", tags=["quotes"])

_PAGE_SIZE_DEFAULT = 20  # spec footer "1-20 of N"
_PAGE_SIZE_MAX = 200


class QuoteRow(BaseModel):
    """One quote as rendered in the grid (the M1.3 column subset)."""

    id: uuid.UUID
    number: str
    status: QuoteStatus
    account_id: uuid.UUID | None
    salesperson_id: uuid.UUID | None
    estimator_id: uuid.UUID | None
    rfq_number: str | None
    due_date: datetime | None
    created_at: datetime


class QuoteSearchRequest(BaseModel):
    """Either a computed ``system_view`` key, or an ad-hoc ``filters``/``sort`` set
    (the same shape stored on a saved view) — plus offset pagination."""

    model_config = ConfigDict(extra="forbid")

    system_view: str | None = None
    filters: list[FilterClause] = Field(default_factory=list)
    sort: list[SortClause] = Field(default_factory=list)
    limit: int = Field(default=_PAGE_SIZE_DEFAULT, ge=1, le=_PAGE_SIZE_MAX)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _exclusive(self) -> QuoteSearchRequest:
        if self.system_view is not None and (self.filters or self.sort):
            raise ValueError("system_view cannot be combined with filters/sort")
        return self


class QuoteSearchResponse(BaseModel):
    rows: list[QuoteRow]
    total: int
    limit: int
    offset: int


def _quote_row(q: Quote) -> QuoteRow:
    return QuoteRow(
        id=q.id,
        number=q.number,
        status=q.status,
        account_id=q.account_id,
        salesperson_id=q.salesperson_id,
        estimator_id=q.estimator_id,
        rfq_number=q.rfq_number,
        due_date=q.due_date,
        created_at=q.created_at,
    )


@quotes_router.post("/search")
async def search_quotes(
    req: QuoteSearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> QuoteSearchResponse:
    """Filter/sort/paginate the active org's quotes (RLS-scoped)."""
    stmt = select(Quote)
    if req.system_view is not None:
        if not is_system_view(req.system_view):
            raise AppError(
                "unknown_system_view",
                f"Unknown system view: {req.system_view}",
                status_code=422,
            )
        stmt = apply_system_view(stmt, req.system_view, user_id=principal.user_id)
    else:
        stmt = apply_filters(stmt, req.filters)
        stmt = apply_sort(stmt, req.sort)

    # Total over the filtered set, independent of ordering/pagination (the footer
    # "1-20 of N"). Strip ORDER BY for the count subquery.
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    page = stmt.limit(req.limit).offset(req.offset)
    rows = (await session.execute(page)).scalars().all()
    return QuoteSearchResponse(
        rows=[_quote_row(q) for q in rows],
        total=total or 0,
        limit=req.limit,
        offset=req.offset,
    )
