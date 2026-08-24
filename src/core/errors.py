from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

class ErrorCode(StrEnum):
    """Stable machine readable error codes exposed by API"""

    AUTHENTICATION_REQUIRED = "authentication_required"
    AUTHORIZATION_REQUIRED = "authorization_required"
    INPUT_INVALID = "input_invalid"
    RESOURCE_NOT_FOUND = "resource_not_found"
    RATE_LIMITED= "rate_limited"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    STARTUP_FAILED= "startup_failed"
    BAD_GATEWAY = "bad_gateway"
    FORBIDDEN = "forbidden"
    RESOURCE_CONFLICT = "resource_conflict"
    INTERNAL_SERVER_ERROR = "internal_server_error"


class AppError(Exception):
    """Expected Failure carrying a safe public message and stable code.

    
    ``details`` must contain non-secret, client-actionable values only. Internal
    exception strings, SQL, credentials and provider responses belong in logs.
    """

    def __init__(self, *, 
                 code: ErrorCode,
                 message: str,
                 details: Mapping[str, Any] | None = None,
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.retryable = retryable

class AuthRequiredError(AppError):
    def __init__(self, message: str ="Authentication is required") -> None:
        super().__init__(code=ErrorCode.AUTHENTICATION_REQUIRED, 
                         message=message)

class PermissionDeniedError(AppError):
    def __init__(self, message: str = "The requested operation is forbidden") -> None:
        super().__init__(code=ErrorCode.FORBIDDEN, 
                         message=message)


class ResourceNotFoundError(AppError):
    def __init__(self, resource: str, 
                 identifier: str) -> None:
        super().__init__(code=ErrorCode.RESOURCE_NOT_FOUND, 
                         message=f"{resource} not found",
                         details={
                             "resource":resource,
                              "identifier":identifier
                                }
                        )


class ResourceConflictError(AppError):
    def __init__(self, 
                 message: str, 
                 *, 
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code=ErrorCode.RESOURCE_CONFLICT, 
                         message=message, 
                         details=details)

class DependencyUnavailableError(AppError):
    def __init__(self,
                 dependency: str) -> None:
        super().__init__(
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message="The requested service is temporarily unavailable",
            details={"dependency": dependency},
            retryable=True
        )


class StartUpError(AppError):
    def __init__(self,
                 unavailable_dependecies: list[str]) -> None:
        super().__init__(
            code=ErrorCode.STARTUP_FAILED,
            message="Application startup requirements were not satisfied",
            details={"unavailable_dependecies":sorted(unavailable_dependecies)},
            retryable=True
        )
      
