"""
File: segmented_availability_repository.py
Description: 讀取分段媒合可用性事實，僅提供 lifecycle active 人員。
"""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, Callable, Protocol

from domains.orders.actual_start import calculate_service_dates
from domains.orders.terms import canonical_service_mode


class SegmentedAvailabilityFactsPort(Protocol):
    def load_case_facts(self, case_no: str) -> dict[str, Any]: ...

    def list_assignment_plan_case_options(
        self, after_case_no: str | None, page_size: int
    ) -> tuple[tuple[dict[str, Any], ...], str | None]: ...


class MySqlSegmentedAvailabilityFactsRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    def load_case_facts(self, case_no: str) -> dict[str, Any]:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            order = self._load_order(cursor, case_no)
            if not order or order["status"] not in {"洽談中", "訂單成立"}:
                return {"order": order}
            return self._load_negotiation_facts(cursor, order)
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def list_assignment_plan_case_options(
        self, after_case_no: str | None, page_size: int
    ) -> tuple[tuple[dict[str, Any], ...], str | None]:
        """List only cases that have the owner facts required by Assignment Plan."""

        cursor_case_no = _case_option_cursor(after_case_no)
        result_limit = _case_option_limit(page_size)
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT o.case_no,o.status AS order_status FROM orders o "
                "WHERE o.case_no>%s AND o.status IN ('洽談中','訂單成立') "
                "AND EXISTS ("
                "SELECT 1 FROM confirmed_service_date_versions v "
                "JOIN confirmed_service_date_days d ON d.confirmed_version_id=v.id "
                "WHERE v.case_no=o.case_no AND v.is_current=1"
                ") ORDER BY o.case_no LIMIT %s",
                (cursor_case_no, result_limit),
            )
            rows = tuple(dict(row) for row in (cursor.fetchall() or ()))
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()
        items = rows[:page_size]
        next_cursor = str(items[-1]["case_no"]) if len(rows) > page_size else None
        return items, next_cursor

    def _load_order(self, cursor: Any, case_no: str) -> dict[str, Any] | None:
        cursor.execute(
            "SELECT o.case_no, o.status, o.start_date, o.end_date,"
            "o.service_days,o.service_hours_per_day,o.requires_cooking,o.custom_rest_dates,c.city,c.address,c.service_type,"
            "COALESCE(g.aggregate_version, 0) AS scheduling_version "
            "FROM orders o JOIN clients c ON c.id=o.client_id "
            "LEFT JOIN scheduling_aggregates g ON g.case_no=o.case_no "
            "WHERE o.case_no = %s",
            (case_no,),
        )
        return cursor.fetchone()

    def _load_negotiation_facts(self, cursor: Any, order: dict[str, Any]) -> dict[str, Any]:
        # end_date is an Orders projection, never an extra intake answer.
        # A missing persisted projection must not block the initial inquiry.
        order = dict(order)
        if order.get("end_date") is None:
            mode = canonical_service_mode(order.get("service_type"))
            if mode is None:
                raise ValueError("matching_preference_source_not_ready")
            rest_dates = order.get("custom_rest_dates") or ()
            if isinstance(rest_dates, str):
                rest_dates = json.loads(rest_dates)
            holidays = tuple(sorted({_as_date(value) for value in rest_dates}))
            order["end_date"] = calculate_service_dates(
                _as_date(order["start_date"]), int(order["service_days"]), mode, holidays,
            )[-1]
        confirmed_service_dates = self._load_confirmed_service_dates(cursor, order["case_no"])
        window_start, window_end = _availability_window(order, confirmed_service_dates)
        return {
            "order": dict(order),
            "confirmed_service_dates": confirmed_service_dates,
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
        cursor.execute("SELECT s.id,s.name,s.union_no FROM staff s LEFT JOIN staff_lifecycle_states lifecycle ON lifecycle.staff_id=s.id WHERE s.status='active' AND COALESCE(lifecycle.lifecycle_state,'active')='active' ORDER BY s.id")
        staff_rows = cursor.fetchall() or []
        by_id = {int(row["id"]): row for row in staff_rows}
        _attach_region_rows(cursor, by_id)
        _attach_capability_rows(
            cursor, by_id, "staff_weekly_rest", "rest_type", "custom_rest_detail", "rest_schedule"
        )
        return staff_rows

    def _load_assignments(self, cursor: Any, window_start: str, window_end: str) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT a.id, a.staff_id, a.assigned_start_date, a.assigned_end_date FROM case_staff_assignments a "
            "WHERE (a.status IS NULL OR a.status <> 'cancelled') "
            "AND a.assigned_start_date <= %s AND a.assigned_end_date >= %s "
            "AND NOT (a.generation_id IS NULL AND EXISTS ("
            "SELECT 1 FROM order_lifecycle_state_events restart "
            "WHERE restart.case_no=a.case_no "
            "AND restart.trigger_event='orders_historical_precision_restart'))",
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


def _availability_window(
    order: dict[str, Any], confirmed_service_dates: list[dict[str, Any]] | None = None
) -> tuple[str, str]:
    """Cover both planned bounds and every currently confirmed service date.

    A service-date owner may shift confirmed dates outside the order's original
    planning interval. Availability and assignment conflicts must still be
    read for those dates; otherwise a valid due-shift candidate is silently
    dropped before the typed matching owner can evaluate it.
    """
    starts = [_as_date(order["start_date"]), _as_date(order["end_date"])]
    dates = [
        _as_date(row["service_date"])
        for row in confirmed_service_dates or ()
        if row.get("service_date") is not None
    ]
    bounds = starts + dates
    return min(bounds).isoformat(), max(bounds).isoformat()


def _case_option_cursor(after_case_no: str | None) -> str:
    if after_case_no is None:
        return ""
    if not isinstance(after_case_no, str):
        raise TypeError("after_case_no must be a string or None")
    if not after_case_no or after_case_no.strip() != after_case_no:
        raise ValueError("after_case_no must be canonical")
    if len(after_case_no) > 50:
        raise ValueError("after_case_no exceeds database identity length")
    return after_case_no


def _case_option_limit(page_size: int) -> int:
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise TypeError("page_size must be an integer")
    if not 1 <= page_size <= 200:
        raise ValueError("page_size is outside the bounded query policy")
    return page_size + 1


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


def _attach_capability_rows(cursor, staff_by_id, table, value_column, detail_column, target_key):
    cursor.execute(f"SELECT staff_id,{value_column},{detail_column} FROM {table}")
    for row in cursor.fetchall() or []:
        staff = staff_by_id.get(int(row["staff_id"]))
        if staff is not None:
            value = str(row[value_column])
            if target_key == "service_periods":
                from domains.staff.case_preference_manual import service_period_fields
                period = service_period_fields(value)
                if period["start_time"] is not None:
                    value = f"{period['service_hours']}小時"
            staff.setdefault(target_key, []).append((value, row.get(detail_column)))


def _attach_region_rows(cursor, staff_by_id):
    cursor.execute("SELECT staff_id,region_name,custom_region_detail FROM staff_regions")
    for row in cursor.fetchall() or []:
        staff = staff_by_id.get(int(row["staff_id"]))
        if staff is None:
            continue
        region_name = str(row["region_name"])
        custom_detail = row.get("custom_region_detail")
        if region_name == "其他" and custom_detail:
            region_name = str(custom_detail)
        staff.setdefault("regions", []).append(region_name)


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("staff_matching_preference_value_invalid")
    return parsed
