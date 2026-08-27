"""Top-level route composition."""

from fastapi import APIRouter

from src.api.routes import health, metrics
from src.core.config import AppSettings


def build_operational_router(settings: AppSettings) -> APIRouter:
    """Compose health and metrics routes from configuration."""

    router = APIRouter()
    router.include_router(health.router)
    if settings.observability.metrics_enabled:
        router.include_router(
            metrics.router,
            prefix=settings.observability.metrics_path,
        )
    return router


def build_api_router(settings: AppSettings) -> APIRouter:
    """Create the versioned business router used by later phases."""

    return APIRouter(prefix=settings.api_prefix)
