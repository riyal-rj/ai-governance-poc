"""FastAPI process lifecycle with bounded startup and graceful shutdown."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from time import monotonic

from fastapi import FastAPI

from src.bootstrap.container import Container
from src.core.config import AppSettings
from src.core.errors import AppError, StartupError

logger = logging.getLogger(__name__)

ContainerFactory = Callable[[AppSettings], Awaitable[Container]]


def make_lifespan(
    settings: AppSettings, container_factory: ContainerFactory
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Create a lifespan function with injectable settings and factory"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container: Container | None = None
        try:
            deadline = monotonic() + settings.startup.timeout_seconds
            container = await _create_container_with_retry(
                settings,
                container_factory,
                deadline=deadline,
            )
            app.state.container = container

            if settings.startup.require_ready:
                await _wait_until_ready(container, settings, deadline=deadline)
                ready = True
            else:
                ready = (await container.readiness.evaluate()).ready

            assert container is not None
            container.metrics.service_ready.set(1 if ready else 0)
            logger.info(
                "application started",
                extra={"event": "application_started", "component": settings.service_name},
            )
            yield
        finally:
            if container is not None:
                container.metrics.service_ready.set(0)
                await container.aclose()
            if hasattr(app.state, "container"):
                del app.state.container
            logger.info(
                "application stopped",
                extra={"event": "application_stopped", "component": settings.service_name},
            )

    return lifespan


async def _create_container_with_retry(
    settings: AppSettings,
    container_factory: ContainerFactory,
    *,
    deadline: float,
) -> Container:
    delay = settings.startup.initial_backoff_seconds
    unavailable = {"container"}

    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise StartupError(list(unavailable))
        try:
            async with asyncio.timeout(remaining):
                return await container_factory(settings)
        except TimeoutError as exc:
            raise StartupError(list(unavailable)) from exc
        except AppError as exc:
            if not exc.retryable:
                raise
            dependency = exc.details.get("dependency")
            unavailable = {str(dependency)} if dependency else {"container"}
            logger.warning(
                "dependency graph construction failed, retrying",
                extra={"event": "container_build_retry", "dependency": ",".join(unavailable)},
            )
        except Exception as exc:
            logger.exception(
                "dependency graph construction failed",
                extra={"event": "container_build_failed", "dependency": "container"},
            )
            raise StartupError(["container"]) from exc

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise StartupError(list(unavailable))
        await asyncio.sleep(min(delay, remaining))
        delay = min(delay * 2, settings.startup.max_backoff_seconds)


async def _wait_until_ready(
    container: Container,
    settings: AppSettings,
    *,
    deadline: float,
) -> None:
    delay = settings.startup.initial_backoff_seconds
    unavailable: list[str] = []

    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise StartupError(unavailable or ["readiness"])
        try:
            async with asyncio.timeout(remaining):
                report = await container.readiness.evaluate()
        except TimeoutError as exc:
            raise StartupError(unavailable or ["readiness"]) from exc
        if report.ready:
            return
        unavailable = [
            item.component for item in report.components if item.critical and not item.healthy
        ]
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise StartupError(unavailable or ["readiness"])
        logger.warning(
            "critical dependencies not ready, retrying",
            extra={"event": "critical_dependency_not_ready", "dependency": ",".join(unavailable)},
        )
        await asyncio.sleep(min(delay, remaining))
        delay = min(delay * 2, settings.startup.max_backoff_seconds)
