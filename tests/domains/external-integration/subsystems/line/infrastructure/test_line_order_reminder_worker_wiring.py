"""Focused regression for canonical order reminder source-worker wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.dependencies import line_worker_operation
from infrastructure.mysql.line_notification_repository import (
    MySqlLineNotificationRepository,
)
from infrastructure.mysql.order_pre_start_notification_source_worker import (
    MySqlOrderPreStartNotificationSourceWorker,
)
from subsystems.line.notification_source_adapters import (
    from_order_pre_start_checkpoint,
    from_order_second_payment_checkpoint,
)
from subsystems.line.runtime_contracts import LineRuntimeMode
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime


NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def test_order_reminder_source_worker_is_registered_in_canonical_additional_workers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        line_worker_operation,
        "_required_access_token",
        lambda: "test-line-access-token",
    )
    now = lambda: NOW

    workers = line_worker_operation._additional_workers(
        "worker:test",
        now,
        SimpleNamespace(materialize=lambda _identity: b""),
        object(),
    )

    worker = workers["order_pre_start_notification_sources"]
    assert isinstance(worker, MySqlOrderPreStartNotificationSourceWorker)
    assert worker._connection_factory is line_worker_operation.get_connection
    assert worker._now is now


def test_run_line_cycle_executes_canonical_runtime_that_carries_reminder_worker(
    monkeypatch,
) -> None:
    runtime_identity = SimpleNamespace()
    runs: list[str] = []
    heartbeats: list[tuple[object, int]] = []
    runtime = SimpleNamespace(
        run_once=lambda: runs.append("canonical")
        or {
            "inbox_events": 0,
            "delivery_tasks": 0,
            "order_pre_start_notification_sources": 2,
        }
    )
    monkeypatch.setattr(
        line_worker_operation,
        "validate_line_worker_runtime",
        lambda _environment: SimpleNamespace(worker_mode=LineRuntimeMode.CANONICAL),
    )
    monkeypatch.setattr(
        line_worker_operation,
        "_canonical_runtime",
        lambda _worker_identity, _runtime_identity: runtime,
    )
    monkeypatch.setattr(
        line_worker_operation,
        "record_runtime_heartbeat",
        lambda identity, processed: heartbeats.append((identity, processed)),
    )
    monkeypatch.delenv("KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED", raising=False)

    processed = line_worker_operation.run_line_cycle("worker:test", runtime_identity)

    assert runs == ["canonical"]
    assert processed == 2
    assert heartbeats == [(runtime_identity, 2)]


def test_order_reminder_source_worker_failure_is_not_reported_as_healthy_cycle() -> None:
    heartbeats = []

    class FailingOrderReminderWorker:
        def run_once(self) -> int:
            raise RuntimeError("order reminder source scan failed")

    runtime = CanonicalLineWorkerRuntime(
        SimpleNamespace(run_once=lambda: 0),
        SimpleNamespace(run_once=lambda: 0),
        SimpleNamespace(wait=lambda _timeout: False),
        lambda: None,
        heartbeats.append,
        "worker:test",
        additional_workers={
            "order_pre_start_notification_sources": FailingOrderReminderWorker()
        },
    )

    with pytest.raises(RuntimeError, match="order reminder source scan failed"):
        runtime.run_once()

    assert len(heartbeats) == 1
    assert heartbeats[0].last_error_code == "RuntimeError"
    assert "order reminder source scan failed" in heartbeats[0].last_error_message


class ExistingReminderCursor:
    def __init__(self, event) -> None:
        self.event = event
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = 0
        self.lastrowid = 0
        self._one = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, parameters=()):
        normalized = tuple(parameters)
        self.executed.append((sql, normalized))
        if sql.startswith("INSERT IGNORE INTO line_notification_source_events"):
            self.rowcount = 0
            self._one = None
            return
        if (
            "FROM line_notification_source_events" in sql
            and "source_event_identity=%s" in sql
        ):
            self._one = {
                "id": 41,
                "source_aggregate_type": self.event.source_aggregate_type,
                "source_aggregate_identity": self.event.source_aggregate_identity,
                "source_version": self.event.source_version,
                "historical_silent": self.event.historical_silent,
                "facts_snapshot": self.event.facts,
            }
            return
        if "FROM line_configuration_current" in sql:
            kind = normalized[0]
            definition = (
                {
                    "rules": [
                        {
                            "id": "current-rule",
                            "event_code": self.event.event_code,
                            "recipient_selector": "client.bound_case",
                            "template_id": "unused-template",
                            "enabled": False,
                            "predicates": [],
                        }
                    ]
                }
                if kind == "notification_rules"
                else {"templates": []}
            )
            self._one = {"revision_id": 7, "definition_snapshot": definition}
            return
        if sql.startswith(
            "SELECT 1 FROM line_notification_decisions WHERE source_event_id=%s"
        ):
            self._one = {"present": 1}
            return
        raise AssertionError(f"unexpected SQL during exact reminder replay: {sql}")

    def fetchone(self):
        value = self._one
        self._one = None
        return value


class ExistingReminderConnection:
    def __init__(self, event) -> None:
        self.cursor_instance = ExistingReminderCursor(event)

    def cursor(self):
        return self.cursor_instance


@pytest.mark.parametrize(
    "event",
    (
        from_order_pre_start_checkpoint(
            case_no="CASE-REPLAY-1",
            planned_start_date="2026-09-20",
            first_payment_amount=20000,
            already_settled=False,
            client_line_user_id="U_REPLAY_1",
            occurred_at=NOW,
        ),
        from_order_second_payment_checkpoint(
            case_no="CASE-REPLAY-2",
            second_payment_due_date="2026-09-20",
            second_payment_amount=30000,
            already_settled=False,
            client_line_user_id="U_REPLAY_2",
            occurred_at=NOW,
        ),
    ),
)
def test_exact_reminder_replay_with_existing_decision_creates_no_second_projection(
    event,
) -> None:
    connection = ExistingReminderConnection(event)

    source_event_id = MySqlLineNotificationRepository(connection).register_and_project(
        event
    )

    assert source_event_id == 41
    statements = [sql for sql, _parameters in connection.cursor_instance.executed]
    assert any("line_notification_decisions" in sql for sql in statements)
    assert not any(sql.startswith("INSERT INTO line_notification_decisions") for sql in statements)
    assert not any("line_notification_intents" in sql for sql in statements)
    assert not any("line_delivery_tasks" in sql for sql in statements)