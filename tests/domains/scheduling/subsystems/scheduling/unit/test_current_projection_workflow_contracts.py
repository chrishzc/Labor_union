"""Direct orchestration contracts for Scheduling current-projection workflow."""

from datetime import date, datetime, timezone

import pytest

import subsystems.scheduling.current_projection_workflow as workflow_module
from subsystems.scheduling.current_projection_workflow import (
    SchedulingCurrentProjectionWorkflow,
    SchedulingCurrentQuery,
)


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.requests = []

    def load_current_facts(self, query):
        self.requests.append(query)
        return self.facts


class _Clock:
    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now


def test_query_identity_requires_positive_staff_and_exact_date_bounds() -> None:
    request = SchedulingCurrentQuery(7, date(2026, 8, 1), date(2026, 8, 31))
    assert request.staff_id == 7

    for invalid_staff_id in (0, -1, True):
        with pytest.raises((TypeError, ValueError)):
            SchedulingCurrentQuery(invalid_staff_id, date(2026, 8, 1), date(2026, 8, 31))

    with pytest.raises(TypeError, match="range start"):
        SchedulingCurrentQuery(
            7,
            datetime(2026, 8, 1, tzinfo=timezone.utc),
            date(2026, 8, 31),
        )
    with pytest.raises(TypeError, match="range end"):
        SchedulingCurrentQuery(
            7,
            date(2026, 8, 1),
            datetime(2026, 8, 31, tzinfo=timezone.utc),
        )


def test_workflow_loads_current_facts_once_and_passes_clock_time_to_domain_builder(monkeypatch) -> None:
    request = SchedulingCurrentQuery(7, date(2026, 8, 1), date(2026, 8, 31))
    facts = object()
    repository = _Repository(facts)
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    expected_projection = object()
    calls = []

    def fake_builder(received_facts, range_start, range_end, evaluation_at):
        calls.append((received_facts, range_start, range_end, evaluation_at))
        return expected_projection

    monkeypatch.setattr(workflow_module, "build_scheduling_current_projection", fake_builder)

    result = SchedulingCurrentProjectionWorkflow(repository, _Clock(now)).query(request)

    assert result is expected_projection
    assert repository.requests == [request]
    assert calls == [(facts, request.range_start, request.range_end, now)]
