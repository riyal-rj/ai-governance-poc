"""Concrete readiness probes for mandatory infrastructure dependencies."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter

import httpx

from src.application.ports.health import ComponentHealth, ComponentStatus
from src.infrastructure.database import PostgresDatabase

logger = logging.getLogger(__name__)


class PostgresHealthCheck:
    """Verify that a query can acquire and use a pooled DB connection."""

    name = "postgres"
    critical = True

    def __init__(self, database: PostgresDatabase, *, timeout_seconds: float) -> None:
        self._database = database
        self._timeout_seconds = timeout_seconds

    async def check(self) -> ComponentHealth:
        started = perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._database.ping()
        except Exception:
            logger.warning(
                "postgres readiness check failed",
                extra={"event": "postgres_health_failed", "dependency": self.name},
            )
            return self._result(ComponentStatus.UNHEALTHY, started, "database unavailable")
        return self._result(ComponentStatus.HEALTHY, started)

    def _result(
        self, status: ComponentStatus, started: float, message: str | None = None
    ) -> ComponentHealth:
        return ComponentHealth(
            component=self.name,
            status=status,
            critical=self.critical,
            latency_ms=(perf_counter() - started) * 1000,
            message=message,
        )


class OPAHealthCheck:
    """Verify that the policy decision point is reachable before serving traffic."""

    name = "opa"
    critical = True

    def __init__(
        self, client: httpx.AsyncClient, *, base_url: str, health_path: str, timeout_seconds: float
    ) -> None:
        self._client = client
        self._url = f"{base_url}{health_path}"
        self._timeout_seconds = timeout_seconds

    async def check(self) -> ComponentHealth:
        started = perf_counter()
        try:
            response = await self._client.get(self._url, timeout=self._timeout_seconds)
            response.raise_for_status()
        except (httpx.HTTPError, TimeoutError):
            logger.warning(
                "opa readiness check failed",
                extra={"event": "opa_health_failed", "dependency": self.name},
            )
            return self._result(
                ComponentStatus.UNHEALTHY,
                started,
                "policy service unavailable",
            )

        return self._result(ComponentStatus.HEALTHY, started)

    def _result(
        self, status: ComponentStatus, started: float, message: str | None = None
    ) -> ComponentHealth:
        return ComponentHealth(
            component=self.name,
            status=status,
            critical=self.critical,
            latency_ms=(perf_counter() - started) * 1000,
            message=message,
        )
