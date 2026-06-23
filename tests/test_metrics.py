"""Baseline Prometheus metrics."""

from __future__ import annotations

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY


def _counter(method: str, path: str, status: str) -> float:
    value = REGISTRY.get_sample_value(
        "http_requests_total", {"method": method, "path": path, "status": status}
    )
    return value or 0.0


def test_metrics_endpoint_exposes_prometheus(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_request_duration_seconds" in response.text


def test_request_counter_increments(client: TestClient) -> None:
    before = _counter("GET", "/healthz", "200")
    client.get("/healthz")
    assert _counter("GET", "/healthz", "200") == before + 1
