"""Adjust one formal caregiver assignment's existing daily schedule row."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from services.db_service import get_connection


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("work_date must be an ISO date") from exc
    raise ValueError("work_date must be an ISO date")


def _validate_request(
    assignment_id: Any,
    work_date: Any,
    is_work_day: Any,
    is_double_pay: Any,
    notes: Any,
) -> tuple[int, date, bool, bool, str | None]:
    if isinstance(assignment_id, bool) or not isinstance(assignment_id, int) or assignment_id < 1:
        raise ValueError("assignment_id must be a positive integer")
    if not isinstance(is_work_day, bool):
        raise ValueError("is_work_day must be a boolean")
    if not isinstance(is_double_pay, bool):
        raise ValueError("is_double_pay must be a boolean")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("notes must be a string or None")
    if isinstance(notes, str) and len(notes) > 255:
        raise ValueError("notes must be at most 255 characters")
    return assignment_id, _as_date(work_date), is_work_day, is_double_pay, notes


def adjust_assignment_schedule_day(
    assignment_id: int,
    work_date: date | str,
    is_work_day: bool,
    is_double_pay: bool,
    notes: str | None,
) -> dict[str, Any]:
    """Update one existing assigned day and recompute only that assignment's hours.

    The lock order is assignment/order, payment and settlement snapshots, target
    schedule row, then all schedule rows for the assignment.  No schedule rows
    are created, deleted, or reassigned by this operation.
    """
    assignment_id, target_date, is_work_day, is_double_pay, notes = _validate_request(
        assignment_id, work_date, is_work_day, is_double_pay, notes
    )

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.id, a.case_no, a.staff_id, a.assigned_start_date,
                          a.assigned_end_date, a.status, o.service_hours_per_day
                   FROM case_staff_assignments a
                   JOIN orders o ON o.case_no = a.case_no
                   WHERE a.id = %s FOR UPDATE""",
                (assignment_id,),
            )
            assignment = cursor.fetchone()
            if not assignment:
                raise ValueError("assignment does not exist")
            if assignment["status"] == "cancelled":
                raise ValueError("cancelled assignment cannot be adjusted")

            start_date = assignment.get("assigned_start_date")
            end_date = assignment.get("assigned_end_date")
            if start_date is None or end_date is None:
                raise ValueError("assignment date range is incomplete")
            start_date = _as_date(start_date)
            end_date = _as_date(end_date)
            if not start_date <= target_date <= end_date:
                raise ValueError("work_date is outside the assignment date range")

            cursor.execute(
                """SELECT id FROM staff_payments
                   WHERE assignment_id = %s AND payment_status <> 'cancelled'
                   LIMIT 1 FOR UPDATE""",
                (assignment_id,),
            )
            if cursor.fetchone():
                raise ValueError("assignment with an active staff payment cannot be adjusted")

            cursor.execute(
                """SELECT smsd.id
                   FROM staff_monthly_settlement_details smsd
                   JOIN staff_monthly_settlements sms ON sms.id = smsd.settlement_id
                   WHERE smsd.assignment_id = %s AND sms.status <> 'cancelled'
                   LIMIT 1 FOR UPDATE""",
                (assignment_id,),
            )
            if cursor.fetchone():
                raise ValueError("assignment in an active monthly settlement cannot be adjusted")

            cursor.execute(
                """SELECT id, case_no, staff_id, assignment_id, work_date,
                          is_work_day, is_double_pay, notes
                   FROM staff_schedule
                   WHERE staff_id = %s AND work_date = %s FOR UPDATE""",
                (assignment["staff_id"], target_date),
            )
            schedule_day = cursor.fetchone()
            if not schedule_day:
                raise ValueError("assignment schedule day does not exist")
            if schedule_day.get("assignment_id") != assignment_id:
                raise ValueError("schedule day belongs to another assignment or requires review")
            if schedule_day.get("case_no") != assignment["case_no"]:
                raise ValueError("schedule day case does not match assignment")

            daily_hours = Decimal(str(assignment["service_hours_per_day"]))
            if daily_hours <= 0:
                raise ValueError("service_hours_per_day must be positive")

            cursor.execute(
                """UPDATE staff_schedule
                   SET is_work_day = %s, is_double_pay = %s, notes = %s
                   WHERE id = %s AND assignment_id = %s""",
                (is_work_day, is_double_pay, notes, schedule_day["id"], assignment_id),
            )

            cursor.execute(
                """SELECT id, is_work_day
                   FROM staff_schedule
                   WHERE assignment_id = %s FOR UPDATE""",
                (assignment_id,),
            )
            assignment_days = cursor.fetchall()
            actual_hours = sum(
                (1 for row in assignment_days if bool(row.get("is_work_day"))),
                0,
            ) * daily_hours
            cursor.execute(
                "UPDATE case_staff_assignments SET actual_hours = %s WHERE id = %s",
                (actual_hours, assignment_id),
            )

        connection.commit()
        return {
            "adjusted_schedule_day": {
                **schedule_day,
                "is_work_day": is_work_day,
                "is_double_pay": is_double_pay,
                "notes": notes,
            },
            "actual_hours": actual_hours,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
