"""Pure rules for returning an eligible historical order to the normal lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.scheduling.generation import SchedulingGenerationCandidate
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


@dataclass(frozen=True, slots=True)
class HistoricalPrecisionRestartAssignmentFacts:
    assignment_identity: str
    source_assignment_id: int | None
    staff_id: int
    staff_name: str
    sequence: int
    occupied_service_dates: tuple[date, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalPrecisionRestartFacts:
    case_no: str
    lifecycle_status: OrderLifecycleStatus
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int
    payroll_version: int
    historical_day_revision: int
    planned_start_date: date
    actual_start_date: date | None
    contracted_service_days: int
    service_hours_per_day: int
    service_data_locked: bool
    assignments: tuple[HistoricalPrecisionRestartAssignmentFacts, ...]
    current_assignment_ids: tuple[int, ...] = ()
    holiday_dates: tuple[date, ...] = ()
    open_nonstage_obligation_count: int = 0
    adoption_receipt_id: int | None = None
    adoption_source_identity: str | None = None
    confirmed_service_date_version: int | None = None
    confirmed_service_date_fingerprint: str | None = None
    payroll_obligation_count: int = 0


@dataclass(frozen=True, slots=True)
class HistoricalPrecisionRestartIntent:
    case_no: str


@dataclass(frozen=True, slots=True)
class HistoricalPrecisionRestartCandidate:
    facts: HistoricalPrecisionRestartFacts
    scheduling: SchedulingGenerationCandidate | None
    target_status: OrderLifecycleStatus | None
    actual_end_date: date | None
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint


def build_historical_precision_restart_candidate(
    facts: HistoricalPrecisionRestartFacts,
    intent: HistoricalPrecisionRestartIntent,
) -> HistoricalPrecisionRestartCandidate:
    blockers = list(_eligibility_blockers(facts))
    if intent.case_no != facts.case_no:
        blockers.append("historical_precision_restart_assignment_mismatch")
    blockers = tuple(sorted(set(blockers)))
    target = _target_status(facts.lifecycle_status) if not blockers else None
    scheduling = None
    actual_end = None
    if not blockers:
        scheduling = SchedulingGenerationCandidate(
            case_no=facts.case_no,
            generation_number=facts.scheduling_generation + 1,
            expected_aggregate_version=facts.scheduling_version,
            resulting_aggregate_version=facts.scheduling_version + 1,
            cancelled_assignment_ids=facts.current_assignment_ids,
            assignments=(),
            buffers=(),
        )
    payload = {
        "case_no": facts.case_no,
        "status": facts.lifecycle_status.value,
        "target_status": None if target is None else target.value,
        "versions": (
            facts.order_version,
            facts.scheduling_version,
            facts.scheduling_generation,
            facts.client_finance_version,
            facts.payroll_version,
            facts.historical_day_revision,
            facts.confirmed_service_date_version,
            facts.confirmed_service_date_fingerprint,
        ),
        "provenance": (facts.adoption_receipt_id, facts.adoption_source_identity),
        "restart_mode": "return_to_normal_order_workflow",
        "blockers": blockers,
    }
    return HistoricalPrecisionRestartCandidate(
        facts, scheduling, target, actual_end, blockers, fingerprint_payload(payload)
    )


def _eligibility_blockers(facts: HistoricalPrecisionRestartFacts) -> tuple[str, ...]:
    if facts.lifecycle_status not in {
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
    }:
        return ("historical_precision_restart_not_eligible",)
    blockers: list[str] = []
    if (
        facts.historical_day_revision > 0
        or facts.open_nonstage_obligation_count > 0
        or facts.payroll_obligation_count > 0
    ):
        blockers.append("historical_precision_restart_accounting_bridge_required")
    if facts.service_data_locked:
        blockers.append("service_data_locked")
    return tuple(blockers)


def _target_status(status: OrderLifecycleStatus) -> OrderLifecycleStatus:
    if status in {
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
    }:
        return OrderLifecycleStatus.ESTABLISHED
    raise ValueError("historical_precision_restart_not_eligible")


__all__ = [name for name in globals() if name.startswith("Historical") or name.startswith("build_")]
