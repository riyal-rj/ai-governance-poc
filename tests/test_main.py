from __future__ import annotations

import pytest

from src.main import create_app
from tests.support import make_client, make_container_factory, make_settings


def test_serves_liveness_with_explicit_settings_and_factory() -> None:
    settings = make_settings(service_name="finassist-test", service_version="9.9.9")
    with make_client(settings) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "alive", "service": "finassist-test", "version": "9.9.9"}


def test_docs_disabled_returns_404() -> None:
    settings = make_settings(docs_enabled=False)
    with make_client(settings) as client:
        response = client.get("/docs")

    assert response.status_code == 404


def test_docs_enabled_by_default() -> None:
    settings = make_settings(docs_enabled=True)
    with make_client(settings) as client:
        response = client.get("/docs")

    assert response.status_code == 200


def test_response_carries_request_id_header() -> None:
    with make_client() as client:
        response = client.get("/health/live")

    assert response.headers.get("X-Request-ID")


def test_unknown_route_uses_sanitized_error_contract() -> None:
    with make_client() as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "resource_not_found"
    assert body["path"] == "/does-not-exist"
    assert "request_id" in body
    assert "timestamp" in body


def test_create_app_resolves_settings_when_not_provided(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FINASSIST_DATABASE__DSN", "postgresql://u:p@h:5432/d")
    monkeypatch.setenv("FINASSIST_SERVICE_NAME", "resolved-from-env")

    app = create_app(container_factory=make_container_factory())

    assert app.state.settings.service_name == "resolved-from-env"
