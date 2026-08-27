from __future__ import annotations

from fastapi import FastAPI

from src.api.error_handlers import install_error_handlers
from src.api.router import build_api_router, build_operational_router
from src.bootstrap.container import build_container
from src.bootstrap.lifecycle import ContainerFactory, make_lifespan
from src.core.config import AppSettings, load_settings
from src.core.logging import configure_logging
from src.observability.http_middleware import RequestTelemetryMiddleware


def create_app(
    settings: AppSettings | None = None, container_factory: ContainerFactory | None = None
) -> FastAPI:
    """Build one independently testable ASGI application instance.

    ``settings`` and ```container_factory`` are used to build the application.
    """

    resolved_settings = settings or load_settings()
    configure_logging(level=resolved_settings.log_level, json_logs=resolved_settings.log_json)

    app = FastAPI(
        title="FinAssist API",
        description="Governed digital-lending decision-support platform",
        version=resolved_settings.service_version,
        debug=resolved_settings.debug,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.docs_enabled else None,
        openapi_url="/openapi.json" if resolved_settings.docs_enabled else None,
        lifespan=make_lifespan(
            resolved_settings,
            container_factory or build_container,
        ),
    )
    app.state.settings = resolved_settings

    install_error_handlers(app)
    app.add_middleware(
        RequestTelemetryMiddleware,
        request_id_header=resolved_settings.observability.request_id_header,
    )

    app.include_router(build_operational_router(resolved_settings))
    app.include_router(build_api_router(resolved_settings))

    return app
