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
    actual_start_date: date | None
    actual_end_date: date | None


@dataclass(frozen=True, slots=True)
class HistoricalOrderAdoptionCandidate:
    outcome: HistoricalOrderOutcome
    after_status: OrderLifecycleStatus
    resulting_version: int
    date_patch: tuple[tuple[str, date], ...]
    issue_codes: tuple[str, ...]
    fingerprint: PreviewFingerprint

    @property
    def mutates_order(self) -> bool:
        return self.outcome is HistoricalOrderOutcome.ADOPTED


def build_historical_order_candidate(
    current: HistoricalOrderCurrentFacts,
    source: HistoricalOrderSourceFacts,
) -> HistoricalOrderAdoptionCandidate:
    issues = set(source.issue_codes)
    outcome = _outcome(current.status, source.asserted_status, issues)
    date_patch = _date_patch(current, source, issues, outcome)
    after_status = source.asserted_status if outcome is HistoricalOrderOutcome.ADOPTED else current.status
    resulting_version = current.lifecycle_version + int(outcome is HistoricalOrderOutcome.ADOPTED)
    payload = {
        "case_no": current.case_no,
        "before_status": current.status.value,
        "after_status": after_status.value,
        "expected_version": current.lifecycle_version,
        "resulting_version": resulting_version,
        "date_patch": tuple((field, value.isoformat()) for field, value in date_patch),
        "issue_codes": tuple(sorted(issues)),
        "outcome": outcome.value,
    }
    return HistoricalOrderAdoptionCandidate(
        outcome,
        after_status,
        resulting_version,
        date_patch,
        tuple(sorted(issues)),
        fingerprint_payload(payload),
    )


def _outcome(current_status, asserted_status, issues):
    if asserted_status is None:
        issues.add("historical_status_invalid")
        return HistoricalOrderOutcome.REVIEW_REQUIRED
    if current_status is not OrderLifecycleStatus.DISCUSSION and current_status is not asserted_status:
        issues.add("historical_current_status_conflict")
        return HistoricalOrderOutcome.CURRENT_CONFLICT
    return HistoricalOrderOutcome.ADOPTED


def _date_patch(current, source, issues, outcome):
    if outcome is not HistoricalOrderOutcome.ADOPTED:
        return ()
    patch: list[tuple[str, date]] = []
    invalid_range = "historical_order_date_range_invalid" in issues
    _append_date_patch(patch, issues, "actual_start_date", current.actual_start_date, None if invalid_range else source.actual_start_date)
    _append_date_patch(patch, issues, "actual_end_date", current.actual_end_date, None if invalid_range else source.actual_end_date)
    return tuple(patch)


def _append_date_patch(patch, issues, field, current, incoming):
    if incoming is None:
        return
    if current is None:
        patch.append((field, incoming))
        return
    if current != incoming:
        issues.add(f"historical_nonempty_conflict:{field}")


__all__ = [
    "HistoricalOrderAdoptionCandidate",
    "HistoricalOrderCurrentFacts",
    "HistoricalOrderOutcome",
    "HistoricalOrderSourceFacts",
    "build_historical_order_candidate",
]
