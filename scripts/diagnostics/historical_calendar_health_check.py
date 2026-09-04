"""
File: historical_calendar_health_check.py
Description: 以 historical workbook 與 current monthly calendar reads 執行可重跑的只讀五類健檢。
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
from typing import Callable

from domains.orders.historical_adoption import HistoricalOrderSourceStatus
from infrastructure.mysql.mysql_adapter import get_connection as mysql_get_connection
from subsystems.orders.historical_order_workbook import (
    HistoricalCaregiverSource,
    HistoricalOrderWorkbookRow,
    load_historical_order_workbook,
)
from subsystems.scheduling import staff_monthly_calendar_query


VISIBLE = "可顯示"
MISSING_STAFF = "缺服務人員"
MISSING_DATES = "缺有效日期"
MISSING_COMPLETED_ASSIGNMENT = "缺已完成指派"
SHOULD_NOT_DISPLAY = "不應顯示"
CLASSIFICATIONS = (
    VISIBLE,
    MISSING_STAFF,
    MISSING_DATES,
    MISSING_COMPLETED_ASSIGNMENT,
    SHOULD_NOT_DISPLAY,
)

ConnectionFactory = Callable[[], object]
MonthlyQuery = Callable[..., dict[str, object]]


def historical_calendar_health_check(
    workbook_path: str | Path,
    *,
    connection_factory: ConnectionFactory = mysql_get_connection,
    monthly_query: MonthlyQuery = staff_monthly_calendar_query.get_staff_monthly_calendar_schedule,
) -> dict[str, object]:
    """Classify each workbook row using current read facts without issuing writes."""

    workbook = load_historical_order_workbook(workbook_path)
    previous_connection_factory = staff_monthly_calendar_query.get_connection
    staff_monthly_calendar_query.get_connection = connection_factory
    connection = connection_factory()
    try:
        rows = tuple(
            _classify_row(connection, row, monthly_query)
            for row in workbook.rows
        )
    finally:
        connection.close()
        staff_monthly_calendar_query.get_connection = previous_connection_factory

    counts = Counter(item["classification"] for item in rows)
    return {
        "source": str(workbook_path),
        "source_rows": len(rows),
        "classification_counts": {
            classification: counts.get(classification, 0)
            for classification in CLASSIFICATIONS
        },
        "rows": rows,
    }


def _classify_row(
    connection,
    row: HistoricalOrderWorkbookRow,
    monthly_query: MonthlyQuery,
) -> dict[str, object]:
    if row.asserted_status is not HistoricalOrderSourceStatus.DEPOSIT_PAID:
        return _result(row, SHOULD_NOT_DISPLAY, "source_status_not_deposit_paid")
    if not row.case_no:
        return _result(row, SHOULD_NOT_DISPLAY, "source_case_no_missing")
    if not row.caregivers or any(not caregiver.name for caregiver in row.caregivers):
        return _result(row, MISSING_STAFF, "source_staff_missing")
    if any(not _valid_interval(caregiver) for caregiver in row.caregivers):
        return _result(row, MISSING_DATES, "source_service_interval_invalid")

    resolved_staff: list[tuple[HistoricalCaregiverSource, int]] = []
    for caregiver in row.caregivers:
        staff_rows = _staff_rows(connection, caregiver.name or "")
        if len(staff_rows) != 1:
            reason = "canonical_staff_missing" if not staff_rows else "canonical_staff_name_not_unique"
            return _result(row, MISSING_STAFF, reason)
        resolved_staff.append((caregiver, int(staff_rows[0]["id"])))

    assignment_ids: dict[int, set[int]] = {}
    for caregiver, staff_id in resolved_staff:
        assignments = _completed_assignments(connection, row.case_no, staff_id)
        if not assignments:
            return _result(row, MISSING_COMPLETED_ASSIGNMENT, "completed_assignment_missing")
        assignment_ids[staff_id] = {int(item["id"]) for item in assignments}

    for caregiver, staff_id in resolved_staff:
        if not _visible_under_current_monthly_semantics(
            monthly_query,
            row.case_no,
            staff_id,
            caregiver.start_date,
            caregiver.end_date,
            assignment_ids[staff_id],
        ):
            return _result(row, SHOULD_NOT_DISPLAY, "current_monthly_semantics_exclude_historical_assignment")

    return _result(row, VISIBLE, "current_monthly_projection_visible")


def _valid_interval(caregiver: HistoricalCaregiverSource) -> bool:
    if caregiver.start_date is None or caregiver.end_date is None:
        return False
    if caregiver.start_date > caregiver.end_date:
        return False
    return not any(
        code.endswith("_date_invalid") or code.endswith("_date_range_invalid")
        for code in caregiver.issue_codes
    )


def _staff_rows(connection, staff_name: str) -> tuple[dict[str, object], ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,name FROM staff WHERE name=%s ORDER BY id",
            (staff_name,),
        )
        return tuple(cursor.fetchall())


def _completed_assignments(
    connection,
    case_no: str,
    staff_id: int,
) -> tuple[dict[str, object], ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,assigned_start_date,assigned_end_date "
            "FROM case_staff_assignments "
            "WHERE case_no=%s AND staff_id=%s AND status='completed' "
            "ORDER BY id",
            (case_no, staff_id),
        )
        return tuple(cursor.fetchall())


def _visible_under_current_monthly_semantics(
    monthly_query: MonthlyQuery,
    case_no: str,
    staff_id: int,
    start_date: date | None,
    end_date: date | None,
    assignment_ids: set[int],
) -> bool:
    if start_date is None or end_date is None:
        return False
    for year, month in _months_between(start_date, end_date):
        projection = monthly_query(staff_id, year, month)
        if not any(
            item.get("status") == "historical_assignment"
            and str(item.get("case_no")) == case_no
            and item.get("assignment_id") in assignment_ids
            for item in projection.get("days", ())
        ):
            return False
    return True


def _months_between(start_date: date, end_date: date) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        result.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return tuple(result)


def _result(
    row: HistoricalOrderWorkbookRow,
    classification: str,
    reason: str,
) -> dict[str, object]:
    return {
        "source_row": row.source_row,
        "case_no": row.case_no,
        "classification": classification,
        "reason": reason,
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only historical calendar health check."
    )
    parser.add_argument(
        "workbook",
        nargs="?",
        default="document/資料庫、資料處理/假資料_歷史訂單.xlsx",
    )
    options = parser.parse_args(arguments)
    try:
        result = historical_calendar_health_check(options.workbook)
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CLASSIFICATIONS", "historical_calendar_health_check"]
