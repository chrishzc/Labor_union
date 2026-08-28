"""
File: test_schedule_replacement_anomaly_resolve_guard.py
Description: 驗證 SCHEDULE-002 不受 generic alert resolve 狀態抑制。
"""

import inspect
from datetime import date

from domains.anomalies.registry import (
    AlertWorkflowStatus,
    default_anomaly_registry,
    reduce_current_alert,
    resolve_alert_workflow,
)
from infrastructure.mysql import process_reminder_anomaly_source as mysql_source
from subsystems.anomalies.process_reminder_anomaly_source import (
    build_schedule_replaced_assignment_requests,
)


def _row(identity: int):
    return {
        "id": identity,
        "case_no": f"CASE-{identity}",
        "staff_id": 9,
        "assigned_start_date": date(2026, 8, 1),
        "assigned_end_date": date(2026, 8, 10),
        "floor_fee_allocated": 1000,
        "replacement_reason": "service replacement",
    }


def test_replaced_roots_remain_active_without_workflow_suppression():
    requests = build_schedule_replaced_assignment_requests(
        [_row(31), _row(32)],
        as_of=date(2026, 8, 27),
    )

    assert [request.desired.source_identity for request in requests] == ["31", "32"]
    assert all(request.desired.active for request in requests)


def test_builder_and_mysql_scan_do_not_accept_resolved_alert_state():
    signature = inspect.signature(build_schedule_replaced_assignment_requests)
    assert "already_resolved_assignment_ids" not in signature.parameters
    assert not hasattr(mysql_source, "_SCHEDULE_REPLACED_RESOLVED_SQL")
    source = inspect.getsource(mysql_source._scan_all)
    assert "already_resolved" not in source
    assert "workflow_status" not in source


def test_replaced_root_rescan_reopens_legacy_resolved_projection():
    request = build_schedule_replaced_assignment_requests(
        [_row(31)],
        as_of=date(2026, 8, 27),
    )[0]
    registry = default_anomaly_registry()
    current = reduce_current_alert(registry, request.desired, None)
    assert current is not None
    resolved = resolve_alert_workflow(current, current.workflow_version, "legacy resolved")

    reopened = reduce_current_alert(registry, request.desired, resolved)

    assert reopened is not None
    assert reopened.predicate_active is True
    assert reopened.workflow_status is AlertWorkflowStatus.OPEN
    assert reopened.workflow_version == resolved.workflow_version + 1
