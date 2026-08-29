"""Read-only MySQL adapter for Scheduling multi-caregiver projections."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from subsystems.scheduling.multi_caregiver_schedule_query import (
    AssignmentScheduleAssignment,
    AssignmentScheduleDay,
    AssignmentScheduleGuard,
    AssignmentScheduleQuery,
    CaseAssignment,
    MultiCaregiverScheduleQueryRepository,
    StaffAssignmentOption,
    build_case_assignment,
)


class MySqlMultiCaregiverScheduleQueryRepository(MultiCaregiverScheduleQueryRepository):
    """Borrow the request connection; never close it or control its transaction."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get_assignment_schedule(self, assignment_id: int) -> AssignmentScheduleQuery:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT CURRENT_DATE AS `current_date`")
            current_date_row = cursor.fetchone()
            database_current_date = _required_date(
                _value(current_date_row, "current_date"), "current_date"
            )
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
            assignment_row = cursor.fetchone()
            if assignment_row is None:
                raise ValueError("assignment does not exist")
            assignment = _assignment(assignment_row)

            cursor.execute(
                """SELECT id FROM actual_hours_adjustments
                    WHERE assignment_id = %s LIMIT 1""",
                (assignment_id,),
            )
            has_actual_hours_adjustments = bool(cursor.fetchone())
            cursor.execute(
                """SELECT id FROM staff_payments
                    WHERE assignment_id = %s AND payment_status <> 'cancelled' LIMIT 1""",
                (assignment_id,),
            )
            has_active_staff_payment = bool(cursor.fetchone())
            reasons: list[str] = []
            if assignment.status == "cancelled":
                reasons.append("cancelled_assignment")
            if has_actual_hours_adjustments:
                reasons.append("actual_hours_adjustment_exists")
            if has_active_staff_payment:
                reasons.append("active_staff_payment")

            cursor.execute(
                """SELECT id, case_no, staff_id, assignment_id, work_date,
                          is_work_day, is_double_pay, notes
                     FROM staff_schedule
                    WHERE assignment_id = %s
                    ORDER BY work_date ASC, id ASC""",
                (assignment_id,),
            )
            schedule_days = tuple(
                _schedule_day(row, assignment, database_current_date)
                for row in (cursor.fetchall() or ())
            )
        return AssignmentScheduleQuery(
            assignment=assignment,
            schedule_days=schedule_days,
            database_current_date=database_current_date,
            adjustment_guard=AssignmentScheduleGuard(
                is_cancelled=assignment.status == "cancelled",
                has_actual_hours_adjustments=has_actual_hours_adjustments,
                has_active_staff_payment=has_active_staff_payment,
                reasons=tuple(reasons),
            ),
        )

    def list_staff_assignments(self, staff_id: int) -> tuple[StaffAssignmentOption, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.id, a.case_no, a.staff_id, a.status,
                          a.assigned_start_date, a.assigned_end_date,
                          o.status AS order_status, o.actual_start_date,
                          o.actual_end_date, s.name AS staff_name
                     FROM case_staff_assignments a
                     JOIN orders o ON o.case_no = a.case_no
                     JOIN staff s ON s.id = a.staff_id
                    WHERE a.staff_id = %s AND a.status <> 'cancelled'
                    ORDER BY a.assigned_start_date ASC, a.id ASC""",
                (staff_id,),
            )
            return tuple(_staff_option(row) for row in (cursor.fetchall() or ()))

    def list_case_assignments(self, case_no: str) -> tuple[CaseAssignment, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.id, a.case_no, a.staff_id, a.status,
                          a.assigned_start_date, a.assigned_end_date,
                          a.original_assigned_start_date,
                          a.original_assigned_end_date,
                          a.planned_hours, a.actual_hours, o.service_days,
                          o.service_hours_per_day, s.name AS staff_name,
                          (SELECT COUNT(*) FROM staff_schedule ss
                            WHERE ss.assignment_id = a.id AND ss.is_work_day = TRUE)
                            AS actual_service_days,
                          (SELECT COUNT(*) FROM staff_schedule ss
                            WHERE ss.assignment_id = a.id AND ss.is_work_day = FALSE)
                            AS rest_days,
                          (SELECT COUNT(*)
                             FROM assignment_schedule_leave_substitution_events e
                            WHERE e.substitute_assignment_id = a.id
                              AND e.resolution_type = 'substitute')
                            AS substitute_service_days,
                          (SELECT COUNT(*)
                             FROM assignment_schedule_leave_substitution_events e
                            WHERE e.original_assignment_id = a.id
                              AND e.resolution_type = 'defer_following_assignments')
                            AS deferred_leave_days,
                          (SELECT COUNT(*)
                             FROM assignment_schedule_leave_substitution_events e
                            WHERE e.original_assignment_id = a.id
                              AND e.resolution_type IN
                                  ('defer_following_assignments', 'substitute'))
                            AS leave_resolution_days
                     FROM case_staff_assignments a
                     JOIN orders o ON o.case_no = a.case_no
                     JOIN staff s ON s.id = a.staff_id
                    WHERE a.case_no = %s AND a.status <> 'cancelled'
                    ORDER BY a.assigned_start_date ASC, a.id ASC""",
                (case_no,),
            )
            return tuple(_case_assignment(row) for row in (cursor.fetchall() or ()))


def _assignment(row: Mapping[str, object]) -> AssignmentScheduleAssignment:
    return AssignmentScheduleAssignment(
        id=_positive(row, "id"),
        case_no=_text(row, "case_no", 50),
        staff_id=_positive(row, "staff_id"),
        status=_text(row, "status", 50),
        assigned_start_date=_required_date(row.get("assigned_start_date"), "assigned_start_date"),
        assigned_end_date=_required_date(row.get("assigned_end_date"), "assigned_end_date"),
        planned_hours=_decimal(row.get("planned_hours"), "planned_hours", nullable=True),
        actual_hours=_decimal(row.get("actual_hours"), "actual_hours", nullable=True),
        service_hours_per_day=_decimal(row.get("service_hours_per_day"), "service_hours_per_day"),
        staff_name=_text(row, "staff_name", 200),
        client_name=_text(row, "client_name", 200),
    )


def _schedule_day(
    row: Mapping[str, object],
    assignment: AssignmentScheduleAssignment,
    current_date: date,
) -> AssignmentScheduleDay:
    if row.get("case_no") != assignment.case_no:
        raise ValueError("schedule day case does not match assignment")
    if row.get("staff_id") != assignment.staff_id:
        raise ValueError("schedule day staff does not match assignment")
    if row.get("assignment_id") != assignment.id:
        raise ValueError("schedule day does not belong to assignment")
    work_date = _required_date(row.get("work_date"), "work_date")
    return AssignmentScheduleDay(
        id=_positive(row, "id"),
        case_no=assignment.case_no,
        staff_id=assignment.staff_id,
        assignment_id=assignment.id,
        work_date=work_date,
        is_work_day=_boolean(row, "is_work_day"),
        is_double_pay=_boolean(row, "is_double_pay"),
        notes=_nullable_text(row.get("notes"), "notes", 1000),
        is_historical=work_date < current_date,
    )


def _staff_option(row: Mapping[str, object]) -> StaffAssignmentOption:
    return StaffAssignmentOption(
        id=_positive(row, "id"),
        case_no=_text(row, "case_no", 50),
        staff_id=_positive(row, "staff_id"),
        status=_text(row, "status", 50),
        assigned_start_date=_required_date(row.get("assigned_start_date"), "assigned_start_date"),
        assigned_end_date=_required_date(row.get("assigned_end_date"), "assigned_end_date"),
        order_status=_text(row, "order_status", 100),
        actual_start_date=_optional_date(row.get("actual_start_date"), "actual_start_date"),
        actual_end_date=_optional_date(row.get("actual_end_date"), "actual_end_date"),
        staff_name=_text(row, "staff_name", 200),
    )


def _case_assignment(row: Mapping[str, object]) -> CaseAssignment:
    return build_case_assignment(
        id=_positive(row, "id"),
        case_no=_text(row, "case_no", 50),
        staff_id=_positive(row, "staff_id"),
        status=_text(row, "status", 50),
        assigned_start_date=_required_date(row.get("assigned_start_date"), "assigned_start_date"),
        assigned_end_date=_required_date(row.get("assigned_end_date"), "assigned_end_date"),
        original_assigned_start_date=_optional_date(
            row.get("original_assigned_start_date"), "original_assigned_start_date"
        ),
        original_assigned_end_date=_optional_date(
            row.get("original_assigned_end_date"), "original_assigned_end_date"
        ),
        planned_hours=_decimal_or_zero(row.get("planned_hours"), "planned_hours"),
        actual_hours=_decimal_or_zero(row.get("actual_hours"), "actual_hours"),
        service_days=_nonnegative_or_zero(row, "service_days"),
        service_hours_per_day=_decimal(row.get("service_hours_per_day"), "service_hours_per_day"),
        staff_name=_text(row, "staff_name", 200),
        actual_service_days=_nonnegative_or_zero(row, "actual_service_days"),
        rest_days=_nonnegative_or_zero(row, "rest_days"),
        substitute_service_days=_nonnegative_or_zero(row, "substitute_service_days"),
        deferred_leave_days=_nonnegative_or_zero(row, "deferred_leave_days"),
        leave_resolution_days=_nonnegative_or_zero(row, "leave_resolution_days"),
    )


def _value(row: object, field: str) -> object:
    if not isinstance(row, Mapping):
        raise ValueError(f"{field} row is invalid")
    return row.get(field, row.get(field.upper()))


def _positive(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} is invalid")
    return value


def _nonnegative(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool):
        raise ValueError(f"{field} is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is invalid") from exc
    if result < 0:
        raise ValueError(f"{field} is invalid")
    return result


def _nonnegative_or_zero(row: Mapping[str, object], field: str) -> int:
    return 0 if row.get(field) is None else _nonnegative(row, field)


def _boolean(row: Mapping[str, object], field: str) -> bool:
    value = row.get(field)
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"{field} is invalid")


def _text(row: Mapping[str, object], field: str, maximum: int) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{field} is invalid")
    return value.strip()


def _nullable_text(value: object, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{field} is invalid")
    return value


def _decimal(value: object, field: str, *, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} is invalid") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} is invalid")
    return result


def _decimal_or_zero(value: object, field: str) -> Decimal:
    result = _decimal(0 if value is None else value, field)
    assert result is not None
    return result


def _required_date(value: object, field: str) -> date:
    result = _optional_date(value, field)
    if result is None:
        raise ValueError(f"{field} is invalid")
    return result


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} is invalid") from exc


__all__ = ["MySqlMultiCaregiverScheduleQueryRepository"]
