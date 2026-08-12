"""MySQL repository for one typed leave/substitution batch transaction."""

from __future__ import annotations

from datetime import date
import json
from typing import Any, Mapping

from domains.scheduling.assignment_plan import AssignmentPlanFacts, EffectiveAssignmentFact
from domains.scheduling.leave_substitution import LeaveSubstitutionFacts, OfficialScheduleFact
from infrastructure.mysql.assignment_plan_repository import (
    build_assignment_plan_workflow_facts,
    ensure_scheduling_aggregate,
    load_occupancy_snapshot,
)
from infrastructure.mysql.order_terms_read_model import (
    _order_facts,
    _segments,
    _select_assignments,
    _select_generation,
    _select_schedules,
    _service_dates_by_assignment,
    load_locked_facts,
    load_preview_facts,
    preflight_staff_ids,
    select_order,
    select_scheduling_aggregate,
)
from infrastructure.mysql.scheduling_replacement_writer import (
    persist_scheduling_replacement,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from subsystems.orders.terms_workflow import SchedulingReplacementCommand
from subsystems.scheduling.leave_substitution_workflow import (
    CommandClaimState,
    LeaveApplyEvidence,
    LeaveBatchHeaderEvidence,
    LeaveOutcomeEvidence,
    LeaveSubstitutionApplyRequest,
    LeaveSubstitutionReceipt,
    LeaveSubstitutionWorkflowFacts,
    StoredLeaveSubstitutionReceipt,
    leave_request_fingerprint,
)


_COMMAND_FAMILY = "scheduling_leave_substitution"


class MySqlLeaveSubstitutionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_for_preview(self, case_no, intent):
        with self._connection.cursor() as cursor:
            staff_ids = _preflight_staff_ids(cursor, case_no, intent)
            occupancy, lock_ids = load_occupancy_snapshot(
                cursor,
                staff_ids,
                case_no,
                lock=False,
            )
            schedules = _official_schedules(cursor, case_no)
            try:
                source = load_preview_facts(cursor, case_no)
            except ValueError as error:
                blocker = _preview_dependency_blocker(error)
                if blocker is None:
                    raise
                return LeaveSubstitutionWorkflowFacts(
                    None,
                    schedules,
                    (blocker,),
                    _scheduling_only_leave_facts(
                        cursor, case_no, occupancy, lock_ids, schedules
                    ),
                )
        return _workflow_facts(source, occupancy, lock_ids, schedules)

    def list_effective_assignments(self, case_no):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT a.id,a.staff_id,a.assigned_start_date,a.assigned_end_date "
                "FROM scheduling_aggregates g JOIN case_staff_assignments a "
                "ON a.generation_id=g.effective_generation_id "
                "WHERE g.case_no=%s AND a.status NOT IN ('cancelled','replaced') "
                "ORDER BY a.assignment_sequence,a.id",
                (case_no,),
            )
            return tuple(cursor.fetchall())

    def preflight_impacted_staff_ids(self, case_no, intent):
        with self._connection.cursor() as cursor:
            return _preflight_staff_ids(cursor, case_no, intent)

    # Kept cohesive because replay must sit between staff and generation locks.
    def load_for_apply(
        self,
        request,
        preflight_staff_ids,
        command_fingerprint,
    ):
        evidence_rows = {}
        occupancy = ()
        lock_ids = ()
        claim_state = CommandClaimState.CREATED

        def after_staff_lock(cursor):
            nonlocal evidence_rows, claim_state
            claim_state = _claim_command(
                cursor,
                request,
                command_fingerprint,
            )
            evidence_rows = _locked_evidence_rows(
                cursor,
                request.idempotency_key.value,
            )

        with self._connection.cursor() as cursor:
            ensure_scheduling_aggregate(cursor, request.case_no)
            source = load_locked_facts(
                cursor,
                request.case_no,
                preflight_staff_ids,
                after_staff_lock,
            )
            occupancy, lock_ids = load_occupancy_snapshot(
                cursor,
                preflight_staff_ids,
                request.case_no,
                lock=True,
            )
            schedules = _official_schedules(cursor, request.case_no)
        facts = _workflow_facts(source, occupancy, lock_ids, schedules)
        return _apply_evidence(facts, claim_state, evidence_rows)

    def replace_scheduling_generation(self, candidate, context):
        command = SchedulingReplacementCommand(
            candidate=candidate,
            command_family=_COMMAND_FAMILY,
            expected_order_version=context.expected_order_version,
            command_fingerprint=context.command_fingerprint,
            preview_fingerprint=context.preview_fingerprint,
            idempotency_key=context.idempotency_key,
            actor=context.actor,
            reason=context.reason,
            correlation_id=context.correlation_id,
        )
        with self._connection.cursor() as cursor:
            return persist_scheduling_replacement(cursor, command)

    # Kept cohesive because header, outcomes, occupancy, and special pay are one fact set.
    def append_batch_outcomes(
        self,
        request,
        preview,
        command_fingerprint,
        scheduling_result,
    ):
        with self._connection.cursor() as cursor:
            _insert_batch_header(cursor, request, preview, command_fingerprint)
            event_ids = tuple(
                _insert_outcome(
                    cursor,
                    request,
                    outcome,
                    scheduling_result,
                )
                for outcome in preview.candidate.outcomes
            )
            _insert_leave_occupancy(
                cursor,
                request,
                preview,
                scheduling_result,
                event_ids,
            )
            _insert_special_pay_events(
                cursor,
                request,
                preview,
                scheduling_result,
            )
        return event_ids

    def save_receipt(self, stored, scheduling_result, context):
        values = _receipt_values(stored, scheduling_result, context)
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, values)


def _workflow_facts(source, occupancy, lock_ids, schedules):
    impact_facts = build_assignment_plan_workflow_facts(
        source,
        occupancy,
        lock_ids,
    )
    return LeaveSubstitutionWorkflowFacts(impact_facts, schedules)


def _preview_dependency_blocker(error):
    code = str(error)
    return code if code in {
        "client_finance_bootstrap_required",
        "payroll_bootstrap_required",
    } else None


def _scheduling_only_leave_facts(cursor, case_no, occupancy, lock_ids, schedules):
    order_row = select_order(cursor, case_no, lock=False)
    order = _order_facts(order_row)
    aggregate = select_scheduling_aggregate(cursor, case_no, lock=False)
    generation = _select_generation(cursor, aggregate, lock=False)
    assignment_rows = _select_assignments(cursor, generation, lock=False)
    schedule_rows = _select_schedules(cursor, generation, lock=False)
    segments = _segments(
        assignment_rows,
        _service_dates_by_assignment(schedule_rows),
    )
    assignment_plan = AssignmentPlanFacts(
        case_no=order.case_no,
        order_version=order.version,
        scheduling_version=int(aggregate["aggregate_version"]),
        scheduling_generation=(
            0 if generation is None else int(generation["generation_number"])
        ),
        client_finance_version=0,
        payroll_version=0,
        contracted_service_days=order.terms.service_days,
        service_hours_per_day=order.terms.service_hours_per_day,
        service_started=order_row["actual_start_date"] is not None,
        effective_assignments=tuple(
            EffectiveAssignmentFact(
                assignment_id=segment.assignment_id,
                staff_id=segment.staff_id,
                sequence=segment.sequence,
                assigned_start_date=segment.assigned_start_date,
                assigned_end_date=segment.assigned_end_date,
                official_service_dates=segment.official_service_dates,
            )
            for segment in segments
        ),
        external_occupancy=occupancy,
        current_waiting_lock_ids=lock_ids,
    )
    return LeaveSubstitutionFacts(
        assignment_plan,
        schedules,
        order.service_data_locked,
    )


def _preflight_staff_ids(cursor, case_no, intent):
    current = preflight_staff_ids(cursor, case_no)
    substitutes = tuple(
        item.substitute_staff_id
        for item in intent.items
        if item.substitute_staff_id is not None
    )
    return tuple(sorted(set(current + substitutes)))


def _official_schedules(cursor, case_no):
    cursor.execute(_OFFICIAL_SCHEDULE_SQL, (case_no,))
    return tuple(
        OfficialScheduleFact(
            int(row["id"]),
            int(row["assignment_id"]),
            int(row["staff_id"]),
            row["work_date"],
            bool(row["is_double_pay"]),
        )
        for row in cursor.fetchall()
    )


def _insert_claim(cursor, request, fingerprint):
    cursor.execute(
        "INSERT IGNORE INTO application_command_claims "
        "(idempotency_key,command_family,aggregate_identity,"
        "command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)",
        (
            request.idempotency_key.value,
            _COMMAND_FAMILY,
            request.case_no,
            fingerprint.value,
            request.correlation_id.value,
        ),
    )
    return cursor.rowcount == 1


def _claim_command(cursor, request, fingerprint):
    if _insert_claim(cursor, request, fingerprint):
        return CommandClaimState.CREATED
    row = _locked_claim(cursor, request.idempotency_key)
    return _claim_state(request, fingerprint, row)


def _locked_claim(cursor, key):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
        (key.value,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("idempotency_claim_missing")
    return row


def _claim_state(request, fingerprint, row):
    matches = (
        str(row["command_family"]) == _COMMAND_FAMILY
        and str(row["aggregate_identity"]) == request.case_no
        and str(row["command_fingerprint"]) == fingerprint.value
    )
    return CommandClaimState.MATCHED if matches else CommandClaimState.MISMATCH


def _locked_evidence_rows(cursor, batch_key):
    cursor.execute(_HEADER_SELECT_SQL + " FOR UPDATE", (batch_key,))
    header = cursor.fetchone()
    cursor.execute(_OUTCOME_SELECT_SQL + " FOR UPDATE", (batch_key,))
    outcomes = tuple(cursor.fetchall())
    cursor.execute(_RECEIPT_SELECT_SQL + " FOR UPDATE", (batch_key,))
    receipt = cursor.fetchone()
    return {"header": header, "outcomes": outcomes, "receipt": receipt}


def _apply_evidence(facts, claim_state, rows):
    header = _header_evidence(rows["header"])
    outcomes = tuple(_outcome_evidence(row) for row in rows["outcomes"])
    receipt = _stored_receipt(rows["receipt"])
    return LeaveApplyEvidence(facts, claim_state, header, outcomes, receipt)


def _header_evidence(row):
    if not isinstance(row, Mapping):
        return None
    return LeaveBatchHeaderEvidence(
        str(row["batch_key"]),
        str(row["case_no"]),
        PreviewFingerprint(str(row["command_fingerprint"])),
        PreviewFingerprint(str(row["preview_fingerprint"])),
        int(row["item_count"]),
        str(row["actor"]),
        str(row["reason"]),
        PreviewFingerprint(str(row["request_fingerprint"])),
    )


def _outcome_evidence(row):
    result_fingerprint = PreviewFingerprint(str(row["result_fingerprint"]))
    if fingerprint_payload(_json_value(row["outcome_snapshot"])) != result_fingerprint:
        raise RuntimeError("leave_outcome_fingerprint_invalid")
    return LeaveOutcomeEvidence(
        int(row["id"]),
        int(row["item_index"]),
        int(row["original_assignment_id"]),
        int(row["original_schedule_id"]),
        _iso_date(row["original_work_date"]),
        str(row["resolution_type"]),
        result_fingerprint,
    )


# Receipt materialization must preserve every exact-replay field together.
def _stored_receipt(row):
    if not isinstance(row, Mapping):
        return None
    receipt = LeaveSubstitutionReceipt(
        batch_key=str(row["batch_key"]),
        case_no=str(row["case_no"]),
        order_version=int(row["resulting_order_version"]),
        scheduling_generation=int(row["resulting_generation_number"]),
        scheduling_version=int(row["resulting_scheduling_version"]),
        client_finance_version=int(row["resulting_client_finance_version"]),
        payroll_version=int(row["resulting_payroll_version"]),
        outcome_event_ids=tuple(
            int(value) for value in _json_value(row["outcome_event_ids"])
        ),
        preview_fingerprint=PreviewFingerprint(
            str(row["preview_fingerprint"])
        ),
    )
    return StoredLeaveSubstitutionReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _insert_batch_header(cursor, request, preview, command_fingerprint):
    request_snapshot = _request_snapshot(request)
    cursor.execute(
        _HEADER_INSERT_SQL,
        (
            request.idempotency_key.value,
            request.case_no,
            request.intent.original_assignment_id,
            command_fingerprint.value,
            request.preview_fingerprint.value,
            leave_request_fingerprint(request.intent).value,
            len(request.intent.items),
            request.actor.actor_id,
            request.reason,
            _canonical_json(request_snapshot),
            request.correlation_id.value,
        ),
    )


def _request_snapshot(request):
    return {
        "case_no": request.case_no,
        "original_assignment_id": request.intent.original_assignment_id,
        "items": [
            {
                "original_schedule_id": item.original_schedule_id,
                "work_date": item.work_date.isoformat(),
                "resolution_type": item.resolution_type.value,
                "substitute_staff_id": item.substitute_staff_id,
                "is_double_pay": item.is_double_pay,
            }
            for item in request.intent.items
        ],
    }


# Assignment resolution and immutable outcome lineage are one persisted fact.
def _insert_outcome(cursor, request, outcome, scheduling_result):
    assignment_id = _resolved_assignment_id(
        scheduling_result,
        outcome.resulting_assignment_key,
    )
    snapshot = _outcome_snapshot(outcome, assignment_id)
    result_fingerprint = fingerprint_payload(snapshot)
    cursor.execute(
        _OUTCOME_INSERT_SQL,
        (
            request.idempotency_key.value,
            outcome.item_index,
            _child_identity(request.idempotency_key, "outcome", outcome.item_index),
            outcome.original_assignment_id,
            outcome.original_schedule_id,
            outcome.original_staff_id,
            outcome.original_work_date,
            outcome.resolution_type.value,
            outcome.leave_occupancy_date,
            assignment_id,
            outcome.resulting_staff_id,
            outcome.resulting_service_date,
            outcome.is_double_pay,
            result_fingerprint.value,
            _canonical_json(snapshot),
        ),
    )
    return int(cursor.lastrowid)


def _outcome_snapshot(outcome, assignment_id):
    return {
        "item_index": outcome.item_index,
        "original_assignment_id": outcome.original_assignment_id,
        "original_schedule_id": outcome.original_schedule_id,
        "original_staff_id": outcome.original_staff_id,
        "original_work_date": outcome.original_work_date.isoformat(),
        "resolution_type": outcome.resolution_type.value,
        "leave_occupancy_date": outcome.leave_occupancy_date.isoformat(),
        "resulting_assignment_id": assignment_id,
        "resulting_staff_id": outcome.resulting_staff_id,
        "resulting_service_date": outcome.resulting_service_date.isoformat(),
        "is_double_pay": outcome.is_double_pay,
    }


# All batch outcomes must create their active leave occupancy projection together.
def _insert_leave_occupancy(
    cursor,
    request,
    preview,
    scheduling_result,
    event_ids,
):
    rows = tuple(
        (
            request.idempotency_key.value,
            outcome.item_index,
            event_id,
            scheduling_result.generation_id,
            outcome.original_staff_id,
            outcome.leave_occupancy_date,
        )
        for event_id, outcome in zip(event_ids, preview.candidate.outcomes)
    )
    cursor.executemany(
        "INSERT INTO scheduling_leave_occupancy_days "
        "(batch_key,item_index,outcome_id,generation_id,staff_id,"
        "occupancy_date,status,active_marker) "
        "VALUES (%s,%s,%s,%s,%s,%s,'active',1)",
        rows,
    )


# Explicit double-pay dates are persisted only from the rebuilt assignments.
def _insert_special_pay_events(
    cursor,
    request,
    preview,
    scheduling_result,
):
    for assignment in preview.candidate.scheduling.assignments:
        assignment_id = _resolved_assignment_id(
            scheduling_result,
            assignment.candidate_key,
        )
        for service_date in assignment.double_pay_dates:
            cursor.execute(
                "INSERT INTO payroll_special_pay_events "
                "(assignment_id,service_date,event_type,source_event_identity,"
                "actor,reason,idempotency_key) "
                "VALUES (%s,%s,'double_pay',%s,%s,%s,%s)",
                (
                    assignment_id,
                    service_date,
                    _special_pay_source_identity(request.idempotency_key),
                    request.actor.actor_id,
                    request.reason,
                    _child_identity(
                        request.idempotency_key,
                        "special-pay",
                        assignment.sequence,
                        service_date,
                    ),
                ),
            )


def _special_pay_source_identity(key):
    return "leave-special-pay:" + fingerprint_payload(
        {"batch_key": key.value}
    ).value


# Expected/result versions and replay snapshot form one receipt row.
def _receipt_values(stored, scheduling_result, context):
    receipt = stored.receipt
    snapshot = {
        "batch_key": receipt.batch_key,
        "case_no": receipt.case_no,
        "scheduling_generation": receipt.scheduling_generation,
        "outcome_event_ids": receipt.outcome_event_ids,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }
    return (
        receipt.batch_key,
        stored.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.case_no,
        receipt.order_version - 1,
        receipt.order_version,
        receipt.scheduling_version - 1,
        receipt.scheduling_version,
        receipt.scheduling_generation,
        receipt.client_finance_version - 1,
        receipt.client_finance_version,
        receipt.payroll_version - 1,
        receipt.payroll_version,
        scheduling_result.scheduling_receipt_id,
        _canonical_json(receipt.outcome_event_ids),
        _canonical_json(snapshot),
        context.correlation_id.value,
    )


def _resolved_assignment_id(scheduling_result, candidate_key):
    assignment_id = (
        scheduling_result.assignment_resolution.assignment_id_by_candidate_key.get(
            candidate_key
        )
    )
    if assignment_id is None:
        raise ValueError("assignment identity resolution is incomplete")
    return int(assignment_id)


def _child_identity(key, purpose, ordinal, service_date=None):
    return "child:" + fingerprint_payload(
        {
            "outer_key": key.value,
            "domain": "scheduling-leave-substitution",
            "purpose": purpose,
            "ordinal": ordinal,
            "service_date": (
                service_date.isoformat() if service_date is not None else None
            ),
        }
    ).value


def _iso_date(value):
    return value.isoformat() if isinstance(value, date) else str(value)


def _json_value(value):
    return json.loads(value) if isinstance(value, str) else value


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_OFFICIAL_SCHEDULE_SQL = (
    "SELECT s.id,s.assignment_id,s.staff_id,s.work_date,s.is_double_pay "
    "FROM scheduling_aggregates a "
    "JOIN staff_schedule s ON s.generation_id=a.effective_generation_id "
    "WHERE a.case_no=%s AND s.effective_marker=1 AND s.is_work_day=1 "
    "ORDER BY s.work_date,s.id"
)

_HEADER_SELECT_SQL = (
    "SELECT batch_key,case_no,command_fingerprint,preview_fingerprint,"
    "request_fingerprint,item_count,actor,reason "
    "FROM scheduling_leave_substitution_batches WHERE batch_key=%s"
)

_OUTCOME_SELECT_SQL = (
    "SELECT id,item_index,original_assignment_id,original_schedule_id,"
    "original_work_date,resolution_type,result_fingerprint,outcome_snapshot "
    "FROM scheduling_leave_substitution_outcomes WHERE batch_key=%s "
    "ORDER BY item_index"
)

_RECEIPT_SELECT_SQL = (
    "SELECT batch_key,command_fingerprint,preview_fingerprint,case_no,"
    "resulting_order_version,resulting_scheduling_version,"
    "resulting_generation_number,resulting_client_finance_version,"
    "resulting_payroll_version,outcome_event_ids "
    "FROM scheduling_leave_substitution_receipts WHERE batch_key=%s"
)

_HEADER_INSERT_SQL = (
    "INSERT INTO scheduling_leave_substitution_batches "
    "(batch_key,case_no,original_assignment_id,command_fingerprint,"
    "preview_fingerprint,request_fingerprint,item_count,actor,reason,"
    "request_snapshot,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_OUTCOME_INSERT_SQL = (
    "INSERT INTO scheduling_leave_substitution_outcomes "
    "(batch_key,item_index,event_key,original_assignment_id,"
    "original_schedule_id,original_staff_id,original_work_date,"
    "resolution_type,leave_occupancy_date,resulting_assignment_id,"
    "resulting_staff_id,resulting_service_date,is_double_pay,"
    "result_fingerprint,outcome_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_RECEIPT_INSERT_SQL = (
    "INSERT INTO scheduling_leave_substitution_receipts "
    "(batch_key,command_fingerprint,preview_fingerprint,case_no,"
    "expected_order_version,resulting_order_version,"
    "expected_scheduling_version,resulting_scheduling_version,"
    "resulting_generation_number,expected_client_finance_version,"
    "resulting_client_finance_version,expected_payroll_version,"
    "resulting_payroll_version,scheduling_receipt_id,outcome_event_ids,"
    "result_snapshot,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
