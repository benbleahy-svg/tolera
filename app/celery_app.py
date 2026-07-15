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
    include=["app.tasks", "app.file_split", "app.email_ingest"],
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
)
