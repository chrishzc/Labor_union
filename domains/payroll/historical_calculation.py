"""Single-pay Payroll calculation from historical per-assignment day counts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domains.orders.floor_fee import (
    allocate_largest_remainder,
    prorate_historical_floor_fee,
)
from domains.payroll.calculation import (
    AssignmentRateSnapshot,
    PayrollAdjustment,
    PayrollTerms,
    assignment_floor_fee_order,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_positive_integer


@dataclass(frozen=True, slots=True)
class HistoricalAssignmentServiceFacts:
    assignment_identity: str
    staff_id: int
    actual_service_days: int
    actual_service_hours: Decimal | None = None

    def __post_init__(self) -> None:
        if not str(self.assignment_identity).strip():
            raise ValueError("historical_actual_service_days_assignment_mismatch")
        require_positive_integer(self.staff_id, "staff id")
        require_positive_integer(self.actual_service_days, "actual service days")
        if self.actual_service_hours is not None and (
            not isinstance(self.actual_service_hours, Decimal)
            or not self.actual_service_hours.is_finite() or self.actual_service_hours <= 0
            or self.actual_service_hours % Decimal("0.5")
        ):
            raise ValueError("historical_completed_service_hours_invalid")


@dataclass(frozen=True, slots=True)
class HistoricalAssignmentPayrollCandidate:
    assignment_identity: str
    staff_id: int
    actual_service_days: int
    actual_hours: float | int
    double_pay_hours: float | int
    hourly_rate: MoneyNTD
    service_salary: MoneyNTD
    floor_fee_allocated: MoneyNTD
    effective_adjustments: MoneyNTD
    total_payable: MoneyNTD


@dataclass(frozen=True, slots=True)
class HistoricalCasePayrollCandidate:
    assignments: tuple[HistoricalAssignmentPayrollCandidate, ...]
    earned_floor_fee: MoneyNTD
    total_payable: MoneyNTD
    fingerprint: PreviewFingerprint


def build_historical_case_payroll_candidate(
    service_facts: tuple[HistoricalAssignmentServiceFacts, ...],
    rate_snapshots: tuple[AssignmentRateSnapshot, ...],
    terms: PayrollTerms,
    adjustments: tuple[PayrollAdjustment, ...] = (),
) -> HistoricalCasePayrollCandidate:
    identities = tuple(item.assignment_identity for item in service_facts)
    if not identities:
        raise ValueError("historical_actual_service_days_required")
    if identities != tuple(sorted(set(identities))):
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    rates = {item.assignment_identity: item for item in rate_snapshots}
    if set(rates) != set(identities) or len(rates) != len(rate_snapshots):
        raise ValueError("payroll_rate_policy_not_found")
    adjustment_totals = {identity: MoneyNTD(0) for identity in identities}
    for adjustment in adjustments:
        if adjustment.assignment_identity not in adjustment_totals:
            raise ValueError("payroll_adjustment_assignment_not_effective")
        adjustment_totals[adjustment.assignment_identity] += adjustment.amount
    floor_fee, floor_allocations = allocate_historical_floor_fee(
        service_facts, terms.contracted_service_days, terms.floor_fee,
    )
    assignments = tuple(
        _assignment_candidate(
            item,
            rates[item.assignment_identity],
            terms,
            floor_allocations[item.assignment_identity],
            adjustment_totals[item.assignment_identity],
        )
        for item in service_facts
    )
    payload = {
        "basis": "historical_actual_service_day_count",
        "historical_double_pay_hours": 0,
        "terms": {
            "contracted_service_days": terms.contracted_service_days,
            "service_hours_per_day": terms.service_hours_per_day,
            "floor_fee_ntd": terms.floor_fee.amount,
        },
        "assignments": tuple(
            {
                "assignment_identity": item.assignment_identity,
                "staff_id": item.staff_id,
                "actual_service_days": item.actual_service_days,
                "actual_hours": item.actual_hours,
                "double_pay_hours": item.double_pay_hours,
                "hourly_rate_ntd": item.hourly_rate.amount,
                "service_salary_ntd": item.service_salary.amount,
                "floor_fee_allocated_ntd": item.floor_fee_allocated.amount,
                "effective_adjustments_ntd": item.effective_adjustments.amount,
                "total_payable_ntd": item.total_payable.amount,
            }
            for item in assignments
        ),
    }
    return HistoricalCasePayrollCandidate(
        assignments=assignments,
        earned_floor_fee=floor_fee,
        total_payable=MoneyNTD(sum(item.total_payable.amount for item in assignments)),
        fingerprint=fingerprint_payload(payload),
    )


def allocate_historical_floor_fee(
    service_facts: tuple[HistoricalAssignmentServiceFacts, ...],
    contracted_service_days: int,
    floor_fee: MoneyNTD,
) -> tuple[MoneyNTD, dict[str, MoneyNTD]]:
    earned = prorate_historical_floor_fee(
        floor_fee, contracted_service_days, sum(item.actual_service_days for item in service_facts),
    )
    ordered = sorted(service_facts, key=lambda item: assignment_floor_fee_order(item.assignment_identity))
    width = len(str(len(ordered)))
    indexed = {str(index).zfill(width): item for index, item in enumerate(ordered)}
    allocated = allocate_largest_remainder(
        earned, {key: item.actual_service_days for key, item in indexed.items()},
    )
    return earned, {item.assignment_identity: allocated[key] for key, item in indexed.items()}


def _assignment_candidate(
    facts: HistoricalAssignmentServiceFacts, rate: AssignmentRateSnapshot,
    terms: PayrollTerms, floor_fee: MoneyNTD, adjustments: MoneyNTD,
) -> HistoricalAssignmentPayrollCandidate:
    actual_hours = (facts.actual_service_hours if facts.actual_service_hours is not None
                    else facts.actual_service_days * terms.service_hours_per_day)
    actual_hours = float(actual_hours)
    service_salary = historical_service_salary(actual_hours, rate.hourly_rate)
    return HistoricalAssignmentPayrollCandidate(
        assignment_identity=facts.assignment_identity,
        staff_id=facts.staff_id,
        actual_service_days=facts.actual_service_days,
        actual_hours=actual_hours,
        double_pay_hours=0,
        hourly_rate=rate.hourly_rate,
        service_salary=service_salary,
        floor_fee_allocated=floor_fee,
        effective_adjustments=adjustments,
        total_payable=service_salary + floor_fee + adjustments,
    )


def historical_service_salary(hours: Decimal | float | int, hourly_rate: MoneyNTD) -> MoneyNTD:
    return MoneyNTD(_whole_ntd(float(hours) * hourly_rate.amount))


def _whole_ntd(value: Decimal | float | int) -> int:
    if value != int(value):
        raise ValueError("half-hour payroll amount must resolve to whole NTD")
    return int(value)


__all__ = [
    "HistoricalAssignmentPayrollCandidate",
    "HistoricalAssignmentServiceFacts",
    "HistoricalCasePayrollCandidate",
    "build_historical_case_payroll_candidate",
    "historical_service_salary",
]
