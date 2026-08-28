from __future__ import annotations

from src.core.errors import (
    AppError,
    AuthRequiredError,
    DependencyUnavailableError,
    ErrorCode,
    PermissionDeniedError,
    ResourceConflictError,
    ResourceNotFoundError,
    StartupError,
)


def test_app_error_defaults() -> None:
    err = AppError(code=ErrorCode.INPUT_INVALID, message="bad input")
    assert err.code is ErrorCode.INPUT_INVALID
    assert err.message == "bad input"
    assert err.details == {}
    assert err.retryable is False
    assert str(err) == "bad input"


def test_app_error_copies_details() -> None:
    details = {"field": "amount"}
    err = AppError(code=ErrorCode.INPUT_INVALID, message="bad", details=details)
    details["field"] = "mutated"
    assert err.details == {"field": "amount"}


def test_auth_required_error() -> None:
    err = AuthRequiredError()
    assert err.code is ErrorCode.AUTHENTICATION_REQUIRED
    assert err.message == "Authentication is required"


def test_permission_denied_error() -> None:
    err = PermissionDeniedError()
    assert err.code is ErrorCode.FORBIDDEN


def test_resource_not_found_error() -> None:
    err = ResourceNotFoundError("dispute", "d-1")
    assert err.code is ErrorCode.RESOURCE_NOT_FOUND
    assert err.details == {"resource": "dispute", "identifier": "d-1"}


def test_resource_conflict_error() -> None:
    err = ResourceConflictError("already used", details={"key": "abc"})
    assert err.code is ErrorCode.RESOURCE_CONFLICT
    assert err.details == {"key": "abc"}


def test_dependency_unavailable_error() -> None:
    err = DependencyUnavailableError("postgres")
    assert err.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert err.retryable is True
    assert err.details == {"dependency": "postgres"}


def test_startup_error_sorts_dependencies() -> None:
    err = StartupError(["opa", "postgres"])
    assert err.retryable is True
    assert err.details == {"unavailable_dependencies": ["opa", "postgres"]}
