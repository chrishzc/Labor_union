"""
File: leave_substitution_repository.py
Description: 查詢正式assignment schedule，並在單一MySQL交易保存請假代班fact與strict replay receipt。"""

from __future__ import annotations

from datetime import date
import json
from typing import Any, Mapping

from domains.scheduling.assignment_plan import AssignmentPlanFacts, EffectiveAssignmentFact
from domains.scheduling.leave_substitution import (
    LeaveResolutionType,
    LeaveSubstitutionFacts,
    OfficialScheduleFact,
)
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
    LinkedLeaveRequestResult,
    LeaveSubstitutionApplyRequest,
    LeaveSubstitutionReceipt,
    LeaveSubstitutionWorkflowFacts,
    StoredLeaveSubstitutionReceipt,
)
from subsystems.scheduling.matching_leave_integration import (
    CanonicalSchedulingLeaveReference,
)


_COMMAND_FAMILY = "scheduling_leave_substitution"


class _ExistingLeaveSubstitutionClaim(Exception):
    pass


def _group_effective_assignment_schedules(rows):
    assignments: dict[int, dict[str, Any]] = {}
    schedule_identities: dict[int, set[tuple[int, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("invalid leave assignment projection row")
        assignment_id = int(row["id"])
        identity = (
            int(row["staff_id"]),
            row["assigned_start_date"],
            row["assigned_end_date"],
        )
        assignment = assignments.get(assignment_id)
        if assignment is None:
            assignment = {
                "id": assignment_id,
                "staff_id": identity[0],
                "assigned_start_date": identity[1],
                "assigned_end_date": identity[2],
                "official_schedules": [],
            }
            assignments[assignment_id] = assignment
            schedule_identities[assignment_id] = set()
        elif identity != (
            assignment["staff_id"],
            assignment["assigned_start_date"],
            assignment["assigned_end_date"],
        ):
            raise ValueError("leave assignment projection identity drift")

        schedule_id = row.get("schedule_id")
        work_date = row.get("work_date")
        if schedule_id is None and work_date is None:
            continue
        if schedule_id is None or work_date is None:
            raise ValueError("incomplete official schedule projection")
        schedule_identity = (int(schedule_id), work_date)
        if schedule_identity in schedule_identities[assignment_id]:
            raise ValueError("duplicate official schedule projection")
        schedule_identities[assignment_id].add(schedule_identity)
        assignment["official_schedules"].append(
            {"schedule_id": schedule_identity[0], "work_date": work_date}
        )

    return tuple(
        {
            **assignment,
            "official_schedules": tuple(assignment["official_schedules"]),
        }
        for assignment in assignments.values()
    )


class MySqlLeaveSubstitutionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get_canonical_receipt(
        self, receipt_key: str
    ) -> CanonicalSchedulingLeaveReference | None:
        """Project an immutable Scheduling receipt for M3 without writing roots."""

        if not isinstance(receipt_key, str) or not receipt_key.strip():
            raise ValueError("leave receipt key is required")
        with self._connection.cursor() as cursor:
            cursor.execute(_MATCHING_LEAVE_REFERENCE_SQL, (receipt_key.strip(),))
            rows = tuple(cursor.fetchall())
        return _matching_leave_reference(rows)

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
                "SELECT a.id,a.staff_id,a.assigned_start_date,a.assigned_end_date,"
                "s.id AS schedule_id,s.work_date "
                "FROM scheduling_aggregates g JOIN case_staff_assignments a "
                "ON a.generation_id=g.effective_generation_id "
                "LEFT JOIN staff_schedule s "
                "ON s.generation_id=g.effective_generation_id "
                "AND s.assignment_id=a.id AND s.effective_marker=1 "
                "AND s.is_work_day=1 "
                "WHERE g.case_no=%s AND a.status NOT IN ('cancelled','replaced') "
                "ORDER BY a.assignment_sequence,a.id,s.work_date,s.id",
                (case_no,),
            )
            return _group_effective_assignment_schedules(cursor.fetchall())

    def preflight_impacted_staff_ids(self, case_no, intent):
        with self._connection.cursor() as cursor:
            return _preflight_staff_ids(cursor, case_no, intent)

    def load_replay_evidence(self, request, command_fingerprint):
        with self._connection.cursor() as cursor:
            row = _optional_locked_claim(cursor, request.idempotency_key)
            if row is None:
                return None
            claim_state = _claim_state(request, command_fingerprint, row)
            evidence_rows = _locked_evidence_rows(
                cursor,
                request.idempotency_key.value,
            )
        return _apply_evidence(None, claim_state, evidence_rows)

    # Kept cohesive because replay must sit between staff and generation locks.
    def load_for_apply(
        self,
        request,
        preflight_staff_ids,
        command_fingerprint,
        after_command_lock,
    ):
        evidence_rows = {}
        occupancy = ()
        lock_ids = ()
        claim_state = CommandClaimState.CREATED
        linked_request = None

        def after_staff_lock(cursor):
            nonlocal evidence_rows, claim_state, linked_request
            claim_state = _claim_command(
                cursor,
                request,
                command_fingerprint,
            )
            evidence_rows = _locked_evidence_rows(
                cursor,
                request.idempotency_key.value,
            )
            if claim_state is CommandClaimState.CREATED:
                linked_request = after_command_lock(
                    _locked_original_assignment_staff(
                        cursor,
                        request.case_no,
                        request.intent.original_assignment_id,
                    )
                )
            else:
                raise _ExistingLeaveSubstitutionClaim

        with self._connection.cursor() as cursor:
            ensure_scheduling_aggregate(cursor, request.case_no)
            try:
                source = load_locked_facts(
                    cursor,
                    request.case_no,
                    preflight_staff_ids,
                    after_staff_lock,
                )
            except _ExistingLeaveSubstitutionClaim:
                return _apply_evidence(None, claim_state, evidence_rows), None
            occupancy, lock_ids = load_occupancy_snapshot(
                cursor,
                preflight_staff_ids,
                request.case_no,
                lock=True,
            )
            schedules = _official_schedules(cursor, request.case_no)
        facts = _workflow_facts(source, occupancy, lock_ids, schedules)
        return _apply_evidence(facts, claim_state, evidence_rows), linked_request

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

    # Kept cohesive because header, outcomes, and occupancy are one fact set.
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


def _locked_original_assignment_staff(cursor, case_no, assignment_id):
    cursor.execute(
        "SELECT a.staff_id FROM scheduling_aggregates g "
        "JOIN case_staff_assignments a ON a.generation_id=g.effective_generation_id "
        "WHERE g.case_no=%s AND a.id=%s "
        "AND a.status NOT IN ('cancelled','replaced') FOR UPDATE",
        (case_no, assignment_id),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("assignment_not_found")
    return int(row["staff_id"])


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


def _optional_locked_claim(cursor, key):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
        (key.value,),
    )
    row = cursor.fetchone()
    return row if isinstance(row, Mapping) else None


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
    request_snapshot = _json_object(
        row["request_snapshot"],
        "invalid_batch_replay_snapshot",
    )
    return LeaveBatchHeaderEvidence(
        str(row["batch_key"]),
        str(row["case_no"]),
        PreviewFingerprint(str(row["command_fingerprint"])),
        PreviewFingerprint(str(row["preview_fingerprint"])),
        int(row["item_count"]),
        str(row["actor"]),
        str(row["reason"]),
        PreviewFingerprint(str(row["request_fingerprint"])),
        request_snapshot,
    )


def _outcome_evidence(row):
    result_fingerprint = PreviewFingerprint(str(row["result_fingerprint"]))
    try:
        snapshot = _json_value(row["outcome_snapshot"])
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("invalid_batch_replay_snapshot") from error
    if fingerprint_payload(snapshot) != result_fingerprint:
        raise RuntimeError("invalid_batch_replay_snapshot")
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
    result_snapshot = _json_object(
        row["result_snapshot"],
        "invalid_batch_replay_snapshot",
    )
    linked_request = _linked_result(result_snapshot.get("linked_request"))
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
        linked_request=linked_request,
    )
    return StoredLeaveSubstitutionReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
        result_snapshot,
    )


def _matching_leave_reference(rows) -> CanonicalSchedulingLeaveReference | None:
    if not rows:
        return None
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("leave receipt projection returned an invalid row")
    first = rows[0]
    receipt_key = str(first["batch_key"])
    case_no = str(first["case_no"])
    leave_version = int(first["resulting_scheduling_version"])
    receipt_event_ids = tuple(
        str(int(value)) for value in _json_value(first["receipt_outcome_event_ids"])
    )
    row_event_ids = tuple(str(int(row["outcome_event_id"])) for row in rows)
    if receipt_event_ids != row_event_ids:
        raise ValueError("leave receipt outcome lineage is incomplete")
    if any(
        str(row["batch_key"]) != receipt_key
        or str(row["case_no"]) != case_no
        or int(row["resulting_scheduling_version"]) != leave_version
        for row in rows
    ):
        raise ValueError("leave receipt projection identity is ambiguous")
    staff_ids = {int(row["original_staff_id"]) for row in rows}
    resolutions = {str(row["resolution_type"]) for row in rows}
    if len(staff_ids) != 1 or len(resolutions) != 1:
        raise ValueError("leave receipt requires one original staff and resolution")
    resolution = LeaveResolutionType(next(iter(resolutions)))
    original_dates = tuple(_date_value(row["original_work_date"]) for row in rows)
    resulting_dates = tuple(_date_value(row["resulting_service_date"]) for row in rows)
    resulting_staff_ids = {int(row["resulting_staff_id"]) for row in rows}
    original_staff_id = next(iter(staff_ids))
    substitute_staff_id = None
    if resolution is LeaveResolutionType.SUBSTITUTE:
        if len(resulting_staff_ids) != 1:
            raise ValueError("leave substitute receipt has multiple resulting staff")
        substitute_staff_id = next(iter(resulting_staff_ids))
        original_work_date = min(original_dates)
        resulting_work_date = original_work_date
    else:
        if resulting_staff_ids != {original_staff_id}:
            raise ValueError("leave defer receipt changed staff owner")
        original_work_date = min(original_dates)
        resulting_work_date = max(resulting_dates)
    receipt_fingerprint = fingerprint_payload(
        {
            "batch_key": receipt_key,
            "case_no": case_no,
            "leave_version": leave_version,
            "outcomes": tuple(
                {
                    "event_id": str(int(row["outcome_event_id"])),
                    "original_staff_id": int(row["original_staff_id"]),
                    "original_work_date": _date_value(row["original_work_date"]).isoformat(),
                    "resolution_type": str(row["resolution_type"]),
                    "resulting_staff_id": int(row["resulting_staff_id"]),
                    "resulting_service_date": _date_value(row["resulting_service_date"]).isoformat(),
                    "result_fingerprint": str(row["result_fingerprint"]),
                }
                for row in rows
            ),
        }
    )
    return CanonicalSchedulingLeaveReference(
        receipt_key=receipt_key,
        case_no=case_no,
        leave_version=leave_version,
        original_staff_id=original_staff_id,
        resolution_type=resolution,
        original_work_date=original_work_date,
        resulting_work_date=resulting_work_date,
        outcome_event_ids=row_event_ids,
        receipt_fingerprint=receipt_fingerprint,
        substitute_staff_id=substitute_staff_id,
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
            fingerprint_payload(request_snapshot).value,
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
        "linked_request": (
            None
            if request.linked_request is None
            else {
                "request_id": request.linked_request.request_id,
                "expected_version": request.linked_request.expected_version,
            }
        ),
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


# Expected/result versions and replay snapshot form one receipt row.
def _receipt_values(stored, scheduling_result, context):
    receipt = stored.receipt
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
        _canonical_json(dict(stored.result_snapshot)),
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


def _date_value(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _json_value(value):
    return json.loads(value) if isinstance(value, str) else value


def _json_object(value, code):
    try:
        parsed = _json_value(value)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(code) from error
    if not isinstance(parsed, Mapping):
        raise RuntimeError(code)
    return dict(parsed)


def _linked_result(value):
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "request_id",
        "expected_version",
        "resolved_version",
        "status",
        "receipt_key",
        "notification_intent",
        "staff_id",
    }:
        raise RuntimeError("invalid_batch_replay_snapshot")
    try:
        if any(
            isinstance(value[key], bool) or not isinstance(value[key], int)
            for key in ("request_id", "expected_version", "staff_id")
        ):
            raise TypeError
        resolved_version = value["resolved_version"]
        if resolved_version is not None and (
            isinstance(resolved_version, bool) or not isinstance(resolved_version, int)
        ):
            raise TypeError
        if value["status"] not in {"accepted_for_processing", "resolved"}:
            raise ValueError
        if value["notification_intent"] not in {"not_requested", "enqueued"}:
            raise ValueError
        if value["request_id"] <= 0 or value["expected_version"] <= 0 or value["staff_id"] <= 0:
            raise ValueError
        receipt_key = value["receipt_key"]
        if receipt_key is not None and (
            not isinstance(receipt_key, str) or not receipt_key.strip()
        ):
            raise TypeError
        if value["status"] == "accepted_for_processing" and (
            resolved_version is not None
            or receipt_key is not None
            or value["notification_intent"] != "not_requested"
        ):
            raise ValueError
        if value["status"] == "resolved" and (
            resolved_version is None
            or resolved_version <= value["expected_version"]
            or receipt_key is None
            or value["notification_intent"] != "enqueued"
        ):
            raise ValueError
        return LinkedLeaveRequestResult(
            request_id=value["request_id"],
            expected_version=value["expected_version"],
            resolved_version=(
                None
                if resolved_version is None
                else resolved_version
            ),
            status=value["status"],
            receipt_key=(
                None if value["receipt_key"] is None else value["receipt_key"]
            ),
            notification_intent=value["notification_intent"],
            staff_id=value["staff_id"],
        )
    except (TypeError, ValueError) as error:
        raise RuntimeError("invalid_batch_replay_snapshot") from error


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
    "request_fingerprint,item_count,actor,reason,request_snapshot "
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
    "resulting_payroll_version,outcome_event_ids,result_snapshot "
    "FROM scheduling_leave_substitution_receipts WHERE batch_key=%s"
)

_MATCHING_LEAVE_REFERENCE_SQL = (
    "SELECT r.batch_key,r.case_no,r.resulting_scheduling_version,"
    "r.outcome_event_ids AS receipt_outcome_event_ids,"
    "o.id AS outcome_event_id,o.original_staff_id,o.original_work_date,"
    "o.resolution_type,o.resulting_staff_id,o.resulting_service_date,"
    "o.result_fingerprint "
    "FROM scheduling_leave_substitution_receipts r "
    "JOIN scheduling_leave_substitution_outcomes o ON o.batch_key=r.batch_key "
    "WHERE r.batch_key=%s ORDER BY o.item_index"
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
