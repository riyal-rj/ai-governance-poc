"""FAastAPI process lifecycle with bounded startup and graceful shutdown."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from time import monotonic

from fastapi import FastAPI

from src.bootstrap.container import Container
from src.core.config import AppSettings
from src.core.errors import AppError, StartUpError

logger = logging.getLogger(__name__)

ContainerFactory = Callable[[AppSettings], Awaitable[Container]]

def make_lifespan(settings: AppSettings,
                  container_factory : ContainerFactory) -> Callable[[FastAPI] , AbstractAsyncContextManager[None]]:
    """Create a lifespan function with injectable settings and factory"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
       container: Container | None = None
       try:
           container = await _create_container_with_retry(settings, container_factory)
           app.state.container = container

           if settings.startup.require_ready:
               await _wait_untill_ready(container, settings)

           assert container is not None
           container.metrics.service_ready.set(1)
           logger.info(
               "application started",
               extra = {
                   "event":"application_started",
                    "component":settings.service_name
               }
           )
           yield
       finally:
           if container is not None:
               container.metrics.service_ready.set(0)
               await container.aclose()
           if hasattr(app.state,"container"):
               del app.state.container
           logger.info(
               "application stopped",
               extra = {
                   "event":"application_stopped",
                    "component":settings.service_name
               }
           )

    return lifespan

async def _create_container_with_retry(settings: AppSettings,
                                       container_factory: ContainerFactory) -> Container:
    deadline = monotonic() + settings.startup.timeout_seconds
    delay = settings.startup.initial_backoff_seconds
    unavailable = {"container"}


    while True:
        try:
            return await container_factory(settings)
        except AppError as exc:
            dependency = exc.details["dependency"]
            unavailable = {str(dependency)} if dependency else {"container"}
            logger.warning(
                "dependency graph  construction failed, retrying",
                extra = {
                    "event":"container_build_retry",
                    "dependency":",".join(unavailable)
                }
            )
        except Exception:
            unavailable = {"container"}
            logger.exception(
                "dependency graph construction failed, retrying",
                extra = {
                    "event":"container_build_retry",
                    "dependency":"container"
                }
            )

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise StartUpError(list(unavailable))
        await asyncio.sleep(min(delay, remaining))
        delay = min(delay * 2, settings.startup.max_backoff_seconds)


async def _wait_untill_ready(container:Container, settings: AppSettings) -> None:
    deadline = monotonic() + settings.startup.timeout_seconds
    delay = settings.startup.initial_backoff_seconds
    unavailable:list[str] = []

    while True:
        report = await container.readiness.evaluate()
        if report.ready:
            return
        unavailable =[
            item.component for item in report.components if item.critical and not item.healthy
        ]
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise StartUpError(unavailable)
        logger.warning(
            "critical dependencies not ready, retrying",
            extra={
                "event":"critical_dependency_not_ready",
                "dependency":",".join(unavailable)
            }
        )
        await asyncio.sleep(min(delay, remaining))
        delay = min(delay * 2, settings.startup.max_backoff_seconds)
