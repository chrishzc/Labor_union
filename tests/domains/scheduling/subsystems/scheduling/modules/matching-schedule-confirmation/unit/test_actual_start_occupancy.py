"""Orders actual-start facts determine cross-case scheduling occupancy in the current UoW."""

from datetime import date, time
from types import SimpleNamespace

import pytest

from domains.orders.terms import ServiceTimeTerms
from domains.scheduling.assignment_plan import first_shift_conflict
from infrastructure.mysql.scheduling_occupancy_facts import historical_reservation_occupancy, load_occupancy_snapshot


DAY = date(2026, 11, 23)
TERMS = ServiceTimeTerms(time(8), time(12), 0)
ASSIGNMENTS = (SimpleNamespace(staff_id=7, service_dates=(DAY,)),)


class _Cursor:
    def __init__(self, current_actual, other_actual, source="schedule"):
        self.current_actual, self.other_actual, self.source = current_actual, other_actual, source
        self.sql = ""

    def execute(self, sql, params):
        self.sql = sql

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def fetchone(self):
        if "SELECT service_start_time" in self.sql:
            return {"service_start_time": time(8), "service_end_time": time(12), "service_end_day_offset": 0}
        return {"actual_start_date": self.current_actual}

    def fetchall(self):
        if "FROM staff s LEFT JOIN staff_lifecycle_states" in self.sql:
            return [{"id": 7, "status": "active", "lifecycle_state": "active"}]
        row = {"staff_id": 7, "occupancy_date": DAY, "case_no": "OTHER", "owner_case_no": "OTHER",
               "actual_start_date": self.other_actual, "service_start_time": time(8),
               "service_end_time": time(12), "service_end_day_offset": 0}
        if self.sql.startswith("SELECT s.id AS source_id") and self.source in {"schedule", "unknown"}:
            return [{**row, "owner_case_no": None if self.source == "unknown" else "OTHER"}]
        if "FROM caregiver_availability_lock_days" in self.sql and self.source == "lock":
            return [{**row, "lock_id": 3}]
        if "FROM scheduling_staff_unavailability_blocks" in self.sql and self.source == "unavailable":
            return [{"staff_id": 7, "start_date": DAY, "end_date": DAY}]
        return []


@pytest.mark.parametrize("current_actual,other_actual,blocked", [
    (None, None, False), (DAY, None, False), (None, DAY, False), (DAY, DAY, True),
])
def test_canonical_assignment_uses_both_orders_actual_start_dates(current_actual, other_actual, blocked):
    facts, _ = load_occupancy_snapshot(_Cursor(current_actual, other_actual), (7,), "CURRENT", lock=True)
    assert (first_shift_conflict("CURRENT", TERMS, ASSIGNMENTS, facts) is not None) is blocked
    assert facts[0].actual_start_date == other_actual


@pytest.mark.parametrize("source", ["unavailable", "unknown"])
def test_non_case_and_unknown_owner_safety_remains_hard(source):
    facts, _ = load_occupancy_snapshot(_Cursor(None, None, source), (7,), "CURRENT", lock=True)
    assert first_shift_conflict("CURRENT", TERMS, ASSIGNMENTS, facts) is not None


@pytest.mark.parametrize("current_actual,other_actual", [(None, None), (DAY, None), (None, DAY), (DAY, DAY)])
def test_waiting_deposit_never_blocks_canonical_assignment(current_actual, other_actual):
    facts, _ = load_occupancy_snapshot(_Cursor(current_actual, other_actual, "lock"), (7,), "CURRENT", lock=True)
    assert first_shift_conflict("CURRENT", TERMS, ASSIGNMENTS, facts) is None


def test_fresh_orders_state_in_same_uow_and_prospective_actual_start_are_both_checked():
    cursor = _Cursor(None, DAY)
    facts, _ = load_occupancy_snapshot(cursor, (7,), "CURRENT", lock=True)
    assert first_shift_conflict("CURRENT", TERMS, ASSIGNMENTS, facts) is None
    prospective, _ = load_occupancy_snapshot(cursor, (7,), "CURRENT", lock=True, actual_start_date=DAY)
    assert first_shift_conflict("CURRENT", TERMS, ASSIGNMENTS, prospective) is not None
    cursor.current_actual = DAY
    fresh, _ = load_occupancy_snapshot(cursor, (7,), "CURRENT", lock=True)
    assert first_shift_conflict("CURRENT", TERMS, ASSIGNMENTS, fresh) is not None


@pytest.mark.parametrize("wanted_hour,blocked", [(8, True), (12, False), (13, False)])
def test_historical_multiple_day_time_range_checks_later_dates_as_half_open(wanted_hour, blocked):
    first, last = date(2026, 11, 20), date(2026, 11, 25)
    occupied = historical_reservation_occupancy({
        "staff_id": 7, "case_no": "HISTORY", "start_date": first, "end_date": last,
        "actual_start_date": first, "service_start_time": time(8),
        "service_end_time": time(12), "service_end_day_offset": 0,
    }, DAY)
    wanted = ServiceTimeTerms(time(wanted_hour), time(wanted_hour + 4), 0)
    assert (first_shift_conflict("CURRENT", wanted, ASSIGNMENTS, (occupied,)) is not None) is blocked


def test_historical_last_day_cross_midnight_shift_retains_next_day_overlap():
    occupied = historical_reservation_occupancy({
        "staff_id": 7, "case_no": "HISTORY", "start_date": date(2026, 11, 20), "end_date": DAY,
        "actual_start_date": DAY, "service_start_time": time(21),
        "service_end_time": time(9), "service_end_day_offset": 1,
    }, DAY)
    next_day = date(2026, 11, 24)
    assignments = (SimpleNamespace(staff_id=7, service_dates=(next_day,)),)
    assert first_shift_conflict("CURRENT", TERMS, assignments, (occupied,)) is occupied


@pytest.mark.parametrize("other_actual,blocked", [(None, False), (DAY, True)])
def test_actual_start_repository_checks_prospective_second_start_before_order_write(other_actual, blocked):
    from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
    cursor = _Cursor(None, other_actual)
    repository = MySqlOrderActualStartRepository(SimpleNamespace(cursor=lambda: cursor))
    candidate = SimpleNamespace(case_no="CURRENT", assignments=ASSIGNMENTS)
    if blocked:
        with pytest.raises(ValueError, match="actual_start_staff_schedule_conflict"):
            repository.validate_replacement_availability(candidate, actual_start_date=DAY, lock=True)
    else:
        repository.validate_replacement_availability(candidate, actual_start_date=DAY, lock=True)
