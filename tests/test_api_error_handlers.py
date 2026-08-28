from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from src.api.error_handlers import install_error_handlers
from src.core.errors import DependencyUnavailableError
from src.domain.errors import IllegalStateTransitionError, InvariantViolationError


class Payload(BaseModel):
    amount: int


def _build_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom/app-error")
    async def app_error() -> None:
        raise DependencyUnavailableError("postgres")

    @app.get("/boom/domain-error")
    async def domain_error() -> None:
        raise InvariantViolationError("bad money value")

    @app.get("/boom/illegal-transition")
    async def illegal_transition() -> None:
        raise IllegalStateTransitionError("cannot cancel a closed dispute")

    @app.get("/boom/http-exception")
    async def http_exception() -> None:
        raise HTTPException(status_code=418, detail="teapot")

    @app.get("/boom/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("something exploded")

    @app.post("/validate")
    async def validate(payload: Payload) -> dict[str, int]:
        return {"amount": payload.amount}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def test_app_error_maps_to_configured_status_and_code(client: TestClient) -> None:
    response = client.get("/boom/app-error")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "dependency_unavailable"
    assert body["error"]["retryable"] is True
    assert body["error"]["details"] == {"dependency": "postgres"}
    assert body["path"] == "/boom/app-error"


def test_domain_error_maps_to_422(client: TestClient) -> None:
    response = client.get("/boom/domain-error")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invariant_violation"


def test_illegal_state_transition_maps_to_409(client: TestClient) -> None:
    response = client.get("/boom/illegal-transition")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "illegal_state_transition"


def test_http_exception_is_mapped_with_generic_code(client: TestClient) -> None:
    response = client.get("/boom/http-exception")
    assert response.status_code == 418
    body = response.json()
    assert body["error"]["message"] == "teapot"
    assert body["error"]["code"] == "http_418"


def test_unexpected_exception_is_sanitized(client: TestClient) -> None:
    response = client.get("/boom/unexpected")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_server_error"
    assert body["error"]["message"] == "An unexpected error occurred"
    assert "RuntimeError" not in response.text
    assert "something exploded" not in response.text


def test_validation_error_reports_violations(client: TestClient) -> None:
    response = client.post("/validate", json={"amount": "not-an-int"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "input_invalid"
    assert body["error"]["details"]["violations"]
