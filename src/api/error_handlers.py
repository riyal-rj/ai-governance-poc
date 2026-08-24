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

from src.api.schemas import (ErrorBody, ErrorResponse)
from src.core.errors import AppError, ErrorCode
from src.core.request_context import get_request_id
from src.domain.errors import DomainError, IllegalStateTransitionError

logger = logging.getLogger(__name__)

_STATUS_BY_CODE: dict[ErrorCode, int] ={
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
    ErrorCode.INTERNAL_SERVER_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR
}

def install_error_handlers(app: FastAPI) -> None:
   """Registers every handlers in one location during app construction."""

   app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, _handle_domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected_error)



def _handle_app_error(request: Request,
                      exc: AppError) -> JSONResponse:
   status = _STATUS_BY_CODE.get(exc.code, HTTPStatus.INTERNAL_SERVER_ERROR)
   logger.warning(
      "expected application error",
      extra={
         "event":"application_error",
         "path":request.url.path,
         "status_code": int(status)
      }
   )

   return _response(
      request=request,
      status_code=int(status),
      code=exc.code.value,
      message=exc.message,
    retryable=exc.retryable,
      details=exc.details,
   )


async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    status = (
        HTTPStatus.CONFLICT
        if isinstance(exc, IllegalStateTransitionError)
        else HTTPStatus.UNPROCESSABLE_ENTITY
    )
    return _response(
        request=request,
        status_code=int(status),
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def _handle_validation_error(request: Request,
                                   exc: RequestValidationError) -> JSONResponse:
    errors = [
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
        details={"violations": errors},
    )

async def _handle_http_exception(request: Request,
                                 exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request Failed"
    code = _http_error_code(exc.status_code)
    return _response(
        request= request,
        status_code = exc.status_code,
        code = code,
        message=message,
        headers = exc.headers,
    )

async def _handle_unexpected_error(request: Request,
                                   exc: Exception) -> JSONResponse:
    logger.exception(
        "unexpected application error",
        exc_info = exc,
        extra = {
            "event" : "unexpected_error",
            "path": request.url.path,
            "status_code" : HTTPStatus.INTERNAL_SERVER_ERROR
        }
    )

    return _response(
        request = request,
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR,
        code = ErrorCode.INTERNAL_SERVER_ERROR.value,
        message = " An unexpected error occured",
        retryable = False
    )

def _response(*,
              request: Request,
              status_code : int,
              code : str,
              message : str,
              retryable : bool = False,
              details: Mapping[str, Any] | None = None,
              headers: Mapping[str, str] | None = None) -> JSONResponse:
    request_id = get_request_id()
    payload = ErrorResponse(
        error = ErrorBody(
            code= code,
            message = message,
            retryable = retryable,
            details = dict(details or {}),
        ),
        request_id = request_id,
        timestamp = datetime.now(UTC),
        path = request.url.path,
    )
    response_headers = dict(headers or {})
    response_headers.setdefault("X-Request-ID", request_id)
    return JSONResponse(
        content = payload.model_dump(mode ="json"),
        status_code = status_code,
        headers = response_headers,
    )


def _http_error_code(status_code: int) -> str:
    if status_code == HTTPStatus.UNAUTHORIZED :
        return ErrorCode.AUTHENTICATION_REQUIRED.value
    if status_code == HTTPStatus.FORBIDDEN:
        return ErrorCode.AUTHORIZATION_REQUIRED.value
    if status_code == HTTPStatus.NOT_FOUND:
        return ErrorCode.RESOURCE_NOT_FOUND.value
    if status_code == HTTPStatus.TOO_MANY_REQUESTS:
        return ErrorCode.RATE_LIMITED.value
    if status_code == HTTPStatus.SERVICE_UNAVAILABLE:
        return ErrorCode.DEPENDENCY_UNAVAILABLE.value
    if status_code == HTTPStatus.BAD_GATEWAY:
        return ErrorCode.BAD_GATEWAY.value
    if status_code == HTTPStatus.CONFLICT:
        return ErrorCode.RESOURCE_CONFLICT.value
    if status_code == HTTPStatus.FORBIDDEN:
        return ErrorCode.FORBIDDEN.value
    return f"http_{status_code}"
