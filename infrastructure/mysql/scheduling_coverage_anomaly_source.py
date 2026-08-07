"""Bounded MySQL root-fact source for Scheduling coverage anomalies."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from pymysql.err import MySQLError

from subsystems.anomalies.scheduling_coverage_anomaly_consumer import (
    AssignmentOfficialServiceDays,
    SchedulingCoverageRootFact,
    SchedulingCoverageScanPage,
    SchedulingCoverageScanRequest,
)
from shared_kernel.fingerprints import fingerprint_payload

_COMPLETED_ORDER_STATUS = "訂單完成"
_MISSING_SCHEMA_ERROR_CODES = frozenset({1054, 1146})


class SchedulingCoverageSchemaUnavailableError(RuntimeError):
    def __init__(self, database_error_code: int) -> None:
        self.database_error_code = database_error_code
        super().__init__("scheduling_coverage_schema_unavailable")


class MySqlSchedulingCoverageAnomalySource:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_page(
        self,
        request: SchedulingCoverageScanRequest,
    ) -> SchedulingCoverageScanPage:
        try:
            with self._connection.cursor() as cursor:
                generation_rows = _load_generation_rows(cursor, request)
                assignment_rows = _load_assignment_rows(cursor, generation_rows)
                schedule_rows = _load_schedule_rows(cursor, assignment_rows)
        except MySQLError as error:
            if _database_error_code(error) in _MISSING_SCHEMA_ERROR_CODES:
                raise SchedulingCoverageSchemaUnavailableError(
                    _database_error_code(error)
                ) from error
            raise
        facts = _build_root_facts(
            generation_rows,
            assignment_rows,
            schedule_rows,
        )
        return SchedulingCoverageScanPage(
            facts,
            _next_cursor(generation_rows, request.limit),
        )


def _load_generation_rows(cursor, request):
    after = _parse_cursor(request.after_source_identity)
    if after is None:
        cursor.execute(_FIRST_PAGE_SQL, (request.limit,))
    else:
        case_no, generation = after
        cursor.execute(
            _NEXT_PAGE_SQL,
            (case_no, case_no, generation, request.limit),
        )
    return _mapping_rows(cursor.fetchall(), "scheduling generations")


def _load_assignment_rows(cursor, generation_rows):
    effective_generation_ids = _effective_generation_ids(generation_rows)
    if not effective_generation_ids:
        return ()
    cursor.execute(
        _ASSIGNMENT_SQL.format(
            placeholders=_placeholders(effective_generation_ids)
        ),
        effective_generation_ids,
    )
    return _mapping_rows(cursor.fetchall(), "effective assignments")


def _load_schedule_rows(cursor, assignment_rows):
    assignment_ids = tuple(
        _positive_integer(row["assignment_id"], "assignment id")
        for row in assignment_rows
    )
    if not assignment_ids:
        return ()
    cursor.execute(
        _SCHEDULE_SQL.format(placeholders=_placeholders(assignment_ids)),
        assignment_ids,
    )
    return _mapping_rows(cursor.fetchall(), "official service dates")


def _build_root_facts(generation_rows, assignment_rows, schedule_rows):
    assignments_by_generation = _assignment_facts(
        assignment_rows,
        schedule_rows,
    )
    return tuple(
        _root_fact(row, assignments_by_generation)
        for row in generation_rows
    )


def _root_fact(row, assignments_by_generation):
    generation_id = _positive_integer(row["generation_id"], "generation id")
    assignments = assignments_by_generation.get(generation_id, ())
    fact_values = _root_fact_values(row, assignments)
    return SchedulingCoverageRootFact(
        **fact_values,
        source_event_identity=_source_event_identity(fact_values),
    )


def _root_fact_values(row, assignments):
    generation_effective = _generation_is_effective(row)
    return {
        "case_no": _canonical_case_no(row["case_no"]),
        "generation": _positive_integer(
            row["generation_number"],
            "generation number",
        ),
        "expected_service_days": _nonnegative_integer(
            row["service_days"],
            "service days",
        ),
        "assignments": assignments if generation_effective else (),
        "generation_effective": generation_effective,
        "completed_eligible": row["order_status"] == _COMPLETED_ORDER_STATUS,
        "source_version": _nonnegative_integer(
            row["aggregate_version"],
            "aggregate version",
        ),
    }


def _assignment_facts(assignment_rows, schedule_rows):
    dates_by_assignment = _dates_by_assignment(schedule_rows)
    grouped: dict[int, list[AssignmentOfficialServiceDays]] = {}
    for row in assignment_rows:
        generation_id = _positive_integer(
            row["generation_id"],
            "assignment generation id",
        )
        assignment_id = _positive_integer(row["assignment_id"], "assignment id")
        fact = AssignmentOfficialServiceDays(
            assignment_id,
            dates_by_assignment.get(assignment_id, ()),
        )
        grouped.setdefault(generation_id, []).append(fact)
    return {
        key: tuple(sorted(values, key=lambda item: item.assignment_id))
        for key, values in grouped.items()
    }


def _dates_by_assignment(schedule_rows):
    grouped: dict[int, list[date]] = {}
    for row in schedule_rows:
        assignment_id = _positive_integer(
            row["assignment_id"],
            "schedule assignment id",
        )
        grouped.setdefault(assignment_id, []).append(
            _as_date(row["work_date"], "work date")
        )
    return {
        key: tuple(sorted(set(values))) for key, values in grouped.items()
    }


def _source_event_identity(fact_values):
    payload = {
        **fact_values,
        "assignments": tuple(
            {
                "assignment_id": assignment.assignment_id,
                "service_dates": tuple(
                    value.isoformat() for value in assignment.service_dates
                ),
            }
            for assignment in fact_values["assignments"]
        ),
    }
    return f"scheduling-coverage:{fingerprint_payload(payload).value}"


def _effective_generation_ids(rows):
    return tuple(
        _positive_integer(row["generation_id"], "generation id")
        for row in rows
        if _generation_is_effective(row)
    )


def _generation_is_effective(row):
    generation_id = _positive_integer(row["generation_id"], "generation id")
    effective_generation_id = row["effective_generation_id"]
    is_current = (
        effective_generation_id is not None
        and generation_id
        == _positive_integer(effective_generation_id, "effective generation id")
    )
    declared_effective = (
        row["generation_status"] == "effective"
        and row["effective_marker"] == 1
    )
    if is_current != declared_effective:
        raise ValueError("scheduling_generation_conflict")
    return is_current


def _next_cursor(rows, limit):
    if len(rows) < limit or not rows:
        return None
    last = rows[-1]
    case_no = _canonical_case_no(last["case_no"])
    generation = _positive_integer(
        last["generation_number"],
        "generation number",
    )
    return f"{case_no}|{generation}"


def _parse_cursor(value):
    if value is None:
        return None
    case_no, separator, generation_text = value.rpartition("|")
    if not separator or not generation_text.isdecimal():
        raise ValueError("scheduling coverage scan cursor is invalid")
    return (
        _canonical_case_no(case_no),
        _positive_integer(int(generation_text), "cursor generation"),
    )


def _mapping_rows(rows, label):
    result = tuple(rows)
    if any(not isinstance(row, Mapping) for row in result):
        raise ValueError(f"{label} contain an invalid row")
    return result


def _canonical_case_no(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("case number must be canonical")
    if len(value) > 50:
        raise ValueError("case number is too long")
    return value


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _as_date(value, label):
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    raise ValueError(f"{label} must be a date")


def _database_error_code(error):
    if error.args and isinstance(error.args[0], int):
        return error.args[0]
    return 0


def _placeholders(values):
    return ",".join("%s" for _ in values)


_GENERATION_SELECT = (
    "SELECT g.id AS generation_id,g.case_no,g.generation_number,"
    "g.status AS generation_status,g.effective_marker,"
    "sa.aggregate_version,sa.effective_generation_id,"
    "o.service_days,o.status AS order_status "
    "FROM scheduling_generations g "
    "JOIN scheduling_aggregates sa ON sa.case_no=g.case_no "
    "JOIN orders o ON o.case_no=g.case_no "
    "WHERE g.status IN ('effective','cancelled') "
)
_FIRST_PAGE_SQL = (
    _GENERATION_SELECT
    + "ORDER BY g.case_no,g.generation_number LIMIT %s"
)
_NEXT_PAGE_SQL = (
    _GENERATION_SELECT
    + "AND (g.case_no>%s OR "
    "(g.case_no=%s AND g.generation_number>%s)) "
    "ORDER BY g.case_no,g.generation_number LIMIT %s"
)
_ASSIGNMENT_SQL = (
    "SELECT a.id AS assignment_id,a.generation_id "
    "FROM case_staff_assignments a "
    "JOIN scheduling_generations g ON g.id=a.generation_id "
    "JOIN scheduling_aggregates sa ON sa.case_no=a.case_no "
    "AND sa.effective_generation_id=g.id "
    "WHERE a.generation_id IN ({placeholders}) "
    "AND g.status='effective' AND g.effective_marker=1 "
    "AND a.status NOT IN ('cancelled','replaced') "
    "ORDER BY a.generation_id,a.id"
)
_SCHEDULE_SQL = (
    "SELECT ss.assignment_id,ss.work_date "
    "FROM staff_schedule ss "
    "JOIN case_staff_assignments a ON a.id=ss.assignment_id "
    "JOIN scheduling_generations g ON g.id=a.generation_id "
    "JOIN scheduling_aggregates sa ON sa.case_no=a.case_no "
    "AND sa.effective_generation_id=g.id "
    "WHERE ss.assignment_id IN ({placeholders}) "
    "AND ss.generation_id=g.id AND ss.effective_marker=1 "
    "AND ss.is_work_day=1 "
    "AND g.status='effective' AND g.effective_marker=1 "
    "AND a.status NOT IN ('cancelled','replaced') "
    "ORDER BY ss.assignment_id,ss.work_date"
)


__all__ = [
    "MySqlSchedulingCoverageAnomalySource",
    "SchedulingCoverageSchemaUnavailableError",
]
