"""
File: test_access_security_alert_outbox.py
Description: 驗證 Access Control 安全告警 outbox 的成功投影、失敗重試與輸入邊界。
"""

from __future__ import annotations

import json

import pytest

from subsystems.access import security_alert_outbox


def test_completed_intent_is_projected_once_and_marked_completed() -> None:
    connection = _Connection([_event(9), None])
    projected: list[dict[str, object]] = []

    result = security_alert_outbox.consume_security_alert_outbox(
        connection,
        project_alert=lambda _cursor, **values: projected.append(values),
    )

    assert result.delivered_count == 1
    assert result.failed_count == 0
    assert projected == [{
        "alert_code": "access_account_created",
        "source_domain": "ACCESS_CONTROL",
        "case_key": "a" * 64,
        "reason": "admin.account.created",
        "details": {"reason": "admin.account.created", "source_audit_id": 7},
    }]
    assert any("processing_status='completed'" in statement for statement, _ in connection.statements)
    assert connection.commits == 1
    assert connection.rollbacks == 1  # The final empty queue check has no state to commit.


def test_projection_failure_requeues_the_same_intent() -> None:
    connection = _Connection([_event(10)])

    result = security_alert_outbox.consume_security_alert_outbox(
        connection,
        project_alert=lambda _cursor, **_values: (_ for _ in ()).throw(
            RuntimeError("projection down")
        ),
        maximum_events=1,
    )

    assert result.delivered_count == 0
    assert result.failed_count == 1
    assert any("last_error_code='projection_failed'" in statement for statement, _ in connection.statements)
    assert connection.commits == 1
    assert connection.rollbacks == 1


def test_negative_maximum_events_is_rejected() -> None:
    with pytest.raises(ValueError, match="maximum_events_must_not_be_negative"):
        security_alert_outbox.consume_security_alert_outbox(
            _Connection([]),
            project_alert=lambda _cursor, **_values: None,
            maximum_events=-1,
        )


def _event(identifier: int) -> dict[str, object]:
    return {
        "id": identifier,
        "source_audit_id": 7,
        "alert_code": "access_account_created",
        "alert_identity": "a" * 64,
        "payload_snapshot": json.dumps({"reason": "admin.account.created", "source_audit_id": 7}),
    }


class _Connection:
    def __init__(self, events: list[dict[str, object] | None]) -> None:
        self._events = iter(events)
        self.statements: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0

    def begin(self) -> None:
        return None

    def cursor(self) -> "_Cursor":
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        self._last_statement = ""

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, _type, _value, _traceback) -> bool:
        return False

    def execute(self, statement: str, parameters: object = None) -> None:
        self._last_statement = statement
        self._connection.statements.append((statement, parameters))

    def fetchone(self) -> dict[str, object] | None:
        assert "FROM admin_security_alert_outbox" in self._last_statement
        return next(self._connection._events)
