"""
File: scheduling_current_projection_repository.py
Description: 從 MySQL 載入 current Scheduling assignment、全案首個服務日與占用根事實。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

from domains.orders.terms import ServiceTimeTerms
from domains.scheduling.current_projection import (
    EffectiveAssignmentCurrentFact,
    SchedulingCurrentFacts,
    StaffUnavailabilityCurrentFact,
    StoredEffectiveOccupancyFact,
    WaitingDepositLockCurrentFact,
)
from subsystems.scheduling.current_projection_workflow import (
    SchedulingCurrentQuery,
)


class MySqlSchedulingCurrentProjectionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_current_facts(
        self,
        query: SchedulingCurrentQuery,
    ) -> SchedulingCurrentFacts:
        with self._connection.cursor() as cursor:
            _require_staff(cursor, query.staff_id)
            assignment_rows = _assignment_rows(cursor, query)
            assignments = _assignments(cursor, assignment_rows)
            occupancy = _stored_occupancy(cursor, assignments)
            waiting_locks = _waiting_locks(cursor, query)
            unavailability_blocks = _unavailability_blocks(cursor, query)
        return SchedulingCurrentFacts(
            query.staff_id,
            assignments,
            occupancy,
            waiting_locks,
            unavailability_blocks,
        )


def _unavailability_blocks(cursor, query):
    cursor.execute(
        "SELECT id,staff_id,block_kind,start_date,end_date FROM "
        "scheduling_staff_unavailability_blocks WHERE staff_id=%s "
        "AND status='effective' AND start_date<=%s "
        "AND (end_date IS NULL OR end_date>=%s) ORDER BY start_date,id",
        (query.staff_id, query.range_end, query.range_start),
    )
    return tuple(
        StaffUnavailabilityCurrentFact(
            int(row["id"]),
            int(row["staff_id"]),
            str(row["block_kind"]),
            _as_date(row["start_date"], "availability start date"),
            None
            if row["end_date"] is None
            else _as_date(row["end_date"], "availability end date"),
        )
        for row in _mapping_rows(cursor.fetchall(), "staff unavailability")
    )


def _require_staff(cursor, staff_id):
    cursor.execute("SELECT id FROM staff WHERE id=%s", (staff_id,))
    if cursor.fetchone() is None:
        raise ValueError("staff_not_found")


def _assignment_rows(cursor, query):
    cursor.execute(
        _ASSIGNMENT_SELECT_SQL,
        (
            query.staff_id,
            query.range_end,
            query.range_start,
            query.range_start,
            query.range_end,
        ),
    )
    return _mapping_rows(cursor.fetchall(), "effective assignments")


def _assignments(cursor, rows):
    if not rows:
        return ()
    assignment_ids = tuple(int(row["assignment_id"]) for row in rows)
    generation_ids = tuple(sorted({int(row["generation_id"]) for row in rows}))
    official_dates = _official_service_dates(cursor, assignment_ids)
    buffer_dates = _active_buffer_dates(cursor, assignment_ids)
    case_first_service_dates = _case_first_service_dates(cursor, generation_ids)
    return tuple(
        _assignment_fact(
            row,
            case_first_service_dates[int(row["generation_id"])],
            official_dates.get(int(row["assignment_id"]), ()),
            buffer_dates.get(int(row["assignment_id"]), ()),
        )
        for row in rows
    )


def _case_first_service_dates(cursor, generation_ids):
    cursor.execute(
        _CASE_FIRST_SERVICE_SELECT_SQL.format(
            placeholders=_placeholders(generation_ids)
        ),
        generation_ids,
    )
    return {
        int(row["generation_id"]): _as_date(
            row["first_service_date"], "case first service date"
        )
        for row in _mapping_rows(cursor.fetchall(), "case first service dates")
    }


def _official_service_dates(cursor, assignment_ids):
    cursor.execute(
        _SCHEDULE_SELECT_SQL.format(
            placeholders=_placeholders(assignment_ids)
        ),
        assignment_ids,
    )
    grouped: dict[int, list[date]] = {}
    for row in _mapping_rows(cursor.fetchall(), "official schedules"):
        grouped.setdefault(int(row["assignment_id"]), []).append(
            _as_date(row["work_date"], "work date")
        )
    return {
        key: tuple(sorted(set(values))) for key, values in grouped.items()
    }


def _active_buffer_dates(cursor, assignment_ids):
    cursor.execute(
        _BUFFER_SELECT_SQL.format(
            placeholders=_placeholders(assignment_ids)
        ),
        assignment_ids,
    )
    grouped: dict[int, list[date]] = {}
    for row in _mapping_rows(cursor.fetchall(), "active buffers"):
        grouped.setdefault(int(row["assignment_id"]), []).append(
            _as_date(row["buffer_date"], "buffer date")
        )
    return {
        key: tuple(sorted(set(values))) for key, values in grouped.items()
    }


def _stored_occupancy(cursor, assignments):
    if not assignments:
        return ()
    assignment_ids = tuple(item.assignment_id for item in assignments)
    cursor.execute(
        _OCCUPANCY_SELECT_SQL.format(
            placeholders=_placeholders(assignment_ids)
        ),
        assignment_ids,
    )
    return tuple(
        StoredEffectiveOccupancyFact(
            int(row["staff_id"]),
            _as_date(row["occupancy_date"], "occupancy date"),
            int(row["generation_id"]),
            int(row["assignment_id"]),
            str(row["occupancy_type"]),
        )
        for row in _mapping_rows(cursor.fetchall(), "effective occupancy")
    )


def _waiting_locks(cursor, query):
    cursor.execute(
        _WAITING_SEGMENT_SELECT_SQL,
        (
            query.staff_id,
            query.range_end,
            query.range_start,
        ),
    )
    rows = _mapping_rows(cursor.fetchall(), "waiting lock segments")
    if not rows:
        return ()
    identities = tuple(_waiting_lock_identity(row) for row in rows)
    lock_dates = _waiting_lock_dates(cursor, identities)
    return tuple(
        _waiting_lock_fact(row, lock_dates.get(_waiting_lock_identity(row), ()))
        for row in rows
    )


def _waiting_lock_identity(row):
    return int(row["lock_id"]), int(row["segment_id"])


def _waiting_lock_dates(cursor, identities):
    predicates = " OR ".join(
        "(lock_id=%s AND segment_id=%s)" for _ in identities
    )
    parameters = tuple(
        value for identity in identities for value in identity
    )
    cursor.execute(
        "SELECT lock_id,segment_id,lock_date "
        "FROM caregiver_availability_lock_days "
        f"WHERE active_marker=1 AND ({predicates}) "
        "ORDER BY lock_id,segment_id,lock_date",
        parameters,
    )
    grouped = _group_waiting_lock_dates(cursor.fetchall())
    return {
        key: tuple(sorted(set(values))) for key, values in grouped.items()
    }


def _group_waiting_lock_dates(rows):
    grouped: dict[tuple[int, int], list[date]] = {}
    for row in _mapping_rows(rows, "waiting lock days"):
        identity = _waiting_lock_identity(row)
        grouped.setdefault(identity, []).append(
            _as_date(row["lock_date"], "lock date")
        )
    return grouped


def _assignment_fact(row, case_first_service_date, official_dates, buffer_dates):
    service_time = _service_time_terms(row)
    return EffectiveAssignmentCurrentFact(
        int(row["assignment_id"]),
        str(row["case_no"]),
        int(row["generation_id"]),
        int(row["scheduling_version"]),
        int(row["staff_id"]),
        _as_date(row["assigned_start_date"], "assigned start date"),
        _as_date(row["assigned_end_date"], "assigned end date"),
        case_first_service_date,
        official_dates,
        buffer_dates,
        int(row["service_hours_per_day"]),
        service_time,
    )


def _service_time_terms(row):
    values = (
        row["service_start_time"],
        row["service_end_time"],
        row["service_end_day_offset"],
    )
    if any(value is None for value in values):
        raise ValueError("service_time_terms_incomplete")
    return ServiceTimeTerms(
        _as_time(values[0], "service start time"),
        _as_time(values[1], "service end time"),
        int(values[2]),
    )


def _waiting_lock_fact(row, locked_dates):
    return WaitingDepositLockCurrentFact(
        int(row["lock_id"]),
        int(row["segment_id"]),
        str(row["case_no"]),
        int(row["staff_id"]),
        _as_date(row["assigned_start_date"], "lock start date"),
        _as_date(row["assigned_end_date"], "lock end date"),
        locked_dates,
    )


def _mapping_rows(rows, label):
    result = tuple(rows)
    if any(not isinstance(row, Mapping) for row in result):
        raise ValueError(f"{label} contain an invalid row")
    return result


def _as_date(value, label):
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    raise ValueError(f"{label} is invalid")


def _as_time(value, label):
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        if 0 <= seconds < 86_400:
            return time(
                seconds // 3_600,
                seconds % 3_600 // 60,
                seconds % 60,
            )
    raise ValueError(f"{label} is invalid")


def _placeholders(values):
    return ",".join("%s" for _ in values)


_ASSIGNMENT_SELECT_SQL = (
    "SELECT a.id AS assignment_id,a.case_no,a.generation_id,a.staff_id,"
    "a.assigned_start_date,a.assigned_end_date,"
    "sa.aggregate_version AS scheduling_version,"
    "o.service_hours_per_day,o.service_start_time,o.service_end_time,"
    "o.service_end_day_offset "
    "FROM case_staff_assignments a "
    "JOIN scheduling_generations g ON g.id=a.generation_id "
    "AND g.status='effective' AND g.effective_marker=1 "
    "JOIN scheduling_aggregates sa ON sa.case_no=a.case_no "
    "AND sa.effective_generation_id=g.id "
    "JOIN orders o ON o.case_no=a.case_no "
    "WHERE a.staff_id=%s AND a.status NOT IN ('cancelled','replaced') "
    "AND ((a.assigned_start_date<=%s AND a.assigned_end_date>=%s) "
    "OR EXISTS (SELECT 1 FROM scheduling_buffer_days b "
    "WHERE b.assignment_id=a.id AND b.active_marker=1 "
    "AND b.buffer_date BETWEEN %s AND %s)) "
    "ORDER BY a.case_no,a.id"
)
_SCHEDULE_SELECT_SQL = (
    "SELECT assignment_id,work_date FROM staff_schedule "
    "WHERE assignment_id IN ({placeholders}) "
    "AND effective_marker=1 AND is_work_day=1 "
    "ORDER BY assignment_id,work_date"
)
_CASE_FIRST_SERVICE_SELECT_SQL = (
    "SELECT a.generation_id,MIN(ss.work_date) AS first_service_date "
    "FROM case_staff_assignments a JOIN staff_schedule ss "
    "ON ss.assignment_id=a.id AND ss.effective_marker=1 AND ss.is_work_day=1 "
    "WHERE a.generation_id IN ({placeholders}) GROUP BY a.generation_id "
    "ORDER BY a.generation_id"
)
_BUFFER_SELECT_SQL = (
    "SELECT assignment_id,buffer_date FROM scheduling_buffer_days "
    "WHERE assignment_id IN ({placeholders}) "
    "AND status='active' AND active_marker=1 "
    "ORDER BY assignment_id,buffer_date"
)
_OCCUPANCY_SELECT_SQL = (
    "SELECT staff_id,occupancy_date,generation_id,assignment_id,"
    "occupancy_type FROM scheduling_effective_occupancy "
    "WHERE assignment_id IN ({placeholders}) "
    "ORDER BY staff_id,occupancy_date,assignment_id"
)
_WAITING_SEGMENT_SELECT_SQL = (
    "SELECT l.id AS lock_id,s.id AS segment_id,p.case_no,s.staff_id,"
    "s.assigned_start_date,s.assigned_end_date "
    "FROM caregiver_availability_locks l "
    "JOIN caregiver_matching_plans p ON p.id=l.plan_id "
    "JOIN caregiver_matching_plan_segments s ON s.plan_id=p.id "
    "WHERE l.status='active' AND l.is_active=1 AND s.staff_id=%s "
    "AND s.assigned_start_date<=%s "
    "AND DATE_ADD(s.assigned_end_date,INTERVAL 7 DAY)>=%s "
    "ORDER BY l.id,s.id"
)


__all__ = ["MySqlSchedulingCurrentProjectionRepository"]
