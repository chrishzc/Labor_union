"""
File: historical_calendar_health_check.py
Description: 以既有歷史 workbook、Orders assignment facts 與 staff monthly calendar read model執行只讀月曆健檢。
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
import pymysql

from domains.orders.historical_adoption import HistoricalOrderSourceStatus
from subsystems.orders.historical_order_workbook import (
    HistoricalOrderWorkbookRow,
    load_historical_order_workbook,
)
from subsystems.scheduling.staff_monthly_calendar_query import (
    get_staff_monthly_calendar_schedule,
)


CATEGORY_DISPLAYABLE = "可顯示"
CATEGORY_MISSING_STAFF = "缺服務人員"
CATEGORY_INVALID_DATES = "缺有效日期"
CATEGORY_MISSING_ASSIGNMENT = "缺已完成指派"
CATEGORY_NOT_DISPLAYABLE = "不應顯示"
CATEGORIES = (
    CATEGORY_DISPLAYABLE,
    CATEGORY_MISSING_STAFF,
    CATEGORY_INVALID_DATES,
    CATEGORY_MISSING_ASSIGNMENT,
    CATEGORY_NOT_DISPLAYABLE,
)

MonthlyReader = Callable[[int, int, int], dict[str, Any]]


def run_historical_calendar_health_check(
    workbook_path: str,
    *,
    sheet: str | None = None,
    connection=None,
    monthly_reader: MonthlyReader = get_staff_monthly_calendar_schedule,
) -> dict[str, object]:
    """Run the #112 five-way historical calendar classification without writes."""

    workbook = load_historical_order_workbook(workbook_path, sheet)
    owned_connection = connection is None
    if connection is None:
        load_dotenv()
        connection = _connect()
    case_nos = tuple(sorted({row.case_no for row in workbook.rows if row.case_no}))
    try:
        before_digest = _root_fact_digest(connection, case_nos)
        rows = tuple(
            _classify_row(connection, row, monthly_reader)
            for row in workbook.rows
        )
        after_digest = _root_fact_digest(connection, case_nos)
    finally:
        if owned_connection:
            connection.close()

    if before_digest != after_digest:
        raise RuntimeError("historical_calendar_health_check_root_facts_changed")

    counts = Counter(str(item["category"]) for item in rows)
    return {
        "status": "read_only",
        "sheet": workbook.sheet_name,
        "source_digest": workbook.content_digest,
        "source_rows": len(rows),
        "category_counts": {category: counts.get(category, 0) for category in CATEGORIES},
        "root_facts_unchanged": True,
        "root_fact_digest": after_digest,
        "rows": rows,
    }


def _classify_row(connection, row: HistoricalOrderWorkbookRow, monthly_reader: MonthlyReader) -> dict[str, object]:
    case_no = row.case_no
    base = {
        "source_row": row.source_row,
        "case_no": case_no,
        "client_name": row.client_name,
        "source_status": None if row.asserted_status is None else row.asserted_status.value,
    }
    if case_no is None:
        return {**base, "category": CATEGORY_NOT_DISPLAYABLE, "reason": "case_no_missing"}
    if row.asserted_status in {HistoricalOrderSourceStatus.CANCELLED, HistoricalOrderSourceStatus.DISCUSSION}:
        return {**base, "category": CATEGORY_NOT_DISPLAYABLE, "reason": "source_status_has_no_historical_service"}
    if _has_precision_restart(connection, case_no):
        return {**base, "category": CATEGORY_NOT_DISPLAYABLE, "reason": "precision_restart_suppresses_historical_assignment"}

    source_staff = tuple(item.name for item in row.caregivers if item.name)
    if not source_staff:
        return {**base, "category": CATEGORY_MISSING_STAFF, "reason": "source_service_person_missing"}
    if not _valid_interval(row.actual_start_date, row.actual_end_date):
        return {**base, "category": CATEGORY_INVALID_DATES, "reason": "source_service_interval_invalid"}

    assignments = _completed_assignments(connection, case_no)
    if not assignments:
        return {
            **base,
            "category": CATEGORY_MISSING_ASSIGNMENT,
            "reason": "completed_assignment_missing",
            "source_staff": list(source_staff),
            "source_start_date": row.actual_start_date.isoformat(),
            "source_end_date": row.actual_end_date.isoformat(),
        }
    if all(item.get("staff_exists") is None for item in assignments):
        return {**base, "category": CATEGORY_MISSING_STAFF, "reason": "completed_assignment_staff_root_missing"}

    valid_assignments = tuple(
        item for item in assignments
        if item.get("staff_exists") is not None
        and _valid_interval(_as_date(item.get("assigned_start_date")), _as_date(item.get("assigned_end_date")))
    )
    if not valid_assignments:
        return {**base, "category": CATEGORY_INVALID_DATES, "reason": "completed_assignment_interval_invalid"}

    observed = next(
        (
            item for item in valid_assignments
            if _monthly_projection_contains_assignment(monthly_reader, case_no, item)
        ),
        None,
    )
    if observed is None:
        raise RuntimeError(f"historical_calendar_monthly_projection_mismatch:{case_no}")

    return {
        **base,
        "category": CATEGORY_DISPLAYABLE,
        "reason": "canonical_monthly_projection_contains_completed_assignment",
        "assignment_id": int(observed["assignment_id"]),
        "staff_id": int(observed["staff_id"]),
        "assigned_start_date": _as_date(observed["assigned_start_date"]).isoformat(),
        "assigned_end_date": _as_date(observed["assigned_end_date"]).isoformat(),
    }


def _monthly_projection_contains_assignment(
    monthly_reader: MonthlyReader,
    case_no: str,
    assignment: dict[str, Any],
) -> bool:
    start = _as_date(assignment.get("assigned_start_date"))
    if start is None:
        return False
    projection = monthly_reader(int(assignment["staff_id"]), start.year, start.month)
    return any(
        day.get("case_no") == case_no
        and day.get("assignment_id") == assignment.get("assignment_id")
        for day in projection.get("days", [])
    )


def _completed_assignments(connection, case_no: str) -> tuple[dict[str, Any], ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT csa.id AS assignment_id,csa.case_no,csa.staff_id,csa.status,
                   csa.assigned_start_date,csa.assigned_end_date,
                   s.id AS staff_exists,s.name AS staff_name
            FROM case_staff_assignments csa
            LEFT JOIN staff s ON s.id=csa.staff_id
            WHERE csa.case_no=%s AND csa.status='completed'
            ORDER BY csa.id
            """,
            (case_no,),
        )
        return tuple(cursor.fetchall())


def _has_precision_restart(connection, case_no: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 AS restarted
            FROM order_lifecycle_state_events
            WHERE case_no=%s AND trigger_event='orders_historical_precision_restart'
            LIMIT 1
            """,
            (case_no,),
        )
        return cursor.fetchone() is not None


def _root_fact_digest(connection, case_nos: tuple[str, ...]) -> str:
    if not case_nos:
        return sha256(b"[]").hexdigest()
    placeholders = ",".join(["%s"] * len(case_nos))
    rows: list[dict[str, Any]] = []
    statements = (
        (
            "orders",
            f"SELECT case_no,status,actual_start_date,actual_end_date FROM orders WHERE case_no IN ({placeholders}) ORDER BY case_no",
        ),
        (
            "assignments",
            f"SELECT id,case_no,staff_id,status,assigned_start_date,assigned_end_date FROM case_staff_assignments WHERE case_no IN ({placeholders}) ORDER BY case_no,id",
        ),
        (
            "schedule",
            f"SELECT ss.id,ss.assignment_id,ss.work_date,ss.is_work_day,ss.is_double_pay,ss.notes FROM staff_schedule ss JOIN case_staff_assignments csa ON csa.id=ss.assignment_id WHERE csa.case_no IN ({placeholders}) ORDER BY csa.case_no,ss.id",
        ),
    )
    with connection.cursor() as cursor:
        for owner, sql in statements:
            cursor.execute(sql, case_nos)
            rows.append({"owner": owner, "rows": tuple(cursor.fetchall())})
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _valid_interval(start: date | None, end: date | None) -> bool:
    return start is not None and end is not None and start <= end


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _connect():
    database = _required_environment("DB_DATABASE")
    return pymysql.connect(
        host=_required_environment("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=_required_environment("DB_USER"),
        password=_required_environment("DB_PASSWORD"),
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"historical_calendar_health_check_{name.casefold()}_required")
    return value


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only historical calendar health check.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--sheet")
    options = parser.parse_args(arguments)
    try:
        result = run_historical_calendar_health_check(str(options.workbook), sheet=options.sheet)
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CATEGORIES", "run_historical_calendar_health_check"]
