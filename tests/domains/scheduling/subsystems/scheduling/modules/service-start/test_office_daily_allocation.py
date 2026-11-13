from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from domains.scheduling.assignment_plan import (
    AssignmentPlanDomainError, AssignmentPlanFacts, AssignmentPlanIntent, build_assignment_plan_candidate,
)
from infrastructure.mysql.service_start_arrangement import _office_assignment_intent, _office_schedule_dates


def test_office_first_schedule_allows_interleaving_without_releasing_other_entry_points():
    start = date(2027, 1, 5)
    days = tuple(start + timedelta(days=i) for i in range(4))
    segments = (
        SimpleNamespace(staff_id=7, service_dates=days[::2]),
        SimpleNamespace(staff_id=8, service_dates=days[1::2]),
    )
    assert _office_schedule_dates(segments, start) == days
    intent = _office_assignment_intent(segments, days, start)
    facts = AssignmentPlanFacts("OFFICE-1", 1, 1, 1, 1, 1, 4, 8, False, office_schedule=True)
    candidate = build_assignment_plan_candidate(facts, intent)
    assert [item.service_dates for item in candidate.scheduling.assignments] == [days[::2], days[1::2]]
    with pytest.raises(AssignmentPlanDomainError, match="intervals overlap"):
        AssignmentPlanIntent(intent.segments)
    with pytest.raises(AssignmentPlanDomainError, match="requires office first scheduling"):
        build_assignment_plan_candidate(replace(facts, office_schedule=False), intent)
    duplicate = (segments[0], SimpleNamespace(staff_id=8, service_dates=(days[0], days[3])))
    with pytest.raises(ValueError, match="office_schedule_dates_invalid"):
        _office_schedule_dates(duplicate, start)
