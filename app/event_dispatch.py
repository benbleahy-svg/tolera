"""The internal event-bus subscriber (M6.8).

M5.5 built the **emit** half of the bus — ``app.events.emit_event`` appends to
the ``domain_event`` outbox in the same transaction as the state change — and
left the consuming side to "the M6 dispatcher". This is that consumer, scoped
to what M6.8's acceptance criteria need: an in-process handler registry that
drains undelivered events and drives the CRM/ERP adapters off them.

**What this is not.** It is not the outbound *signed-webhook* delivery to
third-party endpoints (``Tolera-Signature``, per-subscriber signing secrets,
delivery log, manual resend). That surface belongs to the public Streaming API
(INTEGRATION-API-CONTRACT §4) and is not in M6.8's scope or acceptance
criteria; the outbox row shape it will read is unchanged by anything here, so
adding it later is additive. Recorded as an assumption in the PR body.

**Semantics.**

* *At-least-once.* ``delivered_at`` is stamped after handlers run, so a crash
  mid-dispatch replays the event. Handlers must therefore be **idempotent** —
  the CRM handler is, because it upserts by ``crm_opportunity_id`` and a second
  run updates the same deal rather than creating another.
* *One failing handler does not block the batch.* A handler raising is logged
  and its Integration-Action row records the failure; the event is still marked
  delivered, because the durable record of "this export failed" lives in the
  action log where the user can see and retry it — not in an outbox row that
  would otherwise be retried forever.
* *Org-scoped throughout.* Every handler receives the event's ``org_id`` and
  runs on an org-pinned session; nothing here reads across orgs.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DomainEvent

logger = logging.getLogger(__name__)

#: A handler takes the org-pinned session and the event; it returns nothing and
#: is expected to record its own outcome (an Integration-Action row, usually).
EventHandler = Callable[[AsyncSession, DomainEvent], Awaitable[None]]

_HANDLERS: dict[str, list[EventHandler]] = {}


def subscribe(event_type: str, handler: EventHandler) -> None:
    """Register ``handler`` for one dotted event type from the catalog."""
    _HANDLERS.setdefault(event_type, []).append(handler)


def unsubscribe_all(event_type: str | None = None) -> None:
    """Drop registrations — tests use this to isolate a handler."""
    if event_type is None:
        _HANDLERS.clear()
    else:
        _HANDLERS.pop(event_type, None)


def handlers_for(event_type: str) -> list[EventHandler]:
    return list(_HANDLERS.get(event_type, ()))


async def dispatch_event(session: AsyncSession, event: DomainEvent) -> int:
    """Run every handler for one event; returns how many ran without raising."""
    succeeded = 0
    for handler in handlers_for(event.event_type):
        try:
            await handler(session, event)
            succeeded += 1
        except Exception:
            # Logged, not re-raised: see "one failing handler" above.
            logger.warning(
                "event_handler_failed",
                extra={
                    "event_type": event.event_type,
                    "event_id": str(event.id),
                    "org_id": str(event.org_id),
                },
                exc_info=True,
            )
    return succeeded


async def drain_outbox(
    session: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
    limit: int = 100,
    now: datetime | None = None,
) -> int:
    """Dispatch undelivered events oldest-first; returns how many were handled.

    ``org_id`` narrows the drain to one tenant (how the Celery task runs it,
    one org per pinned session). Ordering is by ``occurred_at`` so a
    ``quote.sent`` is never processed before the ``quote.created`` that
    preceded it."""
    stmt = (
        select(DomainEvent)
        .where(DomainEvent.delivered_at.is_(None))
        .order_by(DomainEvent.occurred_at)
        .limit(limit)
    )
    if org_id is not None:
        stmt = stmt.where(DomainEvent.org_id == org_id)

    events = list((await session.execute(stmt)).scalars().all())
    stamp = now or datetime.now(UTC)
    for event in events:
        await dispatch_event(session, event)
        event.delivered_at = stamp
    await session.flush()
    return len(events)
