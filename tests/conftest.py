"""Shared pytest fixtures for the FinAssist test suite."""

from __future__ import annotations

import pytest

from src.core.config import AppSettings, DatabaseSettings


@pytest.fixture
def database_settings() -> DatabaseSettings:
    return DatabaseSettings(dsn="postgresql://finassist:secret@localhost:5432/finassist")


@pytest.fixture
def app_settings(database_settings: DatabaseSettings) -> AppSettings:
    """A fully valid, deterministic settings object independent of the host .env."""

    return AppSettings(_env_file=None, database=database_settings)
