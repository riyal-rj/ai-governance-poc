"""Health-check contracts owned by the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

class ComponentStatus(StrEnum):
    HEALTHY="healthy"
    UNHEALTHY="unhealthy"


class ServiceStatus(StrEnum):
    READY="ready"
    DEGRADED="degraded"
    NOT_READY="not_ready"

@dataclass
class ComponentHealth:
    """Sanitized Result for checking one dependency."""

    component: str
    status: ComponentStatus
    critical: bool
    latency_ms: float
    message: str | None = None

    @property
    def healthy(self) -> bool:
        return self.status is ComponentStatus.HEALTHY

@dataclass(frozen = True, slots = True)
class ReadinessReport:
    """Aggregate Readiness decision returned by the health use case."""

    status: ServiceStatus
    ready: bool
    checked_at: datetime
    components: tuple[ComponentHealth, ...]

class HealthCheck(Protocol):
    """Port implemented by each infrastucture dependency probe."""

    @property
    def name(self) -> str:
        ...

    @property
    def critical(self) -> bool:
        ...

    async def check(self) -> ComponentHealth:
        ...


class HealthObserver(Protocol):
    """Optional telemetry sink notified after a readiness evaluation."""

    def observe_readiness(self, report: ReadinessReport) -> None: 
        ...

