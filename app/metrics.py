"""Baseline Prometheus metrics + the ``/metrics`` endpoint (CLAUDE.md §5).

Exposes the signals the spec calls out from day one: request latency, request
counts (status-labelled), Celery job success/failure, and queue depth. Labels
use the matched **route template** (not the raw path) to bound cardinality.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

logger = logging.getLogger("app.metrics")

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "path", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Celery task outcomes.",
    ["task", "state"],
)
celery_queue_depth = Gauge(
    "celery_queue_depth",
    "Approximate number of tasks waiting in the default Celery queue.",
)


def observe_queue_depth(redis_url: str, queue: str = "celery") -> None:
    """Best-effort: set the queue-depth gauge from Redis. Never raises."""
    try:
        import redis

        client = redis.Redis.from_url(redis_url)
        try:
            celery_queue_depth.set(client.llen(queue))
        finally:
            client.close()
    except Exception:
        # Metrics must never break a scrape.
        logger.debug("queue_depth_unavailable", exc_info=True)


def register_metrics(app: FastAPI) -> None:
    """Mount ``GET /metrics``."""

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        settings = app.state.settings
        observe_queue_depth(settings.redis_url)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
