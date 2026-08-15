"""
File: import_warning_tracking_workflow.py
Description: 編排匯入警示追蹤的唯讀查詢與受版本保護的狀態轉態。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.anomalies.import_warning_tracking import (
    ImportWarningTrackingStatus,
    WarningTransitionError,
    preview_warning_transition,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


@dataclass(frozen=True, slots=True)
class ImportWarningTask:
    occurrence_identity: str
    owning_lane: str
    logical_code: str
    field_path: str
    masked_subject: str
    issue_codes: tuple[str, ...]
    tracking_status: ImportWarningTrackingStatus
    tracking_version: int
    evidence_reference: str | None


@dataclass(frozen=True, slots=True)
class WarningTransitionRequest:
    occurrence_identity: str
    expected_version: int
    target_status: ImportWarningTrackingStatus
    actor: ActorContext
    reason_code: str
    note: str | None
    evidence_reference: str | None
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class WarningTransitionPreview:
    occurrence_identity: str
    expected_version: int
    resulting_status: ImportWarningTrackingStatus
    resulting_version: int


class ImportWarningTrackingRepository(Protocol):
    def query_tasks(self, *, active_only: bool, limit: int, offset: int) -> tuple[ImportWarningTask, ...]: ...

    def load_task(self, occurrence_identity: str, *, for_update: bool) -> ImportWarningTask | None: ...

    def replay(
        self,
        request: WarningTransitionRequest,
    ) -> WarningTransitionPreview | None: ...

    def apply_transition(
        self,
        task: ImportWarningTask,
        request: WarningTransitionRequest,
        preview: WarningTransitionPreview,
    ) -> WarningTransitionPreview: ...


class ImportWarningTrackingApplication:
    def __init__(self, repository: ImportWarningTrackingRepository, unit_of_work_factory) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query_tasks(self, *, active_only: bool = True, limit: int = 100, offset: int = 0) -> tuple[ImportWarningTask, ...]:
        return self._repository.query_tasks(active_only=active_only, limit=limit, offset=offset)

    def preview(self, request: WarningTransitionRequest) -> WarningTransitionPreview:
        task = self._require_task(request.occurrence_identity, for_update=False)
        return self._preview(task, request)

    def apply(self, request: WarningTransitionRequest) -> WarningTransitionPreview:
        replay = self._repository.replay(request)
        if replay is not None:
            return replay
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._repository.replay(request)
            if replay is not None:
                return replay
            task = self._require_task(request.occurrence_identity, for_update=True)
            preview = self._preview(task, request)
            receipt = self._repository.apply_transition(task, request, preview)
            unit_of_work.commit()
        return receipt

    def _require_task(self, occurrence_identity: str, *, for_update: bool) -> ImportWarningTask:
        task = self._repository.load_task(occurrence_identity, for_update=for_update)
        if task is None:
            raise ValueError("import_warning_not_found")
        return task

    @staticmethod
    def _preview(task: ImportWarningTask, request: WarningTransitionRequest) -> WarningTransitionPreview:
        try:
            transition = preview_warning_transition(
                current_status=task.tracking_status,
                current_version=task.tracking_version,
                target_status=request.target_status,
                actor_kind="system" if request.actor.actor_id == "system" else "union_operator",
            )
        except WarningTransitionError as error:
            raise ValueError("import_warning_transition_not_allowed") from error
        if request.expected_version != task.tracking_version:
            raise ValueError("import_warning_version_conflict")
        return WarningTransitionPreview(
            occurrence_identity=task.occurrence_identity,
            expected_version=task.tracking_version,
            resulting_status=transition.resulting_status,
            resulting_version=task.tracking_version + 1,
        )


__all__ = [
    "ImportWarningTask",
    "ImportWarningTrackingApplication",
    "ImportWarningTrackingRepository",
    "WarningTransitionPreview",
    "WarningTransitionRequest",
]
