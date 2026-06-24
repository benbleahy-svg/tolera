"""The trivial org-scoped ``note`` endpoint — M0.2's RLS proof, not a feature.

``GET /notes`` returns notes for the caller's active org (RLS guarantees no other
org's rows are visible). ``POST /notes`` is admin-gated to prove API-layer RBAC.
Both exist only so the tenancy spine has something to isolate; they go away once
a real org-scoped resource lands in M1.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .models import Note

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteOut(BaseModel):
    """A note as returned to clients."""

    id: uuid.UUID
    body: str


class NoteIn(BaseModel):
    """Payload to create a note."""

    body: str = Field(min_length=1, max_length=2000)


@router.get("")
async def list_notes(session: Annotated[AsyncSession, Depends(get_session)]) -> list[NoteOut]:
    """List the active org's notes (org isolation enforced at the DB by RLS)."""
    result = await session.execute(select(Note).order_by(Note.created_at))
    return [NoteOut(id=note.id, body=note.body) for note in result.scalars()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> NoteOut:
    """Create a note in the active org. Gated on ``quote_edit`` (RBAC smoke gate
    through the M0.3 policy module — a viewer is denied, an editor allowed)."""
    note = Note(org_id=principal.active_org_id, body=payload.body)
    session.add(note)
    await session.flush()
    return NoteOut(id=note.id, body=note.body)
