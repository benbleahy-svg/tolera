"""Saved views — user-owned filter/sort presets for the quotes list (M1.3,
spec ``#quoteslist``).

A saved view stores ``filters``/``sort`` in the **same shape** the ``/api/quotes/
search`` body uses, so the list applies a view by replaying its stored clauses. Views
are **org-scoped** (RLS) and **owner-scoped**: a member sees and edits only their own
views (``owner_id``). Alongside a user's stored ("custom") views, the list endpoint
returns the **computed system views** (All Quotes, My Quotes, Drafts, Outstanding,
Overdue) — derived, never stored.

v1 rulings (DECISIONS.md 2026-06-25): only the ``quotes`` scope is implemented
(``line_items`` → M1.6, rejected here); only ``private`` visibility is honored
(org-sharing deferred). Presets **hard-delete** (the app role has DELETE) — a personal
preference, not auditable domain data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import SavedView, SavedViewScope, SavedViewVisibility
from .quote_filters import SYSTEM_QUOTE_VIEWS, FilterClause, SortClause, SystemView

saved_views_router = APIRouter(prefix="/api/saved-views", tags=["saved-views"])

_NAME_MAX = 120


class SavedViewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=_NAME_MAX)
    view_scope: SavedViewScope = SavedViewScope.quotes
    filters: list[FilterClause] = Field(default_factory=list)
    sort: list[SortClause] = Field(default_factory=list)
    visibility: SavedViewVisibility = SavedViewVisibility.private


class SavedViewUpdate(BaseModel):
    """PATCH — every field optional; omitted fields are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=_NAME_MAX)
    filters: list[FilterClause] | None = None
    sort: list[SortClause] | None = None


class SavedViewOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    view_scope: SavedViewScope
    name: str
    filters: list[FilterClause]
    sort: list[SortClause]
    visibility: SavedViewVisibility
    created_at: datetime
    updated_at: datetime


class SavedViewListResponse(BaseModel):
    """The sidebar payload: computed system views + the caller's custom views."""

    system: list[SystemView]
    custom: list[SavedViewOut]


def _saved_view_out(row: SavedView) -> SavedViewOut:
    return SavedViewOut(
        id=row.id,
        owner_id=row.owner_id,
        view_scope=row.view_scope,
        name=row.name,
        # Stored as JSONB (list[dict]); re-validate into typed clauses on the way out
        # (cheap, and guarantees a stored row still satisfies the grammar).
        filters=[FilterClause.model_validate(f) for f in row.filters],
        sort=[SortClause.model_validate(s) for s in row.sort],
        visibility=row.visibility,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _clauses_json(clauses: list[FilterClause] | list[SortClause]) -> list[dict[str, object]]:
    """Serialize validated clauses to the JSONB form stored on the row."""
    return [c.model_dump(mode="json") for c in clauses]


async def _get_owned_or_404(
    session: AsyncSession, view_id: uuid.UUID, owner_id: uuid.UUID
) -> SavedView:
    """Fetch a saved view in the active org that the caller owns, or 404.

    RLS already scopes ``session.get`` to the org (a foreign-org id → ``None``); the
    owner check turns another member's view in the same org into a 404 too (views are
    private in v1)."""
    row = await session.get(SavedView, view_id)
    if row is None or row.owner_id != owner_id:
        raise AppError("not_found", "Saved view not found.", status_code=status.HTTP_404_NOT_FOUND)
    return row


@saved_views_router.get("")
async def list_saved_views(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
    scope: Annotated[SavedViewScope, Query()] = SavedViewScope.quotes,
) -> SavedViewListResponse:
    """List the caller's custom views for ``scope`` plus the computed system views."""
    stmt = (
        select(SavedView)
        .where(SavedView.owner_id == principal.user_id, SavedView.view_scope == scope)
        .order_by(SavedView.name)
    )
    rows = (await session.execute(stmt)).scalars().all()
    system = list(SYSTEM_QUOTE_VIEWS) if scope == SavedViewScope.quotes else []
    return SavedViewListResponse(system=system, custom=[_saved_view_out(r) for r in rows])


@saved_views_router.post("", status_code=status.HTTP_201_CREATED)
async def create_saved_view(
    body: SavedViewCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> SavedViewOut:
    """Create a saved view owned by the caller."""
    if body.view_scope != SavedViewScope.quotes:
        raise AppError(
            "unsupported_scope",
            "Only 'quotes' saved views are supported yet.",
            status_code=422,
        )
    if body.visibility != SavedViewVisibility.private:
        raise AppError(
            "unsupported_visibility",
            "Org-shared views are not yet available.",
            status_code=422,
        )
    row = SavedView(
        org_id=principal.active_org_id,
        owner_id=principal.user_id,
        view_scope=body.view_scope,
        name=body.name,
        filters=_clauses_json(body.filters),
        sort=_clauses_json(body.sort),
        visibility=body.visibility,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_saved_view_owner_scope_name" in str(exc.orig):
            raise AppError(
                "name_conflict",
                "You already have a view with that name.",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise
    return _saved_view_out(row)


@saved_views_router.patch("/{view_id}")
async def update_saved_view(
    view_id: uuid.UUID,
    body: SavedViewUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> SavedViewOut:
    """Update a saved view the caller owns (rename / re-filter / re-sort)."""
    row = await _get_owned_or_404(session, view_id, principal.user_id)
    if body.name is not None:
        row.name = body.name
    if body.filters is not None:
        row.filters = _clauses_json(body.filters)
    if body.sort is not None:
        row.sort = _clauses_json(body.sort)
    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_saved_view_owner_scope_name" in str(exc.orig):
            raise AppError(
                "name_conflict",
                "You already have a view with that name.",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise
    return _saved_view_out(row)


@saved_views_router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_view(
    view_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Response:
    """Hard-delete a saved view the caller owns."""
    row = await _get_owned_or_404(session, view_id, principal.user_id)
    await session.delete(row)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
