from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import httpx

from src.application.ports.health import ComponentStatus
from src.infrastructure.health_checks import OPAHealthCheck, PostgresHealthCheck


class FakeDatabase:
    def __init__(self, *, succeed: bool = True, delay: float = 0.0) -> None:
        self._succeed = succeed
        self._delay = delay

    async def ping(self) -> None:
        if self._delay:
            await asyncio.sleep(self._delay)
        if not self._succeed:
            raise RuntimeError("connection lost")


class FakeResponse:
    def __init__(
        self,
        *,
        json_data: Any = None,
        raise_json_error: bool = False,
        raise_status_error: bool = False,
    ) -> None:
        self._json_data = json_data
        self._raise_json_error = raise_json_error
        self._raise_status_error = raise_status_error

    def raise_for_status(self) -> None:
        if self._raise_status_error:
            request = httpx.Request("GET", "http://opa/v1/data/finassist/system/ready")
            raise httpx.HTTPStatusError("bad status", request=request, response=self)  # type: ignore[arg-type]

    def json(self) -> Any:
        if self._raise_json_error:
            raise ValueError("not valid json")
        return self._json_data


class TestPostgresHealthCheck:
    async def test_healthy_when_ping_succeeds(self) -> None:
        check = PostgresHealthCheck(FakeDatabase(succeed=True), timeout_seconds=1)
        result = await check.check()
        assert result.status is ComponentStatus.HEALTHY
        assert result.critical is True

    async def test_unhealthy_when_ping_raises(self) -> None:
        check = PostgresHealthCheck(FakeDatabase(succeed=False), timeout_seconds=1)
        result = await check.check()
        assert result.status is ComponentStatus.UNHEALTHY
        assert result.message == "database unavailable"

    async def test_unhealthy_on_timeout(self) -> None:
        check = PostgresHealthCheck(FakeDatabase(succeed=True, delay=0.2), timeout_seconds=0.01)
        result = await check.check()
        assert result.status is ComponentStatus.UNHEALTHY


class TestOPAHealthCheck:
    def _check(self, client: object) -> OPAHealthCheck:
        return OPAHealthCheck(
            client,  # type: ignore[arg-type]
            base_url="http://opa:8181",
            decision_path="/v1/data/finassist/system/ready",
            timeout_seconds=1,
        )

    async def test_healthy_when_decision_is_true(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value=FakeResponse(json_data={"result": True}))
        result = await self._check(client).check()
        assert result.status is ComponentStatus.HEALTHY

    async def test_unhealthy_when_decision_is_false(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value=FakeResponse(json_data={"result": False}))
        result = await self._check(client).check()
        assert result.status is ComponentStatus.UNHEALTHY
        assert result.message is not None and "did not evaluate" in result.message

    async def test_unhealthy_when_result_key_missing(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value=FakeResponse(json_data={}))
        result = await self._check(client).check()
        assert result.status is ComponentStatus.UNHEALTHY

    async def test_unhealthy_when_payload_is_not_a_dict(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value=FakeResponse(json_data=[1, 2, 3]))
        result = await self._check(client).check()
        assert result.status is ComponentStatus.UNHEALTHY

    async def test_unhealthy_on_http_error(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value=FakeResponse(raise_status_error=True))
        result = await self._check(client).check()
        assert result.status is ComponentStatus.UNHEALTHY
        assert result.message == "policy service unavailable"

    async def test_unhealthy_on_connect_error(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await self._check(client).check()
        assert result.status is ComponentStatus.UNHEALTHY

    async def test_unhealthy_on_timeout_error(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=TimeoutError())
        result = await self._check(client).check()
        assert result.status is ComponentStatus.UNHEALTHY

    async def test_unhealthy_on_invalid_json(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value=FakeResponse(raise_json_error=True))
        result = await self._check(client).check()
        assert result.status is ComponentStatus.UNHEALTHY
        assert result.message is not None and "json" in result.message
