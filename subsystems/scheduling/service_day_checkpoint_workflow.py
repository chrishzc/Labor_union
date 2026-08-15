"""
File: service_day_checkpoint_workflow.py
Description: 在每日正式服務時段結束後，建立不可變寶寶日誌 checkpoint；沒有服務時段或下廚條件時 fail closed。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class ServiceDayCheckpointCandidate:
    assignment_id: int
    schedule_id: int
    case_no: str
    staff_id: int
    service_date: str
    service_ends_at_utc: datetime
    requires_cooking: bool


class ServiceDayCheckpointRepository(Protocol):
    def due_candidates(self, now: datetime, limit: int) -> tuple[ServiceDayCheckpointCandidate, ...]: ...
    def append_checkpoint(self, candidate: ServiceDayCheckpointCandidate) -> bool: ...


class ServiceDayCheckpointWorker:
    def __init__(
        self,
        repository_factory: Callable[[], ServiceDayCheckpointRepository],
        commit: Callable[[], None],
        now: Callable[[], datetime],
        *,
        limit: int = 100,
    ) -> None:
        self._repository_factory = repository_factory
        self._commit = commit
        self._now = now
        self._limit = limit

    def run_once(self) -> int:
        now = self._now()
        repository = self._repository_factory()
        candidates = repository.due_candidates(now, self._limit)
        created = sum(repository.append_checkpoint(candidate) for candidate in candidates)
        if created:
            self._commit()
        return created


__all__ = [
    "ServiceDayCheckpointCandidate",
    "ServiceDayCheckpointRepository",
    "ServiceDayCheckpointWorker",
]
