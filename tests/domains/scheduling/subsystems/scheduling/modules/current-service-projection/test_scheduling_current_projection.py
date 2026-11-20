"""Current calendars preserve buffer reminders without claiming hard occupancy."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from domains.orders.terms import ServiceTimeTerms
from domains.scheduling.assignment_plan import StaffOccupancyFact
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
        8, ServiceTimeTerms(time(9), time(17), 0), start,
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


@pytest.mark.parametrize("conflict", ["assignment", "unavailability"])
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


@pytest.mark.parametrize("left_actual,right_actual", [(None, None), (None, date(2026, 9, 4)), (date(2026, 9, 3), None)])
def test_unconfirmed_case_overlap_keeps_both_calendar_entries_and_shift_evidence(left_actual, right_actual):
    assignments = (replace(_assignment(), actual_start_date=left_actual),
                   replace(_assignment(2, date(2026, 9, 4)), actual_start_date=right_actual))
    projection = _query(SchedulingCurrentFacts(7, assignments, _occupancy(assignments), ()))
    day = next(day for day in projection.days if day.calendar_date == date(2026, 9, 4))
    shifts = [entry for entry in day.entries if entry.occupancy_kind is SchedulingOccupancyKind.OFFICIAL_WORKDAY]
    assert {entry.case_no for entry in shifts} == {"CASE-1", "CASE-2"}
    assert {entry.actual_start_date for entry in shifts} == {left_actual, right_actual}
    assert all(entry.service_start_at.hour == 9 and entry.service_end_at.hour == 17 for entry in shifts)


def test_historical_reservation_without_daily_assignment_is_a_typed_readonly_calendar_entry():
    reservation = StaffOccupancyFact(7, date(2026, 9, 3), "HISTORY", ServiceTimeTerms(time(21), time(9), 1),
        block_end=date(2026, 9, 4), reservation_only=True)
    assignment = _assignment()
    facts = SchedulingCurrentFacts(7, (assignment,), _occupancy((assignment,)), (), historical_reservations=(reservation,))
    projection = _query(facts)
    day = next(day for day in projection.days if day.calendar_date == date(2026, 9, 3))
    entry, = [entry for entry in day.entries if entry.occupancy_kind is SchedulingOccupancyKind.HISTORICAL_RESERVATION]
    assert entry.case_no == "HISTORY" and entry.assignment_id is None
    assert entry.actual_start_date is None
    assert entry.service_start_at.isoformat() == "2026-09-03T21:00:00+08:00"
    assert entry.service_end_at.isoformat() == "2026-09-04T09:00:00+08:00"


def test_unknown_historical_time_keeps_dates_without_fabricating_service_span():
    reservation = StaffOccupancyFact(7, date(2026, 9, 3), "HISTORY", all_day=True,
        block_end=date(2026, 9, 4), reservation_only=True)
    projection = _query(SchedulingCurrentFacts(7, (), (), (), historical_reservations=(reservation,)))
    entries = [entry for day in projection.days for entry in day.entries if entry.case_no == "HISTORY"]
    assert len(entries) == 2
    assert all(entry.service_start_at is None and entry.service_end_at is None for entry in entries)


@pytest.mark.parametrize("actual_start", [None, date(2026, 9, 4)])
def test_waiting_deposit_can_overlap_official_service_without_hiding_evidence(actual_start):
    assignment = _assignment()
    lock = WaitingDepositLockCurrentFact(1, 1, "LOCK-CASE", 7, date(2026, 9, 4), date(2026, 9, 4),
        (date(2026, 9, 4),), ServiceTimeTerms(time(9), time(17), 0), actual_start)
    projection = _query(SchedulingCurrentFacts(7, (assignment,), _occupancy((assignment,)), (lock,)))
    day = next(day for day in projection.days if day.calendar_date == date(2026, 9, 4))
    assert {entry.case_no for entry in day.entries} == {"CASE-1", "LOCK-CASE"}


def test_current_calendar_http_reads_adopted_history_without_requiring_an_assignment():
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import scheduling_current as route
    from infrastructure.mysql.scheduling_current_projection_repository import MySqlSchedulingCurrentProjectionRepository
    from shared_kernel.clock import FixedBusinessClock
    from subsystems.scheduling.current_projection_workflow import SchedulingCurrentProjectionWorkflow
    class Cursor:
        sql = ""
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def execute(self, sql, _params):
            self.sql = sql
        def fetchone(self):
            return {"id": 7}
        def fetchall(self):
            if "JOIN historical_order_adoption_receipts receipt" in self.sql:
                return [{"source_id": 4, "staff_id": 7, "case_no": "HISTORY", "start_date": date(2026, 9, 3),
                    "end_date": date(2026, 9, 4), "actual_start_date": None,
                    "service_start_time": time(21), "service_end_time": time(9), "service_end_day_offset": 1}]
            return []
    workflow = SchedulingCurrentProjectionWorkflow(MySqlSchedulingCurrentProjectionRepository(SimpleNamespace(cursor=Cursor)),
        FixedBusinessClock(datetime(2026, 9, 2, 12, tzinfo=ZoneInfo("Asia/Taipei"))))
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.require_admin] = lambda: object()
    app.dependency_overrides[route.get_scheduling_current_application] = lambda: workflow
    with TestClient(app) as client:
        response = client.get("/api/v1/scheduling/staff/7/current-calendar?range_start=2026-09-01&range_end=2026-09-10",
            headers={"X-Correlation-ID": "history-current-calendar"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["assignments"] == []
    day = next(day for day in data["days"] if day["calendar_date"] == "2026-09-03")
    entry, = day["entries"]
    assert entry["occupancy_kind"] == "historical_reservation"
    assert entry["case_no"] == "HISTORY" and entry["assignment_id"] is None
    assert entry["actual_start_date"] is None
    assert entry["service_end_at"] == "2026-09-04T09:00:00+08:00"
