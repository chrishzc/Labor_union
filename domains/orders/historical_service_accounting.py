"""Historical service-volume facts that do not fabricate daily schedules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


@dataclass(frozen=True, slots=True)
class HistoricalServiceAssignmentFacts:
    assignment_identity: str
    staff_id: int

    def __post_init__(self) -> None:
        if not str(self.assignment_identity).strip():
            raise ValueError("historical_actual_service_days_assignment_mismatch")
        if not isinstance(self.staff_id, int) or isinstance(self.staff_id, bool) or self.staff_id <= 0:
            raise ValueError("historical_actual_service_days_assignment_mismatch")


@dataclass(frozen=True, slots=True)
class HistoricalActualServiceDaysInput:
    assignment_identity: str
    staff_id: int
    actual_service_days: int


@dataclass(frozen=True, slots=True)
class HistoricalActualServiceDaysAllocation:
    assignment_identity: str
    staff_id: int
    actual_service_days: int
    actual_service_hours: Decimal
    floor_fee_ntd: int


@dataclass(frozen=True, slots=True)
class HistoricalActualServiceDaysCandidate:
    case_no: str
    contracted_service_days: int
    total_actual_service_days: int
    total_actual_service_hours: Decimal
    historical_floor_fee_ntd: int
    historical_double_pay_days: int
    historical_double_pay_hours: Decimal
    allocations: tuple[HistoricalActualServiceDaysAllocation, ...]
    fingerprint: PreviewFingerprint


def build_historical_actual_service_days_candidate(
    *,
    case_no: str,
    assignments: tuple[HistoricalServiceAssignmentFacts, ...],
    inputs: tuple[HistoricalActualServiceDaysInput, ...],
    contracted_service_days: int,
    service_hours_per_day: Decimal,
    contractual_floor_fee_ntd: int,
) -> HistoricalActualServiceDaysCandidate:
    _validate_contract_values(
        case_no,
        contracted_service_days,
        service_hours_per_day,
        contractual_floor_fee_ntd,
    )
    days_by_assignment = _validate_and_index_inputs(assignments, inputs)
    total_days = sum(days_by_assignment.values())
    floor_fee = int(
        (
            Decimal(contractual_floor_fee_ntd)
            * Decimal(total_days)
            / Decimal(contracted_service_days)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    floor_fee_by_assignment = _allocate_integer_amount(
        floor_fee,
        tuple(
            (assignment.assignment_identity, days_by_assignment[assignment.assignment_identity])
            for assignment in assignments
        ),
    )
    allocations = tuple(
        HistoricalActualServiceDaysAllocation(
            assignment.assignment_identity,
            assignment.staff_id,
            days_by_assignment[assignment.assignment_identity],
            service_hours_per_day
            * Decimal(days_by_assignment[assignment.assignment_identity]),
            floor_fee_by_assignment[assignment.assignment_identity],
        )
        for assignment in assignments
    )
    payload = {
        "case_no": case_no,
        "contracted_service_days": contracted_service_days,
        "service_hours_per_day": str(service_hours_per_day),
        "contractual_floor_fee_ntd": contractual_floor_fee_ntd,
        "total_actual_service_days": total_days,
        "historical_floor_fee_ntd": floor_fee,
        "historical_double_pay_days": 0,
        "allocations": tuple(
            {
                "assignment_identity": item.assignment_identity,
                "staff_id": item.staff_id,
                "actual_service_days": item.actual_service_days,
                "actual_service_hours": str(item.actual_service_hours),
                "floor_fee_ntd": item.floor_fee_ntd,
            }
            for item in allocations
        ),
    }
    return HistoricalActualServiceDaysCandidate(
        case_no=case_no,
        contracted_service_days=contracted_service_days,
        total_actual_service_days=total_days,
        total_actual_service_hours=service_hours_per_day * Decimal(total_days),
        historical_floor_fee_ntd=floor_fee,
        historical_double_pay_days=0,
        historical_double_pay_hours=Decimal("0"),
        allocations=allocations,
        fingerprint=fingerprint_payload(payload),
    )


def _validate_contract_values(case_no, contracted_days, hours_per_day, floor_fee) -> None:
    if not str(case_no).strip():
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    if not isinstance(contracted_days, int) or isinstance(contracted_days, bool) or contracted_days <= 0:
        raise ValueError("historical_actual_service_days_invalid")
    if not isinstance(hours_per_day, Decimal) or hours_per_day <= 0:
        raise ValueError("historical_actual_service_days_invalid")
    if not isinstance(floor_fee, int) or isinstance(floor_fee, bool) or floor_fee < 0:
        raise ValueError("historical_actual_service_days_invalid")


def _validate_and_index_inputs(assignments, inputs) -> dict[str, int]:
    if not assignments or not inputs:
        raise ValueError("historical_actual_service_days_required")
    expected = {item.assignment_identity: item.staff_id for item in assignments}
    if len(expected) != len(assignments) or len(set(expected.values())) != len(assignments):
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    actual: dict[str, int] = {}
    seen_staff: set[int] = set()
    for item in inputs:
        if (
            not isinstance(item.actual_service_days, int)
            or isinstance(item.actual_service_days, bool)
            or item.actual_service_days <= 0
        ):
            raise ValueError("historical_actual_service_days_invalid")
        if item.assignment_identity in actual or item.staff_id in seen_staff:
            raise ValueError("historical_actual_service_days_assignment_mismatch")
        if expected.get(item.assignment_identity) != item.staff_id:
            raise ValueError("historical_actual_service_days_assignment_mismatch")
        actual[item.assignment_identity] = item.actual_service_days
        seen_staff.add(item.staff_id)
    if set(actual) != set(expected):
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    return actual


def _allocate_integer_amount(
    total_amount: int,
    weights: tuple[tuple[str, int], ...],
) -> dict[str, int]:
    total_weight = sum(weight for _, weight in weights)
    exact = {
        identity: Decimal(total_amount) * Decimal(weight) / Decimal(total_weight)
        for identity, weight in weights
    }
    allocated = {
        identity: int(value.quantize(Decimal("1"), rounding=ROUND_FLOOR))
        for identity, value in exact.items()
    }
    remainder = total_amount - sum(allocated.values())
    order = sorted(
        weights,
        key=lambda pair: (
            -(exact[pair[0]] - Decimal(allocated[pair[0]])),
            pair[0],
        ),
    )
    for identity, _ in order[:remainder]:
        allocated[identity] += 1
    return allocated


__all__ = [
    "HistoricalActualServiceDaysAllocation",
    "HistoricalActualServiceDaysCandidate",
    "HistoricalActualServiceDaysInput",
    "HistoricalServiceAssignmentFacts",
    "build_historical_actual_service_days_candidate",
]
