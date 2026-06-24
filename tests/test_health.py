"""Health + readiness probes — the M0.1 acceptance oracle."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.support import build_settings


def test_healthz_is_live(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_round_trips_postgres(db_client: TestClient) -> None:
    """The walking-skeleton property: a request reaches Postgres and back."""
    response = db_client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["db"] == "ok"
    assert body["select_1"] == 1
    # alembic_rev is None on a fresh DB, else a non-empty revision string. Kept
    # revision-agnostic so each new migration doesn't break the readiness test.
    rev = body["alembic_rev"]
    assert rev is None or (isinstance(rev, str) and rev)


def test_readyz_returns_503_when_db_unreachable() -> None:
    unreachable = build_settings(database_url="postgresql+asyncpg://x:x@127.0.0.1:1/none")
    with TestClient(create_app(unreachable)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "db": "error"}
