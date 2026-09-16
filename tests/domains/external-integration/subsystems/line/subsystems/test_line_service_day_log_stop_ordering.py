from __future__ import annotations

import json

import pytest

from infrastructure.mysql.service_day_log_notification_stop_worker import (
    MySqlServiceDayLogNotificationStopWorker,
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
