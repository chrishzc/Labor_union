"""Focused safety contract for weekly-report migration operator target confirmation."""
from __future__ import annotations

from unittest.mock import Mock

from scripts import migrate_weekly_report_batches as migration


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.last_sql = ""
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.last_sql = sql.strip()
        self.connection.sql.append(self.last_sql)
        return 1

    def fetchone(self):
        if self.last_sql == "SELECT DATABASE()":
            return (self.connection.database,)
        if self.last_sql.startswith("SELECT COUNT(*) AS cnt"):
            return (1,)
        raise AssertionError(f"unexpected fetchone for {self.last_sql!r}")


class _Connection:
    def __init__(self, database: str):
        self.database = database
        self.sql: list[str] = []
        self.commit_count = 0
        self.close_count = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.close_count += 1


def test_missing_target_confirmation_fails_before_connection(monkeypatch):
    acquire = Mock(side_effect=AssertionError("connection must not be acquired"))
    monkeypatch.setattr(migration, "get_connection", acquire)

    assert migration.main([]) == 2
    acquire.assert_not_called()


def test_mismatched_target_confirmation_fails_before_connection(monkeypatch):
    acquire = Mock(side_effect=AssertionError("connection must not be acquired"))
    monkeypatch.setattr(migration, "get_connection", acquire)

    result = migration.main([
        "--target-db", "authorized_db",
        "--confirm-target-db", "other_db",
    ])

    assert result == 2
    acquire.assert_not_called()


def test_live_database_mismatch_fails_before_any_ddl_or_commit(monkeypatch):
    connection = _Connection("connected_db")
    monkeypatch.setattr(migration, "get_connection", lambda: connection)

    result = migration.main([
        "--target-db", "authorized_db",
        "--confirm-target-db", "authorized_db",
    ])

    assert result == 2
    assert connection.sql == ["SELECT DATABASE()"]
    assert connection.commit_count == 0
    assert connection.close_count == 1


def test_exact_confirmed_live_target_preserves_existing_migration_path(monkeypatch):
    connection = _Connection("authorized_db")
    monkeypatch.setattr(migration, "get_connection", lambda: connection)

    result = migration.main([
        "--target-db", "authorized_db",
        "--confirm-target-db", "authorized_db",
    ])

    assert result == 0
    assert connection.sql[0] == "SELECT DATABASE()"
    assert any(sql.startswith("CREATE TABLE IF NOT EXISTS `weekly_report_batches`") for sql in connection.sql)
    assert any(sql.startswith("CREATE TABLE IF NOT EXISTS `weekly_report_batch_cases`") for sql in connection.sql)
    assert connection.sql[-1].startswith("SELECT COUNT(*) AS cnt")
    assert connection.commit_count == 1
    assert connection.close_count == 1
