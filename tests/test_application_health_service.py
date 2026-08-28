from __future__ import annotations

from src.application.ports.health import (
    ComponentHealth,
    ComponentStatus,
    ReadinessReport,
    ServiceStatus,
)
from src.application.services.health_service import ReadinessService


class FakeHealthCheck:
    def __init__(self, name: str, *, critical: bool, healthy: bool) -> None:
        self.name = name
        self.critical = critical
        self._healthy = healthy

    async def check(self) -> ComponentHealth:
        status = ComponentStatus.HEALTHY if self._healthy else ComponentStatus.UNHEALTHY
        return ComponentHealth(
            component=self.name, status=status, critical=self.critical, latency_ms=1.0
        )


class RaisingHealthCheck:
    name = "flaky"
    critical = True

    async def check(self) -> ComponentHealth:
        raise RuntimeError("boom")


class FakeObserver:
    def __init__(self) -> None:
        self.reports: list[ReadinessReport] = []

    def observe_readiness(self, report: ReadinessReport) -> None:
        self.reports.append(report)


class RaisingObserver:
    def observe_readiness(self, report: ReadinessReport) -> None:
        raise RuntimeError("observer exploded")


async def test_all_healthy_is_ready() -> None:
    service = ReadinessService(
        [FakeHealthCheck("postgres", critical=True, healthy=True)],
    )
    report = await service.evaluate()
    assert report.ready is True
    assert report.status is ServiceStatus.READY


async def test_critical_failure_is_not_ready() -> None:
    service = ReadinessService(
        [
            FakeHealthCheck("postgres", critical=True, healthy=False),
            FakeHealthCheck("opa", critical=True, healthy=True),
        ],
    )
    report = await service.evaluate()
    assert report.ready is False
    assert report.status is ServiceStatus.NOT_READY


async def test_optional_failure_is_degraded() -> None:
    service = ReadinessService(
        [
            FakeHealthCheck("postgres", critical=True, healthy=True),
            FakeHealthCheck("cache", critical=False, healthy=False),
        ],
    )
    report = await service.evaluate()
    assert report.ready is True
    assert report.status is ServiceStatus.DEGRADED


async def test_components_are_sorted_by_name() -> None:
    service = ReadinessService(
        [
            FakeHealthCheck("postgres", critical=True, healthy=True),
            FakeHealthCheck("opa", critical=True, healthy=True),
        ],
    )
    report = await service.evaluate()
    assert [c.component for c in report.components] == ["opa", "postgres"]


async def test_one_check_raising_does_not_abort_the_others() -> None:
    service = ReadinessService(
        [RaisingHealthCheck(), FakeHealthCheck("postgres", critical=True, healthy=True)],
    )
    report = await service.evaluate()
    assert report.ready is False
    flaky = next(c for c in report.components if c.component == "flaky")
    assert flaky.status is ComponentStatus.UNHEALTHY
    assert flaky.message == "health check failed"


async def test_observer_is_notified() -> None:
    observer = FakeObserver()
    service = ReadinessService(
        [FakeHealthCheck("postgres", critical=True, healthy=True)], observer=observer
    )
    report = await service.evaluate()
    assert observer.reports == [report]


async def test_observer_failure_does_not_propagate() -> None:
    service = ReadinessService(
        [FakeHealthCheck("postgres", critical=True, healthy=True)], observer=RaisingObserver()
    )
    report = await service.evaluate()
    assert report.ready is True
