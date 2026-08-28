from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from scripts import migrate
from src.core.config import AppSettings, DatabaseSettings


class FakeTransaction:
    async def __aenter__(self) -> FakeTransaction:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class FakeConnection:
    def __init__(self, *, existing: list[dict[str, str]] | None = None) -> None:
        self.executed: list[str] = []
        self.rows: list[dict[str, str]] = existing or []
        self.closed = False

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append(query)
        if query.strip().startswith("INSERT INTO app.schema_migrations"):
            filename, checksum = args
            self.rows.append({"filename": str(filename), "checksum": str(checksum)})
        return "OK"

    async def fetch(self, query: str, *args: object) -> list[dict[str, str]]:
        return list(self.rows)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def close(self) -> None:
        self.closed = True


def _write_migration(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


class TestDiscoverMigrations:
    def test_returns_sql_files_in_sorted_order(self, tmp_path: Path) -> None:
        _write_migration(tmp_path, "0002_second.sql", "SELECT 2;")
        _write_migration(tmp_path, "0001_first.sql", "SELECT 1;")
        (tmp_path / "readme.txt").write_text("not a migration", encoding="utf-8")

        files = migrate.discover_migrations(tmp_path)

        assert [f.name for f in files] == ["0001_first.sql", "0002_second.sql"]

    def test_missing_directory_returns_empty_list(self, tmp_path: Path) -> None:
        assert migrate.discover_migrations(tmp_path / "does-not-exist") == []


class TestChecksum:
    def test_is_deterministic(self) -> None:
        assert migrate.checksum("CREATE TABLE x;") == migrate.checksum("CREATE TABLE x;")

    def test_differs_for_different_content(self) -> None:
        assert migrate.checksum("A") != migrate.checksum("B")


class TestApplyMigrations:
    async def test_applies_pending_migrations_in_order(self, tmp_path: Path) -> None:
        _write_migration(tmp_path, "0001_first.sql", "CREATE TABLE app.a (id int);")
        _write_migration(tmp_path, "0002_second.sql", "CREATE TABLE app.b (id int);")
        conn = FakeConnection()

        applied = await migrate.apply_migrations(conn, tmp_path)  # type: ignore[arg-type]

        assert applied == ["0001_first.sql", "0002_second.sql"]
        assert [row["filename"] for row in conn.rows] == ["0001_first.sql", "0002_second.sql"]

    async def test_skips_already_applied_migration_with_matching_checksum(
        self, tmp_path: Path
    ) -> None:
        content = "CREATE TABLE app.a (id int);"
        _write_migration(tmp_path, "0001_first.sql", content)
        conn = FakeConnection(
            existing=[{"filename": "0001_first.sql", "checksum": migrate.checksum(content)}]
        )

        applied = await migrate.apply_migrations(conn, tmp_path)  # type: ignore[arg-type]

        assert applied == []

    async def test_raises_on_checksum_mismatch(self, tmp_path: Path) -> None:
        _write_migration(tmp_path, "0001_first.sql", "CREATE TABLE app.a (id int);")
        conn = FakeConnection(
            existing=[{"filename": "0001_first.sql", "checksum": "stale-checksum"}]
        )

        with pytest.raises(migrate.MigrationError, match="checksum mismatch"):
            await migrate.apply_migrations(conn, tmp_path)  # type: ignore[arg-type]

    async def test_acquires_and_releases_advisory_lock(self, tmp_path: Path) -> None:
        conn = FakeConnection()

        await migrate.apply_migrations(conn, tmp_path)  # type: ignore[arg-type]

        assert conn.executed[0] == "SELECT pg_advisory_lock($1)"
        assert conn.executed[-1] == "SELECT pg_advisory_unlock($1)"

    async def test_releases_lock_even_when_checksum_mismatch_raises(self, tmp_path: Path) -> None:
        _write_migration(tmp_path, "0001_first.sql", "CREATE TABLE app.a (id int);")
        conn = FakeConnection(existing=[{"filename": "0001_first.sql", "checksum": "stale"}])

        with pytest.raises(migrate.MigrationError):
            await migrate.apply_migrations(conn, tmp_path)  # type: ignore[arg-type]

        assert conn.executed[-1] == "SELECT pg_advisory_unlock($1)"


class TestRun:
    async def test_connects_applies_and_closes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _write_migration(tmp_path, "0001_first.sql", "CREATE TABLE app.a (id int);")
        conn = FakeConnection()

        async def fake_connect(*, dsn: str) -> FakeConnection:
            assert dsn == "postgresql://u:p@h:5432/d"
            return conn

        monkeypatch.setattr(asyncpg, "connect", fake_connect)

        applied = await migrate.run("postgresql://u:p@h:5432/d", tmp_path)

        assert applied == ["0001_first.sql"]
        assert conn.closed is True


class TestMain:
    def _settings(self) -> AppSettings:
        return AppSettings(
            _env_file=None,
            database=DatabaseSettings(dsn="postgresql://u:p@h:5432/d"),
            log_json=True,
        )

    def test_returns_zero_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(migrate, "load_settings", lambda: self._settings())

        async def fake_run(dsn: str, directory: Path = migrate.MIGRATIONS_DIR) -> list[str]:
            return ["0001_first.sql"]

        monkeypatch.setattr(migrate, "run", fake_run)

        assert migrate.main() == 0

    def test_returns_one_on_migration_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(migrate, "load_settings", lambda: self._settings())

        async def fake_run(dsn: str, directory: Path = migrate.MIGRATIONS_DIR) -> list[str]:
            raise migrate.MigrationError("checksum mismatch")

        monkeypatch.setattr(migrate, "run", fake_run)

        assert migrate.main() == 1

    def test_returns_one_on_connection_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(migrate, "load_settings", lambda: self._settings())

        async def fake_run(dsn: str, directory: Path = migrate.MIGRATIONS_DIR) -> list[str]:
            raise OSError("connection refused")

        monkeypatch.setattr(migrate, "run", fake_run)

        assert migrate.main() == 1
