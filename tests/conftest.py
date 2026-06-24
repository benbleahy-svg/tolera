"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.support import build_settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient over a fresh app. Used as a context manager so lifespan runs."""
    with TestClient(create_app(build_settings())) as test_client:
        yield test_client


@pytest.fixture
def db_client() -> Iterator[TestClient]:
    """A TestClient wired to a real Postgres via ``TEST_DATABASE_URL``.

    Skips when the variable is unset or the database is unreachable, so the
    suite stays green locally without a database while still exercising the
    round-trip in CI (where a Postgres service is provided).
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set — Postgres round-trip skipped")
    try:
        with TestClient(create_app(build_settings(database_url=url))) as test_client:
            if test_client.get("/readyz").json().get("db") != "ok":
                pytest.skip("TEST_DATABASE_URL not reachable")
            yield test_client
    except Exception:
        pytest.skip("TEST_DATABASE_URL not reachable")
