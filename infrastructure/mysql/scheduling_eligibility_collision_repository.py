"""
File: scheduling_eligibility_collision_repository.py
Description: 以 MySQL 唯讀載入 Scheduling eligibility/collision projection 所需根事實。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import json
from typing import Any

from subsystems.scheduling.eligibility_collision_query import (
    SchedulingAssignmentFact,
    SchedulingBufferFact,
    SchedulingCaseFacts,
    SchedulingEligibilityCollisionFacts,
    SchedulingEligibilityCollisionQuery,
    SchedulingLockFact,
    SchedulingPreferenceFact,
    SchedulingScheduleFact,
    SchedulingStaffFacts,
    SchedulingUnavailabilityFact,
)


class MySqlSchedulingEligibilityCollisionRepository:
    """Load only current Scheduling facts; this adapter never commits or writes."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_facts(
        self, request: SchedulingEligibilityCollisionQuery
    ) -> SchedulingEligibilityCollisionFacts:
        cursor = self._connection.cursor()
        try:
            case = self._load_case(cursor, request.case_no)
            if case is None:
                return SchedulingEligibilityCollisionFacts(None, ())
            staff = self._load_staff(cursor, request.staff_id)
            staff_ids = tuple(item.staff_id for item in staff)
            if not staff_ids:
                return SchedulingEligibilityCollisionFacts(case, ())
            window = _query_window(case)
            assignments = self._load_assignments(cursor, window, staff_ids)
            schedules = self._load_schedules(cursor, window, staff_ids)
            buffers = self._load_buffers(cursor, window, staff_ids)
            locks = self._load_locks(cursor, window, staff_ids)
            unavailability = self._load_unavailability(cursor, window, staff_ids)
            self._attach_staff_collections(cursor, staff)
            return SchedulingEligibilityCollisionFacts(
                case=case,
                staff=tuple(staff),
                assignments=tuple(assignments),
                schedules=tuple(schedules),
                buffers=tuple(buffers),
                locks=tuple(locks),
                unavailability=tuple(unavailability),
            )
        finally:
            cursor.close()

    @staticmethod
    def _load_case(cursor: Any, case_no: str) -> SchedulingCaseFacts | None:
        cursor.execute(
            "SELECT o.case_no,o.status,o.start_date,o.end_date,o.service_days,"
            "o.service_hours_per_day,o.requires_cooking,"
            "NULLIF(TRIM(CONCAT_WS(' / ',c.city,c.address)),'') AS location_text,"
            "COALESCE(g.aggregate_version,0) AS scheduling_version "
            "FROM orders o JOIN clients c ON c.id=o.client_id "
            "LEFT JOIN scheduling_aggregates g ON g.case_no=o.case_no "
            "WHERE o.case_no=%s",
            (case_no,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return SchedulingCaseFacts(
            case_no=str(row["case_no"]),
            status=str(row.get("status") or ""),
            start_date=_as_date(row.get("start_date")),
            end_date=_as_date(row.get("end_date")),
            service_days=_as_optional_int(row.get("service_days")),
            service_hours_per_day=_as_optional_int(row.get("service_hours_per_day")),
            requires_cooking=_as_optional_bool(row.get("requires_cooking")),
            location_text=_as_optional_text(row.get("location_text")),
            scheduling_version=_as_optional_int(row.get("scheduling_version")),
        )

    @staticmethod
    def _load_staff(cursor: Any, staff_id: int | None) -> list[SchedulingStaffFacts]:
        sql = (
            "SELECT s.id,s.status,COALESCE(l.lifecycle_state,'active') AS lifecycle_state "
            "FROM staff s LEFT JOIN staff_lifecycle_states l ON l.staff_id=s.id "
        )
        parameters: tuple[Any, ...] = ()
        if staff_id is not None:
            sql += "WHERE s.id=%s "
            parameters = (staff_id,)
        sql += "ORDER BY s.id"
        cursor.execute(sql, parameters)
        return [
            SchedulingStaffFacts(
                staff_id=int(row["id"]),
                status=_as_optional_text(row.get("status")),
                lifecycle_state=_as_optional_text(row.get("lifecycle_state")),
            )
            for row in (cursor.fetchall() or [])
        ]

    def _attach_staff_collections(
        self, cursor: Any, staff: list[SchedulingStaffFacts]
    ) -> None:
        by_id = {item.staff_id: item for item in staff}
        staff_ids = tuple(by_id)
        placeholders = _placeholders(staff_ids)
        regions: dict[int, list[str]] = {staff_id: [] for staff_id in staff_ids}
        cursor.execute(
            f"SELECT staff_id,region_name FROM staff_regions WHERE staff_id IN ({placeholders}) "
            "ORDER BY staff_id,region_name",
            staff_ids,
        )
        for row in cursor.fetchall() or []:
            staff_item = by_id.get(int(row["staff_id"]))
            if staff_item is not None and row.get("region_name") is not None:
                regions[staff_item.staff_id].append(str(row["region_name"]))

        cooking: dict[int, list[str]] = {staff_id: [] for staff_id in staff_ids}
        cursor.execute(
            f"SELECT staff_id,skill_name FROM staff_cooking_skills WHERE staff_id IN ({placeholders}) "
            "ORDER BY staff_id,skill_name",
            staff_ids,
        )
        for row in cursor.fetchall() or []:
            staff_item = by_id.get(int(row["staff_id"]))
            if staff_item is not None and row.get("skill_name") is not None:
                cooking[staff_item.staff_id].append(str(row["skill_name"]))

        preferences: dict[int, list[SchedulingPreferenceFact]] = {
            staff_id: [] for staff_id in staff_ids
        }
        cursor.execute(
            "SELECT v.staff_id,d.preference_key,d.order_fact_key,d.comparison_operator,"
            "v.value_json,p.version AS profile_version "
            "FROM staff_matching_preference_values v "
            "JOIN staff_matching_preference_definitions d ON d.id=v.definition_id "
            "LEFT JOIN staff_matching_preference_profiles p ON p.staff_id=v.staff_id "
            f"WHERE d.status='active' AND d.is_filterable=1 AND v.staff_id IN ({placeholders}) "
            "ORDER BY v.staff_id,d.preference_key",
            staff_ids,
        )
        for row in cursor.fetchall() or []:
            staff_item = by_id.get(int(row["staff_id"]))
            if staff_item is None:
                continue
            preferences[staff_item.staff_id].append(
                SchedulingPreferenceFact(
                    preference_key=str(row["preference_key"]),
                    order_fact_key=_as_optional_text(row.get("order_fact_key")),
                    comparison_operator=str(row["comparison_operator"]),
                    value=_json_object(row.get("value_json")),
                    source_version=_as_optional_int(row.get("profile_version")),
                )
            )

        for index, item in enumerate(staff):
            staff[index] = SchedulingStaffFacts(
                staff_id=item.staff_id,
                status=item.status,
                lifecycle_state=item.lifecycle_state,
                regions=tuple(regions[item.staff_id]),
                cooking_skills=tuple(cooking[item.staff_id]),
                preferences=tuple(preferences[item.staff_id]),
            )

    @staticmethod
    def _load_assignments(
        cursor: Any,
        window: tuple[date, date] | None,
        staff_ids: tuple[int, ...],
    ) -> list[SchedulingAssignmentFact]:
        if window is None:
            return []
        placeholders = _placeholders(staff_ids)
        cursor.execute(
            "SELECT a.id,a.case_no,a.staff_id,a.assigned_start_date,a.assigned_end_date "
            "FROM case_staff_assignments a "
            "LEFT JOIN scheduling_generations g ON g.id=a.generation_id "
            f"WHERE a.staff_id IN ({placeholders}) "
            "AND a.status NOT IN ('cancelled','replaced') "
            "AND (a.generation_id IS NULL OR (g.status='effective' AND g.effective_marker=1)) "
            "AND (a.assigned_start_date IS NULL OR a.assigned_end_date IS NULL "
            "OR a.assigned_start_date>a.assigned_end_date "
            "OR (a.assigned_start_date<=%s AND a.assigned_end_date>=%s)) "
            "ORDER BY a.staff_id,a.assigned_start_date,a.id",
            (*staff_ids, window[1], window[0]),
        )
        return [
            SchedulingAssignmentFact(
                assignment_id=int(row["id"]),
                case_no=str(row["case_no"]),
                staff_id=int(row["staff_id"]),
                start_date=_as_date(row.get("assigned_start_date")),
                end_date=_as_date(row.get("assigned_end_date")),
            )
            for row in (cursor.fetchall() or [])
        ]

    @staticmethod
    def _load_schedules(
        cursor: Any,
        window: tuple[date, date] | None,
        staff_ids: tuple[int, ...],
    ) -> list[SchedulingScheduleFact]:
        if window is None:
            return []
        placeholders = _placeholders(staff_ids)
        cursor.execute(
            "SELECT s.id,s.case_no,s.assignment_id,s.staff_id,s.work_date,"
            "s.is_work_day,COALESCE(s.effective_marker,1) AS effective_marker "
            f"FROM staff_schedule s WHERE s.staff_id IN ({placeholders}) "
            "AND (s.work_date IS NULL OR s.work_date BETWEEN %s AND %s) "
            "ORDER BY s.staff_id,s.work_date,s.id",
            (*staff_ids, window[0], window[1]),
        )
        return [
            SchedulingScheduleFact(
                schedule_id=int(row["id"]),
                case_no=_as_optional_text(row.get("case_no")),
                assignment_id=_as_optional_int(row.get("assignment_id")),
                staff_id=int(row["staff_id"]),
                work_date=_as_date(row.get("work_date")),
                is_work_day=bool(row.get("is_work_day")),
                effective=bool(row.get("effective_marker")),
            )
            for row in (cursor.fetchall() or [])
        ]

    @staticmethod
    def _load_buffers(
        cursor: Any,
        window: tuple[date, date] | None,
        staff_ids: tuple[int, ...],
    ) -> list[SchedulingBufferFact]:
        if window is None:
            return []
        placeholders = _placeholders(staff_ids)
        cursor.execute(
            "SELECT b.id,b.assignment_id,b.staff_id,b.buffer_date,a.case_no "
            "FROM scheduling_buffer_days b LEFT JOIN case_staff_assignments a "
            "ON a.id=b.assignment_id "
            f"WHERE b.staff_id IN ({placeholders}) AND b.status='active' "
            "AND b.active_marker=1 "
            "AND (b.buffer_date IS NULL OR b.buffer_date BETWEEN %s AND %s) "
            "ORDER BY b.staff_id,b.buffer_date,b.id",
            (*staff_ids, window[0], window[1]),
        )
        return [
            SchedulingBufferFact(
                buffer_id=int(row["id"]),
                assignment_id=_as_optional_int(row.get("assignment_id")),
                case_no=_as_optional_text(row.get("case_no")),
                staff_id=int(row["staff_id"]),
                buffer_date=_as_date(row.get("buffer_date")),
            )
            for row in (cursor.fetchall() or [])
        ]

    @staticmethod
    def _load_locks(
        cursor: Any,
        window: tuple[date, date] | None,
        staff_ids: tuple[int, ...],
    ) -> list[SchedulingLockFact]:
        if window is None:
            return []
        placeholders = _placeholders(staff_ids)
        cursor.execute(
            "SELECT d.id AS lock_day_id,l.id AS lock_id,d.segment_id,p.case_no,"
            "d.staff_id,d.lock_date "
            "FROM caregiver_availability_lock_days d "
            "JOIN caregiver_availability_locks l ON l.id=d.lock_id "
            "LEFT JOIN caregiver_matching_plan_segments segment ON segment.id=d.segment_id "
            "LEFT JOIN caregiver_matching_plans p ON p.id=segment.plan_id "
            f"WHERE d.staff_id IN ({placeholders}) AND l.status='active' AND l.is_active=1 "
            "AND d.active_marker=1 "
            "AND (d.lock_date IS NULL OR d.lock_date BETWEEN %s AND %s) "
            "ORDER BY d.staff_id,d.lock_date,d.id",
            (*staff_ids, window[0], window[1]),
        )
        return [
            SchedulingLockFact(
                lock_day_id=int(row["lock_day_id"]),
                lock_id=int(row["lock_id"]),
                segment_id=_as_optional_int(row.get("segment_id")),
                case_no=_as_optional_text(row.get("case_no")),
                staff_id=int(row["staff_id"]),
                lock_date=_as_date(row.get("lock_date")),
            )
            for row in (cursor.fetchall() or [])
        ]

    @staticmethod
    def _load_unavailability(
        cursor: Any,
        window: tuple[date, date] | None,
        staff_ids: tuple[int, ...],
    ) -> list[SchedulingUnavailabilityFact]:
        if window is None:
            return []
        placeholders = _placeholders(staff_ids)
        cursor.execute(
            "SELECT id,staff_id,block_kind,start_date,end_date "
            f"FROM scheduling_staff_unavailability_blocks "
            f"WHERE staff_id IN ({placeholders}) AND status='effective' "
            "AND (start_date IS NULL "
            "OR (start_date<=%s AND (end_date IS NULL OR end_date>=%s)) "
            "OR (end_date IS NOT NULL AND end_date<start_date)) "
            "ORDER BY staff_id,start_date,id",
            (*staff_ids, window[1], window[0]),
        )
        return [
            SchedulingUnavailabilityFact(
                block_id=int(row["id"]),
                staff_id=int(row["staff_id"]),
                kind=str(row["block_kind"]),
                start_date=_as_date(row.get("start_date")),
                end_date=_as_date(row.get("end_date")),
            )
            for row in (cursor.fetchall() or [])
        ]


def _query_window(case: SchedulingCaseFacts) -> tuple[date, date] | None:
    if type(case.start_date) is not date or type(case.end_date) is not date:
        return None
    if case.start_date > case.end_date:
        return None
    return case.start_date, case.end_date


def _placeholders(values: tuple[int, ...]) -> str:
    return ",".join("%s" for _ in values)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _as_optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_object(value: Any) -> object:
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, Mapping) else {}


__all__ = ["MySqlSchedulingEligibilityCollisionRepository"]
