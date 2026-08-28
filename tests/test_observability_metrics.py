from __future__ import annotations

from datetime import UTC, datetime

from src.application.ports.health import (
    ComponentHealth,
    ComponentStatus,
    ReadinessReport,
    ServiceStatus,
)
from src.observability.metrics import Metrics


def _metrics() -> Metrics:
    return Metrics(service_name="finassist-api", service_version="0.1.0", environment="local")


def test_observe_http_updates_counters_and_histogram() -> None:
    metrics = _metrics()
    metrics.observe_http(method="GET", route="/health/live", status_code=200, duration_seconds=0.01)

    body, _content_type = metrics.render()
    text = body.decode("utf-8")
    assert (
        'finassist_http_requests_total{method="GET",route="/health/live",status_code="200"}' in text
    )


def test_observe_readiness_sets_service_ready_and_dependency_gauges() -> None:
    metrics = _metrics()
    report = ReadinessReport(
        status=ServiceStatus.READY,
        ready=True,
        checked_at=datetime.now(UTC),
        components=(
            ComponentHealth(
                component="postgres", status=ComponentStatus.HEALTHY, critical=True, latency_ms=5.0
            ),
        ),
    )

    metrics.observe_readiness(report)

    body, _content_type = metrics.render()
    text = body.decode("utf-8")
    assert "finassist_service_ready 1.0" in text
    assert 'finassist_dependency_up{component="postgres",critical="true"} 1.0' in text


def test_observe_readiness_marks_not_ready() -> None:
    metrics = _metrics()
    report = ReadinessReport(
        status=ServiceStatus.NOT_READY,
        ready=False,
        checked_at=datetime.now(UTC),
        components=(),
    )

    metrics.observe_readiness(report)

    body, _content_type = metrics.render()
    assert "finassist_service_ready 0.0" in body.decode("utf-8")


def test_render_returns_prometheus_content_type() -> None:
    metrics = _metrics()
    _body, content_type = metrics.render()
    assert content_type.startswith("text/plain")


def test_registries_are_independent_per_instance() -> None:
    first = _metrics()
    second = _metrics()
    first.observe_http(method="GET", route="/x", status_code=200, duration_seconds=0.01)

    second_text = second.render()[0].decode("utf-8")
    assert 'route="/x"' not in second_text
