"""Current calendars preserve buffer reminders without claiming hard occupancy."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from domains.orders.terms import ServiceTimeTerms
from domains.scheduling.current_projection import (
    EffectiveAssignmentCurrentFact,
    SchedulingCurrentDomainError,
    SchedulingCurrentErrorCode,
    SchedulingCurrentFacts,
    SchedulingOccupancyKind,
    StaffUnavailabilityCurrentFact,
    StoredEffectiveOccupancyFact,
    WaitingDepositLockCurrentFact,
    build_scheduling_current_projection,
)


def _assignment(identity=1, start=date(2026, 9, 3)):
    end = start + timedelta(days=1)
    return EffectiveAssignmentCurrentFact(
        identity, f"CASE-{identity}", identity, 1, 7, start, end, start,
        (start, end), tuple(end + timedelta(days=offset) for offset in range(1, 8)),
        8, ServiceTimeTerms(time(9), time(17), 0),
    )


def _occupancy(assignments):
    return tuple(
        StoredEffectiveOccupancyFact(
            item.staff_id, day, item.generation_id, item.assignment_id, "assignment_interval"
        )
        for item in assignments
        for day in item.official_service_dates
    )


def _query(facts, evaluated_on=2):
    return build_scheduling_current_projection(
        facts, date(2026, 9, 1), date(2026, 9, 20),
        datetime(2026, 9, evaluated_on, 12, tzinfo=ZoneInfo("Asia/Taipei")),
    )


@pytest.mark.parametrize("legacy_buffer_rows", [False, True])
def test_buffers_overlap_service_locks_and_other_buffers_as_reminders(legacy_buffer_rows):
    assignments = (_assignment(), _assignment(2, date(2026, 9, 5)))
    occupancy = _occupancy(assignments)
    if legacy_buffer_rows:
        occupancy += tuple(
            StoredEffectiveOccupancyFact(7, day, 1, 1, "buffer")
            for day in assignments[0].active_buffer_dates
        )
    lock = WaitingDepositLockCurrentFact(
        1, 1, "LOCK-CASE", 7, date(2026, 9, 12), date(2026, 9, 12), (date(2026, 9, 12),)
    )
    projection = _query(SchedulingCurrentFacts(7, assignments, occupancy, (lock,)))
    days = {day.calendar_date: day.entries for day in projection.days}
    assert {entry.occupancy_kind for entry in days[date(2026, 9, 5)]} == {
        SchedulingOccupancyKind.OFFICIAL_WORKDAY, SchedulingOccupancyKind.ASSIGNMENT_BUFFER,
    }
    assert len(days[date(2026, 9, 7)]) == 2
    assert {entry.occupancy_kind for entry in days[date(2026, 9, 13)]} == {
        SchedulingOccupancyKind.ASSIGNMENT_BUFFER, SchedulingOccupancyKind.WAITING_DEPOSIT_BUFFER,
    }


def test_buffer_can_overlap_staff_unavailability():
    assignment = _assignment()
    block = StaffUnavailabilityCurrentFact(1, 7, "long_leave", date(2026, 9, 5), date(2026, 9, 5), "leave")
    projection = _query(SchedulingCurrentFacts(7, (assignment,), _occupancy((assignment,)), (), (block,)))
    day = next(day for day in projection.days if day.calendar_date == date(2026, 9, 5))
    assert {entry.occupancy_kind for entry in day.entries} == {
        SchedulingOccupancyKind.ASSIGNMENT_BUFFER, SchedulingOccupancyKind.STAFF_UNAVAILABILITY,
    }


def test_started_case_hides_stale_active_buffer_reminders():
    assignment = _assignment()
    projection = _query(SchedulingCurrentFacts(7, (assignment,), _occupancy((assignment,)), ()), evaluated_on=3)
    assert all(entry.occupancy_kind != SchedulingOccupancyKind.ASSIGNMENT_BUFFER
               for day in projection.days for entry in day.entries)


@pytest.mark.parametrize("drift", ["missing", "duplicate", "extra"])
def test_hard_occupancy_integrity_remains_required(drift):
    assignment = _assignment()
    occupancy = _occupancy((assignment,))
    if drift == "missing":
        occupancy = occupancy[:-1]
    elif drift == "duplicate":
        occupancy += (occupancy[0],)
    else:
        occupancy += (replace(occupancy[0], occupancy_date=date(2026, 9, 5)),)
    with pytest.raises(SchedulingCurrentDomainError) as captured:
        _query(SchedulingCurrentFacts(7, (assignment,), occupancy, ()))
    assert captured.value.code is SchedulingCurrentErrorCode.DATA_INTEGRITY


@pytest.mark.parametrize("conflict", ["assignment", "lock", "unavailability"])
def test_actual_occupancy_conflicts_remain_blocked(conflict):
    assignments = (_assignment(),)
    locks = ()
    blocks = ()
    if conflict == "assignment":
        assignments += (_assignment(2, date(2026, 9, 4)),)
    elif conflict == "lock":
        locks = (WaitingDepositLockCurrentFact(1, 1, "LOCK-CASE", 7, date(2026, 9, 4), date(2026, 9, 4), (date(2026, 9, 4),)),)
    else:
        blocks = (StaffUnavailabilityCurrentFact(1, 7, "long_leave", date(2026, 9, 4), date(2026, 9, 4), "leave"),)
    with pytest.raises(SchedulingCurrentDomainError) as captured:
        _query(SchedulingCurrentFacts(7, assignments, _occupancy(assignments), locks, blocks))
    assert captured.value.code is SchedulingCurrentErrorCode.OCCUPANCY_CONFLICT
