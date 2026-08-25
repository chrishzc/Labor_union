"""
File: test_scheduling_current_projection_workflow.py
Description: 驗證 current Scheduling workflow 的時鐘狀態、占用與不可服務投影。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from domains.scheduling.current_projection import (
    AssignmentLifecycleStatus,
    EffectiveAssignmentCurrentFact,
    SchedulingCurrentFacts,
    SchedulingOccupancyKind,
    StaffUnavailabilityCurrentFact,
    StoredEffectiveOccupancyFact,
    WaitingDepositLockCurrentFact,
)
from domains.orders.terms import ServiceTimeTerms
from infrastructure.mysql.scheduling_current_projection_repository import (
    _assignments,
    _unavailability_blocks,
    _waiting_lock_fact,
)
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from subsystems.scheduling.current_projection_workflow import (
    SchedulingCurrentProjectionWorkflow,
    SchedulingCurrentQuery,
)


class _Repository:
    def __init__(self) -> None:
        self.request = None

    def load_current_facts(self, request):
        self.request = request
        return SchedulingCurrentFacts(request.staff_id, (), (), ())


class _FactsRepository:
    def __init__(self, facts: SchedulingCurrentFacts) -> None:
        self.facts = facts

    def load_current_facts(self, request):
        assert request.staff_id == self.facts.staff_id
        return self.facts


def test_current_projection_workflow_is_readable_source_without_bridge():
    source = Path("subsystems/scheduling/current_projection_workflow.py").read_text(encoding="utf-8")
    assert "load_preserved_module" not in source
    assert "_bytecode_bridge" not in source


def test_current_projection_query_uses_repository_facts_and_business_clock():
    repository = _Repository()
    clock = FixedBusinessClock(datetime(2026, 8, 3, 9, 0, tzinfo=TAIPEI_TIME_ZONE))
    request = SchedulingCurrentQuery(1, date(2026, 8, 3), date(2026, 8, 4))

    projection = SchedulingCurrentProjectionWorkflow(repository, clock).query(request)

    assert repository.request == request
    assert projection.staff_id == 1
    assert projection.evaluated_at == clock.now()
    assert projection.days[0].calendar_date == date(2026, 8, 3)


def test_current_projection_query_rejects_datetime_range_boundary():
    with pytest.raises(TypeError, match="range start must be a date"):
        SchedulingCurrentQuery(1, datetime(2026, 8, 3), date(2026, 8, 4))


def test_current_projection_marks_long_leave_as_unavailable():
    class Repository:
        def load_current_facts(self, request):
            block = StaffUnavailabilityCurrentFact(
                9,
                request.staff_id,
                "long_leave",
                date(2026, 8, 3),
                date(2026, 8, 4),
                "返鄉休息",
            )
            return SchedulingCurrentFacts(request.staff_id, (), (), (), (block,))

    workflow = SchedulingCurrentProjectionWorkflow(
        Repository(),
        FixedBusinessClock(datetime(2026, 8, 3, 9, 0, tzinfo=TAIPEI_TIME_ZONE)),
    )
    result = workflow.query(
        SchedulingCurrentQuery(1, date(2026, 8, 3), date(2026, 8, 5))
    )

    assert result.days[0].available is False
    assert result.days[0].entries[0].occupancy_kind is SchedulingOccupancyKind.STAFF_UNAVAILABILITY
    assert result.days[0].entries[0].unavailability_reason == "返鄉休息"
    assert result.days[2].available is True


def test_current_projection_repository_reads_unavailability_reason():
    class Cursor:
        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchall(self):
            return [
                {
                    "id": 9,
                    "staff_id": 1,
                    "block_kind": "paused_service",
                    "start_date": date(2026, 8, 3),
                    "end_date": None,
                    "reason": "暫停接新案",
                }
            ]

    cursor = Cursor()
    blocks = _unavailability_blocks(
        cursor,
        SchedulingCurrentQuery(1, date(2026, 8, 3), date(2026, 8, 5)),
    )

    assert "reason" in cursor.sql
    assert blocks[0].reason == "暫停接新案"


def test_current_projection_repository_fails_typed_when_generation_has_no_official_dates():
    class Cursor:
        def __init__(self):
            self.result_sets = [[], [], []]

        def execute(self, _sql, _params):
            return None

        def fetchall(self):
            return self.result_sets.pop(0)

    rows = (
        {
            "assignment_id": 21,
            "generation_id": 16,
        },
    )

    with pytest.raises(ValueError, match="^official_service_dates_incomplete$"):
        _assignments(Cursor(), rows)


def test_current_projection_accepts_waiting_lock_for_official_days_only():
    """固定週休不屬於等待訂金鎖的正式服務日，七日 buffer 另行投影。"""
    waiting_lock = WaitingDepositLockCurrentFact(
        7,
        9,
        "CASE-WAITING-REST",
        11,
        date(2026, 9, 10),
        date(2026, 9, 16),
        (
            date(2026, 9, 10),
            date(2026, 9, 11),
            date(2026, 9, 14),
            date(2026, 9, 15),
            date(2026, 9, 16),
        ),
    )
    facts = SchedulingCurrentFacts(11, (), (), (waiting_lock,))

    result = SchedulingCurrentProjectionWorkflow(
        _FactsRepository(facts),
        FixedBusinessClock(datetime(2026, 8, 24, 9, 0, tzinfo=TAIPEI_TIME_ZONE)),
    ).query(SchedulingCurrentQuery(11, date(2026, 9, 10), date(2026, 9, 23)))

    service_days = {
        day.calendar_date
        for day in result.days
        if any(
            entry.occupancy_kind is SchedulingOccupancyKind.WAITING_DEPOSIT_SERVICE
            for entry in day.entries
        )
    }
    buffer_days = {
        day.calendar_date
        for day in result.days
        if any(
            entry.occupancy_kind is SchedulingOccupancyKind.WAITING_DEPOSIT_BUFFER
            for entry in day.entries
        )
    }

    assert service_days == {
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
    }
    assert buffer_days == {
        date(2026, 9, 17),
        date(2026, 9, 18),
        date(2026, 9, 19),
        date(2026, 9, 20),
        date(2026, 9, 21),
        date(2026, 9, 22),
        date(2026, 9, 23),
    }


def test_waiting_lock_repository_excludes_stored_buffer_dates_from_service_facts():
    fact = _waiting_lock_fact(
        {
            "lock_id": 7,
            "segment_id": 9,
            "case_no": "CASE-WAITING-REST",
            "staff_id": 11,
            "assigned_start_date": date(2026, 9, 10),
            "assigned_end_date": date(2026, 9, 16),
        },
        (
            date(2026, 9, 10),
            date(2026, 9, 11),
            date(2026, 9, 14),
            date(2026, 9, 15),
            date(2026, 9, 16),
            date(2026, 9, 17),
            date(2026, 9, 18),
            date(2026, 9, 19),
            date(2026, 9, 20),
            date(2026, 9, 21),
            date(2026, 9, 22),
            date(2026, 9, 23),
        ),
    )

    assert fact.locked_service_dates == (
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
    )


def _assignment_with_active_buffer(
    *,
    assignment_id: int = 31,
    case_no: str = "CASE-SCH-BUFFER",
    generation_id: int = 41,
    assigned_date: date = date(2026, 8, 10),
    case_first_service_date: date | None = None,
) -> tuple[
    EffectiveAssignmentCurrentFact,
    tuple[StoredEffectiveOccupancyFact, ...],
]:
    buffer_dates = tuple(assigned_date + timedelta(days=offset) for offset in range(1, 8))
    assignment = EffectiveAssignmentCurrentFact(
        assignment_id,
        case_no,
        generation_id,
        3,
        11,
        assigned_date,
        assigned_date,
        case_first_service_date or assigned_date,
        (assigned_date,),
        buffer_dates,
        8,
        ServiceTimeTerms(time(9), time(17), 0),
    )
    occupancy = (
        StoredEffectiveOccupancyFact(
            11, assigned_date, generation_id, assignment_id, "assignment_interval"
        ),
        *(
            StoredEffectiveOccupancyFact(
                11, buffer_date, generation_id, assignment_id, "buffer"
            )
            for buffer_date in buffer_dates
        ),
    )
    return assignment, occupancy


@pytest.mark.parametrize(
    ("evaluated_at", "expected_status"),
    (
        (datetime(2026, 8, 10, 10, tzinfo=TAIPEI_TIME_ZONE), AssignmentLifecycleStatus.ACTIVE),
        (datetime(2026, 8, 10, 18, tzinfo=TAIPEI_TIME_ZONE), AssignmentLifecycleStatus.COMPLETED),
    ),
)
def test_current_projection_hides_assignment_buffer_after_service_starts(
    evaluated_at,
    expected_status,
):
    assignment, occupancy = _assignment_with_active_buffer()

    facts = SchedulingCurrentFacts(11, (assignment,), occupancy, ())
    projection = SchedulingCurrentProjectionWorkflow(
        _FactsRepository(facts), FixedBusinessClock(evaluated_at)
    ).query(SchedulingCurrentQuery(11, date(2026, 8, 10), date(2026, 8, 17)))

    assert projection.assignments[0].status is expected_status
    assert all(
        entry.occupancy_kind is not SchedulingOccupancyKind.ASSIGNMENT_BUFFER
        for day in projection.days
        for entry in day.entries
    )
    assert all(day.available for day in projection.days[1:])


def test_current_projection_keeps_assignment_buffer_before_service_starts():
    assignment, occupancy = _assignment_with_active_buffer()

    facts = SchedulingCurrentFacts(11, (assignment,), occupancy, ())
    projection = SchedulingCurrentProjectionWorkflow(
        _FactsRepository(facts),
        FixedBusinessClock(datetime(2026, 8, 9, 10, tzinfo=TAIPEI_TIME_ZONE)),
    ).query(SchedulingCurrentQuery(11, date(2026, 8, 10), date(2026, 8, 17)))

    assert projection.assignments[0].status is AssignmentLifecycleStatus.PLANNED
    assert sum(
        entry.occupancy_kind is SchedulingOccupancyKind.ASSIGNMENT_BUFFER
        for day in projection.days
        for entry in day.entries
    ) == 7


def test_current_projection_uses_case_start_fact_across_staff_scope():
    future_same_case, same_case_occupancy = _assignment_with_active_buffer(
        assignment_id=32,
        assigned_date=date(2026, 9, 1),
        case_first_service_date=date(2026, 8, 10),
    )
    future_other_case, other_case_occupancy = _assignment_with_active_buffer(
        assignment_id=33,
        case_no="CASE-SCH-OTHER",
        generation_id=42,
        assigned_date=date(2026, 9, 20),
    )
    facts = SchedulingCurrentFacts(
        11,
        (future_same_case, future_other_case),
        (*same_case_occupancy, *other_case_occupancy),
        (),
    )

    projection = SchedulingCurrentProjectionWorkflow(
        _FactsRepository(facts),
        FixedBusinessClock(datetime(2026, 8, 10, 10, tzinfo=TAIPEI_TIME_ZONE)),
    ).query(SchedulingCurrentQuery(11, date(2026, 9, 2), date(2026, 9, 27)))

    buffer_case_numbers = {
        entry.case_no
        for day in projection.days
        for entry in day.entries
        if entry.occupancy_kind is SchedulingOccupancyKind.ASSIGNMENT_BUFFER
    }
    assert projection.assignments[0].status is AssignmentLifecycleStatus.PLANNED
    assert buffer_case_numbers == {"CASE-SCH-OTHER"}
