import json
import asyncio

import pytest

from line import line_bot


pytestmark = pytest.mark.skip(
    reason="WP35 retired the direct-writer webhook; this module is legacy characterization evidence."
)


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
        raise AssertionError("legacy willing postback must not roll back")

    def close(self):
        pass


class _Request:
    headers = {"x-line-signature": "valid"}

    def __init__(self, payload):
        self._payload = payload

    async def body(self):
        return json.dumps(self._payload).encode("utf-8")


@pytest.mark.parametrize("action", ["willing", "unwilling", "client_approve", "client_reject"])
def test_retired_legacy_postback_does_not_mutate_business_state(monkeypatch, action):
    monkeypatch.setenv("LINE_WEBHOOK_RUNTIME_MODE", "legacy")
    monkeypatch.setenv("LINE_WORKER_RUNTIME_MODE", "legacy")
    connection = _Connection()
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "verify_line_signature", lambda *_args: True)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)

    response = asyncio.run(line_bot.line_webhook(
        _Request(
            {
                "destination": "U-destination",
                "events": [
                    {
                        "type": "postback",
                        "webhookEventId": "event-1",
                        "source": {"type": "user", "userId": "U-staff"},
                        "postback": {
                            "data": f"action={action}&case_no=C-1&staff_id=8"
                        },
                    }
                ],
            }
        )
    ))

    assert response == {"status": "ok"}
    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert not any("UPDATE matching_records" in statement for statement in statements)
    assert not any("UPDATE orders SET client_approved" in statement for statement in statements)
    assert any("INSERT IGNORE INTO line_tasks" in statement for statement in statements)
    assert connection.commits == 1
