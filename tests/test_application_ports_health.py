from __future__ import annotations

from datetime import UTC, datetime

from src.application.ports.health import (
    ComponentHealth,
    ComponentStatus,
    ReadinessReport,
    ServiceStatus,
)


def test_component_health_healthy_true() -> None:
    component = ComponentHealth(
        component="postgres", status=ComponentStatus.HEALTHY, critical=True, latency_ms=1.2
    )
    assert component.healthy is True


def test_component_health_healthy_false() -> None:
    component = ComponentHealth(
        component="opa", status=ComponentStatus.UNHEALTHY, critical=True, latency_ms=1.2
    )
    assert component.healthy is False


def test_readiness_report_holds_components() -> None:
    component = ComponentHealth(
        component="postgres", status=ComponentStatus.HEALTHY, critical=True, latency_ms=0.5
    )
    report = ReadinessReport(
        status=ServiceStatus.READY,
        ready=True,
        checked_at=datetime.now(UTC),
        components=(component,),
    )
    assert report.components == (component,)
    assert report.ready is True
