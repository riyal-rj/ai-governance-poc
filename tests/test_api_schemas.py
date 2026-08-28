from __future__ import annotations

from datetime import UTC, datetime

from src.api.schemas import (
    ComponentHealthResponse,
    ErrorBody,
    ErrorResponse,
    LivenessResponse,
    ReadinessResponse,
)
from src.application.ports.health import (
    ComponentHealth,
    ComponentStatus,
    ReadinessReport,
    ServiceStatus,
)


def test_component_health_response_from_result() -> None:
    result = ComponentHealth(
        component="postgres", status=ComponentStatus.HEALTHY, critical=True, latency_ms=3.5
    )
    response = ComponentHealthResponse.from_result(result)
    assert response.component == "postgres"
    assert response.status == "healthy"
    assert response.critical is True
    assert response.latency_ms == 3.5
    assert response.message is None


def test_liveness_response_defaults_status_alive() -> None:
    response = LivenessResponse(service="finassist-api", version="0.1.0")
    assert response.status == "alive"


def test_readiness_response_from_report() -> None:
    checked_at = datetime.now(UTC)
    report = ReadinessReport(
        status=ServiceStatus.DEGRADED,
        ready=True,
        checked_at=checked_at,
        components=(
            ComponentHealth(
                component="cache", status=ComponentStatus.UNHEALTHY, critical=False, latency_ms=1.0
            ),
        ),
    )
    response = ReadinessResponse.from_report(report)
    assert response.status == "degraded"
    assert response.ready is True
    assert response.checked_at == checked_at
    assert len(response.components) == 1
    assert response.components[0].component == "cache"


def test_error_body_defaults() -> None:
    body = ErrorBody(code="input_invalid", message="bad request")
    assert body.retryable is False
    assert body.details == {}


def test_error_response_round_trips_via_model_dump() -> None:
    response = ErrorResponse(
        error=ErrorBody(code="resource_not_found", message="not found"),
        request_id="req-1",
        timestamp=datetime.now(UTC),
        path="/api/v1/disputes/1",
    )
    dumped = response.model_dump(mode="json")
    assert dumped["error"]["code"] == "resource_not_found"
    assert dumped["path"] == "/api/v1/disputes/1"
