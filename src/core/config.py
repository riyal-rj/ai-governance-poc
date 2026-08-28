"""
Validated process configuration.
Only this module reads environment variables. The rest of the application receives
an immutable `AppSettings` object through construction.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported deployment environments"""

    LOCAL = "local"
    TEST = "test"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class DatabaseSettings(BaseModel):
    """PostgreSQL pool and timeout configuration."""

    model_config = {"frozen": True}

    dsn: SecretStr
    min_pool_size: int = Field(default=2, ge=1, le=100)
    max_pool_size: int = Field(default=10, ge=1, le=200)
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    command_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    close_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    @field_validator("dsn")
    @classmethod
    def validate_dsn(cls, value: SecretStr) -> SecretStr:
        dsn = value.get_secret_value().strip()
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("dsn must use postgresql:// or postgres://")
        return SecretStr(dsn)

    @model_validator(mode="after")
    def validate_pool_bounds(self) -> Self:
        if self.min_pool_size > self.max_pool_size:
            raise ValueError("min_pool_size cannot exceed max_pool_size")
        return self


class OPASettings(BaseModel):
    """Connection details for the internal policy decision point."""

    model_config = {"frozen": True}

    base_url: str = "http://opa:8181"
    decision_path: str = "/v1/data/finassist/system/ready"
    decision_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    health_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("base_url must use http:// or https://")
        return normalized

    @field_validator("decision_path")
    @classmethod
    def validate_decision_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("decision_path must start with '/'")
        return value


class HttpClientSettings(BaseModel):
    """Timeout and connection limits for the shared outbound HTTP client."""

    model_config = {"frozen": True}

    connect_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    read_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    write_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    pool_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    max_connections: int = Field(default=100, gt=1, le=1_000)
    max_keepalive_connections: int = Field(default=10, gt=0, le=200)
    keepalive_expiry_seconds: float = Field(default=30.0, gt=0, le=600)

    @model_validator(mode="after")
    def validate_connection_limits(self) -> Self:
        if self.max_keepalive_connections > self.max_connections:
            raise ValueError("max_keepalive_connections cannot exceed max_connections")
        return self


class StartupSettings(BaseModel):
    """Bounded startup-readiness policy."""

    model_config = {"frozen": True}

    require_ready: bool = True
    timeout_seconds: float = Field(default=45.0, gt=0, le=600)
    initial_backoff_seconds: float = Field(default=0.25, gt=0, le=30)
    max_backoff_seconds: float = Field(default=3.0, gt=0, le=60)

    @model_validator(mode="after")
    def validate_backoff(self) -> Self:
        if self.initial_backoff_seconds > self.max_backoff_seconds:
            raise ValueError("initial_backoff_seconds cannot exceed max_backoff_seconds")
        return self


class ObservabilitySettings(BaseModel):
    """Operational endpoint and request-correlation configuration."""

    model_config = {"frozen": True}

    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    request_id_header: str = "X-Request-ID"

    @field_validator("metrics_path")
    @classmethod
    def validate_metrics_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("metrics_path must start with '/'")
        return value

    @field_validator("request_id_header")
    @classmethod
    def validate_request_id_header(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", normalized):
            raise ValueError("request_id_header must be a valid HTTP field name")
        return normalized


class AppSettings(BaseSettings):
    """Immutable, environment-backed configuration for one service process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FINASSIST_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
        validate_default=True,
    )

    service_name: str = Field(default="finassist-api", min_length=1, max_length=80)
    service_version: str = Field(default="0.1.0", min_length=1, max_length=40)
    environment: Environment = Environment.LOCAL
    debug: bool = False
    docs_enabled: bool = True
    log_level: str = "INFO"
    log_json: bool = True
    api_prefix: str = "/api/v1"

    database: DatabaseSettings
    opa: OPASettings = OPASettings()
    http_client: HttpClientSettings = HttpClientSettings()
    startup: StartupSettings = StartupSettings()
    observability: ObservabilitySettings = ObservabilitySettings()

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        if len(value) > 1 and value.endswith("/"):
            raise ValueError("api_prefix must not end with '/'")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper().strip()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @model_validator(mode="after")
    def validate_environment_safety(self) -> Self:
        if self.environment is Environment.PRODUCTION and self.debug:
            raise ValueError("debug must be false in production")
        if self.environment is Environment.PRODUCTION and not self.log_json:
            raise ValueError("structured JSON logs are required in production")
        if self.environment is Environment.PRODUCTION and self.docs_enabled:
            raise ValueError("API documentation must be disabled in production")
        return self


def load_settings() -> AppSettings:
    """Load and validate settings exactly once at application construction."""

    return AppSettings()
