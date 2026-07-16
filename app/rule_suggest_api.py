"""Rule Auto-Suggestion API (M3.10 — spec ``#ai-rule-suggest``).

The read/dismiss surface over :mod:`app.rule_suggest`:

* ``GET  /api/suggested-actions``                       — the dashboard
  suggested-actions strip: open suggestions for the org, newest first.
* ``POST /api/suggested-actions/{id}/dismiss``          — wave one away (never
  re-surfaced; the ``open`` upsert guard leaves it dismissed).
* ``GET  /api/components/{component_id}/rule-suggestion`` — the operation-drawer
  chip: the pattern (if any) involving this component, right after a manual add.

Every route is gated by ``org_ai_settings`` inside :mod:`app.rule_suggest`; when
rule-suggestion is off the drawer probe returns ``null`` and the strip is empty.
Nothing here creates a rule — the payload only pre-seeds M3.8's Create Rule
dialog, whose CREATE RULE button is the sole writer (the human gate)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import Component, SuggestedAction, SuggestedActionStatus
from .rule_suggest import suggestion_for_component

rule_suggest_router = APIRouter(prefix="/api", tags=["rule-suggest"])


class SuggestedActionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    kind: str
    status: str
    operation_def_id: uuid.UUID | None
    payload: dict[str, Any]
    created_at: datetime


@rule_suggest_router.get("/suggested-actions")
async def list_suggested_actions(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[SuggestedActionOut]:
    """Open suggestions for the org (dashboard strip), newest first."""
    rows = (
        await session.scalars(
            select(SuggestedAction)
            .where(SuggestedAction.status == SuggestedActionStatus.open.value)
            .order_by(SuggestedAction.created_at.desc())
        )
    ).all()
    return [
        SuggestedActionOut(
            id=r.id,
            kind=r.kind,
            status=r.status,
            operation_def_id=r.operation_def_id,
            payload=r.payload,
            created_at=r.created_at,
        )
        for r in rows
    ]


@rule_suggest_router.post("/suggested-actions/{action_id}/dismiss")
async def dismiss_suggested_action(
    action_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> SuggestedActionOut:
    """Dismiss a suggestion — hidden and never re-surfaced."""
    row = await session.get(SuggestedAction, action_id)
    if row is None:
        raise AppError("not_found", "Suggested action not found.", status_code=404)
    if row.status == SuggestedActionStatus.open.value:
        row.status = SuggestedActionStatus.dismissed.value
        row.dismissed_at = datetime.now(UTC)
    return SuggestedActionOut(
        id=row.id,
        kind=row.kind,
        status=row.status,
        operation_def_id=row.operation_def_id,
        payload=row.payload,
        created_at=row.created_at,
    )


class RuleSuggestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion: dict[str, Any] | None


@rule_suggest_router.get("/components/{component_id}/rule-suggestion")
async def component_rule_suggestion(
    component_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> RuleSuggestionOut:
    """The drawer chip after a manual add: the pattern involving this component,
    or ``null``. Runs the AI-free detector and persists any patterns so they
    also reach the dashboard strip."""
    component = await session.get(Component, component_id)
    if component is None:
        raise AppError("not_found", "Component not found.", status_code=404)
    suggestion = await suggestion_for_component(session, principal.active_org_id, component)
    return RuleSuggestionOut(suggestion=suggestion)
