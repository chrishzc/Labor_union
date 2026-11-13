"""Focused regression for canonical order reminder source-worker wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.dependencies import line_worker_operation
from subsystems.line.runtime_contracts import LineRuntimeMode
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime


NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def test_canonical_group_postback_routes_to_start_day_application(monkeypatch):
    calls=[]
    monkeypatch.setattr(line_worker_operation,'ServiceStartDayPostbackApplication',
        lambda:SimpleNamespace(handle=lambda event,unit:calls.append((event,unit)) or True))
    consumer=line_worker_operation._event_consumer('synthetic-group-postback',lambda:NOW)
    event=SimpleNamespace(event=SimpleNamespace(event_type='postback'))
    unit=object()
    assert consumer._dispatcher.dispatch(event,unit).status.value=='processed'
    assert calls==[(event,unit)]


def test_retired_order_group_source_worker_is_not_registered(
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

    assert "order_pre_start_notification_sources" not in workers
    assert "payment_reminder_notifications" in workers


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
            "payment_reminder_notifications": 2,
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
            "payment_reminder_notifications": FailingOrderReminderWorker()
        },
    )

    with pytest.raises(RuntimeError, match="order reminder source scan failed"):
        runtime.run_once()

    assert len(heartbeats) == 1
    assert heartbeats[0].last_error_code == "RuntimeError"
    assert "order reminder source scan failed" in heartbeats[0].last_error_message
