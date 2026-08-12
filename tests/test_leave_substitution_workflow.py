from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from domains.scheduling.leave_substitution import (
    LeaveSubstitutionFacts,
    LeaveResolutionType,
    LeaveSubstitutionBatchIntent,
    LeaveSubstitutionItem,
    OfficialScheduleFact,
    build_leave_substitution_candidate,
)
from domains.scheduling.assignment_plan import (
    AssignmentPlanFacts,
    EffectiveAssignmentFact,
)
from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
from subsystems.scheduling.leave_substitution_workflow import (
    _canonical_staff_ids,
    leave_request_fingerprint,
)


def _intent() -> LeaveSubstitutionBatchIntent:
    return LeaveSubstitutionBatchIntent(
        1,
        (LeaveSubstitutionItem(10, date(2026, 8, 3), LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS),),
    )


def test_leave_substitution_workflow_is_readable_source_without_bridge():
    source = Path("subsystems/scheduling/leave_substitution_workflow.py").read_text(encoding="utf-8")
    assert "load_preserved_module" not in source
    assert "_bytecode_bridge" not in source


def test_leave_request_fingerprint_is_deterministic_for_typed_batch():
    assert leave_request_fingerprint(_intent()) == leave_request_fingerprint(_intent())


def test_preflight_staff_ids_must_be_already_canonical():
    assert _canonical_staff_ids((1, 2)) == (1, 2)
    with pytest.raises(ValueError, match="canonical"):
        _canonical_staff_ids((2, 1))


def test_holiday_rest_day_defers_service_without_changing_contract_day_count():
    service_dates = (date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3))
    assignment = EffectiveAssignmentFact(1, 1, 1, service_dates[0], service_dates[-1], service_dates)
    facts = LeaveSubstitutionFacts(
        AssignmentPlanFacts("case-1", 1, 1, 1, 1, 1, 3, 8, True, (assignment,)),
        tuple(OfficialScheduleFact(index + 1, 1, 1, value) for index, value in enumerate(service_dates)),
        False,
    )
    intent = LeaveSubstitutionBatchIntent(
        1,
        (LeaveSubstitutionItem(1, service_dates[0], LeaveResolutionType.SUBSTITUTE, 2),),
    )

    candidate = build_leave_substitution_candidate(
        facts,
        intent,
        (date(2026, 8, 2),),
    )

    planned_dates = sorted(
        service_date
        for assignment in candidate.scheduling.assignments
        for service_date in assignment.service_dates
    )
    assert planned_dates == [date(2026, 8, 1), date(2026, 8, 3), date(2026, 8, 4)]
    assert len(planned_dates) == facts.assignment_plan.contracted_service_days


def test_holiday_only_preview_requires_no_manual_leave_item():
    service_dates = (date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3))
    assignment = EffectiveAssignmentFact(1, 1, 1, service_dates[0], service_dates[-1], service_dates)
    facts = LeaveSubstitutionFacts(
        AssignmentPlanFacts("case-2", 1, 1, 1, 1, 1, 3, 8, True, (assignment,)),
        tuple(OfficialScheduleFact(index + 1, 1, 1, value) for index, value in enumerate(service_dates)),
        False,
    )

    candidate = build_leave_substitution_candidate(
        facts,
        LeaveSubstitutionBatchIntent(1, ()),
        (date(2026, 8, 2),),
    )

    assert candidate.outcomes == ()
    assert candidate.scheduling.assignments[0].service_dates == (
        date(2026, 8, 1), date(2026, 8, 3), date(2026, 8, 4)
    )


def test_holiday_query_version_is_deterministic_for_sorted_facts():
    query = MySqlSchedulingHolidayQuery(_HolidayConnection())

    first = query.query(date(2026, 8, 1), date(2026, 8, 31), lock=False)
    second = query.query(date(2026, 8, 1), date(2026, 8, 31), lock=False)

    assert first.holiday_version == second.holiday_version
    assert tuple(item.holiday_date for item in first.holidays) == (date(2026, 8, 8), date(2026, 8, 15))


class _HolidayConnection:
    def cursor(self):
        return _HolidayCursor()


class _HolidayCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, *_args):
        return None

    def fetchall(self):
        return [
            {"holiday_date": date(2026, 8, 8), "holiday_name": "父親節", "is_double_pay_default": False},
            {"holiday_date": date(2026, 8, 15), "holiday_name": "地方紀念日", "is_double_pay_default": False},
        ]
