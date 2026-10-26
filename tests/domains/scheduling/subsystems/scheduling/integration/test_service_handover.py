from dataclasses import replace
from datetime import date, timedelta

import pytest

from domains.scheduling.assignment_plan import AssignmentPlanFacts, EffectiveAssignmentFact
from domains.scheduling.leave_substitution import (LeaveResolutionType, LeaveSubstitutionBatchIntent,
    LeaveSubstitutionDomainError, LeaveSubstitutionFacts, LeaveSubstitutionItem,
    OfficialScheduleFact, build_leave_substitution_candidate)
from subsystems.scheduling.leave_substitution_workflow import leave_request_fingerprint

TODAY = date(2026, 10, 21)


def facts():
    days = tuple(TODAY + timedelta(days=offset) for offset in range(-2, 18))
    later = (TODAY + timedelta(days=20), TODAY + timedelta(days=21))
    return LeaveSubstitutionFacts(
        AssignmentPlanFacts("HANDOVER", 1, 1, 1, 1, 1, 22, 8, True, (
            EffectiveAssignmentFact(1, 7, 1, days[0], days[-1], days),
            EffectiveAssignmentFact(2, 9, 2, later[0], later[-1], later),
        )), tuple(OfficialScheduleFact(index + 10, 1, 7, day, index == 3) for index, day in enumerate(days))
            + tuple(OfficialScheduleFact(index + 100, 2, 9, day) for index, day in enumerate(later)),
        False, business_date=TODAY,
    )


def intent(source=None):
    source = source or facts()
    return LeaveSubstitutionBatchIntent(1, tuple(LeaveSubstitutionItem(row.schedule_id, row.work_date,
        LeaveResolutionType.SUBSTITUTE, 8, row.is_double_pay) for row in source.official_schedules
        if row.assignment_id == 1 and row.work_date >= TODAY), TODAY)


def test_long_handover_forms_one_successor_preserves_past_other_family_and_special_pay():
    before = facts()
    result = build_leave_substitution_candidate(before, intent(before), (TODAY + timedelta(days=1),))
    assert len(result.scheduling.assignments) == 3
    original, successor, other = result.scheduling.assignments
    assert original.staff_id == 7 and original.service_dates == (TODAY - timedelta(days=2), TODAY - timedelta(days=1))
    assert successor.staff_id == 8 and len(successor.service_dates) == 18
    assert successor.service_dates[0] == TODAY
    assert successor.double_pay_dates == (TODAY + timedelta(days=1),)
    assert other.service_dates == before.assignment_plan.effective_assignments[1].official_service_dates
    assert sorted(day for item in result.scheduling.assignments for day in item.service_dates) == [row.work_date for row in before.official_schedules]
    assert len(result.outcomes) == 18


@pytest.mark.parametrize("change,code", [
    (lambda command: replace(command, handover_date=TODAY - timedelta(days=1)), "handover_date_in_past"),
    (lambda command: replace(command, items=command.items[:-1]), "handover_remaining_service_changed"),
    (lambda command: replace(command, items=(replace(command.items[0], substitute_staff_id=10),) + command.items[1:]), "handover_requires_one_successor"),
    (lambda command: replace(command, items=(replace(command.items[0], is_double_pay=True),) + command.items[1:]), "handover_must_preserve_service_terms"),
])
def test_invalid_handover_is_rejected_by_domain(change, code):
    with pytest.raises(LeaveSubstitutionDomainError, match=code):
        build_leave_substitution_candidate(facts(), change(intent()))


def test_handover_requires_service_started_and_business_clock():
    current = facts()
    for source in (replace(current, business_date=None),
                   replace(current, assignment_plan=replace(current.assignment_plan, service_started=False))):
        with pytest.raises(LeaveSubstitutionDomainError):
            build_leave_substitution_candidate(source, intent())


def test_handover_mode_is_part_of_command_identity():
    command = intent()
    assert leave_request_fingerprint(command) != leave_request_fingerprint(replace(command, handover_date=None))


def test_handover_does_not_persist_new_leave_occupancy():
    from types import SimpleNamespace
    from infrastructure.mysql.leave_substitution_repository import _insert_leave_occupancy

    cursor = SimpleNamespace(executemany=lambda *_args: pytest.fail("handover must not create leave occupancy"))
    _insert_leave_occupancy(cursor, SimpleNamespace(intent=intent()), None, None, ())


def test_handover_preserves_prior_leave_occupancy_even_when_the_temporary_replacement_has_a_new_successor():
    from types import SimpleNamespace
    from infrastructure.mysql.scheduling_replacement_writer import _preserve_previous_leave_occupancy

    class Cursor:
        rowcount = 1
        calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchall(self):
            return ({"staff_id": 7, "occupancy_date": TODAY,
                     "resulting_staff_id": 8, "resulting_service_date": TODAY},)

    cursor = Cursor()
    command = SimpleNamespace(preserve_leave_occupancy=True, candidate=SimpleNamespace(assignments=(
        SimpleNamespace(staff_id=10, service_dates=(TODAY,)),)))
    _preserve_previous_leave_occupancy(cursor, command, 1, 2)
    assert cursor.calls[-1][1] == (2, 1)
    assert "SET generation_id=%s" in cursor.calls[-1][0]
    assert not any("cancelled" in sql for sql, _ in cursor.calls)


def test_long_substitute_period_groups_successor_and_keeps_daily_outcome_lineage():
    source=facts()
    result=build_leave_substitution_candidate(source,replace(intent(source),handover_date=None))
    successor=[a for a in result.scheduling.assignments if a.staff_id==8]
    assert len(successor)==1 and len(successor[0].service_dates)==18
    assert len(result.scheduling.assignments)==3
    assert successor[0].lineage_source_assignment_ids==(1,)
    assert len(result.outcomes)==18
    assert {o.original_schedule_id for o in result.outcomes}=={i.original_schedule_id for i in intent(source).items}
