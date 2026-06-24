"""Liveness + readiness probes.

``/healthz`` answers "is the process up?" without touching anything external.
``/readyz`` is the architectural tracer: it round-trips a read through Postgres
(the M0.1 acceptance criterion) and reports the applied Alembic revision.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe — no I/O."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, str | int | None]:
    """Readiness probe — round-trips a read through Postgres.

    ``SELECT 1`` proves connectivity (the readiness signal). The applied Alembic
    revision is read best-effort: it is informational and absent before the
    baseline migration has run, so it never fails the probe on its own.
    """
    engine: AsyncEngine = request.app.state.engine
    try:
        async with engine.connect() as conn:
            select_one = (await conn.execute(text("SELECT 1"))).scalar_one()
            alembic_rev = await _read_alembic_rev(conn)
    except Exception as exc:
        # Log only the error class — a DB connection error can embed the DSN in
        # its message/stack, and secrets must never reach the logs (CLAUDE.md §5).
        logger.warning("readiness_check_failed", extra={"error_type": type(exc).__name__})
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "db": "error"}

    return {
        "status": "ready",
        "db": "ok",
        "select_1": select_one,
        "alembic_rev": alembic_rev,
    }


async def _read_alembic_rev(conn: AsyncConnection) -> str | None:
    """Return the applied migration revision, or ``None`` if not yet migrated."""
    try:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        return result.scalar_one_or_none()
    except Exception:
        return None
