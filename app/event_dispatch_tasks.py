"""The Celery beat task that drains the domain-event outbox (M6.8).

``app.events.emit_event`` writes to the outbox inside the emitting request's
transaction; nothing consumes it synchronously, because a CRM being slow or
down must never add latency to — or fail — the quote send that produced the
event. This periodic task is the consumer.

**Per-org, not global.** Every session is pinned to one ``org_id`` so RLS is in
force for the handlers exactly as it is for a request; a single cross-org drain
would have to run unpinned, which is precisely the thing the tenancy model
forbids. The task therefore lists the orgs with undelivered events (as the
owner role, reading only ``org_id``) and drains each on its own pinned session.

**Idempotency.** ``delivered_at`` is stamped after handlers run, so a crash
replays the batch — handlers are written to tolerate that (see
``app.event_dispatch``). The ``AsyncResult`` redelivery guard used by the
heavier tasks is unnecessary here: a replayed drain finds the rows already
stamped and does nothing.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from celery.result import AsyncResult
from sqlalchemy import text

from .celery_app import celery_app
from .tasks import BaseTask

logger = logging.getLogger(__name__)

#: How many events one org may drain per tick — a backlog drains over several
#: ticks rather than holding a worker for an unbounded stretch.
DRAIN_BATCH_SIZE = 100


async def _drain_all_orgs(db_url: str, *, batch_size: int) -> dict[str, Any]:
    from .db import make_engine, make_sessionmaker, org_scoped_session
    from .event_dispatch import drain_outbox

    engine = make_engine(db_url)
    handled = 0
    org_ids: list[uuid.UUID] = []
    try:
        sessionmaker = make_sessionmaker(engine)
        # Which orgs have work? Read org_id only — no tenant data crosses here.
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT DISTINCT org_id FROM domain_event WHERE delivered_at IS NULL LIMIT 500"
                )
            )
            org_ids = [row[0] for row in rows]

        for org_id in org_ids:
            async with org_scoped_session(sessionmaker, org_id) as session:
                handled += await drain_outbox(session, org_id=org_id, limit=batch_size)
                await session.commit()
    finally:
        await engine.dispose()
    return {"orgs": len(org_ids), "events": handled}


@celery_app.task(
    base=BaseTask,
    name="app.drain_event_outbox",
    bind=True,
    soft_time_limit=120,
    time_limit=180,
)
def drain_event_outbox_task(self: Any, batch_size: int = DRAIN_BATCH_SIZE) -> dict[str, Any]:
    """Dispatch every org's undelivered domain events."""
    from .interrogation import _run_on_own_loop
    from .task_resources import resolve as resolve_task_resources

    task_id = self.request.id
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)

    db_url, _storage = resolve_task_resources()
    result = cast(
        "dict[str, Any]", _run_on_own_loop(_drain_all_orgs(db_url, batch_size=batch_size))
    )
    logger.info("event_outbox_drained", extra=result)
    return result
