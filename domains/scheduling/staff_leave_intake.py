"""File: staff_leave_intake.py
Description: 定義月嫂請假待辦的純 Domain 狀態與轉移規則。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class StaffLeaveRequestStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED_FOR_PROCESSING = "accepted_for_processing"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    RESOLVED = "resolved"


class StaffLeaveRequestIssue(StrEnum):
    INVALID_DATE_RANGE = "leave_request_invalid"
    INVALID_TRANSITION = "leave_request_state_conflict"
    REASON_REQUIRED = "leave_request_reason_required"
    RECEIPT_CONFLICT = "leave_request_receipt_conflict"


class StaffLeaveRequestDomainError(ValueError):
    def __init__(self, issue: StaffLeaveRequestIssue) -> None:
        super().__init__(issue.value)
        self.issue = issue


@dataclass(frozen=True, slots=True)
class StaffLeaveRequestIntent:
    leave_start_date: date
    leave_end_date: date
    reason: str = ""

    def __post_init__(self) -> None:
        if self.leave_start_date > self.leave_end_date:
            raise StaffLeaveRequestDomainError(StaffLeaveRequestIssue.INVALID_DATE_RANGE)


def transition_request(
    current: StaffLeaveRequestStatus,
    *,
    action: str,
    actor_is_staff: bool,
    reason: str = "",
) -> StaffLeaveRequestStatus:
    normalized_reason = reason.strip()
    transitions = {
        "accept": (StaffLeaveRequestStatus.PENDING, StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING),
        "reject": (StaffLeaveRequestStatus.PENDING, StaffLeaveRequestStatus.REJECTED),
        "resolve": (StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING, StaffLeaveRequestStatus.RESOLVED),
    }
    if action == "cancel":
        allowed = (StaffLeaveRequestStatus.PENDING,) if actor_is_staff else (
            StaffLeaveRequestStatus.PENDING,
            StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING,
        )
        if current not in allowed:
            raise StaffLeaveRequestDomainError(StaffLeaveRequestIssue.INVALID_TRANSITION)
        if not normalized_reason:
            raise StaffLeaveRequestDomainError(StaffLeaveRequestIssue.REASON_REQUIRED)
        return StaffLeaveRequestStatus.CANCELLED
    if action in {"accept", "reject"} and actor_is_staff:
        raise StaffLeaveRequestDomainError(StaffLeaveRequestIssue.INVALID_TRANSITION)
    source_target = transitions.get(action)
    if source_target is None or current is not source_target[0]:
        raise StaffLeaveRequestDomainError(StaffLeaveRequestIssue.INVALID_TRANSITION)
    if action == "reject" and not normalized_reason:
        raise StaffLeaveRequestDomainError(StaffLeaveRequestIssue.REASON_REQUIRED)
    return source_target[1]
