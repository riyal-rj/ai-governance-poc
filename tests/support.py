"""Test-only doubles shared across the API integration tests.

Not a test module itself (no `test_` prefix) so pytest does not collect it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi.testclient import TestClient

from src.application.ports.health import ComponentHealth, ComponentStatus
from src.application.services.health_service import ReadinessService
from src.bootstrap.container import Container
from src.core.config import AppSettings, DatabaseSettings, StartupSettings
from src.main import create_app
from src.observability.metrics import Metrics


class FakeHealthCheck:
    def __init__(self, name: str, *, critical: bool = True, healthy: bool = True) -> None:
        self.name = name
        self.critical = critical
        self._healthy = healthy

    async def check(self) -> ComponentHealth:
        status = ComponentStatus.HEALTHY if self._healthy else ComponentStatus.UNHEALTHY
        return ComponentHealth(
            component=self.name, status=status, critical=self.critical, latency_ms=1.0
        )


@dataclass
class FakeContainer:
    """Structurally compatible with the `Container` protocol, no real I/O."""

    settings: AppSettings
    metrics: Metrics
    readiness: ReadinessService
    database: object = None
    http_client: object = None
    aclose_calls: int = 0

    async def aclose(self) -> None:
        self.aclose_calls += 1


def make_settings(**overrides: object) -> AppSettings:
    """Defaults `require_ready=False` so `TestClient` startup never blocks on a
    (fake) dependency a test deliberately made unhealthy; pass `startup=` to
    override.
    """

    defaults: dict[str, object] = {
        "_env_file": None,
        "database": DatabaseSettings(dsn="postgresql://u:p@h:5433/d"),
        "startup": StartupSettings(
            require_ready=False,
            timeout_seconds=1.0,
            initial_backoff_seconds=0.01,
            max_backoff_seconds=0.02,
        ),
    }
    defaults.update(overrides)
    return AppSettings(**defaults)  # type: ignore[arg-type]


def make_container_factory(
    *, healthy: bool = True
) -> Callable[[AppSettings], Awaitable[Container]]:
    async def factory(settings: AppSettings) -> Container:
        metrics = Metrics(
            service_name=settings.service_name,
            service_version=settings.service_version,
            environment=settings.environment.value,
        )
        checks = [
            FakeHealthCheck("postgres", critical=True, healthy=healthy),
            FakeHealthCheck("opa", critical=True, healthy=healthy),
        ]
        readiness = ReadinessService(checks, observer=metrics)
        return FakeContainer(settings=settings, metrics=metrics, readiness=readiness)

    return factory


def make_client(settings: AppSettings | None = None, *, healthy: bool = True) -> TestClient:
    resolved = settings or make_settings()
    app = create_app(settings=resolved, container_factory=make_container_factory(healthy=healthy))
    return TestClient(app)
