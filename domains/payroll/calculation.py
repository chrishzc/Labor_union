"""Pure integer Payroll calculation from assignment-owned service facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from domains.orders.floor_fee import (
    allocate_largest_remainder,
    prorate_floor_fee,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191


class PayrollPolicyKind(StrEnum):
    CITIZEN = "citizen"
    SUBSIDIZED_CITIZEN = "subsidized_citizen"
    NON_CITIZEN = "non_citizen"


_HOURLY_RATE_BY_POLICY = {
    PayrollPolicyKind.CITIZEN: MoneyNTD(300),
    PayrollPolicyKind.SUBSIDIZED_CITIZEN: MoneyNTD(350),
    PayrollPolicyKind.NON_CITIZEN: MoneyNTD(320),
}


@dataclass(frozen=True, slots=True)
class OfficialAssignmentServiceFacts:
    assignment_identity: str
    staff_id: int
    service_dates: tuple[date, ...]
    double_pay_dates: tuple[date, ...] = ()
    effective: bool = True

    def __post_init__(self) -> None:
        _validate_identity(self.assignment_identity, "assignment identity")
        require_positive_integer(self.staff_id, "staff id")
        _validate_dates(self.service_dates, "service dates")
        _validate_dates(self.double_pay_dates, "double-pay dates")
        if self.effective and not self.service_dates:
            raise ValueError("effective_assignment_service_days_required")
        if not set(self.double_pay_dates).issubset(self.service_dates):
            raise ValueError("special_pay_terms_invalid")
        if not isinstance(self.effective, bool):
            raise TypeError("effective must be bool")


@dataclass(frozen=True, slots=True)
class AssignmentRateSnapshot:
    assignment_identity: str
    policy_version: str
    policy_kind: PayrollPolicyKind
    hourly_rate: MoneyNTD

    def __post_init__(self) -> None:
        _validate_identity(self.assignment_identity, "assignment identity")
        _validate_identity(self.policy_version, "payroll policy version")
        _require_nonnegative_money(self.hourly_rate, "hourly rate")
        if self.hourly_rate != _HOURLY_RATE_BY_POLICY[self.policy_kind]:
            raise ValueError("payroll_rate_snapshot_mismatch")


@dataclass(frozen=True, slots=True)
class PayrollTerms:
    contracted_service_days: int
    service_hours_per_day: int
    floor_fee: MoneyNTD

    def __post_init__(self) -> None:
        require_positive_integer(
            self.contracted_service_days,
            "contracted service days",
        )
        require_positive_integer(
            self.service_hours_per_day,
            "service hours per day",
        )
        _require_nonnegative_money(self.floor_fee, "floor fee")


@dataclass(frozen=True, slots=True)
class PayrollAdjustment:
    assignment_identity: str
    amount: MoneyNTD

    def __post_init__(self) -> None:
        _validate_identity(self.assignment_identity, "assignment identity")
        if not isinstance(self.amount, MoneyNTD):
            raise TypeError("payroll adjustment must be MoneyNTD")


@dataclass(frozen=True, slots=True)
class AssignmentPayrollCandidate:
    assignment_identity: str
    staff_id: int
    official_service_day_count: int
    actual_hours: int
    double_pay_hours: int
    hourly_rate: MoneyNTD
    service_salary: MoneyNTD
    floor_fee_allocated: MoneyNTD
    effective_adjustments: MoneyNTD
    total_payable: MoneyNTD


@dataclass(frozen=True, slots=True)
class CasePayrollCandidate:
    assignments: tuple[AssignmentPayrollCandidate, ...]
    earned_floor_fee: MoneyNTD
    total_payable: MoneyNTD
    fingerprint: PreviewFingerprint


def build_case_payroll_candidate(
    service_facts: tuple[OfficialAssignmentServiceFacts, ...],
    rate_snapshots: tuple[AssignmentRateSnapshot, ...],
    terms: PayrollTerms,
    adjustments: tuple[PayrollAdjustment, ...] = (),
) -> CasePayrollCandidate:
    effective_facts = tuple(item for item in service_facts if item.effective)
    _validate_service_ownership(effective_facts)
    rates = _index_rates(rate_snapshots, effective_facts)
    adjustment_totals = _index_adjustments(adjustments, effective_facts)
    earned_floor_fee = _earned_floor_fee(terms, effective_facts)
    floor_allocations = _allocate_floor_fee(earned_floor_fee, effective_facts)
    assignments = _build_assignment_candidates(
        effective_facts,
        rates,
        terms,
        floor_allocations,
        adjustment_totals,
    )
    return _case_candidate(assignments, earned_floor_fee, effective_facts, rates, terms)


def _case_candidate(assignments, earned_floor_fee, facts, rates, terms):
    return CasePayrollCandidate(
        assignments=assignments,
        earned_floor_fee=earned_floor_fee,
        total_payable=MoneyNTD(
            sum(item.total_payable.amount for item in assignments)
        ),
        fingerprint=fingerprint_payload(
            _candidate_payload(assignments, facts, rates, terms)
        ),
    )


def rate_snapshot(
    assignment_identity: str,
    policy_version: str,
    policy_kind: PayrollPolicyKind,
) -> AssignmentRateSnapshot:
    return AssignmentRateSnapshot(
        assignment_identity,
        policy_version,
        policy_kind,
        _HOURLY_RATE_BY_POLICY[policy_kind],
    )


def _validate_service_ownership(
    facts: tuple[OfficialAssignmentServiceFacts, ...],
) -> None:
    identities = tuple(item.assignment_identity for item in facts)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("assignment_identities_must_be_sorted_and_unique")
    all_dates = tuple(value for item in facts for value in item.service_dates)
    if len(all_dates) != len(set(all_dates)):
        raise ValueError("official_service_ownership_conflict")


def _index_rates(rate_snapshots, service_facts):
    rates = {item.assignment_identity: item for item in rate_snapshots}
    expected = {item.assignment_identity for item in service_facts}
    if set(rates) != expected or len(rates) != len(rate_snapshots):
        raise ValueError("payroll_rate_policy_not_found")
    return rates


def _index_adjustments(adjustments, service_facts):
    identities = {item.assignment_identity for item in service_facts}
    totals = {identity: MoneyNTD(0) for identity in identities}
    for adjustment in adjustments:
        if adjustment.assignment_identity not in identities:
            raise ValueError("payroll_adjustment_assignment_not_effective")
        current = totals[adjustment.assignment_identity]
        totals[adjustment.assignment_identity] = current + adjustment.amount
    return totals


def _earned_floor_fee(terms, facts) -> MoneyNTD:
    actual_service_days = sum(len(item.service_dates) for item in facts)
    return prorate_floor_fee(
        terms.floor_fee,
        terms.contracted_service_days,
        actual_service_days,
    )


def _allocate_floor_fee(earned_floor_fee, facts):
    service_days = {
        item.assignment_identity: len(item.service_dates) for item in facts
    }
    return allocate_largest_remainder(earned_floor_fee, service_days)


def _build_assignment_candidate(facts, rate, terms, floor_fee, adjustments):
    service_day_count = len(facts.service_dates)
    actual_hours = service_day_count * terms.service_hours_per_day
    double_pay_hours = len(facts.double_pay_dates) * terms.service_hours_per_day
    service_salary = MoneyNTD(
        (actual_hours + double_pay_hours) * rate.hourly_rate.amount
    )
    total_payable = service_salary + floor_fee + adjustments
    return AssignmentPayrollCandidate(
        assignment_identity=facts.assignment_identity,
        staff_id=facts.staff_id,
        official_service_day_count=service_day_count,
        actual_hours=actual_hours,
        double_pay_hours=double_pay_hours,
        hourly_rate=rate.hourly_rate,
        service_salary=service_salary,
        floor_fee_allocated=floor_fee,
        effective_adjustments=adjustments,
        total_payable=total_payable,
    )


def _build_assignment_candidates(facts, rates, terms, floor_fees, adjustments):
    return tuple(
        _build_assignment_candidate(
            item,
            rates[item.assignment_identity],
            terms,
            floor_fees[item.assignment_identity],
            adjustments[item.assignment_identity],
        )
        for item in facts
    )


def _candidate_payload(assignments, facts, rates, terms) -> dict[str, object]:
    return {
        "assignments": tuple(_assignment_payload(item) for item in assignments),
        "root_facts": tuple(_facts_payload(item, rates) for item in facts),
        "terms": {
            "contracted_service_days": terms.contracted_service_days,
            "service_hours_per_day": terms.service_hours_per_day,
            "floor_fee_ntd": terms.floor_fee.amount,
        },
    }


def _assignment_payload(item) -> dict[str, object]:
    return {
        "assignment_identity": item.assignment_identity,
        "staff_id": item.staff_id,
        "official_service_day_count": item.official_service_day_count,
        "actual_hours": item.actual_hours,
        "double_pay_hours": item.double_pay_hours,
        "hourly_rate_ntd": item.hourly_rate.amount,
        "service_salary_ntd": item.service_salary.amount,
        "floor_fee_allocated_ntd": item.floor_fee_allocated.amount,
        "effective_adjustments_ntd": item.effective_adjustments.amount,
        "total_payable_ntd": item.total_payable.amount,
    }


def _facts_payload(item, rates) -> dict[str, object]:
    rate = rates[item.assignment_identity]
    return {
        "assignment_identity": item.assignment_identity,
        "service_dates": tuple(value.isoformat() for value in item.service_dates),
        "double_pay_dates": tuple(
            value.isoformat() for value in item.double_pay_dates
        ),
        "policy_version": rate.policy_version,
        "policy_kind": rate.policy_kind.value,
    }


def _validate_dates(values: tuple[date, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if any(not isinstance(value, date) for value in values):
        raise TypeError(f"{field_name} contains an invalid date")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _require_nonnegative_money(value: MoneyNTD, field_name: str) -> None:
    if not isinstance(value, MoneyNTD):
        raise TypeError(f"{field_name} must be MoneyNTD")
    require_nonnegative_integer(value.amount, field_name)


def _validate_identity(value: str, field_name: str) -> None:
    require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)
