from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import (
    AppSettings,
    DatabaseSettings,
    Environment,
    HttpClientSettings,
    ObservabilitySettings,
    OPASettings,
    StartupSettings,
    load_settings,
)


class TestDatabaseSettings:
    def test_accepts_postgresql_scheme(self) -> None:
        settings = DatabaseSettings(dsn="postgresql://u:p@host:5432/db")
        assert settings.dsn.get_secret_value() == "postgresql://u:p@host:5432/db"

    def test_accepts_postgres_scheme(self) -> None:
        settings = DatabaseSettings(dsn="postgres://u:p@host:5432/db")
        assert settings.dsn.get_secret_value().startswith("postgres://")

    def test_rejects_non_postgres_scheme(self) -> None:
        with pytest.raises(ValidationError, match="postgresql"):
            DatabaseSettings(dsn="mysql://u:p@host:3306/db")

    def test_rejects_min_pool_size_above_max(self) -> None:
        with pytest.raises(ValidationError, match="min_pool_size"):
            DatabaseSettings(dsn="postgresql://u:p@h:5432/d", min_pool_size=10, max_pool_size=2)

    def test_is_frozen(self) -> None:
        settings = DatabaseSettings(dsn="postgresql://u:p@h:5432/d")
        with pytest.raises(ValidationError):
            settings.min_pool_size = 5  # type: ignore[misc]


class TestOPASettings:
    def test_strips_trailing_slash(self) -> None:
        settings = OPASettings(base_url="http://opa:8181/")
        assert settings.base_url == "http://opa:8181"

    def test_rejects_invalid_scheme(self) -> None:
        with pytest.raises(ValidationError, match="base_url"):
            OPASettings(base_url="ftp://opa:8181")

    def test_default_decision_path(self) -> None:
        settings = OPASettings()
        assert settings.decision_path == "/v1/data/finassist/system/ready"

    def test_rejects_decision_path_without_leading_slash(self) -> None:
        with pytest.raises(ValidationError, match="decision_path"):
            OPASettings(decision_path="v1/data/finassist/system/ready")


class TestHttpClientSettings:
    def test_rejects_keepalive_above_max_connections(self) -> None:
        with pytest.raises(ValidationError, match="max_keepalive_connections"):
            HttpClientSettings(max_connections=5, max_keepalive_connections=10)

    def test_defaults_are_valid(self) -> None:
        settings = HttpClientSettings()
        assert settings.max_keepalive_connections <= settings.max_connections


class TestStartupSettings:
    def test_rejects_initial_backoff_above_max(self) -> None:
        with pytest.raises(ValidationError, match="initial_backoff_seconds"):
            StartupSettings(initial_backoff_seconds=10, max_backoff_seconds=1)


class TestObservabilitySettings:
    def test_rejects_metrics_path_without_leading_slash(self) -> None:
        with pytest.raises(ValidationError, match="metrics_path"):
            ObservabilitySettings(metrics_path="metrics")

    def test_rejects_invalid_request_id_header(self) -> None:
        with pytest.raises(ValidationError, match="request_id_header"):
            ObservabilitySettings(request_id_header="bad header/name")

    def test_accepts_valid_header(self) -> None:
        settings = ObservabilitySettings(request_id_header="X-Trace-Id")
        assert settings.request_id_header == "X-Trace-Id"


class TestAppSettings:
    def test_requires_database(self) -> None:
        with pytest.raises(ValidationError):
            AppSettings(_env_file=None)  # type: ignore[call-arg]

    def test_defaults_apply(self, database_settings: DatabaseSettings) -> None:
        settings = AppSettings(_env_file=None, database=database_settings)
        assert settings.environment is Environment.LOCAL
        assert settings.api_prefix == "/api/v1"

    def test_rejects_api_prefix_without_leading_slash(
        self, database_settings: DatabaseSettings
    ) -> None:
        with pytest.raises(ValidationError, match="api_prefix"):
            AppSettings(_env_file=None, database=database_settings, api_prefix="api/v1")

    def test_rejects_api_prefix_with_trailing_slash(
        self, database_settings: DatabaseSettings
    ) -> None:
        with pytest.raises(ValidationError, match="api_prefix"):
            AppSettings(_env_file=None, database=database_settings, api_prefix="/api/v1/")

    def test_normalizes_log_level_case(self, database_settings: DatabaseSettings) -> None:
        settings = AppSettings(_env_file=None, database=database_settings, log_level="debug")
        assert settings.log_level == "DEBUG"

    def test_rejects_unknown_log_level(self, database_settings: DatabaseSettings) -> None:
        with pytest.raises(ValidationError, match="log_level"):
            AppSettings(_env_file=None, database=database_settings, log_level="verbose")

    def test_production_rejects_debug(self, database_settings: DatabaseSettings) -> None:
        with pytest.raises(ValidationError, match="debug"):
            AppSettings(
                _env_file=None,
                database=database_settings,
                environment=Environment.PRODUCTION,
                debug=True,
                log_json=True,
                docs_enabled=False,
            )

    def test_production_rejects_non_json_logs(self, database_settings: DatabaseSettings) -> None:
        with pytest.raises(ValidationError, match="JSON"):
            AppSettings(
                _env_file=None,
                database=database_settings,
                environment=Environment.PRODUCTION,
                debug=False,
                log_json=False,
                docs_enabled=False,
            )

    def test_production_rejects_docs_enabled(self, database_settings: DatabaseSettings) -> None:
        with pytest.raises(ValidationError, match="documentation"):
            AppSettings(
                _env_file=None,
                database=database_settings,
                environment=Environment.PRODUCTION,
                debug=False,
                log_json=True,
                docs_enabled=True,
            )

    def test_production_allows_safe_configuration(
        self, database_settings: DatabaseSettings
    ) -> None:
        settings = AppSettings(
            _env_file=None,
            database=database_settings,
            environment=Environment.PRODUCTION,
            debug=False,
            log_json=True,
            docs_enabled=False,
        )
        assert settings.environment is Environment.PRODUCTION

    def test_is_frozen(self, app_settings: AppSettings) -> None:
        with pytest.raises(ValidationError):
            app_settings.debug = True  # type: ignore[misc]


class TestLoadSettings:
    def test_raises_without_required_database_dsn(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("FINASSIST_DATABASE__DSN", raising=False)
        with pytest.raises(ValidationError):
            load_settings()

    def test_reads_dsn_from_environment(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("FINASSIST_DATABASE__DSN", "postgresql://u:p@h:5432/d")
        settings = load_settings()
        assert settings.database.dsn.get_secret_value() == "postgresql://u:p@h:5432/d"
