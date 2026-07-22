"""Manual actual-hours adjustments and payroll-confirmation validation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from services.db_service import get_connection


def _case_number(case_no: object) -> str:
    if not isinstance(case_no, str) or not case_no.strip():
        raise ValueError("case_no is required")
    return case_no.strip()


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name} must be a finite decimal") from error
    if not result.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return result


def _normalise_adjustments(adjustments: object) -> list[dict[str, Any]]:
    if not isinstance(adjustments, list) or not adjustments:
        raise ValueError("adjustments are required")

    normalised: list[dict[str, Any]] = []
    assignment_ids: set[int] = set()
    for adjustment in adjustments:
        if not isinstance(adjustment, dict):
            raise ValueError("each adjustment must be an object")
        assignment_id = adjustment.get("assignment_id")
        if isinstance(assignment_id, bool) or not isinstance(assignment_id, int) or assignment_id <= 0:
            raise ValueError("assignment_id must be a positive integer")
        if assignment_id in assignment_ids:
            raise ValueError("duplicate assignment_id in adjustments")

        adjusted_hours = _decimal(adjustment.get("adjusted_actual_hours"), "adjusted_actual_hours")
        if adjusted_hours < 0:
            raise ValueError("adjusted_actual_hours cannot be negative")

        normalised.append(
            {
                "assignment_id": assignment_id,
                "adjusted_actual_hours": adjusted_hours,
                "adjustment_reason": _required_text(
                    adjustment.get("adjustment_reason"), "adjustment_reason"
                ),
            }
        )
        assignment_ids.add(assignment_id)
    return normalised


def _load_case_for_confirmation(cursor: Any, case_no: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cursor.execute(
        """SELECT service_days, service_hours_per_day
           FROM orders WHERE case_no = %s FOR UPDATE""",
        (case_no,),
    )
    order = cursor.fetchone()
    if order is None:
        raise ValueError("case_no does not exist")

    cursor.execute(
        """SELECT id AS assignment_id, staff_id, actual_hours, status
           FROM case_staff_assignments
           WHERE case_no = %s AND status <> 'cancelled'
           ORDER BY id FOR UPDATE""",
        (case_no,),
    )
    return order, cursor.fetchall()


def _confirmation(case_no: str, order: dict[str, Any], assignments: list[dict[str, Any]]) -> dict[str, Any]:
    service_days = _decimal(order.get("service_days"), "service_days")
    hours_per_day = _decimal(order.get("service_hours_per_day"), "service_hours_per_day")
    if service_days < 0 or hours_per_day < 0:
        raise ValueError("order service hours cannot be negative")
    target_hours = service_days * hours_per_day

    details: list[dict[str, Any]] = []
    invalid = False
    actual_hours_total = Decimal("0")
    for assignment in assignments:
        actual_hours = assignment.get("actual_hours")
        normalised_hours: Decimal | None = None
        if actual_hours is not None:
            try:
                normalised_hours = _decimal(actual_hours, "actual_hours")
            except ValueError:
                invalid = True
            else:
                if normalised_hours < 0:
                    invalid = True
                else:
                    actual_hours_total += normalised_hours
        else:
            invalid = True
        details.append(
            {
                "assignment_id": int(assignment["assignment_id"]),
                "staff_id": assignment.get("staff_id"),
                "actual_hours": normalised_hours,
            }
        )

    if invalid:
        actual_hours_total_value: Decimal | None = None
        difference: Decimal | None = None
    else:
        actual_hours_total_value = actual_hours_total
        difference = target_hours - actual_hours_total

    return {
        "case_no": case_no,
        "target_hours": target_hours,
        "actual_hours_total": actual_hours_total_value,
        "difference": difference,
        "assignments": details,
        "can_confirm": not invalid and difference == Decimal("0"),
    }


def _assert_assignments_unlocked(cursor: Any, assignment_ids: list[int]) -> None:
    placeholders = ", ".join(["%s"] * len(assignment_ids))
    cursor.execute(
        f"""SELECT assignment_id FROM staff_payments
              WHERE assignment_id IN ({placeholders})
                AND payment_status <> 'cancelled'
              LIMIT 1 FOR UPDATE""",
        tuple(assignment_ids),
    )
    if cursor.fetchone() is not None:
        raise ValueError("assignment with an active staff payment cannot be adjusted")

    cursor.execute(
        f"""SELECT smsd.assignment_id
              FROM staff_monthly_settlement_details smsd
              JOIN staff_monthly_settlements sms ON sms.id = smsd.settlement_id
              WHERE smsd.assignment_id IN ({placeholders})
                AND sms.status <> 'cancelled'
              LIMIT 1 FOR UPDATE""",
        tuple(assignment_ids),
    )
    if cursor.fetchone() is not None:
        raise ValueError("assignment with an active monthly settlement cannot be adjusted")


def validate_case_actual_hours_for_payment(case_no: str) -> dict[str, Any]:
    """Return the exact, assignment-level actual-hours confirmation result."""
    normalised_case_no = _case_number(case_no)
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            order, assignments = _load_case_for_confirmation(cursor, normalised_case_no)
            return _confirmation(normalised_case_no, order, assignments)
    finally:
        connection.close()


def adjust_actual_hours_before_payment(
    case_no: str, adjustments: list[dict[str, Any]], adjusted_by: str
) -> dict[str, Any]:
    """Append audited manual overrides, then return the payroll-confirmation result."""
    normalised_case_no = _case_number(case_no)
    operator = _required_text(adjusted_by, "adjusted_by")
    normalised_adjustments = _normalise_adjustments(adjustments)

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            order, assignments = _load_case_for_confirmation(cursor, normalised_case_no)
            assignments_by_id = {int(item["assignment_id"]): item for item in assignments}
            requested_ids = [item["assignment_id"] for item in normalised_adjustments]
            for assignment_id in requested_ids:
                if assignment_id not in assignments_by_id:
                    raise ValueError("assignment does not belong to this case or is cancelled")

            _assert_assignments_unlocked(cursor, requested_ids)
            adjustment_records: list[dict[str, Any]] = []
            for adjustment in normalised_adjustments:
                assignment = assignments_by_id[adjustment["assignment_id"]]
                previous_value = assignment.get("actual_hours")
                if previous_value is None:
                    raise ValueError("assignment actual_hours is required before manual adjustment")
                previous_hours = _decimal(previous_value, "actual_hours")
                if previous_hours < 0:
                    raise ValueError("assignment actual_hours cannot be negative")
                if previous_hours == adjustment["adjusted_actual_hours"]:
                    raise ValueError("manual adjustment must change actual_hours")

                cursor.execute(
                    """INSERT INTO actual_hours_adjustments
                       (assignment_id, previous_actual_hours, adjusted_actual_hours,
                        adjustment_reason, adjusted_by)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        adjustment["assignment_id"],
                        previous_hours,
                        adjustment["adjusted_actual_hours"],
                        adjustment["adjustment_reason"],
                        operator,
                    ),
                )
                cursor.execute(
                    "UPDATE case_staff_assignments SET actual_hours = %s WHERE id = %s",
                    (adjustment["adjusted_actual_hours"], adjustment["assignment_id"]),
                )
                assignment["actual_hours"] = adjustment["adjusted_actual_hours"]
                adjustment_records.append(
                    {
                        "assignment_id": adjustment["assignment_id"],
                        "previous_actual_hours": previous_hours,
                        "adjusted_actual_hours": adjustment["adjusted_actual_hours"],
                        "adjustment_reason": adjustment["adjustment_reason"],
                        "adjusted_by": operator,
                    }
                )

            confirmation = _confirmation(normalised_case_no, order, assignments)
        connection.commit()
        return {"adjustment_records": adjustment_records, "confirmation": confirmation}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
