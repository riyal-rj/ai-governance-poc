"""Request correlation and bounded-cardinality HTTP telemetry middleware."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.request_context import (
    bind_request_id,
    normalize_request_id,
    reset_request_id,
)
from src.observability.metrics import Metrics

logger = logging.getLogger(__name__)


class RequestTelemetryMiddleware:
    """Attach request IDs and record low-cardinality request telemetry.

    Pure ASGI middleware is used so context variables propagate across the
    complete request task tree.
    """

    def __init__(self, app: ASGIApp, *, request_id_header: str) -> None:
        self.app = app
        self._request_id_header = request_id_header

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = normalize_request_id(headers.get(self._request_id_header))
        token = bind_request_id(request_id)
        started = perf_counter()
        status_code = 500
        metrics = self._get_metrics(scope)
        if metrics is not None:
            metrics.http_in_progress.inc()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers[self._request_id_header] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception(
                "unhandled request exception",
                extra={
                    "event": "http_request_failed",
                    "method": scope.get("method", "UNKNOWN"),
                    "path": scope.get("path", ""),
                    "status_code": 500,
                },
            )
            raise
        finally:
            duration_seconds = perf_counter() - started
            route = self._route_template(scope)
            method = str(scope.get("method", "UNKNOWN"))
            if metrics is not None:
                metrics.http_in_progress.dec()
                metrics.observe_http(
                    method=method,
                    route=route,
                    status_code=status_code,
                    duration_seconds=duration_seconds,
                )
            logger.info(
                "http request completed",
                extra={
                    "event": "http_request_completed",
                    "method": method,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round(duration_seconds * 1000, 3),
                },
            )
            reset_request_id(token)

    @staticmethod
    def _get_metrics(scope: Scope) -> Metrics | None:
        app: Any = scope.get("app")
        container = getattr(getattr(app, "state", None), "container", None)
        return getattr(container, "metrics", None)

    @staticmethod
    def _route_template(scope: Scope) -> str:
        route: Any = scope.get("route")
        template = getattr(route, "path", None)
        return str(template) if template else "unmatched"
