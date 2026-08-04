from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from domains.scheduling.current_projection import SchedulingCurrentFacts
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
