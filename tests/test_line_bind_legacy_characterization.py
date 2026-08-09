"""Preserve the client LINE binding confirmation workflow during migration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from line import line_bot


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, object]] = []
        self.lastrowid = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=None) -> None:
        self.statements.append((" ".join(statement.split()), parameters))

    @staticmethod
    def fetchone():
        return {
            "id": 17,
            "name": "王小美",
            "case_no": "C-2026-01",
            "line_user_id": "",
        }


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.commits = 0

    def cursor(self, *_):
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        raise AssertionError("first-time bind must not roll back")

    def close(self) -> None:
        return None


def test_first_time_bind_does_not_create_an_order(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)
    monkeypatch.setattr(
        line_bot,
        "_trusted_line_user_id",
        lambda *_: asyncio.sleep(0, result="U-client"),
    )
    result = asyncio.run(
        line_bot.line_bind(
            SimpleNamespace(
                name="王小美",
                phone="0912-345-678",
                line_user_id="U-untrusted",
                line_id_token="signed-token",
                force_rebind=False,
            )
        )
    )

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert result["status"] == "success"
    assert any("UPDATE clients SET line_user_id = %s WHERE id = %s" in statement for statement in statements)
    assert any("INSERT IGNORE INTO line_tasks" in statement for statement in statements)
    assert not any("INSERT INTO orders" in statement for statement in statements)
    assert connection.commits == 1
