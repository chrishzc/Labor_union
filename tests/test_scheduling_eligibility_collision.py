"""
File: test_scheduling_eligibility_collision.py
Description: 驗證 Scheduling eligibility/collision projection 的 typed 唯讀契約。
"""

from datetime import date, datetime

import pytest

from api.routes.scheduling_eligibility_collision import router
from api.schemas.scheduling_eligibility_collision import (
    SchedulingEligibilityCollisionProjectionView,
)
from infrastructure.mysql.scheduling_eligibility_collision_repository import (
    MySqlSchedulingEligibilityCollisionRepository,
)
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from subsystems.scheduling.eligibility_collision_query import (
    AvailabilityState,
    CollisionKind,
    CoverageState,
    EligibilityState,
    EligibilityCollisionQueryError,
    QualificationCheckState,
    SchedulingAssignmentFact,
    SchedulingBufferFact,
    SchedulingCaseFacts,
    SchedulingEligibilityCollisionFacts,
    SchedulingEligibilityCollisionQuery,
    SchedulingEligibilityCollisionQueryWorkflow,
    SchedulingPreferenceFact,
    SchedulingScheduleFact,
    SchedulingStaffFacts,
)


class _FactsRepository:
    def __init__(self, facts):
        self.facts = facts
        self.requests = []

    def load_facts(self, request):
        self.requests.append(request)
        return self.facts


def _case(**overrides):
    values = {
        "case_no": "CASE-ELIG-001",
        "status": "洽談中",
        "start_date": date(2026, 8, 20),
        "end_date": date(2026, 8, 22),
        "service_days": 3,
        "service_hours_per_day": 8,
        "requires_cooking": False,
        "location_text": "新竹市東區",
        "scheduling_version": 7,
    }
    values.update(overrides)
    return SchedulingCaseFacts(**values)


def _staff(**overrides):
    values = {
        "staff_id": 11,
        "status": "active",
        "lifecycle_state": "active",
        "regions": ("東區",),
        "cooking_skills": ("葷食",),
        "preferences": (
            SchedulingPreferenceFact(
                "preferred_service_days",
                "service_days",
                "range_with_tolerance",
                {"minimum": 1, "maximum": 10},
                4,
            ),
            SchedulingPreferenceFact(
                "daily_service_hours",
                "service_hours_per_day",
                "contains_integer",
                {"values": [8, 12, 24]},
                4,
            ),
        ),
    }
    values.update(overrides)
    return SchedulingStaffFacts(**values)


def _workflow(facts):
    return SchedulingEligibilityCollisionQueryWorkflow(
        _FactsRepository(facts),
        FixedBusinessClock(datetime(2026, 8, 21, 9, 30, tzinfo=TAIPEI_TIME_ZONE)),
    )


def test_query_projects_qualification_and_hard_collisions_without_writes():
    facts = SchedulingEligibilityCollisionFacts(
        case=_case(),
        staff=(_staff(),),
        assignments=(
            SchedulingAssignmentFact(
                91,
                "OTHER-001",
                11,
                date(2026, 8, 21),
                date(2026, 8, 21),
            ),
        ),
        schedules=(
            SchedulingScheduleFact(
                92,
                "OTHER-002",
                92,
                11,
                date(2026, 8, 22),
                True,
                True,
            ),
        ),
    )

    result = _workflow(facts).query(
        SchedulingEligibilityCollisionQuery(
            "CASE-ELIG-001", date(2026, 8, 21), staff_id=11
        )
    )

    item = result.staff[0]
    assert result.as_of == date(2026, 8, 21)
    assert result.evaluated_at.tzinfo is not None
    assert item.eligibility is EligibilityState.ELIGIBLE
    assert item.availability is AvailabilityState.BLOCKED
    assert item.coverage.status is CoverageState.INCOMPLETE
    assert item.coverage.missing_dates == (
        date(2026, 8, 21),
        date(2026, 8, 22),
    )
    assert {collision.kind for collision in item.collisions} == {
        CollisionKind.ASSIGNMENT_INTERVAL,
        CollisionKind.OFFICIAL_SCHEDULE,
    }


def test_missing_qualification_facts_are_partial_not_false_negative():
    facts = SchedulingEligibilityCollisionFacts(
        case=_case(
            requires_cooking=None,
            location_text=None,
        ),
        staff=(_staff(regions=(), cooking_skills=(), preferences=()),),
        buffers=(
            SchedulingBufferFact(
                33,
                91,
                "OTHER-003",
                11,
                date(2026, 8, 20),
            ),
        ),
    )

    result = _workflow(facts).query(
        SchedulingEligibilityCollisionQuery("CASE-ELIG-001", date(2026, 8, 21))
    )

    item = result.staff[0]
    assert item.eligibility is EligibilityState.PARTIAL
    assert item.availability is AvailabilityState.REQUIRES_REVIEW
    assert item.coverage.status is CoverageState.REQUIRES_REVIEW
    assert item.coverage.missing_dates == ()
    assert item.coverage.review_dates == (date(2026, 8, 20),)
    assert all(
        check.status is QualificationCheckState.UNKNOWN
        for check in item.qualification_checks
        if check.code != "active_lifecycle"
    )
    assert "case_location_missing" in item.partial_data
    assert "staff_regions_missing" in item.partial_data


def test_unknown_case_and_staff_fail_closed():
    empty_case = _workflow(SchedulingEligibilityCollisionFacts(None, ()))
    with pytest.raises(EligibilityCollisionQueryError) as case_error:
        empty_case.query(
            SchedulingEligibilityCollisionQuery("MISSING", date(2026, 8, 21))
        )
    assert case_error.value.code == "case_not_found"

    missing_staff = _workflow(SchedulingEligibilityCollisionFacts(_case(), ()))
    with pytest.raises(EligibilityCollisionQueryError) as staff_error:
        missing_staff.query(
            SchedulingEligibilityCollisionQuery(
                "CASE-ELIG-001", date(2026, 8, 21), staff_id=11
            )
        )
    assert staff_error.value.code == "staff_not_found"


def test_non_current_as_of_never_reuses_current_facts_as_historical_truth():
    facts = SchedulingEligibilityCollisionFacts(
        case=_case(),
        staff=(_staff(),),
        assignments=(
            SchedulingAssignmentFact(
                91,
                "OTHER-001",
                11,
                date(2026, 8, 21),
                date(2026, 8, 21),
            ),
        ),
    )

    result = _workflow(facts).query(
        SchedulingEligibilityCollisionQuery(
            "CASE-ELIG-001", date(2026, 8, 20), staff_id=11
        )
    )

    item = result.staff[0]
    assert result.case_status == "unavailable"
    assert result.scheduling_version is None
    assert "historical_as_of_snapshot_unavailable" in result.partial_data
    assert item.eligibility is EligibilityState.UNAVAILABLE
    assert item.availability is AvailabilityState.UNKNOWN
    assert item.coverage.status is CoverageState.UNAVAILABLE
    assert item.collisions == ()
    assert all(
        check.status is QualificationCheckState.UNKNOWN
        for check in item.qualification_checks
    )


class _SqlCaptureCursor:
    def __init__(self):
        self.sql = ""

    def execute(self, sql, _parameters):
        self.sql = sql

    def fetchall(self):
        return []


@pytest.mark.parametrize(
    ("loader_name", "malformed_clause"),
    [
        ("_load_assignments", "a.assigned_start_date IS NULL"),
        ("_load_schedules", "s.work_date IS NULL"),
        ("_load_buffers", "b.buffer_date IS NULL"),
        ("_load_locks", "d.lock_date IS NULL"),
        ("_load_unavailability", "start_date IS NULL"),
    ],
)
def test_repository_preserves_malformed_temporal_rows_for_partial_projection(
    loader_name, malformed_clause
):
    cursor = _SqlCaptureCursor()
    loader = getattr(MySqlSchedulingEligibilityCollisionRepository, loader_name)

    assert loader(
        cursor,
        (date(2026, 8, 20), date(2026, 8, 22)),
        (11,),
    ) == []
    assert malformed_clause in cursor.sql


def test_public_route_is_get_only_and_response_is_strictly_typed():
    route = next(
        item
        for item in router.routes
        if item.path == "/api/v1/scheduling/eligibility-collisions"
    )
    assert route.methods == {"GET"}

    projection = _workflow(
        SchedulingEligibilityCollisionFacts(case=_case(), staff=(_staff(),))
    ).query(SchedulingEligibilityCollisionQuery("CASE-ELIG-001", date(2026, 8, 21)))
    payload = {
        "case_no": projection.case_no,
        "case_status": projection.case_status,
        "as_of": projection.as_of,
        "evaluated_at": projection.evaluated_at,
        "scheduling_version": projection.scheduling_version,
        "staff": [
            {
                "staff_id": item.staff_id,
                "eligibility": item.eligibility,
                "availability": item.availability,
                "qualification_checks": [
                    {
                        "code": check.code,
                        "status": check.status,
                        "owner": check.owner,
                        "source_identity": check.source_identity,
                        "source_version": check.source_version,
                        "detail": check.detail,
                    }
                    for check in item.qualification_checks
                ],
                "collisions": [],
                "coverage": {
                    "start_date": item.coverage.start_date,
                    "end_date": item.coverage.end_date,
                    "required_day_count": item.coverage.required_day_count,
                    "available_day_count": item.coverage.available_day_count,
                    "missing_dates": list(item.coverage.missing_dates),
                    "review_dates": list(item.coverage.review_dates),
                    "status": item.coverage.status,
                },
                "partial_data": list(item.partial_data),
            }
            for item in projection.staff
        ],
        "partial_data": list(projection.partial_data),
    }
    assert SchedulingEligibilityCollisionProjectionView.model_validate(payload).case_no == "CASE-ELIG-001"
