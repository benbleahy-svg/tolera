"""Request-context middleware: request-id propagation."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_request_id_is_generated(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.headers.get("x-request-id")


def test_incoming_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "trace-abc"})
    assert response.headers["x-request-id"] == "trace-abc"
