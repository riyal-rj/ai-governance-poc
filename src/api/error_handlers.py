"""Central exception-to-HTTP mapping with stable, sanitized error contracts."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.schemas import ErrorBody, ErrorResponse
from src.core.errors import AppError, ErrorCode
from src.core.request_context import get_request_id
from src.domain.errors import DomainError, IllegalStateTransitionError

logger = logging.getLogger(__name__)

_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.AUTHENTICATION_REQUIRED: HTTPStatus.UNAUTHORIZED,
    ErrorCode.AUTHORIZATION_REQUIRED: HTTPStatus.FORBIDDEN,
    ErrorCode.INPUT_INVALID: HTTPStatus.BAD_REQUEST,
    ErrorCode.RESOURCE_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.RATE_LIMITED: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCode.DEPENDENCY_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.STARTUP_FAILED: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.BAD_GATEWAY: HTTPStatus.BAD_GATEWAY,
    ErrorCode.FORBIDDEN: HTTPStatus.FORBIDDEN,
    ErrorCode.RESOURCE_CONFLICT: HTTPStatus.CONFLICT,
    ErrorCode.INTERNAL_SERVER_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
}


def install_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers at application construction time."""

    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, _handle_domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        _handle_validation_error,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        StarletteHTTPException,
        _handle_http_exception,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, _handle_unexpected_error)


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    status_code = _STATUS_BY_CODE.get(exc.code, HTTPStatus.INTERNAL_SERVER_ERROR)
    logger.warning(
        "expected application error",
        extra={
            "event": "application_error",
            "path": request.url.path,
            "status_code": int(status_code),
        },
    )
    return _response(
        request=request,
        status_code=int(status_code),
        code=exc.code.value,
        message=exc.message,
        retryable=exc.retryable,
        details=exc.details,
    )


async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    status_code = (
        HTTPStatus.CONFLICT
        if isinstance(exc, IllegalStateTransitionError)
        else HTTPStatus.UNPROCESSABLE_ENTITY
    )
    logger.info(
        "domain operation rejected",
        extra={
            "event": "domain_error",
            "path": request.url.path,
            "status_code": int(status_code),
        },
    )
    return _response(
        request=request,
        status_code=int(status_code),
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def _handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    violations = [
        {
            "location": [str(part) for part in item.get("loc", ())],
            "message": item.get("msg", "Invalid value"),
            "type": item.get("type", "value_error"),
        }
        for item in exc.errors()
    ]
    return _response(
        request=request,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        code=ErrorCode.INPUT_INVALID.value,
        message="Request validation failed",
        details={"violations": violations},
    )


async def _handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return _response(
        request=request,
        status_code=exc.status_code,
        code=_http_error_code(exc.status_code),
        message=message,
        headers=exc.headers,
    )


async def _handle_unexpected_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "unexpected application error",
        exc_info=exc,
        extra={
            "event": "unexpected_error",
            "path": request.url.path,
            "status_code": HTTPStatus.INTERNAL_SERVER_ERROR,
        },
    )
    return _response(
        request=request,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_SERVER_ERROR.value,
        message="An unexpected error occurred",
    )


def _response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id()
    payload = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            details=dict(details or {}),
        ),
        request_id=request_id,
        timestamp=datetime.now(UTC),
        path=request.url.path,
    )
    response_headers = dict(headers or {})
    response_headers.setdefault(_request_id_header(request), request_id)
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        status_code=int(status_code),
        headers=response_headers,
    )


def _request_id_header(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    observability = getattr(settings, "observability", None)
    return str(getattr(observability, "request_id_header", "X-Request-ID"))


def _http_error_code(status_code: int) -> str:
    mappings: dict[int, str] = {
        HTTPStatus.UNAUTHORIZED: ErrorCode.AUTHENTICATION_REQUIRED.value,
        HTTPStatus.FORBIDDEN: ErrorCode.AUTHORIZATION_REQUIRED.value,
        HTTPStatus.NOT_FOUND: ErrorCode.RESOURCE_NOT_FOUND.value,
        HTTPStatus.TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED.value,
        HTTPStatus.SERVICE_UNAVAILABLE: ErrorCode.DEPENDENCY_UNAVAILABLE.value,
        HTTPStatus.BAD_GATEWAY: ErrorCode.BAD_GATEWAY.value,
        HTTPStatus.CONFLICT: ErrorCode.RESOURCE_CONFLICT.value,
    }
    return mappings.get(status_code, f"http_{status_code}")
