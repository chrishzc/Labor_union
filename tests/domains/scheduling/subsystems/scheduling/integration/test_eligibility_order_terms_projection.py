"""Orders 條款投影至 Scheduling 媒合資格的回歸測試。"""

from datetime import date, datetime, time

import pytest

from domains.orders.terms import ServiceTimeTerms
from domains.scheduling.assignment_plan import StaffOccupancyFact

from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from subsystems.scheduling.eligibility_collision_query import (
    CoverageState,
    CollisionKind,
    SchedulingCaseFacts,
    SchedulingEligibilityCollisionFacts,
    SchedulingEligibilityCollisionQuery,
    SchedulingEligibilityCollisionQueryWorkflow,
    SchedulingHistoricalReservationFact,
    SchedulingPreferenceFact,
    SchedulingStaffFacts,
)


class _FactsRepository:
    def __init__(self, facts):
        self.facts = facts

    def load_facts(self, _request):
        return self.facts


@pytest.mark.parametrize("has_reservation", [False, True])
def test_planned_period_may_include_rest_days_without_marking_order_terms_incomplete(has_reservation):
    case = SchedulingCaseFacts(
        case_no="CASE-REST-DAYS-001",
        status="洽談中",
        start_date=date(2026, 12, 15),
        end_date=date(2027, 1, 4),
        service_days=15,
        service_hours_per_day=4,
        requires_cooking=False,
        location_text="新竹市東區",
        scheduling_version=7,
        service_time=ServiceTimeTerms(time(8), time(12), 0),
    )
    staff = SchedulingStaffFacts(
        staff_id=11,
        status="active",
        lifecycle_state="active",
        regions=("東區",),
        cooking_skills=(),
        preferences=(
            SchedulingPreferenceFact(
                "preferred_service_days",
                "service_days",
                "range_with_tolerance",
                {"minimum": 1, "maximum": 30},
                4,
            ),
            SchedulingPreferenceFact(
                "daily_service_hours",
                "service_hours_per_day",
                "contains_integer",
                {"values": [4, 8, 12, 24]},
                4,
            ),
        ),
    )
    reservations = (
        SchedulingHistoricalReservationFact(9, StaffOccupancyFact(
            11, date(2026, 12, 16), "HIS-009", all_day=True, block_end=date(2026, 12, 16),
        )),
    ) if has_reservation else ()
    workflow = SchedulingEligibilityCollisionQueryWorkflow(
        _FactsRepository(SchedulingEligibilityCollisionFacts(
            case=case, staff=(staff,), historical_reservations=reservations,
        )),
        FixedBusinessClock(datetime(2026, 12, 15, 9, 0, tzinfo=TAIPEI_TIME_ZONE)),
    )

    result = workflow.query(
        SchedulingEligibilityCollisionQuery("CASE-REST-DAYS-001", date(2026, 12, 15), staff_id=11)
    )

    assert "case_service_days_mismatch" not in result.partial_data
    assert result.staff[0].coverage.status is (CoverageState.INCOMPLETE if has_reservation else CoverageState.COMPLETE)
    assert result.staff[0].coverage.required_day_count == 21
    assert [collision.kind for collision in result.staff[0].collisions] == (
        [CollisionKind.HISTORICAL_RESERVATION] if has_reservation else []
    )
