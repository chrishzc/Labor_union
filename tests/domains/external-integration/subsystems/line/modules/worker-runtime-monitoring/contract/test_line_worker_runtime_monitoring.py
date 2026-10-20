"""Protect LINE worker failure heartbeats and runtime health classification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from subsystems.line.runtime_contracts import LineRuntimeMode, LineWorkerHeartbeat
from subsystems.line.runtime_monitoring_application import _line_runtime_observations
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def test_runtime_records_failure_heartbeat_before_reraising_cycle_error() -> None:
    heartbeats = []
    runtime = CanonicalLineWorkerRuntime(
        SimpleNamespace(run_once=lambda: (_ for _ in ()).throw(RuntimeError("cycle failed"))),
        SimpleNamespace(run_once=lambda: 0),
        SimpleNamespace(wait=lambda timeout: False),
        lambda: None,
        heartbeats.append,
        "worker:1",
    )

    with pytest.raises(RuntimeError, match="cycle failed"):
        runtime.run_once()

    assert len(heartbeats) == 1
    assert heartbeats[0].last_error_code == "RuntimeError"
    assert heartbeats[0].last_error_message == "cycle failed"


def test_runtime_monitor_uses_shared_stale_window_and_reports_cycle_failure(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LINE_WORKER_STALE_SECONDS", raising=False)

    class RuntimeRepository:
        def __init__(self, heartbeat) -> None:
            self.heartbeat = heartbeat

        def latest_heartbeat(self):
            return self.heartbeat

        def queue_counts(self):
            return {
                "inbox_pending": 0,
                "delivery_pending": 0,
                "legacy_pending": 0,
                "matching_delivery_active": 0,
                "matching_delivery_failed": 0,
            }

    recent_success = LineWorkerHeartbeat(
        "worker:1",
        123,
        "host-1",
        LineRuntimeMode.CANONICAL,
        "{}",
        NOW,
    )
    recent_failure = LineWorkerHeartbeat(
        "worker:1",
        123,
        "host-1",
        LineRuntimeMode.CANONICAL,
        "{}",
        NOW + timedelta(seconds=61),
        last_error_code="RuntimeError",
        last_error_message="provider detail stays out of the alert",
    )

    success = _line_runtime_observations(
        RuntimeRepository(recent_success), NOW + timedelta(seconds=61)
    )[0]
    failure = _line_runtime_observations(
        RuntimeRepository(recent_failure), NOW + timedelta(seconds=62)
    )[0]

    assert success.status.value == "healthy"
    assert failure.status.value == "critical"
    assert failure.message == "LINE Worker 存活，但最近工作週期失敗"
    assert failure.details == {"age_seconds": 1.0, "last_error_code": "RuntimeError"}


def test_runtime_alert_projection_uses_fixed_rules_without_a_preferences_table() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params) -> None:
            self.executed.append((sql, params))

        def fetchall(self):
            return ({"id": 7, "preferences_json": None},)

    cursor = Cursor()
    connection = SimpleNamespace(cursor=lambda: cursor)

    targets = MySqlRuntimeMonitorRepository(connection).pending_alert_targets(41)

    assert targets == ({"id": 7, "preferences_json": None},)
    assert len(cursor.executed) == 1
    assert "line_alert_target_preferences" not in cursor.executed[0][0]
    assert "NULL AS preferences_json" in cursor.executed[0][0]


@pytest.mark.parametrize("error_code", [1142, 1146])
def test_runtime_alert_projection_does_not_hide_required_table_errors(error_code) -> None:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            raise RuntimeError(error_code, "required runtime table unavailable")

    repository = MySqlRuntimeMonitorRepository(SimpleNamespace(cursor=Cursor))
    with pytest.raises(RuntimeError) as error:
        repository.pending_alert_targets(41)
    assert error.value.args[0] == error_code


@pytest.mark.parametrize("target_type,system_health", [("group", False), ("admin_user", True)])
def test_runtime_alert_preferences_are_fixed_by_target_type(target_type, system_health) -> None:
    repository = MySqlRuntimeMonitorRepository(SimpleNamespace())
    repository.get_alert_target = lambda target_id, **kwargs: {"target_type": target_type}
    expected = dict(customer_service=True, dispatch_matching=True, staff_leave_urgent=True,
                    system_health=system_health, contract_signing=True)
    result = repository.get_target_preferences(7)
    assert result == expected
    result["customer_service"] = False
    assert repository.get_target_preferences(7) == expected
