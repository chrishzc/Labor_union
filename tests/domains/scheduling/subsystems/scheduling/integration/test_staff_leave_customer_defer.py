"""Customer-approved defer uses the existing Scheduling command/receipt path.

The SQL checks run production queries in SQLite with DB-API/JSON adaptations;
they do not qualify MySQL row locks or the cross-owner Apply transaction.
"""
from dataclasses import replace
from datetime import date
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from api.dependencies import leave_substitution as composition
from api.schemas.leave_substitution import (
    CustomerLeaveDeferApplyBody,
    CustomerLeaveDeferPreviewBody,
)
from domains.scheduling.leave_substitution import (
    LeaveResolutionType,
    LeaveSubstitutionBatchIntent,
    LeaveSubstitutionItem,
)
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling import leave_substitution_linked_request_resolution as linked_module
from subsystems.scheduling.leave_substitution_workflow import (
    LeaveSubstitutionApplyRequest,
    LinkedLeaveRequestIntent,
    LinkedLeaveRequestResolutionError,
)


class SqlCursor:
    def __init__(self, owner):
        self.owner = owner
        self.cursor = owner.db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cursor.close()
        return False

    def execute(self, sql, params):
        self.owner.calls.append((sql, params))
        # The transaction/locking assertion is outside this SQLite boundary.
        sql = sql.removesuffix(" FOR UPDATE").replace("%s", "?")
        self.cursor.execute(sql, tuple(
            p.isoformat() if isinstance(p, date) else p for p in params
        ))

    @staticmethod
    def row(row):
        if row is None:
            return None
        result = dict(row)
        for key in ("work_date", "leave_start_date", "leave_end_date"):
            if isinstance(result.get(key), str):
                result[key] = date.fromisoformat(result[key])
        return result

    def fetchone(self):
        return self.row(self.cursor.fetchone())

    def fetchall(self):
        return tuple(self.row(row) for row in self.cursor.fetchall())


class SqlConnection:
    def __init__(self, db):
        self.db = db
        self.calls = []

    def cursor(self):
        return SqlCursor(self)


def decision(**changes):
    return {
        "family": "scheduling-staff-leave-customer-decision/v1",
        "request_id": 17, "request_version": 3, "case_no": "CASE-001",
        "line_user_id": "Uclient", "decision": "agree_defer", **changes,
    }


@pytest.fixture
def fixture():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    # SQLite json_extract returns unquoted scalar strings already.
    db.create_function("JSON_UNQUOTE", 1, lambda value: value)
    db.executescript("""
        CREATE TABLE scheduling_staff_leave_request_aggregates (
            id INTEGER PRIMARY KEY, staff_id INTEGER, line_user_id TEXT,
            leave_start_date TEXT, leave_end_date TEXT, request_reason TEXT,
            request_status TEXT, aggregate_version INTEGER, request_fingerprint TEXT);
        CREATE TABLE scheduling_staff_leave_request_receipts (
            idempotency_key TEXT PRIMARY KEY, request_id INTEGER,
            request_fingerprint TEXT, result_snapshot TEXT);
        CREATE TABLE scheduling_aggregates (case_no TEXT PRIMARY KEY, effective_generation_id INTEGER);
        CREATE TABLE case_staff_assignments (
            id INTEGER PRIMARY KEY, case_no TEXT, staff_id INTEGER, generation_id INTEGER, status TEXT);
        CREATE TABLE staff_schedule (
            id INTEGER PRIMARY KEY, assignment_id INTEGER, staff_id INTEGER, generation_id INTEGER,
            work_date TEXT, is_work_day INTEGER, effective_marker INTEGER);
        CREATE TABLE orders (case_no TEXT PRIMARY KEY, client_id INTEGER);
        CREATE TABLE line_identity_role_bindings (
            line_user_id TEXT, subject_type TEXT, subject_reference TEXT, binding_status TEXT);
        INSERT INTO scheduling_staff_leave_request_aggregates VALUES (
            17,9,'Ustaff','2026-09-20','2026-09-22','leave','accepted_for_processing',3,'fp');
        INSERT INTO scheduling_aggregates VALUES ('CASE-001',20),('CASE-002',21);
        INSERT INTO case_staff_assignments VALUES
            (1,'CASE-001',9,20,'active'), (2,'CASE-002',9,21,'active');
        INSERT INTO staff_schedule VALUES
            (11,1,9,20,'2026-09-20',1,1), (12,1,9,20,'2026-09-21',0,1),
            (13,1,9,20,'2026-09-22',1,1), (14,1,9,20,'2026-09-23',1,1),
            (15,1,9,19,'2026-09-21',1,1), (16,1,9,20,'2026-09-21',1,NULL),
            (21,2,9,21,'2026-09-22',1,1);
        INSERT INTO orders VALUES ('CASE-001',41),('CASE-002',42);
        INSERT INTO line_identity_role_bindings VALUES
            ('Uclient','customer','41','bound'),('Uother','customer','42','bound');
    """)
    db.execute("INSERT INTO scheduling_staff_leave_request_receipts VALUES (?,?,?,?)",
               ("decision-17-v3-case1", 17, "f" * 64, json.dumps(decision())))
    db.commit()
    connection = SqlConnection(db)
    try:
        yield MySqlStaffLeaveIntakeRepository(connection), db, connection
    finally:
        db.close()


def intent(fixture, *, assignment_id=1, version=3, case_no="CASE-001", lock=False):
    return fixture[0].customer_defer_intent(17, version, case_no, assignment_id, lock=lock)


def test_consent_derives_only_current_same_case_staff_work_days(fixture):
    _, db, _ = fixture
    db.execute("PRAGMA query_only=ON")
    result = intent(fixture)
    assert result.original_assignment_id == 1
    assert [(item.original_schedule_id, item.work_date) for item in result.items] == [
        (11, date(2026, 9, 20)), (13, date(2026, 9, 22)),
    ]
    assert all(item.resolution_type is LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS
               and item.substitute_staff_id is None and not item.is_double_pay
               for item in result.items)
    assert not db.in_transaction


def test_apply_validation_uses_current_lock_reads(fixture):
    intent(fixture, lock=True)
    assert len(fixture[2].calls) == 3
    assert all(sql.endswith(" FOR UPDATE") for sql, _ in fixture[2].calls)


@pytest.mark.parametrize("changes", [
    {"family": "other"}, {"request_version": 2}, {"case_no": "CASE-002"},
])
def test_other_receipt_or_old_version_cannot_supply_consent(fixture, changes):
    fixture[1].execute("UPDATE scheduling_staff_leave_request_receipts SET result_snapshot=?",
                       (json.dumps(decision(**changes)),))
    with pytest.raises(ValueError, match="leave_customer_agreement_missing_or_ambiguous"):
        intent(fixture)


def test_missing_consent_cannot_auto_defer(fixture):
    fixture[1].execute("DELETE FROM scheduling_staff_leave_request_receipts")
    with pytest.raises(ValueError, match="leave_customer_agreement_missing_or_ambiguous"):
        intent(fixture)


def test_ambiguous_consent_fails_instead_of_selecting_first_row(fixture):
    fixture[1].execute("INSERT INTO scheduling_staff_leave_request_receipts VALUES (?,?,?,?)",
                       ("another",17,"f"*64,json.dumps(decision())))
    with pytest.raises(ValueError, match="leave_customer_agreement_missing_or_ambiguous"):
        intent(fixture)


def test_rejection_cannot_be_treated_as_agreement(fixture):
    fixture[1].execute("UPDATE scheduling_staff_leave_request_receipts SET result_snapshot=?",
                       (json.dumps(decision(decision="reject_substitution")),))
    with pytest.raises(ValueError, match="leave_customer_defer_not_agreed"):
        intent(fixture)


@pytest.mark.parametrize("change", [
    "UPDATE line_identity_role_bindings SET binding_status='revoked' WHERE subject_reference='41'",
    "UPDATE line_identity_role_bindings SET line_user_id='Unew' WHERE subject_reference='41'",
    "UPDATE line_identity_role_bindings SET subject_type='staff' WHERE subject_reference='41'",
    "UPDATE orders SET client_id=42 WHERE case_no='CASE-001'",
])
def test_current_binding_must_match_original_customer_consent(fixture, change):
    fixture[1].execute(change)
    with pytest.raises(ValueError, match="leave_customer_binding_conflict"):
        intent(fixture)


@pytest.mark.parametrize("change", [
    "UPDATE case_staff_assignments SET staff_id=10 WHERE id=1",
    "UPDATE case_staff_assignments SET status='replaced' WHERE id=1",
    "UPDATE scheduling_aggregates SET effective_generation_id=99 WHERE case_no='CASE-001'",
    "UPDATE staff_schedule SET is_work_day=0 WHERE assignment_id=1",
])
def test_missing_effective_assignment_days_cannot_produce_command(fixture, change):
    fixture[1].execute(change)
    with pytest.raises(ValueError, match="leave_customer_service_days_missing"):
        intent(fixture)


def test_wrong_assignment_for_case_cannot_be_selected(fixture):
    with pytest.raises(ValueError, match="leave_customer_service_days_missing"):
        intent(fixture, assignment_id=2)


@pytest.mark.parametrize("status", ["pending", "resolved", "cancelled", "rejected"])
def test_nonaccepted_request_cannot_be_deferred(fixture, status):
    fixture[1].execute("UPDATE scheduling_staff_leave_request_aggregates SET request_status=?", (status,))
    with pytest.raises(ValueError, match="leave_request_not_accepted"):
        intent(fixture)
    assert len(fixture[2].calls) == 1


def test_stale_request_rejected_before_consent_and_schedule(fixture):
    with pytest.raises(ValueError, match="leave_request_stale"):
        intent(fixture, version=2)
    assert len(fixture[2].calls) == 1


def resolver(fixture, candidate):
    return linked_module.LeaveSubstitutionLinkedRequestResolution(
        fixture[0], Mock(), Mock(),
        customer_defer_case_no="CASE-001", customer_defer_intent=candidate,
    )


def test_resolver_preview_is_readonly_and_apply_revalidates_days(fixture):
    candidate = intent(fixture)
    subject = resolver(fixture, candidate)
    linked = LinkedLeaveRequestIntent(17,3)
    result = subject.preview(linked)
    assert result.status == "accepted_for_processing"
    assert result.notification_intent == "not_requested"
    fixture[1].execute("UPDATE staff_schedule SET work_date='2026-09-21' WHERE id=13")
    with pytest.raises(LinkedLeaveRequestResolutionError, match="leave_customer_defer_intent_conflict"):
        subject.lock_for_apply(linked)
    subject._line_delivery_repository.enqueue.assert_not_called()


def test_substitute_payload_cannot_use_customer_defer_path(fixture):
    candidate = intent(fixture)
    altered = LeaveSubstitutionBatchIntent(1, (
        LeaveSubstitutionItem(11,date(2026,9,20),LeaveResolutionType.SUBSTITUTE,10),
    ))
    with pytest.raises(LinkedLeaveRequestResolutionError, match="leave_customer_defer_intent_conflict"):
        resolver(fixture, altered).lock_for_apply(LinkedLeaveRequestIntent(17,3))
    assert candidate.items


def test_other_case_keeps_whole_request_open_after_first_case_processed(fixture):
    subject = resolver(fixture, intent(fixture))
    locked = subject.lock_for_apply(LinkedLeaveRequestIntent(17,3))
    subject._workflow = Mock()
    # Stand in for the canonical replacement, not for a real Apply transaction.
    fixture[1].execute("UPDATE staff_schedule SET effective_marker=NULL WHERE id IN (11,13)")
    result = subject.resolve_and_enqueue(
        locked, receipt_key="first-batch", idempotency_key=IdempotencyKey("apply1"),
        correlation_id=CorrelationId("corr1"),
    )
    assert result.status == "accepted_for_processing"
    assert result.resolved_version is None
    assert result.receipt_key == "first-batch"
    assert result.notification_intent == "not_requested"
    subject._workflow.resolve.assert_not_called()
    subject._line_delivery_repository.enqueue.assert_not_called()


def test_last_processed_case_uses_existing_resolution_and_notification(fixture, monkeypatch):
    subject = resolver(fixture, intent(fixture))
    locked = subject.lock_for_apply(LinkedLeaveRequestIntent(17,3))
    snapshot = fixture[0].load(17)
    from domains.scheduling.staff_leave_intake import StaffLeaveRequestStatus
    subject._workflow = Mock()
    subject._workflow.resolve.return_value = replace(snapshot, version=4, status=StaffLeaveRequestStatus.RESOLVED)
    fixture[1].execute("UPDATE staff_schedule SET effective_marker=NULL WHERE id IN (11,13,21)")
    notification = object()
    monkeypatch.setattr(linked_module, "_completion_notification", lambda *args: notification)
    result = subject.resolve_and_enqueue(
        locked, receipt_key="last-batch", idempotency_key=IdempotencyKey("apply2"),
        correlation_id=CorrelationId("corr2"),
    )
    assert result.status == "resolved" and result.resolved_version == 4
    assert result.receipt_key == "last-batch" and result.notification_intent == "enqueued"
    assert subject._workflow.resolve.call_args.args[0].leave_substitution_receipt_key == "last-batch"
    subject._line_delivery_repository.enqueue.assert_called_once_with(notification)


def test_missing_link_retains_original_unlinked_behavior(fixture):
    subject = linked_module.LeaveSubstitutionLinkedRequestResolution(fixture[0],Mock(),Mock())
    assert subject.preview(None) is None
    assert subject.lock_for_apply(None) is None
    assert fixture[2].calls == []


def test_application_preview_hands_derived_intent_to_canonical_workflow(fixture, monkeypatch):
    workflow = Mock()
    factory = Mock(return_value=workflow)
    monkeypatch.setattr(composition, "_build_leave_workflow", factory)
    app = composition.LeaveSubstitutionApplication(fixture[2], Mock(), Mock(), Mock())
    candidate, result = app.preview_customer_defer("CASE-001",17,3,1,CorrelationId("preview"))
    request = workflow.preview.call_args.args[0]
    assert request.intent == candidate
    assert request.linked_request == LinkedLeaveRequestIntent(17,3)
    assert result is workflow.preview.return_value
    assert factory.call_args.kwargs == {"customer_defer_case_no":"CASE-001", "customer_defer_intent":candidate}


def apply_request(candidate):
    return LeaveSubstitutionApplyRequest(
        "CASE-001", candidate, ExpectedVersion(1), ExpectedVersion(2), ExpectedVersion(3),
        ExpectedVersion(4), PreviewFingerprint("e"*64), IdempotencyKey("original-apply"),
        ActorContext("test-admin"), "customer agreed", CorrelationId("original-corr"),
        LinkedLeaveRequestIntent(17,3),
    )


def test_application_keeps_original_command_for_canonical_replay(fixture, monkeypatch):
    request = apply_request(intent(fixture))
    # A successful prior Apply may have resolved the root and replaced all rows.
    fixture[1].execute("DELETE FROM scheduling_staff_leave_request_aggregates")
    workflow = Mock()
    factory = Mock(return_value=workflow)
    monkeypatch.setattr(composition, "_build_leave_workflow", factory)
    fixture[2].calls.clear()
    app = composition.LeaveSubstitutionApplication(fixture[2],Mock(),Mock(),Mock())
    result = app.apply_customer_defer(request)
    assert fixture[2].calls == []
    workflow.apply.assert_called_once_with(request)
    assert result is workflow.apply.return_value
    assert factory.call_args.kwargs["customer_defer_intent"] is request.intent


def test_customer_apply_requires_linked_request_before_workflow(fixture, monkeypatch):
    request = replace(apply_request(intent(fixture)), linked_request=None)
    factory = Mock()
    monkeypatch.setattr(composition, "_build_leave_workflow", factory)
    app = composition.LeaveSubstitutionApplication(fixture[2],Mock(),Mock(),Mock())
    with pytest.raises(ValueError, match="leave_request_identity_pair_required"):
        app.apply_customer_defer(request)
    factory.assert_not_called()


def test_composition_uses_existing_owners_and_customer_resolver(fixture, monkeypatch):
    candidate = intent(fixture)
    workflow = Mock()
    monkeypatch.setattr(composition, "LeaveSubstitutionWorkflow", workflow)
    owners = ["MySqlClientFinanceLeaveImpactPort", "MySqlPayrollLeaveImpactPort", "MySqlOrdersLeaveImpactPort",
              "MySqlSchedulingHolidayQuery", "MySqlLineDeliveryTaskRepository", "MySqlUnitOfWork"]
    factories = {name: Mock() for name in owners}
    for name, factory in factories.items():
        monkeypatch.setattr(composition, name, factory)
    clock_factory = Mock()
    monkeypatch.setattr(composition, "SystemBusinessClock", clock_factory)
    repository = Mock()
    result = composition._build_leave_workflow(
        fixture[2], repository, customer_defer_case_no="CASE-001", customer_defer_intent=candidate,
    )
    assert result is workflow.return_value
    args = workflow.call_args.args
    assert args[0] is repository
    assert args[1] is factories[owners[0]].return_value
    assert args[2] is factories[owners[1]].return_value
    assert args[3] is factories[owners[2]].return_value
    assert args[4] is factories[owners[3]].return_value
    assert args[5]() is factories["MySqlUnitOfWork"].return_value
    linked = args[6]
    assert isinstance(linked, linked_module.LeaveSubstitutionLinkedRequestResolution)
    assert linked._customer_defer_intent is candidate
    assert linked._customer_defer_case_no == "CASE-001"
    assert linked.preview(LinkedLeaveRequestIntent(17,3)).status == "accepted_for_processing"


def test_preview_input_cannot_supply_customer_decision_or_service_days():
    payload = {"leave_request_id":17, "expected_leave_request_version":3,"original_assignment_id":1}
    assert CustomerLeaveDeferPreviewBody(**payload).leave_request_id == 17
    for extra in ({"decision":"agree_defer"}, {"items":[]}, {"line_user_id":"Uforged"}):
        with pytest.raises(ValidationError):
            CustomerLeaveDeferPreviewBody(**payload, **extra)


@pytest.mark.parametrize("field", ["leave_request_id", "expected_leave_request_version"])
def test_apply_input_cannot_omit_or_null_linked_identity(field):
    payload = {
        "leave_request_id":17,"expected_leave_request_version":3,"original_assignment_id":1,
        "items":[{"original_schedule_id":11,"work_date":"2026-09-20","resolution_type":"defer_following_assignments"}],
        "expected_order_version":1,"expected_scheduling_version":2,
        "expected_client_finance_version":3,"expected_payroll_version":4,
        "preview_fingerprint":"f"*64,"reason":"customer agreed",
    }
    assert CustomerLeaveDeferApplyBody(**payload).to_intent().items[0].work_date == date(2026,9,20)
    omitted = dict(payload);omitted.pop(field)
    with pytest.raises(ValidationError):
        CustomerLeaveDeferApplyBody(**omitted)
    with pytest.raises(ValidationError):
        CustomerLeaveDeferApplyBody(**{**payload,field:None})


def test_customer_preview_route_returns_canonical_preview_and_exact_apply_items(fixture, monkeypatch):
    from api.routes import leave_substitution as route
    candidate = intent(fixture)
    app = Mock()
    preview = object()
    app.preview_customer_defer.return_value = (candidate, preview)
    monkeypatch.setattr(route, "_preview_payload", lambda value: {"canonical_preview": value is preview})
    body = CustomerLeaveDeferPreviewBody(leave_request_id=17, expected_leave_request_version=3, original_assignment_id=1)
    result = route.preview_customer_leave_defer(body, "CASE-001", "request-corr", object(), app)
    assert result.data["canonical_preview"] is True
    assert result.data["leave_request_id"] == 17
    assert result.data["expected_leave_request_version"] == 3
    assert result.data["original_assignment_id"] == 1
    assert result.data["items"] == [
        {"original_schedule_id":11,"work_date":"2026-09-20","resolution_type":"defer_following_assignments",
         "substitute_staff_id":None,"is_double_pay":False,"replacement_work_date":None},
        {"original_schedule_id":13,"work_date":"2026-09-22","resolution_type":"defer_following_assignments",
         "substitute_staff_id":None,"is_double_pay":False,"replacement_work_date":None},
    ]
    assert "line_user_id" not in result.data and "decision" not in result.data
    app.preview_customer_defer.assert_called_once_with("CASE-001",17,3,1,CorrelationId("request-corr"))


def test_customer_apply_route_passes_exact_versions_fingerprint_identity_and_receipt(monkeypatch):
    from api.routes import leave_substitution as route
    app = Mock()
    app.apply_customer_defer.return_value = SimpleNamespace(
        batch_key="saved-batch",case_no="CASE-001",order_version=2,scheduling_generation=3,
        scheduling_version=3,client_finance_version=4,payroll_version=5,
        outcome_event_ids=(101,),preview_fingerprint=PreviewFingerprint("a"*64),linked_request=None,
    )
    body = CustomerLeaveDeferApplyBody(
        leave_request_id=17,expected_leave_request_version=3,original_assignment_id=1,
        items=[{"original_schedule_id":11,"work_date":"2026-09-20","resolution_type":"defer_following_assignments"}],
        expected_order_version=1,expected_scheduling_version=2,expected_client_finance_version=3,
        expected_payroll_version=4,preview_fingerprint="a"*64,reason="confirmed current preview",
    )
    result = route.apply_customer_leave_defer(body,"CASE-001","same-apply-key","same-corr",
                                            SimpleNamespace(username="test-admin"),app)
    command = app.apply_customer_defer.call_args.args[0]
    assert command.case_no == "CASE-001" and command.intent == body.to_intent()
    assert [command.expected_order_version.value,command.expected_scheduling_version.value,
            command.expected_client_finance_version.value,command.expected_payroll_version.value] == [1,2,3,4]
    assert command.idempotency_key.value == "same-apply-key"
    assert command.correlation_id.value == "same-corr"
    assert command.preview_fingerprint.value == "a"*64
    assert command.linked_request == LinkedLeaveRequestIntent(17,3)
    assert result.data["batch_key"] == "saved-batch" and result.data["outcome_event_ids"] == [101]
    app.apply.assert_not_called()


def test_customer_preview_conflict_has_no_apply_or_success_response():
    from api.routes import leave_substitution as route
    from fastapi import HTTPException
    app = Mock()
    app.preview_customer_defer.side_effect = ValueError("leave_customer_binding_conflict")
    body = CustomerLeaveDeferPreviewBody(leave_request_id=17,expected_leave_request_version=3,original_assignment_id=1)
    with pytest.raises(HTTPException) as error:
        route.preview_customer_leave_defer(body,"CASE-001","corr",object(),app)
    assert error.value.status_code == 409
    assert error.value.detail["error"]["code"] == "leave_customer_binding_conflict"
    app.apply_customer_defer.assert_not_called()
