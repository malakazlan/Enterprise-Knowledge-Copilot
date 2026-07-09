"""Prometheus metrics for the HTTP layer."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests.",
    labelnames=("method", "path", "status"),
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def render_metrics() -> tuple[bytes, str]:
    """Return the current metrics exposition and its content type."""
    return generate_latest(), CONTENT_TYPE_LATEST
