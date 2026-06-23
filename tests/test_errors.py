"""Every error path returns the single envelope; no stack traces leak."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import AppError
from app.main import create_app
from tests.support import build_settings


def _error_app() -> FastAPI:
    app = create_app(build_settings())

    @app.get("/_t/app-error")
    async def _app_error() -> dict[str, str]:
        raise AppError("teapot", "I am a teapot", status_code=418, details={"x": 1})

    @app.get("/_t/boom")
    async def _boom() -> dict[str, str]:
        raise ValueError("internal-secret-detail")

    @app.get("/_t/validate")
    async def _validate(n: int) -> dict[str, int]:
        return {"n": n}

    return app


@pytest.fixture
def error_client() -> Iterator[TestClient]:
    # raise_server_exceptions=False so the 500 handler runs instead of re-raising.
    with TestClient(_error_app(), raise_server_exceptions=False) as test_client:
        yield test_client


def test_app_error_maps_to_envelope(error_client: TestClient) -> None:
    response = error_client.get("/_t/app-error")
    assert response.status_code == 418
    assert response.json() == {"code": "teapot", "message": "I am a teapot", "details": {"x": 1}}


def test_unhandled_error_is_masked(error_client: TestClient) -> None:
    response = error_client.get("/_t/boom")
    assert response.status_code == 500
    body = response.json()
    assert body == {"code": "internal_error", "message": "Internal server error", "details": None}
    # The internal exception message must never reach the client.
    assert "internal-secret-detail" not in response.text


def test_validation_error_uses_envelope(error_client: TestClient) -> None:
    response = error_client.get("/_t/validate", params={"n": "secret-value-xyz"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["details"], list)
    # The submitted (potentially sensitive) input must not be echoed back.
    assert "secret-value-xyz" not in response.text
    assert all("input" not in detail for detail in body["details"])


def test_not_found_uses_envelope(error_client: TestClient) -> None:
    response = error_client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "http_404"
