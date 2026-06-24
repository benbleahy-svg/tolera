"""Celery base task + an idempotent example (CLAUDE.md §5).

``BaseTask`` is the policy every later task inherits: retried with exponential
backoff, timeout-bounded (via :mod:`app.celery_app`), and dead-lettered on final
failure. ``example_idempotent`` proves the idempotent-on-retry property the M0.1
acceptance requires; the actual logic lives in the pure :func:`apply_idempotent`
so it can be unit-tested without a broker.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

from celery import Task

from .celery_app import celery_app
from .metrics import celery_tasks_total

logger = logging.getLogger("app.tasks")


class BaseTask(Task):
    """Shared task policy: retry-with-backoff, bounded, dead-lettered."""

    autoretry_for = (Exception,)
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    def on_success(
        self, retval: Any, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        celery_tasks_total.labels(self.name, "success").inc()

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        celery_tasks_total.labels(self.name, "retry").inc()

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        # Retries exhausted → dead-letter. A durable DLQ sink lands with the jobs work.
        celery_tasks_total.labels(self.name, "failure").inc()
        logger.error(
            "task_dead_lettered",
            extra={"task": self.name, "task_id": task_id, "exc_type": type(exc).__name__},
        )


def apply_idempotent(
    item_id: str, payload: str, store: MutableMapping[str, dict[str, Any]]
) -> dict[str, Any]:
    """Idempotent unit of work, keyed on ``item_id``.

    A first call records the result and reports ``created=True``; any re-run
    (e.g. a Celery retry) returns the same result with ``created=False`` and
    performs no duplicate side effect.
    """
    cached = store.get(item_id)
    if cached is not None:
        return {**cached, "created": False}
    result: dict[str, Any] = {"item_id": item_id, "value": payload.upper()}
    store[item_id] = result
    return {**result, "created": True}


# Process-local stand-in for durable, keyed storage (real persistence: M0.2+).
_STORE: dict[str, dict[str, Any]] = {}


@celery_app.task(base=BaseTask, name="app.example_idempotent")
def example_idempotent(item_id: str, payload: str) -> dict[str, Any]:
    """Example task delegating to the idempotent core."""
    return apply_idempotent(item_id, payload, _STORE)
