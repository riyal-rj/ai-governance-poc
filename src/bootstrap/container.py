"""Explicit dependency container: the application's only composition root."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from src.application.services.health_service import ReadinessService
from src.core.config import AppSettings
from src.infrastructure.database import PostgresDatabase
from src.infrastructure.health_checks import OPAHealthCheck, PostgresHealthCheck
from src.infrastructure.http_client import create_http_client
from src.observability.metrics import Metrics


class Container(Protocol):
    """Dependencies exposed to http adapters and future use cases."""

    settings: AppSettings
    database: PostgresDatabase
    http_client: httpx.AsyncClient
    readiness: ReadinessService
    metrics: Metrics

    async def aclose(self) -> None: ...


@dataclass(slots=True)
class AppContainer:
    """Process-scoped dependency graph with deterministic cleanup."""

    settings: AppSettings
    database: PostgresDatabase
    http_client: httpx.AsyncClient
    readiness: ReadinessService
    metrics: Metrics
    _resources: AsyncExitStack = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._resources.aclose()


async def build_container(settings: AppSettings) -> AppContainer:
    """Construct concrete adapters and injects them into application services.

    The ``AsyncExitStack`` context manager is used to ensure that all resources
    are closed in the event of an exception.
    """

    resources = AsyncExitStack()
    try:
        metrics = Metrics(
            service_name=settings.service_name,
            service_version=settings.service_version,
            environment=settings.environment.value,
        )

        http_client = create_http_client(
            settings.http_client,
            service_name=settings.service_name,
            service_version=settings.service_version,
        )

        resources.push_async_callback(http_client.aclose)

        database = PostgresDatabase(settings.database, application_name=settings.service_name)

        await database.connect()
        resources.push_async_callback(database.aclose)

        health_checks = (
            PostgresHealthCheck(
                database, timeout_seconds=settings.database.connect_timeout_seconds
            ),
            OPAHealthCheck(
                http_client,
                base_url=settings.opa.base_url,
                health_path=settings.opa.health_path,
                timeout_seconds=settings.opa.health_timeout_seconds,
            ),
        )

        readiness = ReadinessService(health_checks, observer=metrics)

        return AppContainer(
            settings=settings,
            database=database,
            http_client=http_client,
            readiness=readiness,
            metrics=metrics,
            _resources=resources.pop_all(),
        )

    except BaseException:
        await resources.aclose()
        raise
