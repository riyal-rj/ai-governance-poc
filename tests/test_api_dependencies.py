from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.api.dependencies import get_container, get_metrics, get_readiness_service
from src.core.errors import DependencyUnavailableError


def _request_with_container(container: Any) -> Any:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)))


def _request_without_container() -> Any:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


def test_get_container_returns_state_container() -> None:
    sentinel = object()
    request = _request_with_container(sentinel)
    assert get_container(request) is sentinel


def test_get_container_raises_when_unset() -> None:
    with pytest.raises(DependencyUnavailableError):
        get_container(_request_without_container())


def test_get_readiness_service_reads_from_container() -> None:
    container = SimpleNamespace(readiness="the-readiness-service")
    assert get_readiness_service(container) == "the-readiness-service"  # type: ignore[arg-type]


def test_get_metrics_reads_from_container() -> None:
    container = SimpleNamespace(metrics="the-metrics-registry")
    assert get_metrics(container) == "the-metrics-registry"  # type: ignore[arg-type]
