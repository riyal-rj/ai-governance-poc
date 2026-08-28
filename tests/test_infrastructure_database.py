from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from src.core.config import DatabaseSettings
from src.core.errors import DependencyUnavailableError
from src.infrastructure.database import PostgresDatabase


def _settings(**overrides: object) -> DatabaseSettings:
    defaults: dict[str, object] = {"dsn": "postgresql://u:p@h:5432/d"}
    defaults.update(overrides)
    return DatabaseSettings(**defaults)  # type: ignore[arg-type]


def _fake_pool() -> MagicMock:
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=1)
    pool.close = AsyncMock(return_value=None)
    pool.terminate = MagicMock()
    return pool


async def test_connect_opens_pool_once(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _fake_pool()
    create_pool = AsyncMock(return_value=pool)
    monkeypatch.setattr(asyncpg, "create_pool", create_pool)

    database = PostgresDatabase(_settings(), application_name="finassist-test")
    assert database.connected is False

    await database.connect()
    await database.connect()  # second call must be a no-op

    assert database.connected is True
    create_pool.assert_awaited_once()


async def test_connect_wraps_postgres_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def raise_postgres_error(**kwargs: object) -> None:
        raise asyncpg.PostgresError("connection refused")

    monkeypatch.setattr(asyncpg, "create_pool", raise_postgres_error)
    database = PostgresDatabase(_settings(), application_name="finassist-test")

    with pytest.raises(DependencyUnavailableError):
        await database.connect()


async def test_connect_wraps_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def raise_os_error(**kwargs: object) -> None:
        raise OSError("network unreachable")

    monkeypatch.setattr(asyncpg, "create_pool", raise_os_error)
    database = PostgresDatabase(_settings(), application_name="finassist-test")

    with pytest.raises(DependencyUnavailableError):
        await database.connect()


async def test_connect_raises_when_pool_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=None))
    database = PostgresDatabase(_settings(), application_name="finassist-test")

    with pytest.raises(DependencyUnavailableError):
        await database.connect()


async def test_ping_success(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _fake_pool()
    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=pool))
    database = PostgresDatabase(_settings(), application_name="finassist-test")
    await database.connect()

    await database.ping()

    pool.fetchval.assert_awaited_once_with("SELECT 1")


async def test_ping_raises_on_unexpected_value(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _fake_pool()
    pool.fetchval = AsyncMock(return_value=0)
    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=pool))
    database = PostgresDatabase(_settings(), application_name="finassist-test")
    await database.connect()

    with pytest.raises(DependencyUnavailableError):
        await database.ping()


async def test_ping_without_connect_raises() -> None:
    database = PostgresDatabase(_settings(), application_name="finassist-test")
    with pytest.raises(DependencyUnavailableError):
        await database.ping()


async def test_aclose_without_connect_is_a_noop() -> None:
    database = PostgresDatabase(_settings(), application_name="finassist-test")
    await database.aclose()  # must not raise
    assert database.connected is False


async def test_aclose_closes_pool_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _fake_pool()
    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=pool))
    database = PostgresDatabase(_settings(), application_name="finassist-test")
    await database.connect()

    await database.aclose()

    pool.close.assert_awaited_once()
    pool.terminate.assert_not_called()
    assert database.connected is False


async def test_aclose_terminates_pool_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _fake_pool()

    async def slow_close() -> None:
        await asyncio.sleep(0.2)

    pool.close = slow_close
    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=pool))
    database = PostgresDatabase(
        _settings(close_timeout_seconds=0.01), application_name="finassist-test"
    )
    await database.connect()

    await database.aclose()

    pool.terminate.assert_called_once()
