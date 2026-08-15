"""
File: retirement.py
Description: 驗證 Staff 退役與復職的純狀態轉移契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class StaffLifecycleState(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class StaffLifecycleTransition(StrEnum):
    RETIRE = "retire"
    REACTIVATE = "reactivate"


@dataclass(frozen=True, slots=True)
class StaffLifecycleFact:
    staff_id: int
    state: StaffLifecycleState
    version: int
    effective_at: datetime | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.staff_id, bool) or not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("staff_id_invalid")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 0:
            raise ValueError("staff_lifecycle_version_invalid")
        if self.effective_at is not None and (
            not isinstance(self.effective_at, datetime)
            or self.effective_at.tzinfo is None
            or self.effective_at.utcoffset() is None
        ):
            raise ValueError("staff_retirement_effective_at_invalid")


@dataclass(frozen=True, slots=True)
class StaffLifecycleCandidate:
    before: StaffLifecycleFact
    after: StaffLifecycleFact
    transition: StaffLifecycleTransition
    effective_at: datetime
    reason_code: str
    is_noop: bool


def build_transition(
    fact: StaffLifecycleFact,
    transition: StaffLifecycleTransition,
    *,
    effective_at: datetime,
    reason_code: str,
) -> StaffLifecycleCandidate:
    if (
        not isinstance(effective_at, datetime)
        or effective_at.tzinfo is None
        or effective_at.utcoffset() is None
    ):
        raise ValueError("staff_retirement_effective_at_invalid")
    _validate_reason(transition, reason_code)
    target = _target_state(transition)
    is_noop = fact.state is target
    after = (
        fact
        if is_noop
        else StaffLifecycleFact(
            fact.staff_id,
            target,
            fact.version + 1,
            effective_at,
            reason_code,
        )
    )
    return StaffLifecycleCandidate(
        before=fact,
        after=after,
        transition=transition,
        effective_at=effective_at,
        reason_code=reason_code,
        is_noop=is_noop,
    )


def _target_state(transition: StaffLifecycleTransition) -> StaffLifecycleState:
    if transition is StaffLifecycleTransition.RETIRE:
        return StaffLifecycleState.RETIRED
    if transition is StaffLifecycleTransition.REACTIVATE:
        return StaffLifecycleState.ACTIVE
    raise ValueError("staff_lifecycle_transition_invalid")


def _validate_reason(transition: StaffLifecycleTransition, reason_code: str) -> None:
    allowed = {
        StaffLifecycleTransition.RETIRE: {"left_union", "no_longer_available", "qualification_changed"},
        StaffLifecycleTransition.REACTIVATE: {"returned_to_service"},
    }
    if reason_code not in allowed[transition]:
        raise ValueError("staff_retirement_reason_invalid")
