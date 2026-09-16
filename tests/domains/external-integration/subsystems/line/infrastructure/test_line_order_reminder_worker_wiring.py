"""Focused regression for canonical order reminder source-worker wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.dependencies import line_worker_operation
from infrastructure.mysql.order_pre_start_notification_source_worker import (
    MySqlOrderPreStartNotificationSourceWorker,
)
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
