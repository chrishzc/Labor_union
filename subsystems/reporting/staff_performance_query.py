"""Read-only staff performance composition from scheduling and pricing owners."""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Literal, Protocol

from domains.orders.actual_start import calculate_service_dates
from domains.orders.terms import canonical_service_mode
from shared_kernel.clock import TAIPEI_TIME_ZONE

PeriodKind = Literal["month", "quarter", "year"]


@dataclass(frozen=True, slots=True)
class PerformanceStaff:
    staff_id: int
    union_no: str | None
    staff_name: str


@dataclass(frozen=True, slots=True)
class PerformanceServiceDay:
    staff_id: int
    case_no: str
    work_date: date
    hours: float | None
    work_days: int = 1


@dataclass(frozen=True, slots=True)
class PerformanceHistoricalAssignment:
    staff_id: int
    case_no: str
    start_date: date
    end_date: date
    service_mode: str | None
    hours_per_day: float
    registered_days: int
    confirmed_days: int | None


@dataclass(frozen=True, slots=True)
class PerformanceCaseOpening:
    case_no: str
    actual_start_date: date | None
    primary_staff_id: int


class StaffPerformanceFacts(Protocol):
    def list_staff(self) -> tuple[PerformanceStaff, ...]: ...
    def list_years(self) -> tuple[int, ...]: ...
    def list_service_days(self, start: date, end: date) -> tuple[PerformanceServiceDay, ...]: ...
    def list_historical_assignments(self, start: date, end: date) -> tuple[PerformanceHistoricalAssignment, ...]: ...
    def list_case_openings(self, start: date, end: date, service_cases: tuple[str, ...]) -> tuple[PerformanceCaseOpening, ...]: ...
    def case_amounts(self, case_nos: tuple[str, ...]) -> dict[str, int | None]: ...


@dataclass(frozen=True, slots=True)
class PerformanceTotals:
    case_count: int | None
    service_hours: float | None
    total_amount_ntd: int | None


@dataclass(frozen=True, slots=True)
class PerformanceTrend:
    start_date: date
    end_date: date
    label: str
    totals: PerformanceTotals


@dataclass(frozen=True, slots=True)
class PerformanceCase:
    case_no: str
    service_start: date | None
    service_end: date | None
    work_days: int
    service_hours: float | None
    total_amount_ntd: int | None
    actual_start_date: date | None
    primary_staff_id: int
    recognized_case_count: int | None
    recognized_amount_ntd: int | None


@dataclass(frozen=True, slots=True)
class StaffPerformanceRow:
    staff_id: int
    union_no: str | None
    staff_name: str
    totals: PerformanceTotals
    previous_totals: PerformanceTotals
    cases: tuple[PerformanceCase, ...]
    trend: tuple[PerformanceTrend, ...]


@dataclass(frozen=True, slots=True)
class StaffPerformanceReport:
    schema_version: str
    period: PeriodKind
    year: int
    month: int | None
    quarter: int | None
    start_date: date
    end_date: date
    through_date: date
    previous_start_date: date
    previous_end_date: date
    generated_at: datetime
    selected_staff_id: int | None
    available_years: tuple[int, ...]
    staff_options: tuple[PerformanceStaff, ...]
    service_staff_count: int
    totals: PerformanceTotals
    rows: tuple[StaffPerformanceRow, ...]
    trend: tuple[PerformanceTrend, ...]


def _bounds(year: int, first_month: int, months: int) -> tuple[date, date]:
    last_month = first_month + months - 1
    return date(year, first_month, 1), date(year, last_month, monthrange(year, last_month)[1])


def _historical_service_days(
    assignments: tuple[PerformanceHistoricalAssignment, ...], start: date, end: date,
) -> tuple[PerformanceServiceDay, ...]:
    registered_candidates: dict[str, list[tuple[date, int]]] = defaultdict(list)
    allocation: dict[tuple[str, int, date], int] = defaultdict(int)
    case_terms: dict[str, tuple[float, int]] = {}

    def distribute(case_no: str, candidates: list[tuple[date, int]], total: int) -> None:
        # Differences of rounded cumulative shares preserve the total across report periods.
        size = len(candidates)
        previous = 0
        for index, (day, staff_id) in enumerate(candidates, 1):
            cumulative = (2 * total * index + size) // (2 * size)
            if cumulative > previous and start <= day <= end:
                allocation[case_no, staff_id, day] += cumulative - previous
            previous = cumulative

    for item in assignments:
        span = (item.end_date - item.start_date).days + 1
        mode = canonical_service_mode(item.service_mode) or "連續服務"
        dates = [day for day in calculate_service_dates(item.start_date, span, mode, ()) if day <= item.end_date]
        candidates = [(day, item.staff_id) for day in dates or [item.start_date]]
        case_terms[item.case_no] = (item.hours_per_day, item.registered_days)
        if item.confirmed_days is None:
            registered_candidates[item.case_no].extend(candidates)
        else:
            distribute(item.case_no, candidates, item.confirmed_days)

    for case_no, candidates in registered_candidates.items():
        distinct = sorted(set(candidates))
        distribute(case_no, distinct, case_terms[case_no][1] or len(distinct))

    return tuple(
        PerformanceServiceDay(staff_id, case_no, day, case_terms[case_no][0] * count, work_days=count)
        for (case_no, staff_id, day), count in allocation.items()
    )


def _recognition(opening: PerformanceCaseOpening, start: date, end: date, served_cases: set[str]) -> int | None:
    if opening.actual_start_date is None:
        return None if opening.case_no in served_cases else 0
    return int(start <= opening.actual_start_date <= end)


def _totals(days: tuple[PerformanceServiceDay, ...], amounts: dict[str, int | None],
            openings: tuple[PerformanceCaseOpening, ...], start: date, end: date,
            served_cases: set[str], staff_id: int | None = None) -> PerformanceTotals:
    relevant = tuple(opening for opening in openings if staff_id is None or opening.primary_staff_id == staff_id)
    recognized = tuple(opening for opening in relevant if _recognition(opening, start, end, served_cases) == 1)
    pending = any(_recognition(opening, start, end, served_cases) is None for opening in relevant)
    hours = None if any(day.hours is None for day in days) else sum(day.hours or 0 for day in days)
    amount = None if pending or any(amounts.get(opening.case_no) is None for opening in recognized) else sum(amounts[opening.case_no] or 0 for opening in recognized)
    return PerformanceTotals(None if pending else len(recognized), hours, amount)


def _trend(start: date, end: date, days: tuple[PerformanceServiceDay, ...], amounts: dict[str, int | None],
           openings: tuple[PerformanceCaseOpening, ...], all_days: tuple[PerformanceServiceDay, ...],
           staff_id: int | None = None) -> tuple[PerformanceTrend, ...]:
    points = []
    cursor = start
    while cursor <= end:
        stop = min(date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1]), end)
        selected = tuple(day for day in days if cursor <= day.work_date <= stop)
        served_cases = {day.case_no for day in all_days if cursor <= day.work_date <= stop}
        points.append(PerformanceTrend(cursor, stop, f"{cursor.month}月", _totals(selected, amounts, openings, cursor, stop, served_cases, staff_id)))
        cursor = stop + timedelta(days=1)
    return tuple(points)


class StaffPerformanceQuery:
    def __init__(self, facts: StaffPerformanceFacts, now: Callable[[], datetime]):
        self._facts, self._now = facts, now

    def query(self, year: int, period: PeriodKind = "month", month: int | None = None,
              quarter: int | None = None, staff_id: int | None = None) -> StaffPerformanceReport:
        if (type(year) is not int or not 2 <= year <= 9998 or period not in ("month", "quarter", "year")
                or (period == "month" and (type(month) is not int or not 1 <= month <= 12 or quarter is not None))
                or (period == "quarter" and (type(quarter) is not int or not 1 <= quarter <= 4 or month is not None))
                or (period == "year" and (month is not None or quarter is not None))):
            raise ValueError("staff_performance_period_invalid")
        first = month if period == "month" else (quarter - 1) * 3 + 1 if period == "quarter" else 1
        months = {"month": 1, "quarter": 3, "year": 12}[period]
        start, end = _bounds(year, first, months)
        previous_month = first - months
        previous_start, previous_end = _bounds(year if previous_month > 0 else year - 1, previous_month if previous_month > 0 else previous_month + 12, months)
        now = self._now().astimezone(TAIPEI_TIME_ZONE)
        through = min(end, now.date())
        if through < end:
            previous_end = min(previous_end, previous_start + max(timedelta(days=-1), through - start))
        options = self._facts.list_staff()
        if staff_id is not None and staff_id not in {staff.staff_id for staff in options}:
            raise ValueError("staff_performance_staff_not_found")
        service_days = ()
        if previous_start <= through:
            service_days = self._facts.list_service_days(previous_start, through) + _historical_service_days(
                self._facts.list_historical_assignments(previous_start, through), previous_start, through,
            )
        # One person/case/work date is one service day even if source joins repeat it.
        unique: dict[tuple[int, str, date], PerformanceServiceDay] = {}
        for item in service_days:
            key = (item.staff_id, item.case_no, item.work_date)
            if key in unique and unique[key].hours != item.hours:
                raise ValueError("staff_performance_service_day_inconsistent")
            unique[key] = item
        all_days = tuple(unique.values())
        service_cases = tuple(sorted({day.case_no for day in all_days}))
        openings = self._facts.list_case_openings(previous_start, through, service_cases)
        opening_index = {opening.case_no: opening for opening in openings}
        if len(opening_index) != len(openings) or any(case not in opening_index for case in service_cases):
            raise ValueError("staff_performance_opening_facts_incomplete")
        if any(opening.primary_staff_id not in {staff.staff_id for staff in options} for opening in openings):
            raise ValueError("staff_performance_opening_staff_missing")
        days = tuple(item for item in all_days if staff_id is None or item.staff_id == staff_id)
        current = tuple(item for item in days if start <= item.work_date <= through)
        previous = tuple(item for item in days if previous_start <= item.work_date <= previous_end)
        current_served = {day.case_no for day in all_days if start <= day.work_date <= through}
        previous_served = {day.case_no for day in all_days if previous_start <= day.work_date <= previous_end}
        amounts = self._facts.case_amounts(tuple(sorted(set(service_cases) | {opening.case_no for opening in openings})))
        rows = []
        for staff in options:
            if staff_id is not None and staff.staff_id != staff_id:
                continue
            own = tuple(item for item in current if item.staff_id == staff.staff_id)
            prior = tuple(item for item in previous if item.staff_id == staff.staff_id)
            cases = []
            credited = {opening.case_no for opening in openings if opening.primary_staff_id == staff.staff_id
                        and _recognition(opening, start, through, current_served) in (1, None)}
            for case_no in sorted({item.case_no for item in own} | credited):
                case_days = tuple(item for item in own if item.case_no == case_no)
                opening = opening_index[case_no]
                recognition = _recognition(opening, start, through, current_served) if opening.primary_staff_id == staff.staff_id else 0
                hours = None if any(item.hours is None for item in case_days) else sum(item.hours or 0 for item in case_days)
                recognized_amount = 0 if recognition == 0 else amounts.get(case_no) if recognition == 1 else None
                cases.append(PerformanceCase(case_no, min((item.work_date for item in case_days), default=None),
                    max((item.work_date for item in case_days), default=None), sum(item.work_days for item in case_days), hours, amounts.get(case_no),
                    opening.actual_start_date, opening.primary_staff_id, recognition, recognized_amount))
            rows.append(StaffPerformanceRow(staff.staff_id, staff.union_no, staff.staff_name,
                _totals(own, amounts, openings, start, through, current_served, staff.staff_id),
                _totals(prior, amounts, openings, previous_start, previous_end, previous_served, staff.staff_id), tuple(cases),
                _trend(start, through, own, amounts, openings, all_days, staff.staff_id)))
        return StaffPerformanceReport("staff-performance.v2", period, year, month, quarter, start, end, through,
            previous_start, previous_end, now, staff_id, tuple(sorted({*self._facts.list_years(), now.year, year}, reverse=True)),
            options, len({day.staff_id for day in current}),
            _totals(current, amounts, openings, start, through, current_served, staff_id), tuple(rows),
            _trend(start, through, current, amounts, openings, all_days, staff_id))
