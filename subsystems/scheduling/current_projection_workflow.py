"""Read-only workflow for the current Scheduling projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from domains.scheduling.current_projection import (
    SchedulingCurrentFacts,
    SchedulingCurrentProjection,
    build_scheduling_current_projection,
)
from shared_kernel.clock import BusinessClock
from shared_kernel.validation import require_positive_integer


@dataclass(frozen=True, slots=True)
class SchedulingCurrentQuery:
    staff_id: int
    range_start: date
    range_end: date

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff id")
        if type(self.range_start) is not date:
            raise TypeError("range start must be a date")
        if type(self.range_end) is not date:
            raise TypeError("range end must be a date")


class SchedulingCurrentProjectionRepository(Protocol):
    def load_current_facts(
        self,
        query: SchedulingCurrentQuery,
    ) -> SchedulingCurrentFacts: ...


class SchedulingCurrentProjectionWorkflow:
    def __init__(
        self,
        repository: SchedulingCurrentProjectionRepository,
        clock: BusinessClock,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def query(
        self,
        request: SchedulingCurrentQuery,
    ) -> SchedulingCurrentProjection:
        facts = self._repository.load_current_facts(request)
        return build_scheduling_current_projection(
            facts,
            request.range_start,
            request.range_end,
            self._clock.now(),
        )
