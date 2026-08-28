from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_container
from src.api.router import build_api_router, build_operational_router
from tests.support import FakeContainer, make_container_factory, make_settings


def _client_for(router: FastAPI) -> TestClient:
    settings = make_settings()
    container_factory = make_container_factory()

    async def override() -> FakeContainer:
        return await container_factory(settings)  # type: ignore[return-value]

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_container] = override
    return TestClient(app)


def test_operational_router_includes_health_and_metrics_when_enabled() -> None:
    settings = make_settings()
    router = build_operational_router(settings)

    with _client_for(router) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get(settings.observability.metrics_path).status_code == 200


def test_operational_router_excludes_metrics_when_disabled() -> None:
    settings = make_settings()
    disabled = settings.model_copy(
        update={
            "observability": settings.observability.model_copy(update={"metrics_enabled": False})
        }
    )
    router = build_operational_router(disabled)

    with _client_for(router) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get(disabled.observability.metrics_path).status_code == 404


def test_api_router_uses_configured_prefix_and_has_no_routes_yet() -> None:
    settings = make_settings(api_prefix="/api/v2")
    router = build_api_router(settings)

    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        assert client.get("/api/v2/anything").status_code == 404
