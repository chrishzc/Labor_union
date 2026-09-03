"""File: test_customer_service_escalation_repository.py
Description: 驗證 M4 escalation adapter 的 parameterization、CAS 與 fail-closed 邊界。
"""

from __future__ import annotations

import pytest

from datetime import datetime, timezone
import json

from domains.customer_service.escalation import (
    AutomationHoldState,
    EscalationEventType,
    EscalationWorkflowStatus,
    EscalationAlertIntent,
    EscalationContext,
    TriggerCode,
)
from domains.customer_service.ticket import CustomerServiceCategory
from infrastructure.mysql.customer_service_escalation_repository import (
    CustomerServiceEscalationNotImplementedError,
    CustomerServiceEscalationVersionConflictError,
    MySqlCustomerServiceEscalationRepository,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.customer_service.escalation_contracts import CreateHumanEscalation, HumanEscalationReceipt


class _Cursor:
    def __init__(self, row=None, *, lastrowid=7, rowcount=1):
        self.row = row
        self.lastrowid = lastrowid
        self.rowcount = rowcount
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))

    def fetchone(self):
        return self.row

class _TargetCursor(_Cursor):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, *cursors):
        self.cursors = list(cursors)

    def cursor(self):
        return self.cursors.pop(0) if self.cursors else _Cursor()


def _command() -> CreateHumanEscalation:
    return CreateHumanEscalation(
        source_event_identity="line-event:m4",
        source_kind="line_inbox",
        source_fingerprint="a" * 64,
        trigger_code=TriggerCode.COMPLAINT,
        trigger_policy_version="complaint.v1",
        ticket_category=CustomerServiceCategory.OTHER,
        context=EscalationContext("complaint_explicit", "complaint.v1", "other", "m4-mask.v1"),
        hold_scope="conversation:opaque",
        idempotency_key=IdempotencyKey("m4-create-1"),
        correlation_id=CorrelationId("m4-correlation-1"),
        actor=ActorContext("system:m4"),
    )


def test_lookup_is_parameterized_and_locks_when_requested():
    cursor = _Cursor({"id": 7})
    repository = MySqlCustomerServiceEscalationRepository(_Connection(cursor))
    assert repository.get_by_id(7, lock=True) == {"id": 7}
    sql, params = cursor.calls[0]
    assert "WHERE id=%s FOR UPDATE" in sql
    assert params == (7,)


def test_create_serializes_allowlisted_masked_context():
    insert, read = _Cursor(lastrowid=11), _Cursor({"id": 11, "ticket_id": 21})
    result = MySqlCustomerServiceEscalationRepository(_Connection(insert, read)).create(
        _command(), {"ticket_id": 21}
    )
    assert result["id"] == 11
    _, params = insert.calls[0]
    assert any("complaint_explicit" in str(value) for value in params)
    assert all("line_user_id" not in str(value) for value in params)


def test_transition_fails_closed_on_stale_cas():
    cursor = _Cursor(rowcount=0)
    repository = MySqlCustomerServiceEscalationRepository(_Connection(cursor))
    with pytest.raises(CustomerServiceEscalationVersionConflictError):
        repository.transition(7, workflow_status="claimed", workflow_version=1)
    assert cursor.calls[0][1][-2:] == (7, 0)


def test_append_event_has_exact_parameter_count():
    cursor = _Cursor()
    MySqlCustomerServiceEscalationRepository(_Connection(cursor)).append_event(
        7,
        EscalationEventType.CREATED,
        expected_escalation_version=0,
        resulting_escalation_version=0,
        expected_ticket_version=None,
        resulting_ticket_version=None,
        actor_ref="system:m4",
        reason_code="complaint",
        reason_evidence_digest="b" * 64,
        receipt_id="receipt:m4",
        idempotency_key="m4-create-1",
        correlation_id="m4-correlation-1",
    )
    sql, params = cursor.calls[0]
    assert sql.count("%s") == len(params) == 12


def test_receipt_snapshot_is_written_to_existing_immutable_receipt_table():
    cursor = _Cursor()
    receipt = HumanEscalationReceipt(
        "receipt:m4", "customer_service_human_escalation", "create", 7,
        "ticket:21", EscalationWorkflowStatus.OPEN, AutomationHoldState.ACTIVE,
        "v1", False, "corr-m4", datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    MySqlCustomerServiceEscalationRepository(_Connection(cursor)).save_receipt("key", "c" * 64, receipt)
    sql, params = cursor.calls[0]
    assert "line_command_receipts" in sql
    assert params[0] == "key"
    assert "receipt:m4" in str(params[3:5])


def test_masked_alert_uses_existing_global_outbox_and_updates_status():
    cursor = _Cursor()
    intent = EscalationAlertIntent(
        "escalation:7", "ticket:21", TriggerCode.COMPLAINT, "other",
        "complaint_explicit", AutomationHoldState.ACTIVE, "corr-m4", "a" * 64,
    )
    MySqlCustomerServiceEscalationRepository(_Connection(cursor)).enqueue_alert(intent)
    assert len(cursor.calls) == 2
    assert "line_domain_outbox" in cursor.calls[0][0]
    assert "UPDATE customer_service_escalations" in cursor.calls[1][0]
    assert all("line_user_id" not in str(value) for value in cursor.calls[0][1])


def test_masked_alert_captures_active_target_and_configuration_snapshot():
    target = _TargetCursor(({
        "id": 3,
        "target_type": "group",
        "group_id": "Ctask96M4Alert0901",
        "minimum_status": "warning",
        "updated_at_utc": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "linked_line_user_id": None,
    },))
    outbox, update = _Cursor(), _Cursor()
    intent = EscalationAlertIntent(
        "escalation:7", "ticket:21", TriggerCode.COMPLAINT, "other",
        "complaint_explicit", AutomationHoldState.ACTIVE, "corr-m4", "a" * 64,
    )
    MySqlCustomerServiceEscalationRepository(_Connection(target, outbox, update)).enqueue_alert(intent)
    payload = json.loads(outbox.calls[0][1][3])
    assert payload["target_snapshot"] == {
        "target_id": 3,
        "recipient_type": "group",
        "recipient_identity": "Ctask96M4Alert0901",
        "active": True,
        "configuration": {
            "minimum_status": "warning",
            "revision": "2026-09-01T00:00:00+00:00",
        },
    }


def test_source_append_uses_existing_ticket_timeline_without_raw_identity():
    lookup, insert = _Cursor({"id": 7, "ticket_id": 21}), _Cursor()
    MySqlCustomerServiceEscalationRepository(_Connection(lookup, insert)).append_source_event(7, _command())
    sql, params = insert.calls[0]
    assert "customer_service_ticket_events" in sql
    assert params[0] == 21
    assert "line_user_id" not in str(params)
