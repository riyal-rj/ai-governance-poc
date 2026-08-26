"""Concrete readiness probes for mandatory infrastructure dependencies."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter

import httpx

from src.application.ports.health import (
    ComponentHealth,
    ComponentStatus
)
from src.infrastructure.database import PostgresSQLDatabase

logger  = logging.getLogger(__name__)

class PostgresSQLHealthCheck:
    """Verify that a query can acquire and use a pooled DB connection."""

    name = "postgres"
    critical = True

    def __init__(self, database: PostgresSQLDatabase,*, timeout_seconds: float) -> None:
        self._database = database
        self._timeout_seconds = timeout_seconds

    async def check(self) -> ComponentHealth:
        started = perf_counter()
        