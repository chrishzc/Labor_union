"""MySQL persistence for metadata-only Scheduling generation bootstrap."""

from __future__ import annotations

import json

from domains.scheduling.bootstrap import (
    SchedulingBootstrapCandidate,
    SchedulingBootstrapIssue,
)


def persist_scheduling_bootstrap(
    cursor,
    candidate: SchedulingBootstrapCandidate,
    migration_identity: str,
) -> int:
    _insert_aggregate(cursor, candidate.case_no)
    generation_id = _insert_generation(cursor, candidate, migration_identity)
    for assignment in candidate.assignments:
        _attach_assignment(cursor, assignment, generation_id)
        _attach_schedules(cursor, assignment, generation_id)
        _insert_buffers(cursor, assignment, generation_id)
        _insert_occupancy(cursor, assignment, generation_id)
    _activate_generation(cursor, candidate.case_no, generation_id)
    return generation_id


def append_scheduling_bootstrap_reviews(
    cursor,
    case_no: str,
    issues: tuple[SchedulingBootstrapIssue, ...],
    evidence: dict[str, object],
    migration_identity: str,
) -> None:
    payload = _review_evidence_payload(evidence)
    rows = _review_rows(case_no, issues, migration_identity, payload)
    for row in rows:
        _append_review_if_absent(cursor, row)


def _append_review_if_absent(cursor, row) -> None:
    existing_payload = _load_review_payload(cursor, row[:3])
    if existing_payload is not None:
        if _decoded_payload(existing_payload) != _decoded_payload(row[3]):
            raise RuntimeError("scheduling_bootstrap_review_conflict")
        return
    cursor.execute(
        "INSERT INTO scheduling_bootstrap_review_events "
        "(case_no,issue_code,migration_identity,evidence_snapshot) "
        "VALUES (%s,%s,%s,%s)",
        row,
    )


def _load_review_payload(cursor, identity):
    cursor.execute(
        "SELECT evidence_snapshot FROM scheduling_bootstrap_review_events "
        "WHERE case_no=%s AND issue_code=%s AND migration_identity=%s",
        identity,
    )
    existing = cursor.fetchone()
    return existing.get("evidence_snapshot") if existing else None


def _decoded_payload(payload):
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def _review_evidence_payload(evidence: dict[str, object]) -> str:
    return json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _review_rows(case_no, issues, migration_identity, payload):
    return tuple(
        (case_no, issue.value, migration_identity, payload)
        for issue in issues
    )


def _insert_aggregate(cursor, case_no: str) -> None:
    cursor.execute(
        "INSERT INTO scheduling_aggregates "
        "(case_no,aggregate_version,generation_counter) VALUES (%s,1,1)",
        (case_no,),
    )


def _insert_generation(cursor, candidate, migration_identity) -> int:
    cursor.execute(
        "INSERT INTO scheduling_generations "
        "(case_no,generation_number,resulting_aggregate_version,status,"
        "effective_marker,created_by,change_reason) "
        "VALUES (%s,1,1,'effective',1,%s,%s)",
        (
            candidate.case_no,
            migration_identity,
            "Metadata-only bootstrap from verified legacy assignment ownership.",
        ),
    )
    return int(cursor.lastrowid)


def _attach_assignment(cursor, assignment, generation_id) -> None:
    cursor.execute(
        "UPDATE case_staff_assignments "
        "SET generation_id=%s,candidate_key=%s "
        "WHERE id=%s AND generation_id IS NULL",
        (generation_id, assignment.candidate_key, assignment.assignment_id),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("scheduling_bootstrap_assignment_conflict")


def _attach_schedules(cursor, assignment, generation_id) -> None:
    cursor.execute(
        "UPDATE staff_schedule SET generation_id=%s,effective_marker=1 "
        f"WHERE id IN ({_placeholders(assignment.schedule_ids)}) "
        "AND generation_id IS NULL",
        (generation_id, *assignment.schedule_ids),
    )
    if cursor.rowcount != len(assignment.schedule_ids):
        raise RuntimeError("scheduling_bootstrap_schedule_conflict")


def _insert_buffers(cursor, assignment, generation_id) -> None:
    rows = tuple(
        (generation_id, assignment.assignment_id, assignment.staff_id, item)
        for item in assignment.buffer_dates
    )
    if not rows:
        return
    cursor.executemany(
        "INSERT INTO scheduling_buffer_days "
        "(generation_id,assignment_id,staff_id,buffer_date,status,active_marker) "
        "VALUES (%s,%s,%s,%s,'active',1)",
        rows,
    )


def _insert_occupancy(cursor, assignment, generation_id) -> None:
    interval_rows = _occupancy_rows(
        assignment,
        generation_id,
        assignment.interval_dates,
        "assignment_interval",
    )
    buffer_rows = _occupancy_rows(
        assignment,
        generation_id,
        assignment.buffer_dates,
        "buffer",
    )
    cursor.executemany(
        "INSERT INTO scheduling_effective_occupancy "
        "(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) "
        "VALUES (%s,%s,%s,%s,%s)",
        interval_rows + buffer_rows,
    )


def _occupancy_rows(assignment, generation_id, dates, occupancy_type):
    return tuple(
        (
            assignment.staff_id,
            item,
            generation_id,
            assignment.assignment_id,
            occupancy_type,
        )
        for item in dates
    )


def _activate_generation(cursor, case_no, generation_id) -> None:
    cursor.execute(
        "UPDATE scheduling_aggregates SET effective_generation_id=%s "
        "WHERE case_no=%s AND aggregate_version=1 AND generation_counter=1",
        (generation_id, case_no),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("scheduling_bootstrap_aggregate_conflict")


def _placeholders(values) -> str:
    if not values:
        raise ValueError("schedule ids are required")
    return ",".join("%s" for _ in values)
