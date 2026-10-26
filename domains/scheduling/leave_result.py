"""Caregiver-reported, already agreed leave outcomes; Scheduling owns the result."""

from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True, slots=True)
class LeaveDateChange:
    original_date: date
    new_date: date | None = None


@dataclass(frozen=True, slots=True)
class LeaveResultSubmission:
    case_no: str
    staff_id: int
    assignment_id: int
    decision: Literal['defer', 'substitute']
    dates: tuple[LeaveDateChange, ...]
    expected_order_version: int
    expected_scheduling_version: int
    key: str

    def __post_init__(self):
        if self.decision not in ('defer', 'substitute') or not self.dates:
            raise ValueError('leave_result_dates_required')
        originals = tuple(item.original_date for item in self.dates)
        if originals != tuple(sorted(set(originals))):
            raise ValueError('leave_result_original_dates_invalid')
        if self.decision == 'defer':
            replacements = tuple(item.new_date for item in self.dates)
            if any(day is None for day in replacements) or len(set(replacements)) != len(replacements):
                raise ValueError('leave_result_new_dates_required')
            if any(item.new_date <= item.original_date for item in self.dates):
                raise ValueError('leave_result_must_defer')
        elif any(item.new_date is not None for item in self.dates):
            raise ValueError('leave_substitute_dates_not_yet_agreed')
