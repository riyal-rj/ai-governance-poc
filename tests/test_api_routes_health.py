from __future__ import annotations

from tests.support import make_client


def test_liveness_does_not_depend_on_readiness() -> None:
    with make_client(healthy=False) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_returns_200_when_all_dependencies_healthy() -> None:
    with make_client(healthy=True) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["status"] == "ready"
    assert {c["component"] for c in body["components"]} == {"postgres", "opa"}


def test_readiness_returns_503_when_a_critical_dependency_is_unhealthy() -> None:
    with make_client(healthy=False) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["status"] == "not_ready"
