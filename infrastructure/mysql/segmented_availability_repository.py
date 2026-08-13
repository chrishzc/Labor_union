"""MySQL read adapter for Scheduling availability facts."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, Callable, Protocol


class SegmentedAvailabilityFactsPort(Protocol):
    def load_case_facts(self, case_no: str) -> dict[str, Any]: ...


class MySqlSegmentedAvailabilityFactsRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    def load_case_facts(self, case_no: str) -> dict[str, Any]:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            order = self._load_order(cursor, case_no)
            if not order or order["status"] != "洽談中":
                return {"order": order}
            return self._load_negotiation_facts(cursor, order)
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def _load_order(self, cursor: Any, case_no: str) -> dict[str, Any] | None:
        cursor.execute(
            "SELECT o.case_no, o.status, o.start_date, o.end_date,"
            "o.service_days,o.service_hours_per_day,o.requires_cooking,c.city,c.address,"
            "COALESCE(g.aggregate_version, 0) AS scheduling_version "
            "FROM orders o JOIN clients c ON c.id=o.client_id "
            "LEFT JOIN scheduling_aggregates g ON g.case_no=o.case_no "
            "WHERE o.case_no = %s",
            (case_no,),
        )
        return cursor.fetchone()

    def _load_negotiation_facts(self, cursor: Any, order: dict[str, Any]) -> dict[str, Any]:
        window_start, window_end = _availability_window(order)
        return {
            "order": order,
            "confirmed_service_dates": self._load_confirmed_service_dates(cursor, order["case_no"]),
            "staff_rows": self._load_active_staff(cursor),
            "assignments": self._load_assignments(cursor, window_start, window_end),
            "schedule_rows": self._load_assignment_schedule_rows(cursor, window_start, window_end),
            "legacy_schedule_rows": self._load_legacy_schedule_rows(cursor, window_start, window_end),
            "buffer_rows": self._load_buffer_rows(cursor, window_start, window_end),
            "active_lock_rows": self._load_active_lock_rows(cursor, window_start, window_end),
            "waiting_buffer_rows": self._load_waiting_buffer_rows(cursor, window_start, window_end),
            "staff_unavailability_rows": self._load_staff_unavailability_rows(
                cursor, window_start, window_end
            ),
        }

    def _load_confirmed_service_dates(self, cursor: Any, case_no: str) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT d.service_date FROM confirmed_service_date_versions v "
            "JOIN confirmed_service_date_days d ON d.confirmed_version_id=v.id "
            "WHERE v.case_no=%s AND v.is_current=1 ORDER BY d.ordinal",
            (case_no,),
        )
        return cursor.fetchall() or []

    def _load_active_staff(self, cursor: Any) -> list[dict[str, Any]]:
        cursor.execute("SELECT id,name FROM staff WHERE status='active' ORDER BY id")
        staff_rows = cursor.fetchall() or []
        by_id = {int(row["id"]): row for row in staff_rows}
        _attach_grouped_rows(cursor, by_id, "staff_regions", "region_name", "regions")
        _attach_grouped_rows(
            cursor, by_id, "staff_cooking_skills", "skill_name", "cooking_skills"
        )
        cursor.execute(
            "SELECT v.staff_id,d.preference_key,d.order_fact_key,"
            "d.comparison_operator,v.value_json FROM staff_matching_preference_values v "
            "JOIN staff_matching_preference_definitions d ON d.id=v.definition_id "
            "WHERE d.status='active' AND d.is_filterable=1"
        )
        for value_row in cursor.fetchall() or []:
            staff = by_id.get(int(value_row["staff_id"]))
            if staff is None:
                continue
            preferences = staff.setdefault("matching_preferences", {})
            preferences[str(value_row["preference_key"])] = {
                "comparison_operator": str(value_row["comparison_operator"]),
                "order_fact_key": str(value_row["order_fact_key"]),
                "value": _json_object(value_row["value_json"]),
            }
        return staff_rows

    def _load_assignments(self, cursor: Any, window_start: str, window_end: str) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT id, staff_id, assigned_start_date, assigned_end_date FROM case_staff_assignments "
            "WHERE (status IS NULL OR status <> 'cancelled') AND assigned_start_date <= %s AND assigned_end_date >= %s",
            (window_end, window_start),
        )
        return cursor.fetchall() or []

    def _load_assignment_schedule_rows(self, cursor: Any, window_start: str, window_end: str) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT s.assignment_id, s.staff_id, s.work_date FROM staff_schedule s "
            "INNER JOIN case_staff_assignments a ON a.id = s.assignment_id "
            "WHERE s.assignment_id IS NOT NULL AND s.work_date BETWEEN %s AND %s "
            "AND (a.status IS NULL OR a.status <> 'cancelled')",
            (window_start, window_end),
        )
        return cursor.fetchall() or []

    def _load_legacy_schedule_rows(self, cursor: Any, window_start: str, window_end: str) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT staff_id, work_date FROM staff_schedule "
            "WHERE assignment_id IS NULL AND work_date BETWEEN %s AND %s",
            (window_start, window_end),
        )
        return cursor.fetchall() or []

    def _load_buffer_rows(self, cursor: Any, window_start: str, window_end: str) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT assignment_id, staff_id, buffer_date FROM scheduling_buffer_days "
            "WHERE status = 'active' AND active_marker = 1 AND buffer_date BETWEEN %s AND %s",
            (window_start, window_end),
        )
        return cursor.fetchall() or []

    def _load_active_lock_rows(self, cursor: Any, window_start: str, window_end: str) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT d.staff_id, d.lock_date, d.active_marker FROM caregiver_availability_lock_days d "
            "INNER JOIN caregiver_availability_locks h ON h.id = d.lock_id "
            "WHERE h.status = 'active' AND h.is_active = 1 AND d.lock_date BETWEEN %s AND %s",
            (window_start, window_end),
        )
        return cursor.fetchall() or []

    def _load_waiting_buffer_rows(self, cursor: Any, window_start: str, window_end: str) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT segment.id AS segment_id, segment.staff_id, segment.assigned_start_date, segment.assigned_end_date "
            "FROM caregiver_matching_plan_segments segment "
            "INNER JOIN caregiver_availability_locks header ON header.plan_id = segment.plan_id "
            "WHERE header.status = 'active' AND header.is_active = 1 "
            "AND segment.assigned_end_date < %s AND DATE_ADD(segment.assigned_end_date, INTERVAL 7 DAY) >= %s",
            (window_end, window_start),
        )
        return cursor.fetchall() or []

    def _load_staff_unavailability_rows(
        self, cursor: Any, window_start: str, window_end: str
    ) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT id,staff_id,start_date,end_date FROM "
            "scheduling_staff_unavailability_blocks "
            "WHERE status='effective' AND start_date<=%s "
            "AND (end_date IS NULL OR end_date>=%s)",
            (window_end, window_start),
        )
        return cursor.fetchall() or []


def _availability_window(order: dict[str, Any]) -> tuple[str, str]:
    return _as_date(order["start_date"]).isoformat(), _as_date(order["end_date"]).isoformat()


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _attach_grouped_rows(cursor, staff_by_id, table, value_column, target_key):
    cursor.execute(f"SELECT staff_id,{value_column} FROM {table}")
    for row in cursor.fetchall() or []:
        staff = staff_by_id.get(int(row["staff_id"]))
        if staff is not None:
            staff.setdefault(target_key, []).append(str(row[value_column]))


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("staff_matching_preference_value_invalid")
    return parsed
