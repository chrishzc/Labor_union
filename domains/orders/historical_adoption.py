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


@dataclass(frozen=True, slots=True)
class HistoricalOrderSourceFacts:
    asserted_status: OrderLifecycleStatus | None
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
    fingerprint: PreviewFingerprint

    @property
    def mutates_order(self) -> bool:
        return self.order_changed


def build_historical_order_candidate(
    current: HistoricalOrderCurrentFacts,
    source: HistoricalOrderSourceFacts,
) -> HistoricalOrderAdoptionCandidate:
    issues = set(source.issue_codes)
    outcome = _outcome(current.status, source.asserted_status, issues)
    date_patch = _date_patch(current, source, issues, outcome)
    after_status = source.asserted_status if outcome is HistoricalOrderOutcome.ADOPTED else current.status
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
    }
    return HistoricalOrderAdoptionCandidate(
        outcome,
        after_status,
        resulting_version,
        date_patch,
        tuple(sorted(issues)),
        order_changed,
        fingerprint_payload(payload),
    )


def _outcome(current_status, asserted_status, issues):
    del current_status
    if asserted_status is None:
        issues.add("historical_status_invalid")
        return HistoricalOrderOutcome.REVIEW_REQUIRED
    return HistoricalOrderOutcome.ADOPTED


def _date_patch(current, source, issues, outcome):
    del issues
    if outcome is not HistoricalOrderOutcome.ADOPTED:
        return ()
    if source.actual_start_date is None:
        return ()
    actual_start = (
        None
        if source.actual_start_date == current.planned_start_date
        else source.actual_start_date
    )
    if current.actual_start_date == actual_start:
        return ()
    return (("actual_start_date", actual_start),)


__all__ = [
    "HistoricalOrderAdoptionCandidate",
    "HistoricalOrderCurrentFacts",
    "HistoricalOrderOutcome",
    "HistoricalOrderSourceFacts",
    "build_historical_order_candidate",
]
