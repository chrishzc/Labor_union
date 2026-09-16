from __future__ import annotations

from datetime import date

import pytest

from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from subsystems.scheduling.staff_leave_intake_workflow import (
    RecordStaffLeaveCustomerDecision,
    StaffLeaveIntakeWorkflow,
    StaffLeaveIntakeWorkflowError,
)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0
        self._one = None
        self._all = ()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.rowcount = 0
        self._one = None
        self._all = ()
        if "FROM scheduling_staff_leave_request_receipts WHERE idempotency_key" in sql:
            key = params[0]
            self._one = self.connection.receipts.get(key)
            return
        if "FROM scheduling_staff_leave_request_aggregates WHERE id=%s FOR UPDATE" in sql:
            self._one = dict(self.connection.root) if params[0] == self.connection.root["id"] else None
            return
        if sql.startswith("SELECT DISTINCT g.case_no"):
            self._all = tuple(dict(item) for item in self.connection.targets)
            return
        if sql.startswith("INSERT INTO scheduling_staff_leave_request_receipts"):
            key, request_id, fingerprint, result_snapshot = params
            assert request_id == self.connection.root["id"]
            if key in self.connection.receipts:
                raise AssertionError("duplicate receipt insert")
            self.connection.receipts[key] = {
                "request_fingerprint": fingerprint,
                "result_snapshot": result_snapshot,
            }
            self.connection.writes.append((key, result_snapshot))
            self.rowcount = 1
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _Connection:
    def __init__(self):
        self.root = {
            "id": 17,
            "staff_id": 23,
            "line_user_id": "U-staff",
            "leave_start_date": date(2026, 9, 20),
            "leave_end_date": date(2026, 9, 21),
            "request_reason": "family",
            "request_status": "accepted_for_processing",
            "aggregate_version": 4,
            "request_fingerprint": "request-fingerprint",
        }
        self.targets = ({"case_no": "CASE-1", "client_line_user_id": "U-customer"},)
        self.receipts = {}
        self.writes = []

    def cursor(self):
        return _Cursor(self)


def _workflow(connection):
    return StaffLeaveIntakeWorkflow(MySqlStaffLeaveIntakeRepository(connection))


def _command(*, decision="agree_defer", key="leave-decision-1", version=4,
             case_no="CASE-1", line_user_id="U-customer"):
    return RecordStaffLeaveCustomerDecision(
        request_id=17,
        expected_version=version,
        case_no=case_no,
        line_user_id=line_user_id,
        decision=decision,
        idempotency_key=key,
    )


def test_customer_decision_is_immutable_receipt_without_leave_state_transition():
    connection = _Connection()

    receipt = _workflow(connection).record_customer_decision(_command())

    assert receipt.request_id == 17
    assert receipt.request_version == 4
    assert receipt.case_no == "CASE-1"
    assert receipt.line_user_id == "U-customer"
    assert receipt.decision == "agree_defer"
    assert receipt.replayed is False
    assert connection.root["request_status"] == "accepted_for_processing"
    assert connection.root["aggregate_version"] == 4
    assert len(connection.writes) == 1


def test_exact_customer_decision_replay_reads_same_receipt_without_second_write():
    connection = _Connection()
    workflow = _workflow(connection)
    command = _command()
    first = workflow.record_customer_decision(command)

    replay = workflow.record_customer_decision(command)

    assert replay.fingerprint == first.fingerprint
    assert replay.decision == first.decision
    assert replay.replayed is True
    assert len(connection.writes) == 1


def test_same_idempotency_key_cannot_change_terminal_customer_decision():
    connection = _Connection()
    workflow = _workflow(connection)
    workflow.record_customer_decision(_command())

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_decision_idempotency_conflict"):
        workflow.record_customer_decision(
            _command(decision="reject_substitution", key="leave-decision-1")
        )

    assert len(connection.writes) == 1


def test_wrong_recipient_is_rejected_before_receipt_write():
    connection = _Connection()

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_recipient_mismatch"):
        _workflow(connection).record_customer_decision(
            _command(line_user_id="U-someone-else")
        )

    assert connection.writes == []


def test_stale_leave_version_is_rejected_before_target_lookup_or_write():
    connection = _Connection()

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_request_stale"):
        _workflow(connection).record_customer_decision(_command(version=3))

    assert connection.writes == []


def test_unaffected_case_is_rejected_before_receipt_write():
    connection = _Connection()

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_case_not_affected"):
        _workflow(connection).record_customer_decision(_command(case_no="CASE-OTHER"))

    assert connection.writes == []


def test_missing_current_customer_binding_is_not_treated_as_authorized_recipient():
    connection = _Connection()
    connection.targets = ({"case_no": "CASE-1", "client_line_user_id": None},)

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_recipient_unavailable"):
        _workflow(connection).record_customer_decision(_command())

    assert connection.writes == []


def test_unknown_customer_decision_is_rejected_before_repository_access():
    connection = _Connection()

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_decision_invalid"):
        _workflow(connection).record_customer_decision(_command(decision="maybe"))

    assert connection.writes == []
