"""Pure rules for caregiver matching notifications and human decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50


class MatchingNotificationKind(StrEnum):
    CAREGIVER_INFO_1 = "caregiver_info_1"
    CAREGIVER_INFO_2 = "caregiver_info_2"
    CUSTOMER_PROFILES = "customer_profiles"


class CaregiverWillingness(StrEnum):
    PENDING = "pending"
    WILLING = "willing"
    UNWILLING = "unwilling"


class CustomerMatchingDecision(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CONTACT_REQUESTED = "contact_requested"


class MatchingResponseSource(StrEnum):
    LINE = "line"
    ADMIN = "admin"


class MatchingCommunicationConflictError(ValueError):
    """Raised when a response conflicts with an existing root fact."""


class MatchingCommunicationStaleError(ValueError):
    """Raised when a response targets an inactive or superseded plan."""


class MatchingRecipientMismatchError(PermissionError):
    """Raised when a LINE response belongs to a different person."""


class MatchingDecisionNotReadyError(ValueError):
    """Raised when a requested matching decision has unmet prerequisites."""


@dataclass(frozen=True, slots=True)
class MatchingPlanReference:
    case_no: str
    plan_id: int
    version: int

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "matching case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        require_positive_integer(self.plan_id, "matching plan ID")
        require_nonnegative_integer(self.version, "matching plan version")


def record_caregiver_willingness(
    current: CaregiverWillingness,
    target: CaregiverWillingness,
    *,
    plan_is_active: bool,
    recipient_matches: bool,
) -> CaregiverWillingness:
    _require_active_plan(plan_is_active)
    _require_matching_recipient(recipient_matches)
    if target is CaregiverWillingness.PENDING:
        raise MatchingCommunicationConflictError("caregiver response cannot return to pending")
    _require_consistent_response(current, target, "caregiver willingness")
    return target


def record_customer_decision(
    current: CustomerMatchingDecision,
    target: CustomerMatchingDecision,
    *,
    plan_is_active: bool,
    recipient_matches: bool,
    profiles_are_available: bool,
) -> CustomerMatchingDecision:
    _require_active_plan(plan_is_active)
    _require_matching_recipient(recipient_matches)
    if not profiles_are_available:
        raise MatchingDecisionNotReadyError("customer profiles are not available")
    if target is CustomerMatchingDecision.PENDING:
        raise MatchingCommunicationConflictError("customer decision cannot return to pending")
    _require_consistent_response(current, target, "customer matching decision")
    return target


def waiting_deposit_lock_is_allowed(decision: CustomerMatchingDecision) -> bool:
    if not isinstance(decision, CustomerMatchingDecision):
        raise TypeError("customer matching decision is invalid")
    return decision is CustomerMatchingDecision.ACCEPTED


def _require_active_plan(plan_is_active: bool) -> None:
    if not plan_is_active:
        raise MatchingCommunicationStaleError("matching plan is no longer active")


def _require_matching_recipient(recipient_matches: bool) -> None:
    if not recipient_matches:
        raise MatchingRecipientMismatchError("LINE responder does not match the recipient")


def _require_consistent_response(current: StrEnum, target: StrEnum, label: str) -> None:
    if current is target or current.value == "pending":
        return
    raise MatchingCommunicationConflictError(f"{label} was already decided")


__all__ = [
    "CaregiverWillingness",
    "CustomerMatchingDecision",
    "MatchingCommunicationConflictError",
    "MatchingCommunicationStaleError",
    "MatchingDecisionNotReadyError",
    "MatchingNotificationKind",
    "MatchingPlanReference",
    "MatchingRecipientMismatchError",
    "MatchingResponseSource",
    "record_caregiver_willingness",
    "record_customer_decision",
    "waiting_deposit_lock_is_allowed",
]
