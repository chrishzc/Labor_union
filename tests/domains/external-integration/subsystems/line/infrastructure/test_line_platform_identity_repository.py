"""
File: test_line_platform_identity_repository.py
Description: 驗證 verified LINE user 建立 unknown platform root 且不偽造 friend event。
"""

from copy import deepcopy

from domains.line.identities import LineUserId
from domains.line.platform_user import LineFriendStatus
from infrastructure.mysql.line_platform_identity_repository import (
    MySqlLinePlatformUserRepository,
)
from shared_kernel.identities import ExpectedVersion


class FakeConnection:
    def __init__(self, rows=None) -> None:
        self.rows = deepcopy(rows or {})
        self.statements = []
        self.effective_inserts = 0

    def cursor(self):
        return FakeCursor(self)


class FakeCursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.row = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, parameters) -> None:
        self.connection.statements.append((sql, parameters))
        line_user_id = parameters[0]
        if sql.startswith("INSERT IGNORE INTO line_platform_users"):
            if line_user_id not in self.connection.rows:
                self.connection.rows[line_user_id] = _platform_row(line_user_id)
                self.connection.effective_inserts += 1
                self.rowcount = 1
            else:
                self.rowcount = 0
            self.row = None
            return
        if sql.startswith("SELECT line_user_id,friend_status"):
            self.row = deepcopy(self.connection.rows.get(line_user_id))
            self.rowcount = 1 if self.row is not None else 0
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self.row


def test_ensure_verified_user_creates_unknown_platform_root_without_friend_event() -> None:
    connection = FakeConnection()
    repository = MySqlLinePlatformUserRepository(connection)

    snapshot = repository.ensure_verified_user(LineUserId("U-verified-new"))

    assert snapshot.friend_status is LineFriendStatus.UNKNOWN
    assert snapshot.version == ExpectedVersion(0)
    assert connection.effective_inserts == 1
    assert all("line_friend_state_events" not in sql for sql, _ in connection.statements)


def test_ensure_verified_user_is_idempotent_for_repeated_observation() -> None:
    connection = FakeConnection()
    repository = MySqlLinePlatformUserRepository(connection)

    first = repository.ensure_verified_user(LineUserId("U-verified-replay"))
    second = repository.ensure_verified_user(LineUserId("U-verified-replay"))

    assert first == second
    assert connection.effective_inserts == 1
    assert all("line_friend_state_events" not in sql for sql, _ in connection.statements)


def test_ensure_verified_user_preserves_existing_friend_state_and_version() -> None:
    existing = _platform_row(
        "U-existing",
        friend_status="active",
        aggregate_version=ExpectedVersion(4).value,
    )
    connection = FakeConnection({"U-existing": existing})
    repository = MySqlLinePlatformUserRepository(connection)

    snapshot = repository.ensure_verified_user(LineUserId("U-existing"))

    assert snapshot.friend_status is LineFriendStatus.ACTIVE
    assert snapshot.version == ExpectedVersion(4)
    assert connection.rows["U-existing"] == existing
    assert connection.effective_inserts == 0
    assert all("line_friend_state_events" not in sql for sql, _ in connection.statements)


def _platform_row(line_user_id, *, friend_status="unknown", aggregate_version=0):
    return {
        "line_user_id": line_user_id,
        "friend_status": friend_status,
        "first_followed_at_utc": None,
        "last_followed_at_utc": None,
        "blocked_at_utc": None,
        "last_event_at_utc": None,
        "aggregate_version": aggregate_version,
    }
