"""Checksummed, ordered SQL migration runner.

Applies each `migrations/*.sql` file exactly once, in filename order, inside
its own transaction, and records a SHA-256 checksum of the applied content in
`app.schema_migrations`. If a previously-applied file's content changes, the
run aborts instead of silently mutating history.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
from pathlib import Path

import asyncpg

from src.core.config import load_settings
from src.core.logging import configure_logging

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Arbitrary fixed key: scopes the Postgres advisory lock to this migration
# runner so two concurrent `migrate` runs serialize instead of racing.
_ADVISORY_LOCK_KEY = 837_612_501

_BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.schema_migrations (
    filename TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class MigrationError(RuntimeError):
    """Raised when migration history cannot be safely reconciled."""


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """Return migration files in the deterministic order they must apply."""

    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.sql"))


def checksum(content: str) -> str:
    """Return a stable SHA-256 digest used to detect edited migrations."""

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def apply_migrations(conn: asyncpg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every pending migration in `directory`; return newly applied filenames.

    Raises `MigrationError` if an already-applied file's checksum no longer
    matches its recorded value.
    """

    await conn.execute("SELECT pg_advisory_lock($1)", _ADVISORY_LOCK_KEY)
    try:
        await conn.execute(_BOOTSTRAP_SQL)
        applied_rows = await conn.fetch("SELECT filename, checksum FROM app.schema_migrations")
        applied = {row["filename"]: row["checksum"] for row in applied_rows}

        newly_applied: list[str] = []
        for path in discover_migrations(directory):
            content = path.read_text(encoding="utf-8")
            digest = checksum(content)

            if path.name in applied:
                if applied[path.name] != digest:
                    raise MigrationError(
                        f"checksum mismatch for already-applied migration {path.name!r}; "
                        "an applied migration must never be edited"
                    )
                logger.info(
                    "migration already applied",
                    extra={"event": "migration_skipped", "path": path.name},
                )
                continue

            async with conn.transaction():
                await conn.execute(content)
                await conn.execute(
                    "INSERT INTO app.schema_migrations (filename, checksum) VALUES ($1, $2)",
                    path.name,
                    digest,
                )
            logger.info(
                "migration applied",
                extra={"event": "migration_applied", "path": path.name},
            )
            newly_applied.append(path.name)

        return newly_applied
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", _ADVISORY_LOCK_KEY)


async def run(dsn: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Connect, apply pending migrations and disconnect."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        return await apply_migrations(conn, directory)
    finally:
        await conn.close()


def main() -> int:
    settings = load_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    try:
        applied = asyncio.run(run(settings.database.dsn.get_secret_value()))
    except MigrationError:
        logger.exception("migration history invalid", extra={"event": "migration_failed"})
        return 1
    except (asyncpg.PostgresError, OSError, TimeoutError):
        logger.exception(
            "could not reach postgres to apply migrations",
            extra={"event": "migration_connection_failed"},
        )
        return 1
    logger.info(
        "migrations complete",
        extra={"event": "migrations_complete", "applied_count": len(applied)},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
