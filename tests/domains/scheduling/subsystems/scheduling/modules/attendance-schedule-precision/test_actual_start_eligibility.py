"""Eligibility keeps tentative reservations visible without reducing actual coverage."""

from datetime import date, time

import pytest

from domains.orders.terms import ServiceTimeTerms
from subsystems.scheduling.eligibility_collision_query import (
    AvailabilityState, CollisionKind, CollisionSeverity, CoverageState, SchedulingEligibilityCollisionFacts,
    SchedulingEligibilityCollisionQuery, SchedulingHistoricalReservationFact, SchedulingLockFact, SchedulingScheduleFact,
)
from infrastructure.mysql.scheduling_occupancy_facts import historical_reservation_occupancy
from tests.test_scheduling_eligibility_collision import _case, _staff, _workflow


@pytest.mark.parametrize("current_actual,other_actual,blocked", [
    (None, None, False), (None, date(2026, 8, 21), False),
    (date(2026, 8, 21), None, False), (date(2026, 8, 21), date(2026, 8, 21), True),
])
def test_eligibility_requires_both_actual_start_dates_and_preserves_source_span(current_actual, other_actual, blocked):
    terms = ServiceTimeTerms(time(8), time(16), 0)
    facts = SchedulingEligibilityCollisionFacts(
        case=_case(service_time=terms, actual_start_date=current_actual), staff=(_staff(),),
        schedules=(SchedulingScheduleFact(92, "OTHER", 92, 11, date(2026, 8, 21), True, True,
            service_time=terms, actual_start_date=other_actual, owner_known=True),),
    )
    result = _workflow(facts).query(SchedulingEligibilityCollisionQuery("CASE-ELIG-001", date(2026, 8, 21), 11)).staff[0]
    assert result.availability is (AvailabilityState.BLOCKED if blocked else AvailabilityState.AVAILABLE)
    assert result.coverage.status is (CoverageState.INCOMPLETE if blocked else CoverageState.COMPLETE)
    conflict, = result.collisions
    assert conflict.severity is (CollisionSeverity.HARD_BLOCK if blocked else CollisionSeverity.ADVISORY)
    assert conflict.case_no == "OTHER"
    assert conflict.actual_start_date == other_actual
    assert conflict.service_start_at.isoformat() == "2026-08-21T08:00:00+08:00"
    assert conflict.service_end_at.isoformat() == "2026-08-21T16:00:00+08:00"


@pytest.mark.parametrize("current_actual", [None, date(2026, 8, 21)])
@pytest.mark.parametrize("known_time", [False, True])
def test_waiting_deposit_remains_available_with_source_case_and_optional_shift(current_actual, known_time):
    terms = ServiceTimeTerms(time(8), time(16), 0)
    facts = SchedulingEligibilityCollisionFacts(
        case=_case(service_time=terms, actual_start_date=current_actual), staff=(_staff(),),
        locks=(SchedulingLockFact(8, 9, 10, "WAITING", 11, date(2026, 8, 21), service_time=terms if known_time else None),),
    )
    result = _workflow(facts).query(SchedulingEligibilityCollisionQuery("CASE-ELIG-001", date(2026, 8, 21), 11)).staff[0]
    assert result.availability is AvailabilityState.AVAILABLE
    assert result.coverage.status is CoverageState.COMPLETE
    conflict, = result.collisions
    assert conflict.kind is CollisionKind.WAITING_DEPOSIT_LOCK
    assert conflict.severity is CollisionSeverity.ADVISORY and conflict.case_no == "WAITING"
    assert (conflict.service_start_at.isoformat() if conflict.service_start_at else None) == (
        "2026-08-21T08:00:00+08:00" if known_time else None)


@pytest.mark.parametrize("current_actual,other_actual,pending", [
    (None, None, False), (None, date(2026, 8, 21), False),
    (date(2026, 8, 21), None, False), (date(2026, 8, 21), date(2026, 8, 21), True),
])
def test_unknown_historical_time_never_claims_proven_overlap(current_actual, other_actual, pending):
    day = date(2026, 8, 21)
    occupied = historical_reservation_occupancy({"staff_id": 11, "case_no": "HISTORY", "start_date": day,
        "end_date": day, "actual_start_date": other_actual}, current_actual)
    facts = SchedulingEligibilityCollisionFacts(
        case=_case(service_time=ServiceTimeTerms(time(8), time(16), 0), actual_start_date=current_actual), staff=(_staff(),),
        historical_reservations=(SchedulingHistoricalReservationFact(99, occupied),),
    )
    result = _workflow(facts).query(SchedulingEligibilityCollisionQuery("CASE-ELIG-001", day, 11)).staff[0]
    assert result.availability is (AvailabilityState.REQUIRES_REVIEW if pending else AvailabilityState.AVAILABLE)
    assert result.coverage.status is (CoverageState.REQUIRES_REVIEW if pending else CoverageState.COMPLETE)
    conflict, = result.collisions
    assert conflict.severity is (CollisionSeverity.REQUIRES_REVIEW if pending else CollisionSeverity.ADVISORY)
    assert conflict.service_start_at is None and conflict.service_end_at is None
    assert "時段待確認" in conflict.detail


@pytest.mark.parametrize("other_start,collides", [(time(15), True), (time(16), False)])
def test_calendar_read_changes_preserve_overlap_warning_and_touching_endpoint(other_start, collides):
    """S: two started cases; A: overlap or touch; R: only overlap blocks."""
    started = date(2026, 8, 21)
    facts = SchedulingEligibilityCollisionFacts(
        case=_case(service_time=ServiceTimeTerms(time(8), time(16), 0), actual_start_date=started),
        staff=(_staff(),),
        schedules=(SchedulingScheduleFact(
            92, "OTHER", 92, 11, started, True, True,
            service_time=ServiceTimeTerms(other_start, time(20), 0),
            actual_start_date=started, owner_known=True,
        ),),
    )
    result = _workflow(facts).query(SchedulingEligibilityCollisionQuery("CASE-ELIG-001", started, 11)).staff[0]
    assert result.availability is (AvailabilityState.BLOCKED if collides else AvailabilityState.AVAILABLE)
    assert bool(result.collisions) is collides
    if collides:
        assert result.collisions[0].severity is CollisionSeverity.HARD_BLOCK
