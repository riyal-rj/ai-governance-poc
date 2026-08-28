from __future__ import annotations

from tests.support import make_client, make_settings


def test_metrics_endpoint_exposes_prometheus_format() -> None:
    with make_client() as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "finassist_build" in response.text


def test_metrics_endpoint_excluded_from_openapi_schema() -> None:
    with make_client() as client:
        schema = client.get("/openapi.json").json()

    assert "/metrics" not in schema["paths"]


def test_metrics_endpoint_disabled_returns_404() -> None:
    settings = make_settings()
    disabled = settings.model_copy(
        update={
            "observability": settings.observability.model_copy(update={"metrics_enabled": False})
        }
    )
    with make_client(disabled) as client:
        response = client.get("/metrics")

    assert response.status_code == 404
