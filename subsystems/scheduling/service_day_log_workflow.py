"""
File: service_day_log_workflow.py
Description: 協調月嫂已驗證身分、服務日所有權、日誌完成、receipt 與 Scheduling outbox。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.scheduling.service_day_log import ServiceDayLogIntent, require_service_day_log_completion


@dataclass(frozen=True, slots=True)
class SubmitServiceDayLog:
    staff_id: int
    line_user_id: str
    assignment_id: int
    intent: ServiceDayLogIntent
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ServiceDayLogResult:
    log_id: int
    case_no: str
    service_date: str
    requires_cooking: bool
    outcome: str


class ServiceDayLogRepository(Protocol):
    def load_assignment(self, staff_id: int, assignment_id: int, service_date): ...
    def submit(self, command: SubmitServiceDayLog, assignment) -> ServiceDayLogResult: ...


class ServiceDayLogWorkflow:
    def __init__(self, repository: ServiceDayLogRepository) -> None:
        self._repository = repository

    def submit(self, command: SubmitServiceDayLog) -> ServiceDayLogResult:
        assignment = self._repository.load_assignment(
            command.staff_id, command.assignment_id, command.intent.service_date
        )
        require_service_day_log_completion(
            command.intent, requires_cooking=assignment["requires_cooking"]
        )
        return self._repository.submit(command, assignment)


__all__ = ["ServiceDayLogResult", "ServiceDayLogWorkflow", "SubmitServiceDayLog"]
