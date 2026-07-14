"""Collaboration API (M2.11, spec ``#collab``).

The viewer's TEAM/EXTERNAL channels, feature/region-bound messages, ``@mention``
notifications, and **Assign Task → Dashboard**. One router mounted at ``/api``:

* ``GET/POST  /api/parts/{part_id}/channels``     — list (auto-provision TEAM) / create EXTERNAL
* ``GET/POST  /api/channels/{channel_id}/messages`` — thread; POST may bind an annotation + @mention
* ``PATCH/DELETE /api/messages/{message_id}``      — edit / tombstone (author-only)
* ``POST     /api/parts/{part_id}/tasks``          — Assign Task (notifies the assignee)
* ``GET      /api/tasks``                          — the Dashboard task surface (derives overdue)
* ``PATCH    /api/tasks/{task_id}``                — resolve
* ``GET      /api/notifications`` · ``PATCH /api/notifications/{id}`` — the caller's inbox

Every table is org-scoped (RLS pins reads/writes); ``assignee``/``mention`` FK the
org-less ``app_user`` so the **active-membership** guard runs at the edge (the
salesperson pattern). Posting/assigning needs ``quote_annotate``; reading needs
``view_all`` (spec: read + comment is distinct from edit).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import (
    Annotation,
    Channel,
    MembershipStatus,
    Message,
    Notification,
    Part,
    Task,
    TaskStatus,
    UserOrgMembership,
)

collab_router = APIRouter(prefix="/api", tags=["collaboration"])

_MAX_BODY = 10_000
_MAX_MENTIONS = 50


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class ChannelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Annotated[str, Field(pattern="^(team|external)$")] = "external"
    label: Annotated[str | None, Field(max_length=200)] = None
    quote_id: uuid.UUID | None = None


class ChannelOut(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    quote_id: uuid.UUID | None
    scope: str
    label: str | None
    created_at: datetime


class AnnotationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Annotated[str, Field(pattern="^(face|region)$")]
    geometry_ref: dict[str, Any]
    note: Annotated[str | None, Field(max_length=2000)] = None


class AnnotationOut(BaseModel):
    id: uuid.UUID
    kind: str
    geometry_ref: dict[str, Any]
    note: str | None


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(min_length=1, max_length=_MAX_BODY)]
    annotation: AnnotationIn | None = None
    parent_id: uuid.UUID | None = None
    mentions: Annotated[list[uuid.UUID], Field(max_length=_MAX_MENTIONS)] = []


class MessageEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(min_length=1, max_length=_MAX_BODY)]


class MessageOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    author_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    body: str
    mentions: list[uuid.UUID]
    annotation: AnnotationOut | None
    edited_at: datetime | None
    deleted: bool
    created_at: datetime


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignee_id: uuid.UUID
    message: Annotated[str | None, Field(max_length=2000)] = None
    due_date: date | None = None
    annotation_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = None


class TaskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Annotated[str, Field(pattern="^(open|resolved)$")]


class TaskOut(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID | None
    quote_id: uuid.UUID | None
    annotation_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    created_by: uuid.UUID | None
    message: str | None
    due_date: date | None
    status: str
    resolved_at: datetime | None
    created_at: datetime


class NotificationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read: bool = True


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class MemberOut(BaseModel):
    """A teammate the @mention / Assign-Task pickers offer."""

    id: uuid.UUID
    email: str
    first_name: str | None
    last_name: str | None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _get_part_or_404(session: AsyncSession, part_id: uuid.UUID) -> Part:
    part = await session.get(Part, part_id)
    if part is None:
        raise AppError("not_found", "Part not found.", status_code=status.HTTP_404_NOT_FOUND)
    return part


async def _require_active_member(session: AsyncSession, user_id: uuid.UUID, *, field: str) -> None:
    """Reject a user who isn't an **active member of the active org** (the
    tenancy guard the org-less ``app_user`` FK can't give — salesperson pattern).
    The query runs on the org-pinned session, so RLS scopes memberships to the
    active org; a foreign-org user has no visible active membership."""
    member = await session.scalar(
        select(UserOrgMembership.id).where(
            UserOrgMembership.user_id == user_id,
            UserOrgMembership.status == MembershipStatus.active,
        )
    )
    if member is None:
        raise AppError(
            f"invalid_{field}",
            f"{field.capitalize()} must be an active member of this organization.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


def _annotation_out(row: Annotation | None) -> AnnotationOut | None:
    if row is None:
        return None
    return AnnotationOut(id=row.id, kind=row.kind, geometry_ref=row.geometry_ref, note=row.note)


def _message_out(row: Message, annotation: Annotation | None) -> MessageOut:
    deleted = row.deleted_at is not None
    return MessageOut(
        id=row.id,
        channel_id=row.channel_id,
        author_id=row.author_id,
        parent_id=row.parent_id,
        body="" if deleted else row.body,
        mentions=[uuid.UUID(m) for m in row.mentions],
        annotation=_annotation_out(annotation),
        edited_at=row.edited_at,
        deleted=deleted,
        created_at=row.created_at,
    )


def _task_out(row: Task, today: date) -> TaskOut:
    # ``overdue`` is derived at read time: an unresolved task past its due date.
    derived = row.status
    if row.status == TaskStatus.open and row.due_date is not None and row.due_date < today:
        derived = TaskStatus.overdue
    return TaskOut(
        id=row.id,
        part_id=row.part_id,
        quote_id=row.quote_id,
        annotation_id=row.annotation_id,
        assignee_id=row.assignee_id,
        created_by=row.created_by,
        message=row.message,
        due_date=row.due_date,
        status=derived.value,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# Channels
# --------------------------------------------------------------------------- #


@collab_router.get("/parts/{part_id}/channels")
async def list_channels(
    part_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[ChannelOut]:
    """List the part's channels, auto-provisioning the single TEAM channel."""
    await _get_part_or_404(session, part_id)
    # Get-or-create the TEAM channel (partial unique index guards the race).
    await session.execute(
        pg_insert(Channel)
        .values(org_id=principal.active_org_id, part_id=part_id, scope="team")
        .on_conflict_do_nothing()
    )
    await session.flush()
    rows = await session.scalars(
        select(Channel).where(Channel.part_id == part_id).order_by(Channel.created_at)
    )
    return [
        ChannelOut(
            id=c.id,
            part_id=c.part_id,
            quote_id=c.quote_id,
            scope=c.scope,
            label=c.label,
            created_at=c.created_at,
        )
        for c in rows
    ]


@collab_router.post("/parts/{part_id}/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    part_id: uuid.UUID,
    payload: ChannelIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_annotate))],
) -> ChannelOut:
    """Create an EXTERNAL channel (per vendor/customer). ``scope='team'`` returns
    the part's single existing TEAM channel (get-or-create)."""
    await _get_part_or_404(session, part_id)
    if payload.scope == "team":
        await session.execute(
            pg_insert(Channel)
            .values(org_id=principal.active_org_id, part_id=part_id, scope="team")
            .on_conflict_do_nothing()
        )
        await session.flush()
        row = await session.scalar(
            select(Channel).where(Channel.part_id == part_id, Channel.scope == "team")
        )
        assert row is not None
    else:
        row = Channel(
            org_id=principal.active_org_id,
            part_id=part_id,
            scope="external",
            label=payload.label,
            quote_id=payload.quote_id,
        )
        session.add(row)
        await session.flush()
    return ChannelOut(
        id=row.id,
        part_id=row.part_id,
        quote_id=row.quote_id,
        scope=row.scope,
        label=row.label,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #


async def _get_channel_or_404(session: AsyncSession, channel_id: uuid.UUID) -> Channel:
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise AppError("not_found", "Channel not found.", status_code=status.HTTP_404_NOT_FOUND)
    return channel


@collab_router.get("/channels/{channel_id}/messages")
async def list_messages(
    channel_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[MessageOut]:
    """The channel thread, oldest-first. Tombstoned messages remain as
    ``deleted`` placeholders so replies keep their context."""
    await _get_channel_or_404(session, channel_id)
    rows = list(
        await session.scalars(
            select(Message).where(Message.channel_id == channel_id).order_by(Message.created_at)
        )
    )
    ann_ids = {r.annotation_id for r in rows if r.annotation_id is not None}
    anns: dict[uuid.UUID, Annotation] = {}
    if ann_ids:
        for a in await session.scalars(select(Annotation).where(Annotation.id.in_(ann_ids))):
            anns[a.id] = a
    return [_message_out(r, anns.get(r.annotation_id) if r.annotation_id else None) for r in rows]


@collab_router.post("/channels/{channel_id}/messages", status_code=status.HTTP_201_CREATED)
async def post_message(
    channel_id: uuid.UUID,
    payload: MessageIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_annotate))],
) -> MessageOut:
    """Post a message, optionally **bound to a feature/region** (creates the
    annotation) and ``@mention``-ing teammates (fans out notifications)."""
    channel = await _get_channel_or_404(session, channel_id)
    org_id = principal.active_org_id

    # A reply must target a message in THIS channel (the composite FK only pins
    # same-org). Validate at the edge so a bad/foreign parent is a clean 422, not
    # an IntegrityError 500.
    if payload.parent_id is not None:
        parent = await session.get(Message, payload.parent_id)
        if parent is None or parent.channel_id != channel_id:
            raise AppError(
                "invalid_parent",
                "Reply target must be a message in this channel.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    # Dedup mentions and drop a self-mention (no point notifying yourself),
    # preserving order.
    mentions = list(dict.fromkeys(m for m in payload.mentions if m != principal.user_id))
    for mentioned in mentions:
        await _require_active_member(session, mentioned, field="mention")

    annotation: Annotation | None = None
    if payload.annotation is not None:
        annotation = Annotation(
            org_id=org_id,
            part_id=channel.part_id,
            kind=payload.annotation.kind,
            geometry_ref=payload.annotation.geometry_ref,
            note=payload.annotation.note,
        )
        session.add(annotation)
        await session.flush()

    message = Message(
        org_id=org_id,
        channel_id=channel_id,
        author_id=principal.user_id,
        annotation_id=annotation.id if annotation else None,
        parent_id=payload.parent_id,
        body=payload.body,
        mentions=[str(m) for m in mentions],
    )
    session.add(message)
    await session.flush()

    for mentioned in mentions:
        session.add(
            Notification(
                org_id=org_id,
                user_id=mentioned,
                kind="mention",
                payload={
                    "channel_id": str(channel_id),
                    "message_id": str(message.id),
                    "part_id": str(channel.part_id),
                },
            )
        )
    await session.flush()
    return _message_out(message, annotation)


async def _get_own_message_or_error(
    session: AsyncSession, message_id: uuid.UUID, principal: Principal
) -> Message:
    message = await session.get(Message, message_id)
    if message is None:
        raise AppError("not_found", "Message not found.", status_code=status.HTTP_404_NOT_FOUND)
    if message.author_id != principal.user_id:
        raise AppError(
            "forbidden",
            "Only the author may edit or delete this message.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return message


@collab_router.patch("/messages/{message_id}")
async def edit_message(
    message_id: uuid.UUID,
    payload: MessageEdit,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_annotate))],
) -> MessageOut:
    message = await _get_own_message_or_error(session, message_id, principal)
    if message.deleted_at is not None:
        raise AppError("gone", "Message was deleted.", status_code=status.HTTP_404_NOT_FOUND)
    message.body = payload.body
    message.edited_at = datetime.now(UTC)
    await session.flush()
    annotation = (
        await session.get(Annotation, message.annotation_id) if message.annotation_id else None
    )
    return _message_out(message, annotation)


@collab_router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_annotate))],
) -> Response:
    message = await _get_own_message_or_error(session, message_id, principal)
    message.deleted_at = datetime.now(UTC)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Tasks (Assign Task → Dashboard)
# --------------------------------------------------------------------------- #


@collab_router.post("/parts/{part_id}/tasks", status_code=status.HTTP_201_CREATED)
async def assign_task(
    part_id: uuid.UUID,
    payload: TaskIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_annotate))],
) -> TaskOut:
    """Assign a task on the part (optionally bound to an annotation), notifying
    the assignee. Surfaces on the Dashboard via ``GET /api/tasks``."""
    await _get_part_or_404(session, part_id)
    await _require_active_member(session, payload.assignee_id, field="assignee")
    # A bound annotation must belong to THIS part (composite FK only pins same-org)
    # — validate at the edge so a foreign/bad id is a clean 422, not a 500.
    if payload.annotation_id is not None:
        annotation = await session.get(Annotation, payload.annotation_id)
        if annotation is None or annotation.part_id != part_id:
            raise AppError(
                "invalid_annotation",
                "Annotation must belong to this part.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
    org_id = principal.active_org_id
    task = Task(
        org_id=org_id,
        part_id=part_id,
        quote_id=payload.quote_id,
        annotation_id=payload.annotation_id,
        assignee_id=payload.assignee_id,
        created_by=principal.user_id,
        message=payload.message,
        due_date=payload.due_date,
        status=TaskStatus.open,
    )
    session.add(task)
    await session.flush()
    session.add(
        Notification(
            org_id=org_id,
            user_id=payload.assignee_id,
            kind="task_assigned",
            payload={"task_id": str(task.id), "part_id": str(part_id)},
        )
    )
    await session.flush()
    return _task_out(task, datetime.now(UTC).date())


@collab_router.get("/tasks")
async def list_tasks(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    assignee_id: Annotated[uuid.UUID | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[TaskOut]:
    """The Dashboard task surface — the active org's tasks, newest first, with
    ``overdue`` derived. Optional ``assignee_id`` / ``status`` filters."""
    query = select(Task).order_by(Task.created_at.desc())
    if assignee_id is not None:
        query = query.where(Task.assignee_id == assignee_id)
    rows = list(await session.scalars(query))
    today = datetime.now(UTC).date()
    out = [_task_out(r, today) for r in rows]
    if status_filter is not None:
        out = [t for t in out if t.status == status_filter]
    return out


@collab_router.patch("/tasks/{task_id}")
async def update_task(
    task_id: uuid.UUID,
    payload: TaskPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_annotate))],
) -> TaskOut:
    """Resolve (or reopen) a task."""
    task = await session.get(Task, task_id)
    if task is None:
        raise AppError("not_found", "Task not found.", status_code=status.HTTP_404_NOT_FOUND)
    if payload.status == "resolved":
        task.status = TaskStatus.resolved
        task.resolved_at = datetime.now(UTC)
    else:
        task.status = TaskStatus.open
        task.resolved_at = None
    await session.flush()
    return _task_out(task, datetime.now(UTC).date())


# --------------------------------------------------------------------------- #
# Notifications (the caller's inbox)
# --------------------------------------------------------------------------- #


@collab_router.get("/notifications")
async def list_notifications(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[NotificationOut]:
    """The caller's notifications (unread first, newest first)."""
    rows = await session.scalars(
        select(Notification)
        .where(Notification.user_id == principal.user_id)
        .order_by(Notification.read_at.is_(None).desc(), Notification.created_at.desc())
    )
    return [
        NotificationOut(
            id=n.id, kind=n.kind, payload=n.payload, read_at=n.read_at, created_at=n.created_at
        )
        for n in rows
    ]


@collab_router.patch("/notifications/{notification_id}")
async def mark_notification(
    notification_id: uuid.UUID,
    payload: NotificationPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> NotificationOut:
    row = await session.get(Notification, notification_id)
    if row is None or row.user_id != principal.user_id:
        raise AppError(
            "not_found", "Notification not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    row.read_at = datetime.now(UTC) if payload.read else None
    await session.flush()
    return NotificationOut(
        id=row.id,
        kind=row.kind,
        payload=row.payload,
        read_at=row.read_at,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# Teammate directory (mention / assignee pickers)
# --------------------------------------------------------------------------- #


@collab_router.get("/org/members")
async def list_org_members(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[MemberOut]:
    """The active org's active members, for the @mention / Assign-Task pickers.
    Reads through ``app_org_members()`` — the scoped ``SECURITY DEFINER`` view the
    restricted role must use to surface ``app_user`` (M0.2); the function keys on
    the ``app.current_org_id`` GUC, so no other org's users are reachable."""
    raw = (await session.execute(text("SELECT app_org_members()"))).scalar_one()
    members = json.loads(raw) if isinstance(raw, str) else raw
    return [MemberOut(**m) for m in members]
