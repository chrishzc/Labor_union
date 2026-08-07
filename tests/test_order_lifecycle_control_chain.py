from __future__ import annotations

from datetime import date

import pytest

from subsystems.orders.order_lifecycle_command_envelope import (
    lock_order_lifecycle_command_envelope,
)
from subsystems.orders.order_lifecycle_control_commands import (
    CancellationControlCommand,
    OrderLifecycleControlConflict,
    apply_order_lifecycle_control_command,
)


class _Cursor:
    def __init__(self, results):
        self._results = iter(results)
        self.rowcount = 1
        self.lastrowid = 17
        self.executions = []

    def execute(self, sql, values):
        self.executions.append((sql, values))

    def fetchone(self):
        return next(self._results)

    def fetchall(self):
        return next(self._results)


def _order(version=3):
    return {"case_no":"C-1","status":"訂單成立","lifecycle_version":version,"cancel_reason":None,"actual_start_date":date(2026,8,1),"actual_end_date":None,"service_start_time":None,"service_end_time":None,"service_end_day_offset":None}


def _envelope(cursor):
    return lock_order_lifecycle_command_envelope(cursor, "C-1", 3, "key-1")


def test_new_cancellation_control_locks_aggregate_and_cas_projection():
    cursor = _Cursor([_order(), [], None, None])
    result = apply_order_lifecycle_control_command(cursor, _envelope(cursor), CancellationControlCommand("activate", "admin", "requested", 3, "key-1"))
    assert result.outcome == "created"
    assert result.projection.state == "active"
    assert result.projection.control_key == "order_cancelled"
    assert len(cursor.executions) == 6


def test_replay_requires_exact_payload_identity():
    event = {"id":17,"case_no":"C-1","control_type":"cancellation","control_key":"order_cancelled","scope":"order","action":"activate","actor":"admin","reason":"requested","expected_version":3,"idempotency_key":"key-1","payload_hash":"44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a","payload_snapshot":"{}"}
    state = {"control_type":"cancellation","control_key":"order_cancelled","scope":"order","state":"active","current_event_id":17,"release_policy":None,"expires_at_utc":None,"confirmed_start_date":None,"deposit_settlement_identity_hash":None,"reason":"requested","changed_by":"admin"}
    lifecycle = {"id":19,"case_no":"C-1","trigger_event":"cancel","before_status":"訂單成立","after_status":"訂單取消","actor":"admin","business_date":date(2026,8,1),"expected_version":3,"idempotency_key":"key-1","facts_snapshot":"{}"}
    replay_order = _order(4)
    replay_order["status"] = "訂單取消"
    cursor = _Cursor([replay_order, [state], event, lifecycle])
    envelope = _envelope(cursor)
    result = apply_order_lifecycle_control_command(cursor, envelope, CancellationControlCommand("activate", "admin", "requested", 3, "key-1"))
    assert result.outcome == "existing"
    with pytest.raises(OrderLifecycleControlConflict, match="actor"):
        apply_order_lifecycle_control_command(cursor, envelope, CancellationControlCommand("activate", "other", "requested", 3, "key-1"))
