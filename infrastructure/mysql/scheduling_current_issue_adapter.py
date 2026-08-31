"""Read-only MySQL composition for Scheduling current anomaly facts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.scheduling.current_anomaly_facts import (
    SCHEDULING_ANOMALY_OWNER_DOMAIN,
    SCHEDULING_ANOMALY_OWNER_ROOT_TYPE,
    SchedulingCoverageCurrentFact,
    SchedulingCurrentIssueCode,
    SchedulingOverlapCurrentFact,
    SchedulingReplacementCurrentFact,
)


class MySqlSchedulingCurrentIssueAdapter:
    """Compose only Scheduling-owned assignment/generation facts."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        _validate_scope(scope)
        code = SchedulingCurrentIssueCode(scope.subject_type)
        facts = tuple(self._read_fact(code, value) for value in scope.subject_ids)
        token = fingerprint_payload({
            "code": code.value,
            "facts": tuple(_fact_payload(item) for item in facts),
        }).value
        return OwnerSnapshot(
            scope,
            token,
            max((item.owner_version for item in facts), default=0),
            facts,
            all(item.authoritative_complete for item in facts),
        )

    def _read_fact(self, code: SchedulingCurrentIssueCode, subject_id: str):
        if code is SchedulingCurrentIssueCode.REPLACEMENT_INCOMPLETE:
            return self._read_replacement(subject_id)
        if code is SchedulingCurrentIssueCode.ASSIGNMENT_OVERLAP:
            return self._read_overlap(subject_id)
        return self._read_coverage(subject_id)

    def _read_replacement(self, subject_id: str) -> SchedulingReplacementCurrentFact:
        if not subject_id.isdecimal() or int(subject_id) <= 0:
            raise ValueError("Scheduling replacement subject is invalid")
        assignment_id = int(subject_id)
        with self._connection.cursor() as cursor:
            cursor.execute(_REPLACEMENT_FACT_SQL, (assignment_id,))
            row = _mapping_row(cursor.fetchone())
        if row is None:
            token = fingerprint_payload({"assignment_id": assignment_id, "missing": True}).value
            return SchedulingReplacementCurrentFact(assignment_id, None, None, token, 0, False, False, False, False, False, False)
        source_replaced = row["source_status"] == "replaced"
        successor_complete = source_replaced and int(row["successor_count"]) > 0 and int(row["invalid_successor_count"]) == 0
        owner_receipt_complete = successor_complete and int(row["receipt_count"]) > 0
        payload = _canonical_row(row)
        return SchedulingReplacementCurrentFact(
            assignment_id,
            str(row["case_no"]),
            row["actual_start_date"] is not None,
            fingerprint_payload(payload).value,
            int(row["aggregate_version"]),
            True,
            successor_complete,
            owner_receipt_complete,
            successor_complete,
            owner_receipt_complete,
            owner_receipt_complete,
        )

    def _read_overlap(self, subject_id: str) -> SchedulingOverlapCurrentFact:
        left, right = _pair(subject_id)
        with self._connection.cursor() as cursor:
            cursor.execute(_OVERLAP_FACT_SQL, (left, right))
            rows = _mapping_rows(cursor.fetchall())
        complete = len(rows) == 2 and {int(row["assignment_id"]) for row in rows} == {left, right}
        active = complete and _effective_assignment(rows[0]) and _effective_assignment(rows[1]) and _intervals_overlap(rows[0], rows[1])
        version = max((int(row["aggregate_version"]) for row in rows), default=0)
        payload = {"subject": subject_id, "rows": _canonical_rows(rows), "complete": complete, "active": active}
        return SchedulingOverlapCurrentFact(
            left,
            right,
            str(rows[0]["case_no"]) if complete else None,
            str(rows[1]["case_no"]) if complete else None,
            fingerprint_payload(payload).value,
            version,
            complete,
            active,
        )

    def _read_coverage(self, subject_id: str) -> SchedulingCoverageCurrentFact:
        case_no, generation = _case_generation(subject_id)
        with self._connection.cursor() as cursor:
            cursor.execute(_GENERATION_FACT_SQL, (case_no, generation))
            generation_row = _mapping_row(cursor.fetchone())
            if generation_row is None:
                return _missing_coverage(case_no, generation)
            cursor.execute(_GENERATION_ASSIGNMENTS_SQL, (generation_row["generation_id"],))
            assignments = _mapping_rows(cursor.fetchall())
            assignment_ids = tuple(int(row["assignment_id"]) for row in assignments)
            schedules = ()
            conflicts = ()
            if assignment_ids:
                placeholders = ",".join("%s" for _ in assignment_ids)
                cursor.execute(_GENERATION_SCHEDULES_SQL.format(placeholders=placeholders), assignment_ids)
                schedules = _mapping_rows(cursor.fetchall())
                staff_ids = tuple(sorted({int(row["staff_id"]) for row in assignments}))
                staff_placeholders = ",".join("%s" for _ in staff_ids)
                cursor.execute(
                    _EXTERNAL_OCCUPANCY_SQL.format(placeholders=staff_placeholders),
                    (*staff_ids, case_no),
                )
                conflicts = _mapping_rows(cursor.fetchall())
        flags = _coverage_flags(generation_row, assignments, schedules, conflicts)
        payload = {"generation": _canonical_row(generation_row), "assignments": _canonical_rows(assignments), "schedules": _canonical_rows(schedules), "conflicts": _canonical_rows(conflicts), "flags": flags}
        token = fingerprint_payload(payload).value
        return SchedulingCoverageCurrentFact(case_no, generation, token, int(generation_row["aggregate_version"]), True, *flags)


def _coverage_flags(generation, assignments, schedules, conflicts):
    generation_valid = (
        generation["generation_status"] == "effective"
        and int(generation["effective_marker"]) == 1
        and int(generation["generation_id"]) == int(generation["effective_generation_id"])
    )
    dates_by_assignment: dict[int, list[date]] = {}
    for row in schedules:
        dates_by_assignment.setdefault(int(row["assignment_id"]), []).append(_date(row["work_date"]))
    official_valid = bool(assignments) and all(
        dates_by_assignment.get(int(row["assignment_id"]))
        and all(_date(row["assigned_start_date"]) <= value <= _date(row["assigned_end_date"]) for value in dates_by_assignment[int(row["assignment_id"])])
        for row in assignments
    )
    all_dates = tuple(value for values in dates_by_assignment.values() for value in values)
    ownership_valid = (
        len(all_dates) == len(set(all_dates))
        and all(int(row["schedule_effective_marker"]) == 1 for row in schedules)
        and set(dates_by_assignment) == {int(row["assignment_id"]) for row in assignments}
    )
    coverage_valid = len(set(all_dates)) == int(generation["service_days"])
    hours_valid = coverage_valid and int(generation["service_hours_per_day"]) > 0
    occupancy_valid = not _has_external_overlap(assignments, conflicts)
    return official_valid, ownership_valid, coverage_valid, hours_valid, occupancy_valid, generation_valid


def _missing_coverage(case_no: str, generation: int) -> SchedulingCoverageCurrentFact:
    token = fingerprint_payload({"case_no": case_no, "generation": generation, "missing": True}).value
    return SchedulingCoverageCurrentFact(case_no, generation, token, 0, False, False, False, False, False, False, False)


def _effective_assignment(row) -> bool:
    return (
        row["assignment_status"] in {"planned", "active"}
        and row["generation_status"] == "effective"
        and int(row["effective_marker"]) == 1
        and int(row["generation_id"]) == int(row["effective_generation_id"])
    )


def _intervals_overlap(left, right) -> bool:
    return _date(left["assigned_start_date"]) <= _date(right["assigned_end_date"]) and _date(right["assigned_start_date"]) <= _date(left["assigned_end_date"])


def _has_external_overlap(assignments, conflicts) -> bool:
    return any(
        int(current["staff_id"]) == int(external["staff_id"])
        and _intervals_overlap(current, external)
        for current in assignments
        for external in conflicts
    )


def _fact_payload(fact):
    return {
        "type": type(fact).__name__,
        "owner_snapshot_token": fact.owner_snapshot_token,
        "owner_version": fact.owner_version,
        "authoritative_complete": fact.authoritative_complete,
        "predicate_active": fact.predicate_active,
        "unresolved": tuple(item.value for item in fact.unresolved_reason_codes),
    }


def _validate_scope(scope: RecheckScope) -> None:
    if scope.owner_domain != SCHEDULING_ANOMALY_OWNER_DOMAIN or scope.owner_root_type != SCHEDULING_ANOMALY_OWNER_ROOT_TYPE:
        raise ValueError("Scheduling anomaly owner scope is invalid")
    SchedulingCurrentIssueCode(scope.subject_type)


def _pair(value: str) -> tuple[int, int]:
    left, separator, right = value.partition(":")
    if not separator or not left.isdecimal() or not right.isdecimal():
        raise ValueError("Scheduling overlap subject is invalid")
    result = int(left), int(right)
    if result[0] <= 0 or result[0] >= result[1]:
        raise ValueError("Scheduling overlap subject is not canonical")
    return result


def _case_generation(value: str) -> tuple[str, int]:
    case_no, separator, generation = value.rpartition(":")
    if not separator or not case_no or case_no != case_no.strip() or not generation.isdecimal() or int(generation) <= 0:
        raise ValueError("Scheduling coverage subject is invalid")
    return case_no, int(generation)


def _mapping_rows(rows):
    values = tuple(rows)
    if any(not isinstance(row, Mapping) for row in values):
        raise TypeError("Scheduling current-fact row is invalid")
    return values


def _mapping_row(row):
    if row is None:
        return None
    if not isinstance(row, Mapping):
        raise TypeError("Scheduling current-fact row is invalid")
    return row


def _canonical_rows(rows):
    return tuple(_canonical_row(row) for row in rows)


def _canonical_row(row):
    return {
        str(key): value.isoformat() if isinstance(value, (date, datetime)) else value
        for key, value in row.items()
    }


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    raise TypeError("Scheduling current-fact date is invalid")


_OVERLAP_FACT_SQL = (
    "SELECT a.id AS assignment_id,a.case_no,a.status AS assignment_status,a.assigned_start_date,a.assigned_end_date,"
    "a.generation_id,g.status AS generation_status,g.effective_marker,sa.effective_generation_id,sa.aggregate_version "
    "FROM case_staff_assignments a JOIN scheduling_generations g ON g.id=a.generation_id "
    "JOIN scheduling_aggregates sa ON sa.case_no=a.case_no WHERE a.id IN (%s,%s) ORDER BY a.id"
)
_REPLACEMENT_FACT_SQL = (
    "SELECT source.id AS source_assignment_id,source.case_no,source.status AS source_status,"
    "orders.actual_start_date,sa.aggregate_version,"
    "COUNT(DISTINCT lineage.new_assignment_id) AS successor_count,"
    "COALESCE(SUM(CASE WHEN lineage.new_assignment_id IS NOT NULL AND (successor.status NOT IN ('planned','active') "
    "OR successor.generation_id<>sa.effective_generation_id OR generation.status<>'effective' OR generation.effective_marker<>1) THEN 1 ELSE 0 END),0) AS invalid_successor_count,"
    "COUNT(DISTINCT receipt.id) AS receipt_count "
    "FROM case_staff_assignments source JOIN scheduling_aggregates sa ON sa.case_no=source.case_no "
    "JOIN orders ON orders.case_no=source.case_no "
    "LEFT JOIN scheduling_rebuild_lineage lineage ON lineage.old_assignment_identity=CONCAT('assignment:',source.id) "
    "LEFT JOIN case_staff_assignments successor ON successor.id=lineage.new_assignment_id "
    "LEFT JOIN scheduling_generations generation ON generation.id=successor.generation_id "
    "LEFT JOIN scheduling_command_receipts receipt ON receipt.rebuild_event_id=lineage.rebuild_event_id "
    "WHERE source.id=%s GROUP BY source.id,source.case_no,source.status,orders.actual_start_date,sa.aggregate_version"
)
_GENERATION_FACT_SQL = (
    "SELECT g.id AS generation_id,g.generation_number,g.status AS generation_status,g.effective_marker,"
    "sa.effective_generation_id,sa.aggregate_version,o.service_days,o.service_hours_per_day "
    "FROM scheduling_generations g JOIN scheduling_aggregates sa ON sa.case_no=g.case_no "
    "JOIN orders o ON o.case_no=g.case_no WHERE g.case_no=%s AND g.generation_number=%s"
)
_GENERATION_ASSIGNMENTS_SQL = (
    "SELECT id AS assignment_id,staff_id,assigned_start_date,assigned_end_date,status AS assignment_status "
    "FROM case_staff_assignments WHERE generation_id=%s AND status NOT IN ('cancelled','replaced') ORDER BY id"
)
_GENERATION_SCHEDULES_SQL = (
    "SELECT assignment_id,work_date,effective_marker AS schedule_effective_marker FROM staff_schedule "
    "WHERE assignment_id IN ({placeholders}) AND is_work_day=1 ORDER BY assignment_id,work_date"
)
_EXTERNAL_OCCUPANCY_SQL = (
    "SELECT a.id AS assignment_id,a.staff_id,a.assigned_start_date,a.assigned_end_date "
    "FROM case_staff_assignments a JOIN scheduling_generations g ON g.id=a.generation_id "
    "JOIN scheduling_aggregates sa ON sa.case_no=a.case_no AND sa.effective_generation_id=g.id "
    "WHERE a.staff_id IN ({placeholders}) AND a.case_no<>%s AND a.status IN ('planned','active') "
    "AND g.status='effective' AND g.effective_marker=1 LIMIT 1"
)


__all__ = ["MySqlSchedulingCurrentIssueAdapter"]
