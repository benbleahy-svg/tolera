"""Rule Auto-Suggestion API (M3.10 — spec ``#ai-rule-suggest``).

The read/dismiss surface over :mod:`app.rule_suggest`:

* ``GET  /api/suggested-actions``                        — the dashboard
  suggested-actions strip: open suggestions for the org, newest first.
* ``POST /api/suggested-actions/{id}/dismiss``           — wave one away (never
  re-surfaced; the ``open`` upsert guard leaves it dismissed).
* ``POST /api/components/{component_id}/rule-suggestion`` — the operation-drawer
  probe: detect + persist the pattern (if any) involving this component, right
  after a manual add. **POST**, not GET: it mutates persisted state (upserts
  ``suggested_action`` rows), so it must not be prefetched/retried as a safe GET.

Every route is org-scoped explicitly (defense in depth over RLS; CLAUDE.md §5)
and gated by ``org_ai_settings`` (:pyattr:`app.ai_settings.AiFlags.rule_suggest_active`)
— when rule-suggestion is off the probe returns ``null`` and the strip is empty.
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

from .ai_settings import get_ai_flags
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


def _out(row: SuggestedAction) -> SuggestedActionOut:
    return SuggestedActionOut(
        id=row.id,
        kind=row.kind,
        status=row.status,
        operation_def_id=row.operation_def_id,
        payload=row.payload,
        created_at=row.created_at,
    )


@rule_suggest_router.get("/suggested-actions")
async def list_suggested_actions(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[SuggestedActionOut]:
    """Open suggestions for the org (dashboard strip), newest first.

    Gated: when rule-suggestion is disabled the strip is empty even if rows were
    persisted while it was on (spec: "suppressed when ``rule_suggest_enabled`` is
    off")."""
    flags = await get_ai_flags(session, principal.active_org_id)
    if not flags.rule_suggest_active:
        return []
    rows = (
        await session.scalars(
            select(SuggestedAction)
            .where(
                SuggestedAction.org_id == principal.active_org_id,
                SuggestedAction.status == SuggestedActionStatus.open.value,
            )
            .order_by(SuggestedAction.created_at.desc())
        )
    ).all()
    return [_out(r) for r in rows]


@rule_suggest_router.post("/suggested-actions/{action_id}/dismiss")
async def dismiss_suggested_action(
    action_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> SuggestedActionOut:
    """Dismiss a suggestion — hidden and never re-surfaced. Org-scoped: a foreign
    row 404s exactly like a missing one."""
    row = await session.scalar(
        select(SuggestedAction).where(
            SuggestedAction.id == action_id,
            SuggestedAction.org_id == principal.active_org_id,
        )
    )
    if row is None:
        raise AppError("not_found", "Suggested action not found.", status_code=404)
    if row.status == SuggestedActionStatus.open.value:
        row.status = SuggestedActionStatus.dismissed.value
        row.dismissed_at = datetime.now(UTC)
    return _out(row)


class RuleSuggestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion: dict[str, Any] | None


@rule_suggest_router.post("/components/{component_id}/rule-suggestion")
async def component_rule_suggestion(
    component_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> RuleSuggestionOut:
    """The drawer probe after a manual add: the pattern involving this component,
    or ``null``. Runs the AI-free detector and **persists** any patterns (so they
    also reach the dashboard strip) — hence POST, not GET. Org-scoped lookup."""
    component = await session.scalar(
        select(Component).where(
            Component.id == component_id,
            Component.org_id == principal.active_org_id,
        )
    )
    if component is None:
        raise AppError("not_found", "Component not found.", status_code=404)
    suggestion = await suggestion_for_component(session, principal.active_org_id, component)
    return RuleSuggestionOut(suggestion=suggestion)
