"""Stable HTTP Response Contract"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from application.ports.health import (
    ComponentHealth,
    ReadinessReport
)

class ComponentHealthResponse(BaseModel):
    model_config = ConfigDict(frozen = True)

    component: str
    status: str
    critical: bool
    latency_ms: float
    message: str | None = None


    @classmethod
    def from_result(cls,
                    result: ComponentHealth) -> Self:
        return cls(
            component = result.component,
            status = result.status.value,
            critical = result.critical,
            latency_ms = result.latency_ms,
            message = result.message
        )

class LivenessResponse(BaseModel):

    model_config= ConfigDict(frozen=True)

    status: str = "alive"
    service: str
    version: str

class ReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    ready: bool
    checked_at : datetime
    components: tuple[ComponentHealthResponse, ...]

    @classmethod
    def from_report(cls, report: ReadinessReport) -> Self:
        return cls(
            status = report.status.value,
            ready = report.ready,
            checked_at = report.checked_at,
            components = tuple(
                ComponentHealthResponse.from_result(component) for component in report.components)
        )


class ErrorBody(BaseModel):
    model_config= ConfigDict(frozen = True)

    code : str
    message: str
    retryable: bool = False
    details : dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    model_config= ConfigDict(frozen=True)

    error: ErrorBody
    request_id: str
    timestamp: datetime
    path: str