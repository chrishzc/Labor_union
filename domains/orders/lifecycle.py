"""
File: domains/orders/lifecycle.py
Description: 定義訂單生命週期與查詢範圍，待補件案件不得自動進入服務或帳務狀態。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from domains.client_finance.obligation_planning import (
    ClientSettlementProjection,
)
from domains.orders.terms import OrderTerms
from domains.scheduling.generation import SchedulingGenerationCandidate
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text

_CASE_NUMBER_MAXIMUM_LENGTH = 50


class OrderLifecycleStatus(StrEnum):
    PENDING_COMPLETION = "待補件"
    DISCUSSION = "洽談中"
    ESTABLISHED = "訂單成立"
    IN_SERVICE = "服務中"
    COMPLETED = "訂單完成"
    CANCELLED = "訂單取消"
    HISTORICAL_UNSERVED = "歷史訂單－未服務"
    HISTORICAL_IN_SERVICE = "歷史訂單－服務中"
    HISTORICAL_SERVICE_COMPLETED = "歷史訂單－服務完成"
    HISTORICAL_ACCOUNTING_COMPLETED = "歷史訂單－帳務完成"


class OrderLifecycleScope(StrEnum):
    ALL = "all"
    UNFINISHED = "unfinished"


def project_historical_accounting_completion_status(
    current_status: OrderLifecycleStatus,
    *,
    client_settled: bool,
    all_staff_settled: bool,
    service_day_counts_complete: bool,
) -> OrderLifecycleStatus:
    """Project the historical terminal branch from owner settlement facts."""

    if any(
        type(value) is not bool
        for value in (client_settled, all_staff_settled, service_day_counts_complete)
    ):
        raise TypeError("historical accounting completion facts must be boolean")
    if current_status is OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED:
        return current_status
    if current_status is not OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED:
        raise ValueError("historical_order_lifecycle_transition_invalid")
    if client_settled and all_staff_settled and service_day_counts_complete:
        return OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED
    return current_status


@dataclass(frozen=True, slots=True)
class OrderLifecycleRootFacts:
    case_no: str
    current_status: OrderLifecycleStatus
    contract_completed: bool
    actual_start_date: date | None
    actual_start_reconfirmed: bool
    cancellation_effective: bool
    service_data_locked: bool

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        _validate_boolean_roots(self)
        if self.actual_start_date is not None:
            _require_date(self.actual_start_date, "actual start date")


@dataclass(frozen=True, slots=True)
class LifecycleImpactCandidate:
    case_no: str
    before_status: OrderLifecycleStatus
    after_status: OrderLifecycleStatus
    actual_end_date: date | None
    completion_instant: datetime | None
    business_date: date
    service_completion_reached: bool
    service_data_lock_was_present: bool
    service_data_lock_should_exist: bool
    alert_codes: tuple[str, ...]
    fingerprint: PreviewFingerprint


def build_terms_lifecycle_impact(
    root_facts: OrderLifecycleRootFacts,
    order_terms: OrderTerms,
    scheduling: SchedulingGenerationCandidate,
    client_settlement: ClientSettlementProjection,
    evaluation_at: datetime,
) -> LifecycleImpactCandidate:
    _validate_inputs(root_facts, scheduling, evaluation_at)
    actual_end_date = _actual_end_date(scheduling)
    completion_instant = (
        order_terms.service_time.completion_instant(actual_end_date)
        if actual_end_date is not None
        else None
    )
    # Terms、actual-start 與 Scheduling impact workflow 只可重算根事實；
    # 即使 completion instant 已到，也必須由 AutoCompleteOrderService 這個
    # 唯一 owner command 另行持久化完成事件。
    completion_reached = False
    after_status = _lifecycle_status(
        root_facts,
        client_settlement,
        completion_reached,
        evaluation_at,
    )
    alerts = _alert_codes(root_facts, client_settlement, evaluation_at)
    return _candidate(
        root_facts,
        client_settlement,
        actual_end_date,
        completion_instant,
        evaluation_at.date(),
        completion_reached,
        after_status,
        alerts,
    )


def _validate_inputs(root_facts, scheduling, evaluation_at):
    if root_facts.case_no != scheduling.case_no:
        raise ValueError("Orders and Scheduling case numbers must match")
    if evaluation_at.tzinfo is None:
        raise ValueError("lifecycle evaluation time must be timezone-aware")


def _actual_end_date(scheduling):
    service_dates = tuple(
        value
        for assignment in scheduling.assignments
        for value in assignment.service_dates
    )
    return max(service_dates) if service_dates else None


def _service_completion_reached(
    root_facts,
    order_terms,
    scheduling,
    completion_instant,
    evaluation_at,
):
    if completion_instant is None:
        return False
    official_day_count = sum(
        len(item.service_dates) for item in scheduling.assignments
    )
    return (
        root_facts.actual_start_date is not None
        and root_facts.actual_start_reconfirmed
        and official_day_count == order_terms.service_days
        and evaluation_at >= completion_instant
    )


def _lifecycle_status(
    root_facts,
    client_settlement,
    completion_reached,
    evaluation_at,
):
    if root_facts.current_status in {
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }:
        return root_facts.current_status
    if root_facts.current_status is OrderLifecycleStatus.PENDING_COMPLETION:
        return OrderLifecycleStatus.PENDING_COMPLETION
    if root_facts.current_status is OrderLifecycleStatus.COMPLETED:
        return OrderLifecycleStatus.COMPLETED
    if root_facts.cancellation_effective and not completion_reached:
        return OrderLifecycleStatus.CANCELLED
    if completion_reached:
        return OrderLifecycleStatus.COMPLETED
    if _service_should_be_active(root_facts, client_settlement, evaluation_at):
        return OrderLifecycleStatus.IN_SERVICE
    if root_facts.current_status is OrderLifecycleStatus.IN_SERVICE:
        return OrderLifecycleStatus.IN_SERVICE
    if client_settlement.deposit_settled:
        return OrderLifecycleStatus.ESTABLISHED
    return OrderLifecycleStatus.DISCUSSION


def _service_should_be_active(root_facts, client_settlement, evaluation_at):
    return (
        root_facts.actual_start_date is not None
        and root_facts.actual_start_date <= evaluation_at.date()
        and client_settlement.deposit_settled
        and root_facts.contract_completed
        and root_facts.actual_start_reconfirmed
    )


def _alert_codes(root_facts, client_settlement, evaluation_at):
    if root_facts.actual_start_date is None:
        return ()
    if root_facts.actual_start_date > evaluation_at.date():
        return ()
    if not client_settlement.deposit_settled:
        return ("enter_service.deposit_required_before_service",)
    if not root_facts.actual_start_reconfirmed:
        return ("enter_service.actual_start_reconfirmation_required",)
    return ()


def _candidate(
    root_facts,
    client_settlement,
    actual_end_date,
    completion_instant,
    business_date,
    completion_reached,
    after_status,
    alerts,
):
    service_lock = (
        root_facts.service_data_locked
        or completion_reached
        and client_settlement.all_formal_obligations_settled
    )
    payload = {
        "before_status": root_facts.current_status.value,
        "after_status": after_status.value,
        "actual_end_date": actual_end_date.isoformat() if actual_end_date else None,
        "completion_instant": (
            completion_instant.isoformat() if completion_instant else None
        ),
        "service_completion_reached": completion_reached,
        "service_data_lock_should_exist": service_lock,
        "client_settlement_fingerprint": client_settlement.fingerprint.value,
        "alert_codes": alerts,
    }
    return LifecycleImpactCandidate(
        root_facts.case_no,
        root_facts.current_status,
        after_status,
        actual_end_date,
        completion_instant,
        business_date,
        completion_reached,
        root_facts.service_data_locked,
        service_lock,
        alerts,
        fingerprint_payload(payload),
    )


def _validate_boolean_roots(root_facts):
    values = (
        root_facts.contract_completed,
        root_facts.actual_start_reconfirmed,
        root_facts.cancellation_effective,
        root_facts.service_data_locked,
    )
    if any(not isinstance(value, bool) for value in values):
        raise TypeError("lifecycle boolean root is invalid")


def _require_date(value, field_name):
    if not isinstance(value, date):
        raise TypeError(f"{field_name} must be a date")
