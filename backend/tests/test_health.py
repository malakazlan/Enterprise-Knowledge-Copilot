"""Tests for health probes, root, request-id propagation, and metrics."""

from __future__ import annotations

from httpx import AsyncClient


async def test_liveness_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["service"]


async def test_readiness_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    names = {check["name"] for check in body["checks"]}
    assert "database" in names
    assert all(check["healthy"] for check in body["checks"])


async def test_root_returns_service_info(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"]


async def test_request_id_header_is_returned(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.headers.get("X-Request-ID")
    assert resp.headers.get("X-Process-Time-Ms")


async def test_request_id_is_echoed_when_provided(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live", headers={"X-Request-ID": "trace-123"})
    assert resp.headers.get("X-Request-ID") == "trace-123"


async def test_unknown_route_returns_error_envelope(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    assert "error" in resp.json()


async def test_metrics_endpoint(client: AsyncClient) -> None:
    await client.get("/api/v1/health/live")
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert b"http_requests_total" in resp.content
