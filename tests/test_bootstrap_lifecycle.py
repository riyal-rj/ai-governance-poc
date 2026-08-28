from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.application.ports.health import (
    ComponentHealth,
    ComponentStatus,
    ReadinessReport,
    ServiceStatus,
)
from src.bootstrap.lifecycle import _create_container_with_retry, _wait_until_ready, make_lifespan
from src.core.config import AppSettings, DatabaseSettings, StartupSettings
from src.core.errors import AuthRequiredError, DependencyUnavailableError, StartupError
from src.observability.metrics import Metrics


def _settings(**startup_overrides: object) -> AppSettings:
    defaults: dict[str, object] = {
        "require_ready": True,
        "timeout_seconds": 1.0,
        "initial_backoff_seconds": 0.01,
        "max_backoff_seconds": 0.02,
    }
    defaults.update(startup_overrides)
    return AppSettings(
        _env_file=None,
        database=DatabaseSettings(dsn="postgresql://u:p@h:5432/d"),
        startup=StartupSettings(**defaults),  # type: ignore[arg-type]
    )


class SequenceReadiness:
    def __init__(self, reports: list[ReadinessReport]) -> None:
        self._reports = reports
        self.calls = 0

    async def evaluate(self) -> ReadinessReport:
        index = min(self.calls, len(self._reports) - 1)
        self.calls += 1
        return self._reports[index]


def _report(*, ready: bool, critical_unhealthy: str | None = None) -> ReadinessReport:
    components: tuple[ComponentHealth, ...] = ()
    if critical_unhealthy:
        components = (
            ComponentHealth(
                component=critical_unhealthy,
                status=ComponentStatus.UNHEALTHY,
                critical=True,
                latency_ms=1.0,
            ),
        )
    return ReadinessReport(
        status=ServiceStatus.READY if ready else ServiceStatus.NOT_READY,
        ready=ready,
        checked_at=datetime.now(UTC),
        components=components,
    )


@dataclass
class FakeContainer:
    settings: AppSettings
    readiness: SequenceReadiness
    metrics: Metrics = field(
        default_factory=lambda: Metrics(service_name="s", service_version="1", environment="local")
    )
    aclose_calls: int = 0

    async def aclose(self) -> None:
        self.aclose_calls += 1


class TestMakeLifespan:
    async def test_require_ready_true_starts_and_stops_cleanly(self) -> None:
        settings = _settings(require_ready=True)
        container = FakeContainer(
            settings=settings, readiness=SequenceReadiness([_report(ready=True)])
        )

        async def factory(_settings: AppSettings) -> FakeContainer:
            return container

        app: Any = SimpleNamespace(state=SimpleNamespace())
        lifespan = make_lifespan(settings, factory)

        async with lifespan(app):
            assert app.state.container is container
            assert "finassist_service_ready 1.0" in container.metrics.render()[0].decode()

        assert not hasattr(app.state, "container")
        assert container.aclose_calls == 1
        assert "finassist_service_ready 0.0" in container.metrics.render()[0].decode()

    async def test_require_ready_false_evaluates_once(self) -> None:
        settings = _settings(require_ready=False)
        readiness = SequenceReadiness([_report(ready=False)])
        container = FakeContainer(settings=settings, readiness=readiness)

        async def factory(_settings: AppSettings) -> FakeContainer:
            return container

        app: Any = SimpleNamespace(state=SimpleNamespace())
        lifespan = make_lifespan(settings, factory)

        async with lifespan(app):
            assert readiness.calls == 1
            assert "finassist_service_ready 0.0" in container.metrics.render()[0].decode()


class TestCreateContainerWithRetry:
    async def test_retries_retryable_app_error_then_succeeds(self) -> None:
        settings = _settings()
        attempts = {"count": 0}
        container = FakeContainer(
            settings=settings, readiness=SequenceReadiness([_report(ready=True)])
        )

        async def factory(_settings: AppSettings) -> FakeContainer:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise DependencyUnavailableError("postgres")
            return container

        deadline = time.monotonic() + 2.0
        result = await _create_container_with_retry(settings, factory, deadline=deadline)

        assert result is container
        assert attempts["count"] == 2

    async def test_raises_startup_error_after_deadline(self) -> None:
        settings = _settings()

        async def always_fails(_settings: AppSettings) -> FakeContainer:
            raise DependencyUnavailableError("postgres")

        deadline = time.monotonic() + 0.05
        with pytest.raises(StartupError):
            await _create_container_with_retry(settings, always_fails, deadline=deadline)

    async def test_non_retryable_app_error_propagates_immediately(self) -> None:
        settings = _settings()
        attempts = {"count": 0}

        async def factory(_settings: AppSettings) -> FakeContainer:
            attempts["count"] += 1
            raise AuthRequiredError()

        deadline = time.monotonic() + 2.0
        with pytest.raises(AuthRequiredError):
            await _create_container_with_retry(settings, factory, deadline=deadline)
        assert attempts["count"] == 1

    async def test_unexpected_exception_becomes_startup_error(self) -> None:
        settings = _settings()

        async def factory(_settings: AppSettings) -> FakeContainer:
            raise ValueError("unexpected")

        deadline = time.monotonic() + 2.0
        with pytest.raises(StartupError):
            await _create_container_with_retry(settings, factory, deadline=deadline)


class TestWaitUntilReady:
    async def test_retries_until_ready(self) -> None:
        settings = _settings()
        readiness = SequenceReadiness(
            [_report(ready=False), _report(ready=False), _report(ready=True)]
        )
        container = FakeContainer(settings=settings, readiness=readiness)

        deadline = time.monotonic() + 2.0
        await _wait_until_ready(container, settings, deadline=deadline)

        assert readiness.calls == 3

    async def test_raises_startup_error_after_deadline(self) -> None:
        settings = _settings()
        readiness = SequenceReadiness([_report(ready=False, critical_unhealthy="opa")])
        container = FakeContainer(settings=settings, readiness=readiness)

        deadline = time.monotonic() + 0.05
        with pytest.raises(StartupError):
            await _wait_until_ready(container, settings, deadline=deadline)
