import asyncio
import json

from line import line_bot
from subsystems.line.webhook_inbox import mark_events_completed


class _Cursor:
    def __init__(self):
        self.statements = []
        self.lastrowid = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=None):
        self.statements.append((" ".join(statement.split()), parameters))


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()
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
