"""Readiness use case independent of FASTAPI and concrete infratstructure."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime


from src.application.ports.health import (
    ComponentHealth,
    ComponentStatus,
    HealthCheck,
    HealthObserver,
    ReadinessReport,
    ServiceStatus
)


logger = logging.getLogger(__name__)


class ReadinessService:
    """Run all  dependency checks concurrently and calculate service readiness."""

    def __init__(self,
                 checks: Sequence[HealthCheck],
                 *,
                 observer: HealthObserver | None = None) -> None:
        self._checks= checks
        self._observer = observer

    async def evaluate(self) -> ReadinessReport:
        """Return a determinsitic report; an individual check never aborts the rest."""

        components = await asyncio.gather(*(self._safe_check(check) for check in self._checks))
        critical_failure = any(not item.healthy and item.critical for item in components)
        optional_failure = any(not item.healthy and not item.critical for item in components)

        if critical_failure:
            status = ServiceStatus.NOT_READY
        elif optional_failure:
            status = ServiceStatus.DEGRADED
        else:
            status = ServiceStatus.READY

        report = ReadinessReport(
            status=status,
            ready=not critical_failure,
            checked_at=datetime.now(UTC),
            components=tuple(sorted(components, key=lambda item: item.component)),
        )

        if self._observer is not None:
            try:
                self._observer.observe_readiness(report)
            except:
                logger.exception(
                    "health observer failed",
                    extra = {
                        "event":"health obeserver failed"
                    }
                )

        return report

    @staticmethod
    async def _safe_check(check: HealthCheck) -> ComponentHealth:
        try:
            return await check.check()
        except Exception:
            logger.exception(
                "dependency health check raised unexpectedly",
                extra = {
                    "event":"dependency_health_check_failed",
                    "dependecy": check.name
                }
            )

            return ComponentHealth(
                component = check.name,
                status = ComponentStatus.UNHEALTHY,
                critical=check.critical,
                latency_ms=0.0,
                message="health check failed",
            )