"""
File: scheduling_replacement_writer.py
Description: 在單一排班世代交易寫入正式指派、重建事件與通知失效 outbox。
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Any

from domains.scheduling.generation import (
    AssignmentIdentityResolution,
    EmptyAssignmentIdentityResolution,
)
from subsystems.orders.terms_workflow import (
    SchedulingReplacementCommand,
    SchedulingReplacementResult,
)


# Kept cohesive because these statements are one ordered generation transaction.
def persist_scheduling_replacement(
    cursor: Any,
    command: SchedulingReplacementCommand,
) -> SchedulingReplacementResult:
    aggregate_row = _locked_aggregate(cursor, command)
    previous_generation_id = _previous_generation_id(aggregate_row)
    generation_id = _insert_generation(cursor, command)
    assignment_ids = _insert_assignments(cursor, command, generation_id)
    # ``uq_staff_schedule_effective_date`` covers the staff/date pair while
    # the old generation is effective.  Retire that generation inside this
    # same transaction before inserting a shifted replacement (for example an
    # Actual Start correction); rollback still restores the old generation if
    # any later write fails.
    _cancel_previous_state(cursor, command, previous_generation_id)
    _insert_schedules(cursor, command, generation_id, assignment_ids)
    _insert_buffers(cursor, command, generation_id, assignment_ids)
    _activate_new_generation(cursor, generation_id)
    _insert_occupancy(cursor, command, generation_id, assignment_ids)
    _advance_aggregate(cursor, command, previous_generation_id, generation_id)
    rebuild_event_id = _append_rebuild_event(
        cursor,
        command,
        previous_generation_id,
        generation_id,
    )
    _append_notification_invalidation_outbox(
        cursor,
        command,
        rebuild_event_id,
    )
    _append_lineage(
        cursor,
        command,
        rebuild_event_id,
        generation_id,
        assignment_ids,
    )
    receipt_id = _insert_scheduling_receipt(
        cursor,
        command,
        generation_id,
        rebuild_event_id,
        assignment_ids,
    )
    return SchedulingReplacementResult(
        generation_id=generation_id,
        scheduling_version=command.candidate.resulting_aggregate_version,
        rebuild_event_id=rebuild_event_id,
        scheduling_receipt_id=receipt_id,
        assignment_resolution=_assignment_resolution(command, assignment_ids),
    )


def _assignment_resolution(command, assignment_ids):
    if assignment_ids:
        return AssignmentIdentityResolution(assignment_ids)
    if command.command_family not in {
        "orders_cancellation_rebuild",
        "orders_terms_rebuild",
    }:
        raise ValueError("empty scheduling replacement is cancellation-only")
    return EmptyAssignmentIdentityResolution()


def _locked_aggregate(cursor: Any, command: SchedulingReplacementCommand):
    cursor.execute(
        "SELECT aggregate_version,generation_counter,effective_generation_id "
        "FROM scheduling_aggregates WHERE case_no=%s FOR UPDATE",
        (command.candidate.case_no,),
    )
    aggregate_row = cursor.fetchone()
    if aggregate_row is None:
        raise RuntimeError("scheduling_bootstrap_required")
    if int(aggregate_row["aggregate_version"]) != (
        command.candidate.expected_aggregate_version
    ):
        raise RuntimeError("scheduling_version_conflict")
    return aggregate_row


def _previous_generation_id(aggregate_row) -> int | None:
    value = aggregate_row["effective_generation_id"]
    return int(value) if value is not None else None


def _cancel_previous_state(cursor, command, previous_generation_id) -> None:
    if previous_generation_id is None:
        return
    _cancel_previous_buffers(cursor, command, previous_generation_id)
    _cancel_previous_leave_occupancy(cursor, command, previous_generation_id)
    _cancel_previous(cursor, command, previous_generation_id)


def _insert_generation(cursor: Any, command: SchedulingReplacementCommand) -> int:
    candidate = command.candidate
    cursor.execute(
        "INSERT INTO scheduling_generations "
        "(case_no,generation_number,resulting_aggregate_version,status,"
        "effective_marker,created_by,change_reason) "
        "VALUES (%s,%s,%s,'preparing',NULL,%s,%s)",
        (
            candidate.case_no,
            candidate.generation_number,
            candidate.resulting_aggregate_version,
            command.actor.actor_id,
            command.reason,
        ),
    )
    return int(cursor.lastrowid)


def _insert_assignments(
    cursor: Any,
    command: SchedulingReplacementCommand,
    generation_id: int,
) -> dict[str, int]:
    assignment_ids: dict[str, int] = {}
    for assignment in command.candidate.assignments:
        cursor.execute(
            "INSERT INTO case_staff_assignments "
            "(case_no,generation_id,candidate_key,staff_id,"
            "assignment_sequence,assigned_start_date,assigned_end_date,"
            "floor_fee_allocated,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,0,'planned')",
            (
                command.candidate.case_no,
                generation_id,
                assignment.candidate_key,
                assignment.staff_id,
                assignment.sequence,
                assignment.assigned_start_date,
                assignment.assigned_end_date,
            ),
        )
        assignment_ids[assignment.candidate_key] = int(cursor.lastrowid)
    return assignment_ids


def _insert_schedules(cursor, command, generation_id, assignment_ids) -> None:
    schedule_rows = tuple(
        row
        for assignment in command.candidate.assignments
        for row in _assignment_schedule_rows(
            command.candidate.case_no,
            generation_id,
            assignment,
            assignment_ids[assignment.candidate_key],
        )
    )
    cursor.executemany(
        "INSERT INTO staff_schedule "
        "(case_no,staff_id,assignment_id,generation_id,work_date,"
        "is_work_day,is_double_pay,effective_marker) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)",
        schedule_rows,
    )


def _assignment_schedule_rows(case_no, generation_id, assignment, assignment_id):
    double_pay_dates = set(assignment.double_pay_dates)
    for schedule_date in assignment.service_dates:
        yield (
            case_no,
            assignment.staff_id,
            assignment_id,
            generation_id,
            schedule_date,
            True,
            schedule_date in double_pay_dates,
        )


def _insert_buffers(cursor, command, generation_id, assignment_ids) -> None:
    assignment_key_by_buffer = {
        f"{assignment.candidate_key}:buffer": assignment.candidate_key
        for assignment in command.candidate.assignments
    }
    for buffer in command.candidate.buffers:
        assignment_key = assignment_key_by_buffer[buffer.candidate_key]
        for buffer_date in buffer.dates:
            _insert_buffer_day(
                cursor,
                command,
                generation_id,
                assignment_ids[assignment_key],
                buffer,
                buffer_date,
            )


def _insert_buffer_day(
    cursor,
    command,
    generation_id,
    assignment_id,
    buffer,
    buffer_date,
) -> None:
    if buffer.active:
        _insert_active_buffer(
            cursor,
            generation_id,
            assignment_id,
            buffer.staff_id,
            buffer_date,
        )
        return
    _insert_released_buffer(
        cursor,
        command,
        generation_id,
        assignment_id,
        buffer.staff_id,
        buffer_date,
    )


def _insert_active_buffer(
    cursor,
    generation_id,
    assignment_id,
    staff_id,
    buffer_date,
) -> None:
    cursor.execute(
        "INSERT INTO scheduling_buffer_days "
        "(generation_id,assignment_id,staff_id,buffer_date,status,"
        "active_marker) VALUES (%s,%s,%s,%s,'active',1)",
        (generation_id, assignment_id, staff_id, buffer_date),
    )


def _insert_released_buffer(
    cursor,
    command,
    generation_id,
    assignment_id,
    staff_id,
    buffer_date,
) -> None:
    cursor.execute(
        "INSERT INTO scheduling_buffer_days "
        "(generation_id,assignment_id,staff_id,buffer_date,status,"
        "active_marker,released_by,released_at) "
        "VALUES (%s,%s,%s,%s,'released',NULL,%s,CURRENT_TIMESTAMP)",
        (
            generation_id,
            assignment_id,
            staff_id,
            buffer_date,
            command.actor.actor_id,
        ),
    )


def _cancel_previous(cursor, command, previous_generation_id) -> None:
    _cancel_previous_schedules(cursor, previous_generation_id)
    _cancel_previous_assignments(cursor, command, previous_generation_id)
    cursor.execute(
        "DELETE FROM scheduling_effective_occupancy WHERE generation_id=%s",
        (previous_generation_id,),
    )
    cursor.execute(
        "UPDATE scheduling_generations SET status='cancelled',"
        "effective_marker=NULL,cancelled_at=CURRENT_TIMESTAMP "
        "WHERE id=%s AND status='effective' AND effective_marker=1",
        (previous_generation_id,),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("scheduling_generation_conflict")


def _cancel_previous_schedules(cursor, previous_generation_id) -> None:
    cursor.execute(
        "UPDATE staff_schedule SET effective_marker=NULL "
        "WHERE generation_id=%s AND effective_marker=1",
        (previous_generation_id,),
    )


def _cancel_previous_buffers(cursor, command, previous_generation_id) -> None:
    cursor.execute(
        "UPDATE scheduling_buffer_days SET status='cancelled',"
        "active_marker=NULL,released_by=%s,released_at=CURRENT_TIMESTAMP "
        "WHERE generation_id=%s AND active_marker=1",
        (command.actor.actor_id, previous_generation_id),
    )


def _cancel_previous_leave_occupancy(
    cursor,
    command,
    previous_generation_id,
) -> None:
    cursor.execute(
        "UPDATE scheduling_leave_occupancy_days SET status='cancelled',"
        "active_marker=NULL,cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP "
        "WHERE generation_id=%s AND active_marker=1",
        (command.actor.actor_id, previous_generation_id),
    )


def _cancel_previous_assignments(cursor, command, previous_generation_id) -> None:
    expected_ids = tuple(command.candidate.cancelled_assignment_ids)
    if not expected_ids:
        return
    placeholders = ",".join("%s" for _ in expected_ids)
    cursor.execute(
        "UPDATE case_staff_assignments SET status='cancelled',"
        "replacement_reason=%s WHERE generation_id=%s "
        f"AND id IN ({placeholders}) AND status NOT IN ('cancelled','replaced')",
        (
            "Replaced by canonical scheduling generation.",
            previous_generation_id,
            *expected_ids,
        ),
    )
    if cursor.rowcount != len(expected_ids):
        raise RuntimeError("scheduling_assignment_set_conflict")


def _activate_new_generation(cursor, generation_id) -> None:
    cursor.execute(
        "UPDATE scheduling_generations SET status='effective',"
        "effective_marker=1 WHERE id=%s AND status='preparing'",
        (generation_id,),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("scheduling_generation_conflict")
    cursor.execute(
        "UPDATE staff_schedule SET effective_marker=1 "
        "WHERE generation_id=%s AND effective_marker IS NULL",
        (generation_id,),
    )


def _insert_occupancy(cursor, command, generation_id, assignment_ids) -> None:
    occupancy_rows = list(
        _assignment_occupancy_rows(command, generation_id, assignment_ids)
    )
    occupancy_rows.extend(
        _buffer_occupancy_rows(command, generation_id, assignment_ids)
    )
    cursor.executemany(
        "INSERT INTO scheduling_effective_occupancy "
        "(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) "
        "VALUES (%s,%s,%s,%s,%s)",
        tuple(occupancy_rows),
    )


def _assignment_occupancy_rows(command, generation_id, assignment_ids):
    for assignment in command.candidate.assignments:
        for occupied_date in _inclusive_dates(
            assignment.assigned_start_date,
            assignment.assigned_end_date,
        ):
            yield (
                assignment.staff_id,
                occupied_date,
                generation_id,
                assignment_ids[assignment.candidate_key],
                "assignment_interval",
            )


def _buffer_occupancy_rows(command, generation_id, assignment_ids):
    assignment_key_by_buffer = {
        f"{assignment.candidate_key}:buffer": assignment.candidate_key
        for assignment in command.candidate.assignments
    }
    for buffer in command.candidate.buffers:
        if not buffer.active:
            continue
        assignment_id = assignment_ids[
            assignment_key_by_buffer[buffer.candidate_key]
        ]
        for buffer_date in buffer.dates:
            yield (
                buffer.staff_id,
                buffer_date,
                generation_id,
                assignment_id,
                "buffer",
            )


def _advance_aggregate(
    cursor,
    command,
    previous_generation_id,
    generation_id,
) -> None:
    candidate = command.candidate
    statement, parameters = _aggregate_advance_command(
        candidate,
        previous_generation_id,
        generation_id,
    )
    cursor.execute(statement, parameters)
    if cursor.rowcount != 1:
        raise RuntimeError("scheduling_version_conflict")


def _aggregate_advance_command(candidate, previous_generation_id, generation_id):
    statement = (
        "UPDATE scheduling_aggregates SET aggregate_version=%s,"
        "generation_counter=%s,effective_generation_id=%s "
        "WHERE case_no=%s AND aggregate_version=%s "
    )
    parameters = (
        candidate.resulting_aggregate_version,
        candidate.generation_number,
        generation_id,
        candidate.case_no,
        candidate.expected_aggregate_version,
    )
    if previous_generation_id is None:
        return statement + "AND effective_generation_id IS NULL", parameters
    return (
        statement + "AND effective_generation_id=%s",
        parameters + (previous_generation_id,),
    )


def _append_rebuild_event(
    cursor,
    command,
    previous_generation_id,
    generation_id,
) -> int:
    candidate = command.candidate
    cursor.execute(
        "INSERT INTO scheduling_rebuild_events "
        "(case_no,previous_generation_id,new_generation_id,"
        "expected_order_version,expected_scheduling_version,"
        "resulting_scheduling_version,preview_fingerprint,idempotency_key,"
        "actor,reason,correlation_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            candidate.case_no,
            previous_generation_id,
            generation_id,
            command.expected_order_version,
            candidate.expected_aggregate_version,
            candidate.resulting_aggregate_version,
            command.preview_fingerprint.value,
            command.idempotency_key.value,
            command.actor.actor_id,
            command.reason,
            command.correlation_id.value,
        ),
    )
    return int(cursor.lastrowid)


def _append_lineage(
    cursor,
    command,
    rebuild_event_id,
    generation_id,
    assignment_ids,
) -> None:
    lineage_rows = _lineage_rows(
        command, rebuild_event_id, generation_id, assignment_ids
    )
    if not lineage_rows:
        return
    cursor.executemany(
        "INSERT INTO scheduling_rebuild_lineage "
        "(rebuild_event_id,old_assignment_identity,new_assignment_id,"
        "new_generation_id,lineage_ordinal) VALUES (%s,%s,%s,%s,%s)",
        lineage_rows,
    )


def _append_notification_invalidation_outbox(
    cursor,
    command: SchedulingReplacementCommand,
    rebuild_event_id: int,
) -> None:
    """Emit only immutable cancelled-assignment facts; LINE never infers them."""
    cancelled_assignment_ids = tuple(
        sorted({int(value) for value in command.candidate.cancelled_assignment_ids})
    )
    if not cancelled_assignment_ids:
        return
    payload_snapshot = _canonical_json(
        {
            "case_no": command.candidate.case_no,
            "cancelled_assignment_ids": cancelled_assignment_ids,
        }
    )
    cursor.execute(
        "INSERT INTO scheduling_rebuild_notification_outbox "
        "(rebuild_event_id,intent_key,payload_snapshot) VALUES (%s,%s,%s)",
        (
            rebuild_event_id,
            f"scheduling-rebuild-notification-invalidation:{rebuild_event_id}",
            payload_snapshot,
        ),
    )


def _lineage_rows(command, rebuild_event_id, generation_id, assignment_ids):
    rows = []
    for assignment in command.candidate.assignments:
        for source_id in assignment.lineage_source_assignment_ids:
            rows.append(
                (
                    rebuild_event_id,
                    f"assignment:{source_id}",
                    assignment_ids[assignment.candidate_key],
                    generation_id,
                    len(rows) + 1,
                )
            )
    return tuple(rows)


def _insert_scheduling_receipt(
    cursor,
    command,
    generation_id,
    rebuild_event_id,
    assignment_ids,
) -> int:
    candidate = command.candidate
    cursor.execute(
        "INSERT INTO scheduling_command_receipts "
        "(idempotency_key,command_family,command_fingerprint,"
        "preview_fingerprint,case_no,expected_scheduling_version,"
        "resulting_scheduling_version,resulting_generation_id,"
        "rebuild_event_id,correlation_id,result_snapshot) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            command.idempotency_key.value,
            command.command_family,
            command.command_fingerprint.value,
            command.preview_fingerprint.value,
            candidate.case_no,
            candidate.expected_aggregate_version,
            candidate.resulting_aggregate_version,
            generation_id,
            rebuild_event_id,
            command.correlation_id.value,
            _canonical_json(_scheduling_result_payload(command, assignment_ids)),
        ),
    )
    return int(cursor.lastrowid)


def _scheduling_result_payload(command, assignment_ids) -> dict[str, object]:
    candidate = command.candidate
    return {
        "case_no": candidate.case_no,
        "generation_number": candidate.generation_number,
        "scheduling_version": candidate.resulting_aggregate_version,
        "assignment_ids": dict(sorted(assignment_ids.items())),
    }


def _inclusive_dates(start_date: date, end_date: date):
    for offset in range((end_date - start_date).days + 1):
        yield start_date + timedelta(days=offset)


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
