"""Rules for an auditable national-holiday work agreement on a matching plan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer


class HolidayWorkDecision(StrEnum):
    ACCEPTED = "accepted"
    DECLINED = "declined"


@dataclass(frozen=True, slots=True)
class HolidayWorkParticipantDecision:
    participant_role: str
    segment_id: int | None
    decision: HolidayWorkDecision

    def __post_init__(self) -> None:
        if self.participant_role == "customer":
            if self.segment_id is not None:
                raise ValueError("holiday-work customer decision must not target a segment")
        elif self.participant_role == "caregiver":
            if self.segment_id is None:
                raise ValueError("holiday-work caregiver decision requires a segment")
            require_positive_integer(self.segment_id, "holiday-work segment ID")
        else:
            raise ValueError("holiday-work participant role is invalid")
        if not isinstance(self.decision, HolidayWorkDecision):
            raise TypeError("holiday-work decision is invalid")


@dataclass(frozen=True, slots=True)
class HolidayWorkAgreementDraft:
    case_no: str
    plan_id: int
    plan_version: int
    holiday_date: date
    participant_decisions: tuple[HolidayWorkParticipantDecision, ...]
    actor_id: str
    reason: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "holiday-work case number", 50)
        require_positive_integer(self.plan_id, "holiday-work plan ID")
        require_nonnegative_integer(self.plan_version, "holiday-work plan version")
        if not isinstance(self.holiday_date, date):
            raise TypeError("holiday-work date is invalid")
        require_canonical_text(self.actor_id, "holiday-work actor", 191)
        require_canonical_text(self.reason, "holiday-work reason", 500)
        customer_count = sum(item.participant_role == "customer" for item in self.participant_decisions)
        if customer_count != 1:
            raise ValueError("holiday-work agreement requires exactly one customer decision")
        caregiver_segments = [item.segment_id for item in self.participant_decisions if item.participant_role == "caregiver"]
        if not caregiver_segments or len(set(caregiver_segments)) != len(caregiver_segments):
            raise ValueError("holiday-work agreement requires distinct caregiver decisions")

    @property
    def status(self) -> HolidayWorkDecision:
        return (
            HolidayWorkDecision.ACCEPTED
            if all(item.decision is HolidayWorkDecision.ACCEPTED for item in self.participant_decisions)
            else HolidayWorkDecision.DECLINED
        )


def require_exact_plan_participants(
    draft: HolidayWorkAgreementDraft,
    current_segment_ids: tuple[int, ...],
) -> None:
    """Reject a partial, stale, or cross-plan agreement before any write."""

    expected = tuple(sorted(current_segment_ids))
    actual = tuple(sorted(
        int(item.segment_id)
        for item in draft.participant_decisions
        if item.participant_role == "caregiver" and item.segment_id is not None
    ))
    if not expected or actual != expected:
        raise ValueError("holiday-work agreement participants do not match the current plan")


__all__ = [
    "HolidayWorkAgreementDraft",
    "HolidayWorkDecision",
    "HolidayWorkParticipantDecision",
    "require_exact_plan_participants",
]
