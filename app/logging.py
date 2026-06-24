"""Structured JSON logging shared by the API and Celery workers (CLAUDE.md §5).

Every log line is a single JSON object carrying a ``request_id`` and ``org_id``
pulled from context variables, so a request (or job) can be traced end to end.
Secrets and customer PII / print contents must never be passed to the logger.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Request/job-scoped context. ``org_id`` stays ``None`` until auth lands in M0.2.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
org_id_var: ContextVar[str | None] = ContextVar("org_id", default=None)

# Standard ``LogRecord`` attributes — anything else passed via ``extra`` is
# treated as a structured field and merged into the JSON payload.
_RESERVED = frozenset(vars(logging.makeLogRecord({})).keys() | {"message", "asctime", "taskName"})


class JsonFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "org_id": org_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Route uvicorn's loggers through the root handler instead of their own.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
