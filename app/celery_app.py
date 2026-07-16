"""Celery application — broker/result backend on Redis (CLAUDE.md §5).

Task policy (idempotent, retried-with-backoff, timeout-bounded, dead-lettered)
lives on ``BaseTask`` in :mod:`app.tasks`.
"""

from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

celery_app = Celery(
    "tolera",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Every module defining a task must be listed: a worker imports only these,
    # so an omitted module's task is never registered and its `.delay()` dies as
    # an unregistered task at runtime (the API process hides this — it imports
    # the module via its router, so eager/in-process dispatch still works).
    include=[
        "app.tasks",
        "app.file_split",
        "app.email_ingest",
        "app.email_sync",
        "app.lens_extract",
        "app.review_items",
        "app.triage",
    ],
)

celery_app.conf.update(
    task_default_queue="celery",
    task_acks_late=True,  # redeliver if a worker dies mid-task
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=300,  # hard timeout (s)
    task_soft_time_limit=270,  # soft timeout (s)
    worker_max_tasks_per_child=200,
    result_expires=3600,
    # M3.5 — the inbound-mail poll ("Celery task every 5 min", spec
    # #email-connectivity). Sync tasks ride a dedicated "email" queue so the
    # worker serving it can cap concurrency (spec build note: N active users
    # must not flood the provider APIs).
    beat_schedule={
        "email-sync": {
            "task": "app.email_sync_all",
            "schedule": settings.email_sync_interval_seconds,
        },
    },
    task_routes={
        "app.email_sync_all": {"queue": "email"},
        "app.email_sync_connection": {"queue": "email"},
    },
)
