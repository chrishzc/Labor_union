from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from line import line_bot
from subsystems.line.runtime_contracts import LineRuntimeMode


class _FakeCursor:
    def __init__(self, connection: "_FakeConnection") -> None:
        self._connection = connection
        self._last = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        del params
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("SELECT ID, NAME, PHONE, CASE_NO, LINE_USER_ID FROM CLIENTS"):
            self._last = "client"
            return
        if normalized.startswith("SELECT ID FROM BECLASS_RECORDS"):
            self._last = "survey"
            return
        if normalized.startswith("UPDATE CLIENTS SET LINE_USER_ID"):
            self._last = "update"
            self._connection.update_attempts += 1
            if self._connection.fail_on_update:
                raise RuntimeError("synthetic update failure")
            self._connection.pending_line_user_id = "U-new"
            return
        raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        if self._last == "client":
            return {
                "id": 7,
                "name": "合成客戶",
                "phone": "0912345678",
                "case_no": "SYN-LINE-226",
                "line_user_id": self._connection.persisted_line_user_id,
            }
        if self._last == "survey":
            return {"id": 11}
        raise AssertionError(f"fetchone without supported SELECT: {self._last}")


class _FakeConnection:
    def __init__(self, *, existing_line_user_id: str | None = None, fail_on_update: bool = False) -> None:
        self.persisted_line_user_id = existing_line_user_id
        self.pending_line_user_id: str | None = None
        self.fail_on_update = fail_on_update
        self.update_attempts = 0
        self.commit_calls = 0
        self.close_calls = 0

    def cursor(self, *_args, **_kwargs):
        return _FakeCursor(self)

    def commit(self) -> None:
        self.commit_calls += 1
        self.persisted_line_user_id = self.pending_line_user_id
        self.pending_line_user_id = None

    def close(self) -> None:
        self.close_calls += 1
        # Model the configured PyMySQL connection's non-autocommit transaction:
        # uncommitted staged state is discarded on close.
        self.pending_line_user_id = None


def _payload(*, force_rebind: bool = False) -> line_bot.LineBindPayload:
    return line_bot.LineBindPayload(
        name="合成客戶",
        phone="0912-345-678",
        line_user_id="U-new",
        force_rebind=force_rebind,
    )


def test_line_bind_canonical_fails_closed_before_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(line_bot, "line_webhook_runtime_mode", lambda: LineRuntimeMode.CANONICAL)

    def forbidden_connection():
        raise AssertionError("canonical retired route must not acquire a DB connection")

    monkeypatch.setattr(line_bot, "get_db_connection", forbidden_connection)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(line_bot.line_bind(_payload()))

    assert caught.value.status_code == 410
    assert caught.value.detail["code"] == "legacy_line_route_retired"
    assert caught.value.detail["replacement"] == "/api/v1/line/identity/customer/apply"


def test_line_bind_legacy_success_commits_once_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(line_bot, "line_webhook_runtime_mode", lambda: LineRuntimeMode.LEGACY)
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)

    result = asyncio.run(line_bot.line_bind(_payload()))

    assert result["status"] == "state_a"
    assert connection.update_attempts == 1
    assert connection.commit_calls == 1
    assert connection.close_calls == 1
    assert connection.persisted_line_user_id == "U-new"


def test_line_bind_legacy_rebind_confirmation_does_not_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeConnection(existing_line_user_id="U-existing")
    monkeypatch.setattr(line_bot, "line_webhook_runtime_mode", lambda: LineRuntimeMode.LEGACY)
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)

    result = asyncio.run(line_bot.line_bind(_payload()))

    assert result["status"] == "confirm_rebind"
    assert connection.update_attempts == 0
    assert connection.commit_calls == 0
    assert connection.close_calls == 1
    assert connection.persisted_line_user_id == "U-existing"


def test_line_bind_legacy_precommit_sql_failure_closes_without_committed_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(fail_on_update=True)
    monkeypatch.setattr(line_bot, "line_webhook_runtime_mode", lambda: LineRuntimeMode.LEGACY)
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)

    result = asyncio.run(line_bot.line_bind(_payload()))

    assert result["status"] == "state_c"
    assert connection.update_attempts == 1
    assert connection.commit_calls == 0
    assert connection.close_calls == 1
    assert connection.persisted_line_user_id is None
