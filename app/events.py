"""Domain-event outbox (M5.5).

A thin helper over :class:`~app.models.DomainEvent`. Callers ``emit`` an event in
the SAME transaction as the state change it records (e.g. ``quote.sent`` alongside
the Sent lifecycle transition), so the event is durable iff the change committed —
the transactional-outbox pattern. The signed **webhook delivery** off these rows
(INTEGRATION-API-CONTRACT webhook round-trip) is the M6 dispatcher's job.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import DomainEvent


async def emit_event(
    session: AsyncSession,
    org_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> DomainEvent:
    """Append one event to the org's outbox (not yet delivered)."""
    event = DomainEvent(org_id=org_id, event_type=event_type, payload=payload)
    session.add(event)
    await session.flush()
    return event
