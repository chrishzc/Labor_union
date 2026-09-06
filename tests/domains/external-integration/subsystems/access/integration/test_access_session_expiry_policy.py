"""Focused Access Session policy checks without sleeping or touching MySQL."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from subsystems.access import authentication_session


def test_session_expiry_ignores_idle_elapsed_time_before_absolute_deadline() -> None:
    issued_at = datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)
    absolute = issued_at + timedelta(hours=8)

    assert authentication_session._session_expiry(
        issued_at + timedelta(minutes=31), absolute
    ) == absolute


def test_session_queries_keep_revocation_enabled_and_absolute_guards() -> None:
    source = Path(authentication_session.__file__).read_text(encoding="utf-8")

    assert "s.revoked_at IS NULL" in source
    assert "u.enabled=TRUE" in source
    assert "s.absolute_expires_at > UTC_TIMESTAMP()" in source
    assert "s.expires_at > UTC_TIMESTAMP()" not in source


def test_refresh_reports_absolute_expiry_without_idle_renewal() -> None:
    cursor = _RefreshCursor(datetime(2026, 9, 5, 17, 0))
    connection = _RefreshConnection(cursor)

    refreshed = authentication_session.renew_admin_session(
        "session-token",
        connection_factory=lambda: connection,
        session_minutes=30,
    )

    assert refreshed == datetime(2026, 9, 5, 17, 0)
    update_sql = cursor.queries[0]
    assert "SET s.expires_at=s.absolute_expires_at" in update_sql
    assert "DATE_ADD" not in update_sql
    assert "s.expires_at > UTC_TIMESTAMP()" not in update_sql


def test_absolute_deadline_is_strict_and_revoked_or_disabled_remain_sql_guards() -> None:
    source = Path(authentication_session.__file__).read_text(encoding="utf-8")

    assert "s.absolute_expires_at > UTC_TIMESTAMP()" in source
    assert "s.revoked_at IS NULL" in source
    assert "u.enabled=TRUE" in source


class _RefreshCursor:
    def __init__(self, expiry: datetime):
        self.expiry = expiry
        self.queries: list[str] = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, _parameters=None):
        self.queries.append(query)

    def fetchone(self):
        return (self.expiry,)


class _RefreshConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def begin(self):
        return None

    def cursor(self, *_args):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True
