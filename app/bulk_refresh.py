"""M5.0 — Bulk Refresh Pricing (quotes-list multi-select).

DECISIONS 2026-07-09 *Bulk Refresh Pricing placement*: a **thin batch loop** over
M1.10's re-evaluate-with-preserved-overrides engine (``refresh_quote_pricing``) —
no new pricing math. Small selections run inline on the request; a large one is
handed to Celery so the request never blocks (spec E4-d). Every ``manual_*`` is
preserved by the underlying engine; this module only iterates.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from celery.result import AsyncResult

from .celery_app import celery_app
from .db import make_engine, make_sessionmaker, org_scoped_session
from .lens_extract import _run_on_own_loop
from .pricing import refresh_quote_pricing
from .tasks import BaseTask

logger = logging.getLogger("app.bulk_refresh")

#: At or below this many quotes, Bulk Refresh runs inline on the request; above it,
#: the work is handed to Celery (cheap-to-reverse threshold — M5.0 ASSUMED).
BULK_REFRESH_SYNC_MAX = 10


async def run_bulk_refresh(
    db_url: str, *, org_id: uuid.UUID, quote_ids: list[uuid.UUID]
) -> dict[str, Any]:
    """Task core — refresh each quote's pricing, preserving every ``manual_*`` (the
    engine's contract). Missing/trashed quotes are skipped; a quote that errors
    (e.g. a broken Kalk formula) is counted ``failed`` and does not roll back the
    others. **One transaction per quote** so the ``with_for_update`` locks release
    incrementally rather than spanning the whole (up to 500-quote) task. Idempotent:
    re-running re-snapshots to the same result."""
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        refreshed_quotes = 0
        refreshed_items = 0
        skipped = 0
        failed = 0
        for quote_id in quote_ids:
            try:
                async with org_scoped_session(sessionmaker, org_id) as session:
                    n = await refresh_quote_pricing(session, org_id, quote_id)
            except Exception:  # isolate one bad quote from the rest of the batch
                logger.warning("bulk_refresh_quote_failed", extra={"quote_id": str(quote_id)})
                failed += 1
                continue
            if n is None:
                skipped += 1
                continue
            refreshed_quotes += 1
            refreshed_items += n
        return {
            "refreshed_quotes": refreshed_quotes,
            "refreshed_items": refreshed_items,
            "skipped": skipped,
            "failed": failed,
        }
    finally:
        await engine.dispose()


def enqueue_bulk_refresh(org_id: uuid.UUID, quote_ids: list[uuid.UUID]) -> str | None:
    """Dispatch the async batch; returns the Celery task id (or ``None`` on a broker
    hiccup — the caller surfaces that, never crashes)."""
    try:
        result = bulk_refresh_pricing_task.delay(str(org_id), [str(q) for q in quote_ids])
        return cast("str | None", result.id)
    except Exception:  # pragma: no cover - broker down must not 500 the request
        logger.warning("bulk_refresh_enqueue_failed", extra={"quote_count": len(quote_ids)})
        return None


@celery_app.task(
    base=BaseTask,
    name="app.bulk_refresh_pricing",
    bind=True,
    soft_time_limit=600,
    time_limit=660,
)
def bulk_refresh_pricing_task(self: Any, org_id: str, quote_ids: list[str]) -> dict[str, Any]:
    """Large-selection Bulk Refresh (spec E4-d). Loops the M1.10 engine off the
    request path; org-scoped, override-preserving."""
    task_id = self.request.id
    # Redelivery guard (M3.1 precedent): worker died after commit, before ack.
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    from .task_resources import resolve as resolve_task_resources

    db_url, _storage = resolve_task_resources()
    result = _run_on_own_loop(
        run_bulk_refresh(
            db_url, org_id=uuid.UUID(org_id), quote_ids=[uuid.UUID(q) for q in quote_ids]
        )
    )
    out = cast("dict[str, Any]", result)
    logger.info("bulk_refresh_done", extra={"task_id": task_id, "org_id": org_id, **out})
    return out
