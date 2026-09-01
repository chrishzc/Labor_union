"""
File: historical_adoption.py
Description: 建立歷史訂單狀態與 nullable 日期的純採納候選，不猜測缺失事實。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


class HistoricalOrderOutcome(StrEnum):
    ADOPTED = "adopted"
    REVIEW_REQUIRED = "review_required"
    CURRENT_CONFLICT = "current_conflict"
    UNMATCHED_CASE = "unmatched_case"


class HistoricalOrderResult(StrEnum):
    NOT_ADOPTED = "not_adopted"
    MATCHING_PENDING_DEPOSIT = "matching_pending_deposit"
    HISTORICAL_UNSERVED = "historical_unserved"
    HISTORICAL_IN_SERVICE = "historical_in_service"
    HISTORICAL_SERVICE_COMPLETED = "historical_service_completed"


class HistoricalOrderSourceStatus(StrEnum):
    CANCELLED = "cancelled"
    DEPOSIT_PAID = "deposit_paid"
    DISCUSSION = "discussion"


@dataclass(frozen=True, slots=True)
class HistoricalOrderSourceFacts:
    asserted_status: HistoricalOrderSourceStatus | None
    actual_start_date: date | None
    actual_end_date: date | None
    issue_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalOrderCurrentFacts:
    case_no: str
    client_name: str
    status: OrderLifecycleStatus
    lifecycle_version: int
    planned_start_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None


@dataclass(frozen=True, slots=True)
class HistoricalOrderAdoptionCandidate:
    outcome: HistoricalOrderOutcome
    after_status: OrderLifecycleStatus
    resulting_version: int
    date_patch: tuple[tuple[str, date | None], ...]
    issue_codes: tuple[str, ...]
    order_changed: bool
    result: HistoricalOrderResult
    fingerprint: PreviewFingerprint

    @property
    def mutates_order(self) -> bool:
        return self.order_changed


def build_historical_order_candidate(
    current: HistoricalOrderCurrentFacts,
    source: HistoricalOrderSourceFacts,
    business_date: date,
) -> HistoricalOrderAdoptionCandidate:
    if not isinstance(business_date, date):
        raise TypeError("historical order business date must be a date")
    issues = set(source.issue_codes)
    outcome = _outcome(current.status, source.asserted_status, issues)
    result = _result(current, source, outcome, business_date)
    date_patch = _date_patch(current, source, outcome, result)
    after_status = _lifecycle_status(current.status, result)
    order_changed = outcome is HistoricalOrderOutcome.ADOPTED and (
        after_status != current.status or bool(date_patch)
    )
    resulting_version = current.lifecycle_version + int(order_changed)
    payload = {
        "case_no": current.case_no,
        "before_status": current.status.value,
        "after_status": after_status.value,
        "expected_version": current.lifecycle_version,
        "resulting_version": resulting_version,
        "date_patch": tuple(
            (field, value.isoformat() if value is not None else None)
            for field, value in date_patch
        ),
        "issue_codes": tuple(sorted(issues)),
        "outcome": outcome.value,
        "result": result.value,
        "business_date": business_date.isoformat(),
    }
    return HistoricalOrderAdoptionCandidate(
        outcome,
        after_status,
        resulting_version,
        date_patch,
        tuple(sorted(issues)),
        order_changed,
        result,
        fingerprint_payload(payload),
    )


def _outcome(current_status, asserted_status, issues):
    del current_status
    if asserted_status is None:
        return HistoricalOrderOutcome.UNMATCHED_CASE
    if asserted_status is HistoricalOrderSourceStatus.CANCELLED:
        return HistoricalOrderOutcome.UNMATCHED_CASE
    return HistoricalOrderOutcome.ADOPTED


def _result(current, source, outcome, business_date) -> HistoricalOrderResult:
    if outcome is not HistoricalOrderOutcome.ADOPTED:
        return HistoricalOrderResult.NOT_ADOPTED
    if source.asserted_status is HistoricalOrderSourceStatus.DISCUSSION:
        return (
            HistoricalOrderResult.MATCHING_PENDING_DEPOSIT
            if source.actual_start_date is None
            else HistoricalOrderResult.NOT_ADOPTED
        )
    if (
        not isinstance(source.actual_start_date, date)
        or source.actual_start_date == current.planned_start_date
    ):
        return HistoricalOrderResult.HISTORICAL_UNSERVED
    if (
        isinstance(source.actual_end_date, date)
        and source.actual_end_date < business_date
    ):
        return HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED
    return HistoricalOrderResult.HISTORICAL_IN_SERVICE


def _lifecycle_status(
    current_status: OrderLifecycleStatus,
    result: HistoricalOrderResult,
) -> OrderLifecycleStatus:
    return {
        HistoricalOrderResult.NOT_ADOPTED: current_status,
        HistoricalOrderResult.MATCHING_PENDING_DEPOSIT: OrderLifecycleStatus.DISCUSSION,
        HistoricalOrderResult.HISTORICAL_UNSERVED: OrderLifecycleStatus.HISTORICAL_UNSERVED,
        HistoricalOrderResult.HISTORICAL_IN_SERVICE: OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED: OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
    }[result]


def _date_patch(current, source, outcome, result):
    if (
        outcome is HistoricalOrderOutcome.ADOPTED
        and result is HistoricalOrderResult.HISTORICAL_UNSERVED
    ):
        patch = []
        if current.actual_start_date is not None:
            patch.append(("actual_start_date", None))
        if current.actual_end_date is not None:
            patch.append(("actual_end_date", None))
        return tuple(patch)
    if (
        outcome is not HistoricalOrderOutcome.ADOPTED
        or result
        not in {
            HistoricalOrderResult.HISTORICAL_IN_SERVICE,
            HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED,
        }
    ):
        return ()
    actual_start = source.actual_start_date
    actual_end = source.actual_end_date
    patch = []
    if current.actual_start_date != actual_start:
        patch.append(("actual_start_date", actual_start))
    if current.actual_end_date != actual_end:
        patch.append(("actual_end_date", actual_end))
    return tuple(patch)


__all__ = [
    "HistoricalOrderAdoptionCandidate",
    "HistoricalOrderCurrentFacts",
    "HistoricalOrderOutcome",
    "HistoricalOrderResult",
    "HistoricalOrderSourceStatus",
    "HistoricalOrderSourceFacts",
    "build_historical_order_candidate",
]
