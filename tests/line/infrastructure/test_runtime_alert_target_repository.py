"""
File: test_runtime_alert_target_repository.py
Description: 驗證 runtime alert target MySQL adapter 的鎖、row lock 與 immutable receipt SQL。
"""

import inspect
from datetime import datetime, timezone

from infrastructure.mysql.runtime_monitor_repository import (
    ALERT_TARGET_LOCK_NAME,
    _ACTIVE_GROUP_TARGETS,
    _GET_ALERT_TARGET,
    _LIST_ALERT_TARGETS,
    _RELEASE_ALERT_TARGET_LOCK,
)
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from subsystems.line.runtime_alert_target_application import RuntimeAlertTargetApplication


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args):
        return None

    def fetchall(self):
        return ({"id": 1, "target_type": "group", "display_name": "raw",
                 "enabled": True, "minimum_status": "warning",
                 "updated_at_utc": datetime(2026, 8, 21, 12, 0)},)


class _Connection:
    def cursor(self):
        return _Cursor()


class _Uow:
    def __init__(self):
        self.runtime_monitor = MySqlRuntimeMonitorRepository(_Connection())

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_advisory_lock_is_constant_and_bounded():
    assert ALERT_TARGET_LOCK_NAME == "labor_union:line_alert_group_registration_v1"
    assert "%s" in _RELEASE_ALERT_TARGET_LOCK


def test_mutation_queries_lock_same_connection_and_active_singleton():
    assert "FOR UPDATE" in _ACTIVE_GROUP_TARGETS
    assert "FOR UPDATE" in inspect.getsource(MySqlRuntimeMonitorRepository.get_alert_target)
    assert "group_id" not in _LIST_ALERT_TARGETS.split("FROM", 1)[0]


def test_pymysql_dict_cursor_naive_datetime_is_projected_as_utc():
    view = RuntimeAlertTargetApplication(_Uow, lambda: datetime.now(timezone.utc)).list_targets()[0]
    assert view.updated_at.tzinfo == timezone.utc


class _RecoveryCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class _RecoveryConnection:
    def __init__(self, rows):
        self.cursor_value = _RecoveryCursor(rows)

    def cursor(self):
        return self.cursor_value


def test_runtime_escalation_release_requires_same_source_committed_recovery():
    connection = _RecoveryConnection(
        (
            {
                "id": 41,
                "check_name": "line_worker",
                "component": "LINE Worker",
                "resulting_status": "critical",
            },
            {"id": 42},
        )
    )
    repository = MySqlRuntimeMonitorRepository(connection)

    assert repository.can_release(
        {
            "source_kind": "runtime_health",
            "trigger_code": "runtime_critical",
            "source_event_identity": "a" * 64,
        }
    )
    assert all("FOR UPDATE" in sql for sql, _ in connection.cursor_value.executed)


def test_runtime_escalation_release_rejects_wrong_component_or_missing_recovery():
    wrong_component = MySqlRuntimeMonitorRepository(
        _RecoveryConnection(
            ({"id": 41, "check_name": "database", "component": "Database", "resulting_status": "critical"},)
        )
    )
    no_recovery = MySqlRuntimeMonitorRepository(
        _RecoveryConnection(
            ({"id": 41, "check_name": "line_worker", "component": "LINE Worker", "resulting_status": "critical"},)
        )
    )
    escalation = {
        "source_kind": "runtime_health",
        "trigger_code": "runtime_critical",
        "source_event_identity": "b" * 64,
    }

    assert wrong_component.can_release(escalation) is False
    assert no_recovery.can_release(escalation) is False
