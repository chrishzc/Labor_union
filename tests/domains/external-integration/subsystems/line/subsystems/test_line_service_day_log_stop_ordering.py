from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from infrastructure.mysql import service_day_log_notification_stop_worker as stop_worker_module
from infrastructure.mysql.service_day_log_notification_stop_worker import (
    MySqlServiceDayLogNotificationStopWorker,
)
from subsystems.line.service_day_log_notification_stop import (
    ServiceDayLogNotificationStopError,
    ServiceDayLogNotificationStopProjector,
    ServiceDayLogOutboxItem,
)
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime


class _Runner:
    def __init__(
        self,
        name,
        order,
        *,
        result=1,
        run_before_delivery=False,
        error=None,
    ):
        self.name = name
        self.order = order
        self.result = result
        self.run_before_delivery = run_before_delivery
        self.error = error

    def run_once(self):
        self.order.append(self.name)
        if self.error is not None:
            raise self.error
        return self.result


class _Wakeup:
    def wait(self, _timeout):
        return None


def _runtime(order, heartbeats, *, stop_error=None):
    stop = _Runner(
        "stop",
        order,
        result=2,
        run_before_delivery=True,
        error=stop_error,
    )
    post = _Runner("post", order, result=3)
    return CanonicalLineWorkerRuntime(
        _Runner("inbox", order, result=4),
        _Runner("delivery", order, result=5),
        _Wakeup(),
        lambda: None,
        heartbeats.append,
        "worker:test",
        additional_workers={
            "service_day_log_notification_stops": stop,
            "post_worker": post,
        },
    )


def test_service_day_log_stop_worker_declares_pre_delivery_gate():
    assert MySqlServiceDayLogNotificationStopWorker.run_before_delivery is True


def test_marked_stop_projection_runs_before_due_delivery_tasks():
    order = []
    heartbeats = []

    counts = _runtime(order, heartbeats).run_once()

    assert order == ["inbox", "stop", "delivery", "post"]
    assert counts == {
        "inbox_events": 4,
        "service_day_log_notification_stops": 2,
        "delivery_tasks": 5,
        "post_worker": 3,
    }
    assert len(heartbeats) == 1
    assert json.loads(heartbeats[0].component_status_json) == {
        "delivery_tasks": 5,
        "inbox_events": 4,
        "post_worker": 3,
        "service_day_log_notification_stops": 2,
    }


def test_stop_projection_failure_blocks_provider_delivery_for_that_cycle():
    order = []
    heartbeats = []

    with pytest.raises(RuntimeError, match="stop unavailable"):
        _runtime(
            order,
            heartbeats,
            stop_error=RuntimeError("stop unavailable"),
        ).run_once()

    assert order == ["inbox", "stop"]
    assert len(heartbeats) == 1
    assert heartbeats[0].last_error_code == "RuntimeError"
    assert json.loads(heartbeats[0].component_status_json)["delivery_tasks"] == 0


def test_projector_records_retry_then_signals_pre_delivery_failure():
    item = ServiceDayLogOutboxItem(7, 31, "2026-09-16")

    class _Outbox:
        def __init__(self):
            self.retries = []
            self.published = []

        def claim_due(self, _now, _limit):
            return (item,)

        def mark_published(self, outbox_id):
            self.published.append(outbox_id)

        def mark_retry_or_failed(self, outbox_id, now, error):
            self.retries.append((outbox_id, now, type(error).__name__))

    class _Notifications:
        def cancel_service_day_log_reminders(self, _assignment_id, _service_date):
            raise RuntimeError("cancel unavailable")

    now = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    outbox = _Outbox()

    with pytest.raises(
        ServiceDayLogNotificationStopError,
        match="service_day_log_notification_stop_failed:RuntimeError",
    ) as failure:
        ServiceDayLogNotificationStopProjector(
            outbox,
            _Notifications(),
        ).run_once(now)

    assert failure.value.processed == 1
    assert outbox.published == []
    assert outbox.retries == [(7, now, "RuntimeError")]


def test_worker_commits_recorded_retry_before_propagating_gate_failure(monkeypatch):
    state = {"committed": 0, "closed": 0}

    class _Connection:
        def close(self):
            state["closed"] += 1

    class _UnitOfWork:
        def __init__(self, _connection):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            state["committed"] += 1

    class _Projector:
        def __init__(self, *_args):
            pass

        def run_once(self, _now):
            raise ServiceDayLogNotificationStopError(
                1, RuntimeError("cancel unavailable")
            )

    monkeypatch.setattr(stop_worker_module, "MySqlUnitOfWork", _UnitOfWork)
    monkeypatch.setattr(
        stop_worker_module,
        "MySqlServiceDayLogNotificationStopRepository",
        lambda _connection: object(),
    )
    monkeypatch.setattr(
        stop_worker_module,
        "MySqlLineNotificationRepository",
        lambda _connection: object(),
    )
    monkeypatch.setattr(
        stop_worker_module,
        "ServiceDayLogNotificationStopProjector",
        _Projector,
    )

    worker = MySqlServiceDayLogNotificationStopWorker(
        _Connection,
        lambda: datetime(2026, 9, 16, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(ServiceDayLogNotificationStopError):
        worker.run_once()

    assert state == {"committed": 1, "closed": 1}
