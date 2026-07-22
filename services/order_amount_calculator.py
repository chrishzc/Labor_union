"""Pure proposed-accounting calculations for one service case.

This module deliberately has no database dependency.  Its output is a plan used
when a ledger snapshot is created; it never updates an existing payment record.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


MONEY_ZERO = Decimal("0")
SUBSIDY_HOURS_BY_IDENTITY_STATUS = {
    "一般市民": Decimal("40"),
    "補助市民": Decimal("120"),
    "非市民": MONEY_ZERO,
}
CLIENT_RATE_BY_IDENTITY_STATUS = {
    "一般市民": Decimal("300"),
    "補助市民": MONEY_ZERO,
    "非市民": Decimal("350"),
}


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if result < MONEY_ZERO:
        raise ValueError(f"{field} cannot be negative")
    return result


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date") from exc
    raise ValueError(f"{field} must be a date")


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    return date(value.year + month_index // 12, month_index % 12 + 1, 15)


def _claim_schedule(completed_on: date | None) -> dict[str, int | None]:
    if completed_on is None:
        return {"claim_quarter": None, "claim_application_year": None, "claim_application_month": None}
    quarter = (completed_on.month - 1) // 3 + 1
    application_month = quarter * 3 + 1
    application_year = completed_on.year
    if application_month == 13:
        application_month = 1
        application_year += 1
    return {
        "claim_quarter": quarter,
        "claim_application_year": application_year,
        "claim_application_month": application_month,
    }


def _collection_stages(
    *,
    service_days: Decimal,
    hours_per_day: Decimal,
    client_rate: Decimal,
    client_floor_fee: Decimal,
    service_start_date: date,
    schedule: dict[str, Any],
) -> list[dict[str, Any]]:
    deposit_days = _decimal(schedule.get("deposit_service_days"), "deposit_service_days")
    if deposit_days != deposit_days.to_integral_value():
        raise ValueError("collection stage days must be whole days")
    if deposit_days > service_days:
        raise ValueError("deposit days exceed service_days")

    first_days = min(Decimal("15"), max(MONEY_ZERO, service_days - deposit_days))
    second_days = service_days - deposit_days - first_days
    due_dates = {
        "deposit": _parse_date(schedule.get("deposit_due_date"), "deposit_due_date"),
        "first_payment": service_start_date,
        "second_payment": None,
    }
    if due_dates["deposit"] is None:
        raise ValueError("deposit_due_date is required")
    stages = []
    for stage, days, floor_fee in (
        ("deposit", deposit_days, client_floor_fee),
        ("first_payment", first_days, MONEY_ZERO),
        ("second_payment", second_days, MONEY_ZERO),
    ):
        receivable = days * hours_per_day * client_rate + floor_fee
        stages.append({
            "stage": stage,
            "service_days": _number(days),
            "receivable": _number(receivable),
            "received": 0,
            "due_date": due_dates[stage].isoformat() if due_dates[stage] else None,
            "received_at": None,
        })
    return stages


def _staff_payment_plans(
    assignments: list[dict[str, Any]],
    *,
    order_hours: Decimal,
    order_floor_fee: Decimal,
    due_date: date | None,
) -> list[dict[str, Any]]:
    assigned_hours = MONEY_ZERO
    allocated_floor_fee = MONEY_ZERO
    plans = []
    for index, assignment in enumerate(assignments, start=1):
        if not isinstance(assignment, dict):
            raise ValueError(f"assignment {index} must be an object")
        source_hours = assignment.get("actual_hours")
        if source_hours is None:
            source_hours = assignment.get("service_hours")
        hours = _decimal(source_hours, f"assignment {index} service_hours")
        rate = _decimal(assignment.get("hourly_rate"), f"assignment {index} hourly_rate")
        floor_fee = _decimal(assignment.get("floor_fee_amount", 0), f"assignment {index} floor_fee_amount")
        assigned_hours += hours
        allocated_floor_fee += floor_fee
        salary = hours * rate
        plans.append({
            "assignment_id": assignment.get("assignment_id"),
            "staff_id": assignment.get("staff_id"),
            "service_hours": _number(hours),
            "hourly_rate": _number(rate),
            "service_salary": _number(salary),
            "floor_fee_amount": _number(floor_fee),
            "adjustment_amount": 0,
            "total_payable": _number(salary + floor_fee),
            "due_date": due_date.isoformat() if due_date else None,
        })
    if assigned_hours > order_hours:
        raise ValueError("assignment hours exceed total service hours")
    if allocated_floor_fee > order_floor_fee:
        raise ValueError("assignment floor fees exceed client floor fee")
    return plans


def _subsidy_claim_amount(subsidy_hours: Decimal, staff_plans: list[dict[str, Any]]) -> tuple[int | float | None, list[dict[str, Any]]]:
    if subsidy_hours == MONEY_ZERO:
        return 0, []
    eligible = [plan for plan in staff_plans if Decimal(str(plan["service_hours"])) > MONEY_ZERO]
    if not eligible:
        return None, []
    total_staff_hours = sum((Decimal(str(plan["service_hours"])) for plan in eligible), MONEY_ZERO)
    allocations = []
    claim_amount = MONEY_ZERO
    for plan in eligible:
        staff_hours = Decimal(str(plan["service_hours"]))
        staff_rate = Decimal(str(plan["hourly_rate"]))
        allocated_hours = subsidy_hours * staff_hours / total_staff_hours
        allocated_amount = allocated_hours * staff_rate
        claim_amount += allocated_amount
        allocations.append({
            "assignment_id": plan["assignment_id"],
            "staff_id": plan["staff_id"],
            "subsidy_hours": _number(allocated_hours),
            "service_unit_price": _number(staff_rate),
            "subsidy_claim_amount": _number(allocated_amount),
        })
    return _number(claim_amount), allocations


def calculate_order_amounts(
    order_terms: dict[str, Any],
    assignments: list[dict[str, Any]] | None = None,
    collection_schedule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a proposed ledger plan from explicit terms, without persistence.

    Client identity status derives the approved subsidy hours and client rate.
    Staff rates remain assignment facts; contract-selected stage dates remain input.
    """
    if not isinstance(order_terms, dict):
        raise ValueError("order_terms must be an object")
    if not order_terms.get("case_no"):
        raise ValueError("case_no is required")
    if not isinstance(collection_schedule, dict):
        raise ValueError("collection_schedule is required")

    service_days = _decimal(order_terms.get("service_days"), "service_days")
    hours_per_day = _decimal(order_terms.get("service_hours_per_day"), "service_hours_per_day")
    identity_status = str(order_terms.get("identity_status") or "").strip()
    if identity_status not in SUBSIDY_HOURS_BY_IDENTITY_STATUS:
        raise ValueError("unsupported identity_status")
    client_rate = CLIENT_RATE_BY_IDENTITY_STATUS[identity_status]
    client_floor_fee = _decimal(order_terms.get("client_floor_fee", 0), "client_floor_fee")
    service_start_date = _parse_date(order_terms.get("service_start_date"), "service_start_date")
    completed_on = _parse_date(order_terms.get("actual_completion_date"), "actual_completion_date")
    if service_start_date is None:
        raise ValueError("service_start_date is required")

    total_hours = service_days * hours_per_day
    subsidy_hours = min(SUBSIDY_HOURS_BY_IDENTITY_STATUS[identity_status], total_hours)
    if identity_status == "補助市民" and client_floor_fee > MONEY_ZERO:
        raise ValueError("full subsidy cases cannot have a client floor fee")

    stages = _collection_stages(
        service_days=service_days,
        hours_per_day=hours_per_day,
        client_rate=client_rate,
        client_floor_fee=client_floor_fee,
        service_start_date=service_start_date,
        schedule=collection_schedule,
    )
    client_total = sum((Decimal(str(stage["receivable"])) for stage in stages), MONEY_ZERO)
    client_prepaid_subsidy = subsidy_hours * client_rate
    staff_due_date = _add_months(completed_on, 1 if client_total > MONEY_ZERO else 2) if completed_on else None
    staff_plans = _staff_payment_plans(
        assignments or [],
        order_hours=total_hours,
        order_floor_fee=client_floor_fee,
        due_date=staff_due_date,
    )
    claim_amount, claim_allocations = _subsidy_claim_amount(subsidy_hours, staff_plans)
    claim_schedule = _claim_schedule(completed_on) if subsidy_hours > MONEY_ZERO else {
        "claim_quarter": None,
        "claim_application_year": None,
        "claim_application_month": None,
    }

    return {
        "case_no": str(order_terms["case_no"]),
        "identity_status": identity_status,
        "total_service_hours": _number(total_hours),
        "client_ledger_plan": {
            "stages": stages,
            "amount_receivable": _number(client_total),
            "client_prepaid_subsidy_amount": _number(client_prepaid_subsidy),
            "subsidy_return_amount": _number(client_prepaid_subsidy),
        },
        "staff_payment_plans": staff_plans,
        "subsidy_plan": {
            "subsidy_hours": _number(subsidy_hours),
            "subsidy_claim_amount": claim_amount,
            "staff_allocations": claim_allocations,
            "claim_amount_ready": claim_amount is not None,
            "requires_subsidy_claim": subsidy_hours > MONEY_ZERO,
            **claim_schedule,
        },
    }
