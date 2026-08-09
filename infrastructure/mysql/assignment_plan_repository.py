"""MySQL repository for the Scheduling Assignment Plan workflow."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from domains.scheduling.assignment_plan import (
    AssignmentPlanFacts,
    AssignmentPlanIntent,
    EffectiveAssignmentFact,
    StaffOccupancyFact,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.orders.terms_workflow import SchedulingReplacementCommand
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanApplyEvidence,
    AssignmentPlanApplyRequest,
    AssignmentPlanPersistenceContext,
    AssignmentPlanReceipt,
    AssignmentPlanWorkflowFacts,
    CommandClaimState,
    StoredAssignmentPlanReceipt,
)

from .order_terms_read_model import (
    load_locked_facts,
    load_preview_facts,
    preflight_staff_ids,
)
from .scheduling_replacement_writer import persist_scheduling_replacement


_COMMAND_FAMILY = "scheduling_assignment_plan"


class MySqlAssignmentPlanRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_for_query(self, case_no: str) -> AssignmentPlanWorkflowFacts:
        with self._connection.cursor() as cursor:
            source = load_preview_facts(cursor, case_no)
        return build_assignment_plan_workflow_facts(source, (), ())

    def load_for_preview(
        self,
        case_no: str,
        intent: AssignmentPlanIntent,
    ) -> AssignmentPlanWorkflowFacts:
        with self._connection.cursor() as cursor:
            source = load_preview_facts(cursor, case_no)
            case_staff_ids = preflight_staff_ids(cursor, case_no)
            staff_ids = tuple(
                sorted(
                    set(impacted_staff_ids_from_source(source, intent) + case_staff_ids)
                )
            )
            occupancy, lock_ids = load_occupancy_snapshot(
                cursor,
                staff_ids,
                case_no,
                lock=False,
            )
        return build_assignment_plan_workflow_facts(source, occupancy, lock_ids)

    def preflight_impacted_staff_ids(
        self,
        case_no: str,
        intent: AssignmentPlanIntent,
    ) -> tuple[int, ...]:
        with self._connection.cursor() as cursor:
            current = preflight_staff_ids(cursor, case_no)
        proposed = tuple(segment.staff_id for segment in intent.segments)
        return tuple(sorted(set(current + proposed)))

    # Kept cohesive because Apply must preserve one deterministic lock sequence.
    def load_for_apply(
        self,
        request: AssignmentPlanApplyRequest,
        preflight_staff_ids: tuple[int, ...],
        command_fingerprint: PreviewFingerprint,
    ) -> AssignmentPlanApplyEvidence:
        occupancy = ()
        waiting_lock_ids = ()
        claim_state = CommandClaimState.CREATED
        stored_receipt = None

        def load_replay(cursor):
            nonlocal claim_state, stored_receipt
            claim_state = _claim_command(cursor, request, command_fingerprint)
            stored_receipt = _locked_receipt(cursor, request.idempotency_key)

        with self._connection.cursor() as cursor:
            ensure_scheduling_aggregate(cursor, request.case_no)
            source = load_locked_facts(
                cursor,
                request.case_no,
                preflight_staff_ids,
                load_replay,
            )
            occupancy, waiting_lock_ids = load_occupancy_snapshot(
                cursor,
                preflight_staff_ids,
                request.case_no,
                lock=True,
            )
        facts = build_assignment_plan_workflow_facts(
            source, occupancy, waiting_lock_ids
        )
        return AssignmentPlanApplyEvidence(facts, claim_state, stored_receipt)

    def claim_command(
        self,
        request: AssignmentPlanApplyRequest,
        command_fingerprint: PreviewFingerprint,
    ) -> CommandClaimState:
        with self._connection.cursor() as cursor:
            created = _insert_claim(cursor, request, command_fingerprint)
            if created:
                return CommandClaimState.CREATED
            row = _locked_claim(cursor, request.idempotency_key)
        return _claim_state(request, command_fingerprint, row)

    def find_receipt(
        self,
        key: IdempotencyKey,
        *,
        for_update: bool,
    ) -> StoredAssignmentPlanReceipt | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + suffix, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def replace_scheduling_generation(
        self,
        candidate,
        context: AssignmentPlanPersistenceContext,
    ):
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
            result = persist_scheduling_replacement(cursor, command)
            _convert_waiting_locks(cursor, command, result, context)
            return result

    def save_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredAssignmentPlanReceipt,
        scheduling_result: object,
        context: AssignmentPlanPersistenceContext,
    ) -> None:
        values = _receipt_values(key, stored, scheduling_result, context)
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, values)


def build_assignment_plan_workflow_facts(
    source,
    occupancy,
    waiting_lock_ids,
) -> AssignmentPlanWorkflowFacts:
    return AssignmentPlanWorkflowFacts(
        assignment_plan=_assignment_facts(
            source,
            occupancy,
            waiting_lock_ids,
        ),
        order_terms=source.order.terms,
        client_finance=source.client_finance,
        payroll=source.payroll,
        lifecycle=source.lifecycle,
    )


def ensure_scheduling_aggregate(cursor, case_no: str) -> None:
    cursor.execute(
        "INSERT INTO scheduling_aggregates "
        "(case_no,aggregate_version,generation_counter) "
        "VALUES (%s,0,0) ON DUPLICATE KEY UPDATE case_no=VALUES(case_no)",
        (case_no,),
    )


def _assignment_facts(source, occupancy, waiting_lock_ids) -> AssignmentPlanFacts:
    return AssignmentPlanFacts(
        case_no=source.order.case_no,
        order_version=source.order.version,
        scheduling_version=source.scheduling.aggregate_version,
        scheduling_generation=source.scheduling.generation_number,
        client_finance_version=source.client_finance.account_version,
        payroll_version=source.payroll.payroll_version,
        contracted_service_days=source.order.terms.service_days,
        service_hours_per_day=source.order.terms.service_hours_per_day,
        service_started=source.scheduling.service_started,
        effective_assignments=_effective_assignments(source),
        external_occupancy=occupancy,
        current_waiting_lock_ids=waiting_lock_ids,
    )


def _effective_assignments(source) -> tuple[EffectiveAssignmentFact, ...]:
    result = []
    offset = 0
    for segment in sorted(source.scheduling.segments, key=lambda item: item.sequence):
        end = offset + segment.service_day_count
        service_dates = (
            segment.official_service_dates
            or source.planned_service_dates[offset:end]
        )
        result.append(_effective_assignment(segment, service_dates))
        offset = end
    return tuple(result)


def _effective_assignment(segment, service_dates):
    return EffectiveAssignmentFact(
        assignment_id=segment.assignment_id,
        staff_id=segment.staff_id,
        sequence=segment.sequence,
        assigned_start_date=segment.assigned_start_date,
        assigned_end_date=segment.assigned_end_date,
        official_service_dates=service_dates,
    )


def impacted_staff_ids_from_source(source, intent) -> tuple[int, ...]:
    current = tuple(item.staff_id for item in source.scheduling.segments)
    proposed = tuple(item.staff_id for item in intent.segments)
    return tuple(sorted(set(current + proposed)))


def load_occupancy_snapshot(cursor, staff_ids, case_no, *, lock):
    if not staff_ids:
        return (), ()
    rows = _effective_occupancy_rows(cursor, staff_ids, lock)
    rows += _leave_occupancy_rows(cursor, staff_ids, lock)
    waiting_rows = _waiting_lock_rows(cursor, staff_ids, lock)
    rows += waiting_rows
    unique = {
        (int(row["staff_id"]), row["occupancy_date"], str(row["case_no"]))
        for row in rows
    }
    occupancy = tuple(
        StaffOccupancyFact(*identity)
        for identity in sorted(unique, key=lambda item: (item[0], item[1], item[2]))
    )
    lock_ids = tuple(
        sorted(
            {
                int(row["lock_id"])
                for row in waiting_rows
                if str(row["case_no"]) == case_no
            }
        )
    )
    return occupancy, lock_ids


def _effective_occupancy_rows(cursor, staff_ids, lock):
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        "SELECT o.staff_id,o.occupancy_date,g.case_no "
        "FROM scheduling_effective_occupancy o "
        "JOIN scheduling_generations g ON g.id=o.generation_id "
        f"WHERE o.staff_id IN ({placeholders}) "
        "ORDER BY o.staff_id,o.occupancy_date,g.case_no"
        + _lock_suffix(lock),
        staff_ids,
    )
    return tuple(cursor.fetchall())


def _waiting_lock_rows(cursor, staff_ids, lock):
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        "SELECT d.staff_id,d.lock_date AS occupancy_date,p.case_no,l.id AS lock_id "
        "FROM caregiver_availability_lock_days d "
        "JOIN caregiver_availability_locks l ON l.id=d.lock_id "
        "JOIN caregiver_matching_plan_segments s ON s.id=d.segment_id "
        "JOIN caregiver_matching_plans p ON p.id=s.plan_id "
        f"WHERE d.staff_id IN ({placeholders}) "
        "AND d.active_marker=1 AND l.is_active=1 "
        "ORDER BY d.staff_id,d.lock_date,p.case_no"
        + _lock_suffix(lock),
        staff_ids,
    )
    return tuple(cursor.fetchall())


def _leave_occupancy_rows(cursor, staff_ids, lock):
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        "SELECT d.staff_id,d.occupancy_date,b.case_no "
        "FROM scheduling_leave_occupancy_days d "
        "JOIN scheduling_leave_substitution_batches b "
        "ON b.batch_key=d.batch_key "
        f"WHERE d.staff_id IN ({placeholders}) "
        "AND d.active_marker=1 "
        "ORDER BY d.staff_id,d.occupancy_date,b.case_no"
        + _lock_suffix(lock),
        staff_ids,
    )
    return tuple(cursor.fetchall())


def _lock_suffix(lock: bool) -> str:
    return " FOR UPDATE" if lock else ""


def _convert_waiting_locks(cursor, command, result, context) -> None:
    for lock_id in context.waiting_lock_ids:
        _convert_waiting_lock_days(cursor, lock_id, command)
        _convert_waiting_lock_header(cursor, lock_id, command)
        _append_waiting_lock_conversion(cursor, lock_id, command, result)


def _convert_waiting_lock_days(cursor, lock_id, command) -> None:
    cursor.execute(
        "UPDATE caregiver_availability_lock_days "
        "SET active_marker=NULL,released_by=%s,released_at=CURRENT_TIMESTAMP "
        "WHERE lock_id=%s AND active_marker=1",
        (command.actor.actor_id, lock_id),
    )
    if cursor.rowcount < 1:
        raise RuntimeError("waiting_lock_state_conflict")


def _convert_waiting_lock_header(cursor, lock_id, command) -> None:
    cursor.execute(
        "UPDATE caregiver_availability_locks "
        "SET status='converted',is_active=NULL,released_by=%s,"
        "released_at=CURRENT_TIMESTAMP "
        "WHERE id=%s AND status='active' AND is_active=1",
        (command.actor.actor_id, lock_id),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("waiting_lock_state_conflict")


def _append_waiting_lock_conversion(cursor, lock_id, command, result) -> None:
    payload = {
        "case_no": command.candidate.case_no,
        "generation_id": result.generation_id,
        "assignment_ids": tuple(
            sorted(result.assignment_resolution.assignment_id_by_candidate_key.values())
        ),
    }
    cursor.execute(
        "INSERT INTO caregiver_availability_lock_events "
        "(lock_id,event_type,event_key,actor,reason,payload) "
        "VALUES (%s,'lock_converted',%s,%s,%s,%s)",
        (
            lock_id,
            _waiting_lock_event_key(lock_id, command.command_fingerprint.value),
            command.actor.actor_id,
            command.reason,
            _canonical_json(payload),
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("waiting_lock_event_insert_failed")


def _waiting_lock_event_key(lock_id: int, fingerprint: str) -> str:
    return f"assignment-plan:{lock_id}:{fingerprint[:48]}"


def _insert_claim(cursor, request, fingerprint) -> bool:
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


def _locked_receipt(cursor, key):
    cursor.execute(_RECEIPT_SELECT_SQL + " FOR UPDATE", (key.value,))
    row = cursor.fetchone()
    return None if row is None else _stored_receipt(row)


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


def _claim_state(request, fingerprint, row) -> CommandClaimState:
    matches = (
        str(row["command_family"]) == _COMMAND_FAMILY
        and str(row["aggregate_identity"]) == request.case_no
        and str(row["command_fingerprint"]) == fingerprint.value
    )
    return CommandClaimState.MATCHED if matches else CommandClaimState.MISMATCH


def _stored_receipt(row) -> StoredAssignmentPlanReceipt:
    return StoredAssignmentPlanReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        AssignmentPlanReceipt(
            case_no=str(row["case_no"]),
            order_version=int(row["resulting_order_version"]),
            scheduling_generation=int(row["resulting_generation_number"]),
            scheduling_version=int(row["resulting_scheduling_version"]),
            client_finance_version=int(
                row["resulting_client_finance_version"]
            ),
            payroll_version=int(row["resulting_payroll_version"]),
            cancelled_assignment_ids=tuple(
                int(value)
                for value in _json_value(row["cancelled_assignment_ids"])
            ),
            created_assignment_keys=tuple(
                str(value)
                for value in _json_value(row["created_assignment_keys"])
            ),
            preview_fingerprint=PreviewFingerprint(
                str(row["preview_fingerprint"])
            ),
        ),
    )


def _receipt_values(key, stored, scheduling_result, context):
    receipt = stored.receipt
    return (
        key.value,
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
        _canonical_json(receipt.cancelled_assignment_ids),
        _canonical_json(receipt.created_assignment_keys),
        context.correlation_id.value,
    )


def _json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def _canonical_json(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )


_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,case_no,"
    "resulting_order_version,resulting_scheduling_version,"
    "resulting_generation_number,resulting_client_finance_version,"
    "resulting_payroll_version,cancelled_assignment_ids,"
    "created_assignment_keys FROM assignment_plan_apply_receipts "
    "WHERE idempotency_key=%s"
)

_RECEIPT_INSERT_SQL = (
    "INSERT INTO assignment_plan_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "expected_order_version,resulting_order_version,"
    "expected_scheduling_version,resulting_scheduling_version,"
    "resulting_generation_number,expected_client_finance_version,"
    "resulting_client_finance_version,expected_payroll_version,"
    "resulting_payroll_version,scheduling_receipt_id,"
    "cancelled_assignment_ids,created_assignment_keys,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)


# Existing repository tests import these names; keep aliases during the public-helper migration.
_ensure_scheduling_aggregate = ensure_scheduling_aggregate
_occupancy_snapshot = load_occupancy_snapshot
