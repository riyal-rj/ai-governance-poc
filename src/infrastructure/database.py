"""Process scoped async PostgresSQL connection pool."""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from src.core.config import DatabaseSettings
from src.core.errors import DependencyUnavailableError

logger = logging.getLogger(__name__)

class PostgresSQLDatabase:
    """Own one asyncpg pool per application process.
    
        The wrapper centralizes pool sizing, timeouts and shutdown.
        Repositories added in Phase 2recieve this object through dependency 
        injection instead of opening connection themselves."""

    def __init__(self,
                 settings: DatabaseSettings,*,
                 application_name:str) -> None:
        self._settings= settings
        self._application_name = application_name
        self._pool: asyncpg.Pool | None = None

    @property
    def connected(self) -> bool:
        return self._pool is not None

    async def connect(self) -> None:
        """Open the pool once; fail if PostgresSQL cannot be reached in time."""

        if self._pool is not None:
            return
        try:
            pool = await asyncpg.create_pool(
                dsn = self._settings.dsn.get_secret_value(),
                min_size = self._settings.min_pool_size,
                max_size = self._settings.max_pool_size,
                timeout = self._settings.connect_timeout_seconds,
                command_timeout = self._settings.command_timeout_seconds,
                server_settings = {
                    "application_name": self._application_name
                }
            )
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            logger.exception(
                "postgres connection pool creation failed.",
                extra = {
                    "event":"postgres_connection_failed",
                    "dependency" :"postgres"
                }
            )
            raise DependencyUnavailableError("postgres") from exc
        if pool is  None:
            raise DependencyUnavailableError("postgres")
        self._pool = pool


    async def ping(self) -> None:
        """Exceute the smallest meaningful round trip through the pool."""

        pool = self._require_pool()
        value = await pool.fetchval("SELECT 1")
        if value != 1:
            raise DependencyUnavailableError("postgres")

    async def aclose(self) -> None:
        """Gracefully darin the pool with the bounded shutdown timeout."""

        pool, self._pool = self._pool, None
        if pool is None:
            return
        try:
            await asyncio.wait_for(pool.close(),
                                   timeout=self._settings.close_timeout_seconds)
        except TimeoutError:
            logger.error(
                "postgres pool did not close before deadline ; terminating",
                extra = {
                    "event":"postgres_close_timeout",
                    "dependency":"postgres"
                },
            )
            pool.terminate()

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise DependencyUnavailableError("postgres")
        return self._pool
