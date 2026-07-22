"""Read one formal caregiver assignment and only its owned schedule days."""

from __future__ import annotations

from typing import Any

from services.db_service import get_connection


def _validate_assignment_id(assignment_id: Any) -> int:
    if isinstance(assignment_id, bool) or not isinstance(assignment_id, int) or assignment_id < 1:
        raise ValueError("assignment_id must be a positive integer")
    return assignment_id


def _validate_case_no(case_no: Any) -> str:
    if not isinstance(case_no, str) or not case_no.strip():
        raise ValueError("case_no must be a non-empty string")
    return case_no.strip()


def list_case_schedule_assignments(case_no: str) -> dict[str, Any]:
    """List selectable, non-cancelled formal assignments for one chosen case."""

    case_no = _validate_case_no(case_no)
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.id, a.case_no, a.staff_id, a.status,
                          a.assigned_start_date, a.assigned_end_date,
                          a.actual_hours, o.service_hours_per_day,
                          s.name AS staff_name
                     FROM case_staff_assignments a
                     JOIN orders o ON o.case_no = a.case_no
                     JOIN staff s ON s.id = a.staff_id
                    WHERE a.case_no = %s AND a.status <> 'cancelled'
                    ORDER BY a.assigned_start_date ASC, a.id ASC""",
                (case_no,),
            )
            assignments = cursor.fetchall()
        return {"assignments": assignments}
    finally:
        connection.close()


def get_assignment_schedule(assignment_id: int) -> dict[str, Any]:
    """Return only the daily schedule rows owned by one explicit assignment.

    The query deliberately does not use ``orders.staff_id`` or a date-based
    fallback. Legacy rows without an assignment relation remain outside this
    read model until an administrator explicitly reviews them.
    """

    assignment_id = _validate_assignment_id(assignment_id)
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.id, a.case_no, a.staff_id, a.status,
                          a.assigned_start_date, a.assigned_end_date,
                          a.planned_hours, a.actual_hours,
                          o.service_hours_per_day,
                          s.name AS staff_name, c.name AS client_name
                     FROM case_staff_assignments a
                     JOIN orders o ON o.case_no = a.case_no
                     JOIN staff s ON s.id = a.staff_id
                     JOIN clients c ON c.id = o.client_id
                    WHERE a.id = %s""",
                (assignment_id,),
            )
            assignment = cursor.fetchone()
            if assignment is None:
                raise ValueError("assignment does not exist")

            cursor.execute(
                """SELECT id, case_no, staff_id, assignment_id, work_date,
                          is_work_day, is_double_pay, notes
                     FROM staff_schedule
                    WHERE assignment_id = %s
                    ORDER BY work_date ASC""",
                (assignment_id,),
            )
            schedule_days = cursor.fetchall()
            for schedule_day in schedule_days:
                if schedule_day.get("assignment_id") != assignment_id:
                    raise ValueError("schedule day does not belong to assignment")

        return {"assignment": assignment, "schedule_days": schedule_days}
    finally:
        connection.close()
