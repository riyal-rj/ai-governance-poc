from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from src.observability.http_middleware import RequestTelemetryMiddleware
from src.observability.metrics import Metrics


def _make_scope(
    *,
    route_path: str | None = "/health/live",
    headers: list[tuple[bytes, bytes]] | None = None,
    app: Any = None,
) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/health/live",
        "headers": headers or [],
        "app": app,
    }
    if route_path is not None:
        scope["route"] = SimpleNamespace(path=route_path)
    return scope


class RecordingSend:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def __call__(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


async def _noop_receive() -> dict[str, Any]:
    return {"type": "http.request"}


def _app_with_metrics() -> tuple[Any, Metrics]:
    metrics = Metrics(service_name="svc", service_version="1", environment="local")
    container = SimpleNamespace(metrics=metrics)
    app = SimpleNamespace(state=SimpleNamespace(container=container))
    return app, metrics


async def test_passes_through_non_http_scopes_unmodified() -> None:
    calls: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        calls.append(scope["type"])

    middleware = RequestTelemetryMiddleware(inner, request_id_header="X-Request-ID")
    await middleware({"type": "lifespan"}, _noop_receive, RecordingSend())

    assert calls == ["lifespan"]


async def test_successful_request_echoes_request_id_and_records_metrics() -> None:
    app, metrics = _app_with_metrics()

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestTelemetryMiddleware(inner, request_id_header="X-Request-ID")
    send = RecordingSend()
    scope = _make_scope(headers=[(b"x-request-id", b"caller-supplied-id")], app=app)

    await middleware(scope, _noop_receive, send)

    start_message = next(m for m in send.messages if m["type"] == "http.response.start")
    header_map = dict(start_message["headers"])
    assert header_map[b"x-request-id"] == b"caller-supplied-id"

    body, _content_type = metrics.render()
    assert 'route="/health/live"' in body.decode("utf-8")


async def test_malformed_request_id_is_replaced() -> None:
    app, _metrics = _app_with_metrics()

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})

    middleware = RequestTelemetryMiddleware(inner, request_id_header="X-Request-ID")
    send = RecordingSend()
    scope = _make_scope(headers=[(b"x-request-id", b"not a valid id!!")], app=app)

    await middleware(scope, _noop_receive, send)

    header_map = dict(
        next(m for m in send.messages if m["type"] == "http.response.start")["headers"]
    )
    assert header_map[b"x-request-id"] != b"not a valid id!!"


async def test_unhandled_exception_is_logged_and_reraised(caplog: pytest.LogCaptureFixture) -> None:
    app, metrics = _app_with_metrics()

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        raise RuntimeError("boom")

    middleware = RequestTelemetryMiddleware(inner, request_id_header="X-Request-ID")

    with caplog.at_level(logging.ERROR, logger="src.observability.http_middleware"):
        with pytest.raises(RuntimeError):
            await middleware(_make_scope(app=app), _noop_receive, RecordingSend())

    assert any("unhandled request exception" in message for message in caplog.messages)
    body, _content_type = metrics.render()
    assert 'status_code="500"' in body.decode("utf-8")


async def test_missing_container_does_not_crash() -> None:
    app = SimpleNamespace(state=SimpleNamespace())  # no .container

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})

    middleware = RequestTelemetryMiddleware(inner, request_id_header="X-Request-ID")
    await middleware(_make_scope(app=app), _noop_receive, RecordingSend())


async def test_unmatched_route_label_used_when_no_route_on_scope() -> None:
    app, metrics = _app_with_metrics()

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 404, "headers": []})

    middleware = RequestTelemetryMiddleware(inner, request_id_header="X-Request-ID")
    scope = _make_scope(route_path=None, app=app)

    await middleware(scope, _noop_receive, RecordingSend())

    body, _content_type = metrics.render()
    assert 'route="unmatched"' in body.decode("utf-8")
