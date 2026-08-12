import asyncio
import json

import pytest

from line import line_bot
from subsystems.line.webhook_inbox import mark_events_completed


pytestmark = pytest.mark.skip(
    reason="WP35 retired the direct-writer webhook; this module is legacy characterization evidence."
)


class _Cursor:
    def __init__(self, role_row=None):
        self.statements = []
        self.lastrowid = 1
        self.role_row = role_row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=None):
        self.statements.append((" ".join(statement.split()), parameters))

    def fetchone(self):
        return self.role_row


class _Connection:
    def __init__(self, role_row=None):
        self.cursor_instance = _Cursor(role_row)
        self.commits = 0

    def cursor(self, *_args, **_kwargs):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("webhook completion must not roll back")

    def close(self):
        pass


class _Request:
    headers = {"x-line-signature": "valid"}

    def __init__(self, payload):
        self._payload = payload

    async def body(self):
        return json.dumps(self._payload).encode("utf-8")


def test_mark_events_completed_does_not_write_without_event_ids():
    cursor = _Cursor()

    mark_events_completed(cursor, [])

    assert cursor.statements == []


def test_webhook_delegates_batch_completion_to_inbox_workflow(monkeypatch):
    _use_legacy_runtime(monkeypatch)
    connection = _Connection()
    completed_batches = []
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "verify_line_signature", lambda *_args: True)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)
    monkeypatch.setattr(
        line_bot,
        "mark_events_completed",
        lambda _cursor, event_ids: completed_batches.append(event_ids),
    )

    response = asyncio.run(line_bot.line_webhook(_Request({"events": [{
        "type": "unknown", "webhookEventId": "event-1", "source": {}
    }]})))

    assert response == {"status": "ok"}
    assert completed_batches == [["event-1"]]
    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert not any("UPDATE line_webhook_events" in statement for statement in statements)


def test_follow_and_unfollow_lifecycle_share_the_webhook_receipt_transaction(
    monkeypatch,
):
    _use_legacy_runtime(monkeypatch)
    connection = _Connection()
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "verify_line_signature", lambda *_args: True)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)
    monkeypatch.setattr(line_bot, "_create_onboarding_tasks", lambda *_args: None)

    response = asyncio.run(line_bot.line_webhook(_Request({"events": [
        {
            "type": "follow",
            "webhookEventId": "follow-event",
            "source": {"type": "user", "userId": "U-lifecycle"},
        },
        {
            "type": "unfollow",
            "webhookEventId": "unfollow-event",
            "source": {"type": "user", "userId": "U-lifecycle"},
        },
    ]})))

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert response == {"status": "ok"}
    assert connection.commits == 1
    assert any(statement.startswith("INSERT INTO line_users") for statement in statements)
    assert any(statement.startswith("UPDATE line_users SET status='blocked'") for statement in statements)
    assert any("UPDATE line_tasks SET status='cancelled'" in statement for statement in statements)
    assert any("UPDATE line_webhook_events" in statement for statement in statements)


def test_union_menu_legacy_handler_queues_a_role_guarded_menu_link(monkeypatch):
    _use_legacy_runtime(monkeypatch)
    connection = _Connection({"role": "union_staff"})
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "verify_line_signature", lambda *_args: True)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)
    monkeypatch.setattr(line_bot, "_load_rich_menu_id", lambda _role: "menu-union")

    response = asyncio.run(line_bot.line_webhook(_Request({"events": [{
        "type": "message", "webhookEventId": "union-menu-event",
        "source": {"type": "user", "userId": "U-union"},
        "message": {"type": "text", "text": "工會選單"},
    }]})))

    task_statement = next(
        parameters for statement, parameters in connection.cursor_instance.statements
        if "INSERT IGNORE INTO line_tasks" in statement
    )
    assert response == {"status": "ok"}
    assert task_statement[1] == "rich_menu_link"
    assert json.loads(task_statement[3])["rich_menu_id"] == "menu-union"
    assert task_statement[6] == "union-menu:union-menu-event"


def test_esc_legacy_handler_queues_a_menu_unlink_without_role_guard(monkeypatch):
    _use_legacy_runtime(monkeypatch)
    connection = _Connection({"role": "customer"})
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "verify_line_signature", lambda *_args: True)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)
    monkeypatch.setattr(line_bot, "load_message_templates", lambda: {"esc_success": "已恢復預設"})

    response = asyncio.run(line_bot.line_webhook(_Request({"events": [{
        "type": "message", "webhookEventId": "esc-event",
        "source": {"type": "user", "userId": "U-customer"},
        "message": {"type": "text", "text": "esc"},
    }]})))

    task_statement = next(
        parameters for statement, parameters in connection.cursor_instance.statements
        if "INSERT IGNORE INTO line_tasks" in statement
    )
    assert response == {"status": "ok"}
    assert task_statement[1] == "rich_menu_unlink"
    assert json.loads(task_statement[3])["success_message"] == "已恢復預設"
    assert task_statement[6] == "menu-unlink:esc-event"


def test_union_menu_legacy_redelivery_does_not_enqueue_a_second_task(monkeypatch):
    _use_legacy_runtime(monkeypatch)
    connection = _Connection({"role": "union_staff"})
    registrations = iter((True, False))
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "verify_line_signature", lambda *_args: True)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)
    monkeypatch.setattr(line_bot, "_load_rich_menu_id", lambda _role: "menu-union")
    monkeypatch.setattr(line_bot, "register_event", lambda *_args: next(registrations))
    event = {
        "type": "message", "webhookEventId": "union-menu-replay",
        "source": {"type": "user", "userId": "U-union"},
        "message": {"type": "text", "text": "工會選單"},
    }

    response = asyncio.run(line_bot.line_webhook(_Request({"events": [event, event]})))

    task_inserts = [
        statement for statement, _ in connection.cursor_instance.statements
        if "INSERT IGNORE INTO line_tasks" in statement
    ]
    assert response == {"status": "ok"}
    assert len(task_inserts) == 1


def _use_legacy_runtime(monkeypatch):
    monkeypatch.setenv("LINE_WEBHOOK_RUNTIME_MODE", "legacy")
    monkeypatch.setenv("LINE_WORKER_RUNTIME_MODE", "legacy")
