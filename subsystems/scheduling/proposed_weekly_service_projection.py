"""Canonical Monday--Sunday projection for a not-yet-effective matching plan.

The operations report counts effective ``staff_schedule`` work dates.  Before
acceptance that table must not be fabricated, so this projection applies the
same work-date definition to the plan's authoritative segments and staff
rest-day facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from collections.abc import Iterable

from subsystems.reporting.weekly_report_metrics_service import monday_of, sunday_of


@dataclass(frozen=True, slots=True)
class ProposedServiceSegment:
    segment_id: int
    staff_id: int
    start_date: date
    end_date: date
    weekly_rest_days: frozenset[int]
    service_hours_per_day: int
    special_rest_dates: frozenset[date] = frozenset()

    def __post_init__(self) -> None:
        if self.segment_id <= 0 or self.staff_id <= 0:
            raise ValueError("proposed service segment identity is invalid")
        if self.start_date > self.end_date or self.service_hours_per_day <= 0:
            raise ValueError("proposed service segment facts are invalid")
        if any(day < 0 or day > 6 for day in self.weekly_rest_days):
            raise ValueError("weekly rest days are invalid")


@dataclass(frozen=True, slots=True)
class ProposedWeeklyServiceRow:
    segment_id: int
    staff_id: int
    week_start_date: date
    week_end_date: date
    weekly_work_days: int
    weekly_hours: int


def project_proposed_weekly_service(
    segments: Iterable[ProposedServiceSegment],
) -> tuple[ProposedWeeklyServiceRow, ...]:
    """Count only actual proposed work dates in each calendar week."""
    rows: list[ProposedWeeklyServiceRow] = []
    for segment in segments:
        for week_start in _week_starts(segment.start_date, segment.end_date):
            week_end = sunday_of(week_start)
            start, end = max(segment.start_date, week_start), min(segment.end_date, week_end)
            work_days = sum(
                1 for value in _dates_between(start, end)
                if value.weekday() not in segment.weekly_rest_days
                and value not in segment.special_rest_dates
            )
            rows.append(ProposedWeeklyServiceRow(
                segment.segment_id, segment.staff_id, week_start, week_end,
                work_days, work_days * segment.service_hours_per_day,
            ))
    return tuple(rows)


def _week_starts(start: date, end: date) -> tuple[date, ...]:
    current, result = monday_of(start), []
    while current <= end:
        result.append(current)
        current += timedelta(days=7)
    return tuple(result)


def _dates_between(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


__all__ = [
    "ProposedServiceSegment", "ProposedWeeklyServiceRow",
    "project_proposed_weekly_service",
]
