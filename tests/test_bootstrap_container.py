from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from src.bootstrap.container import build_container
from src.core.config import AppSettings, DatabaseSettings
from src.core.errors import DependencyUnavailableError


def _settings() -> AppSettings:
    return AppSettings(_env_file=None, database=DatabaseSettings(dsn="postgresql://u:p@h:5432/d"))


def _fake_pool() -> MagicMock:
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=1)
    pool.close = AsyncMock(return_value=None)
    pool.terminate = MagicMock()
    return pool


async def test_build_container_wires_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=_fake_pool()))

    container = await build_container(_settings())
    try:
        assert container.database.connected is True
        assert container.http_client.is_closed is False
        report = await container.readiness.evaluate()
        assert {c.component for c in report.components} == {"postgres", "opa"}
    finally:
        await container.aclose()

    assert container.database.connected is False
    assert container.http_client.is_closed is True


async def test_build_container_aclose_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=_fake_pool()))

    container = await build_container(_settings())
    await container.aclose()
    await container.aclose()  # must not raise or double-close


async def test_build_container_closes_partial_resources_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_clients: list[object] = []
    from src.bootstrap import container as container_module
    from src.infrastructure.http_client import create_http_client as real_create_http_client

    def spying_create_http_client(*args: object, **kwargs: object) -> object:
        client = real_create_http_client(*args, **kwargs)  # type: ignore[arg-type]
        created_clients.append(client)
        return client

    monkeypatch.setattr(container_module, "create_http_client", spying_create_http_client)

    async def raise_postgres_error(**kwargs: object) -> None:
        raise asyncpg.PostgresError("connection refused")

    monkeypatch.setattr(asyncpg, "create_pool", raise_postgres_error)

    with pytest.raises(DependencyUnavailableError):
        await build_container(_settings())

    assert len(created_clients) == 1
    assert created_clients[0].is_closed is True  # type: ignore[attr-defined]
