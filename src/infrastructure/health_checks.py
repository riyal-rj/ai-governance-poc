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
    """Verify that OPA has the required policy loaded and evaluating, not merely alive.

    A plain process/HTTP health probe would still report healthy if OPA is running
    with no bundle loaded. Querying the decision document confirms the policy this
    application depends on is actually present and produces the expected boolean.
    """

    name = "opa"
    critical = True

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        decision_path: str,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._url = f"{base_url}{decision_path}"
        self._timeout_seconds = timeout_seconds

    async def check(self) -> ComponentHealth:
        started = perf_counter()
        try:
            response = await self._client.get(self._url, timeout=self._timeout_seconds)
            response.raise_for_status()
            payload = response.json()
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
        except ValueError:
            logger.warning(
                "opa readiness check received a non-json response",
                extra={"event": "opa_health_failed", "dependency": self.name},
            )
            return self._result(
                ComponentStatus.UNHEALTHY,
                started,
                "policy decision response was not valid json",
            )

        if not isinstance(payload, dict) or payload.get("result") is not True:
            logger.warning(
                "opa decision document did not evaluate to true",
                extra={"event": "opa_health_failed", "dependency": self.name},
            )
            return self._result(
                ComponentStatus.UNHEALTHY,
                started,
                "required policy is not loaded or did not evaluate to true",
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
