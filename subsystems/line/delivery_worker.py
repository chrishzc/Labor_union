"""
File: delivery_worker.py
Description: 執行 LINE 耐久投遞，並在 provider 呼叫前重新確認任務未被取消。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from domains.line.delivery import LineDeliveryTaskSnapshot
from shared_kernel.identities import IdempotencyKey
from subsystems.line.delivery_contracts import (
    ClaimLineDeliveryTasksQuery,
    LineProviderOutcome,
    LineProviderOutcomeType,
    RecordLineDeliveryAttemptCommand,
)
from subsystems.line.ports import LineMessagingProviderPort, LineUnitOfWorkPort


class LineDeliveryWorker:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        provider: LineMessagingProviderPort,
        worker_identity: str,
        now: Callable[[], datetime],
        batch_size: int = 25,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._provider = provider
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size

    def run_once(self) -> int:
        claimed = self._claim()
        for task in claimed:
            if not self._still_sendable(task):
                continue
            outcome = self._send(task)
            self._record(task, outcome)
        return len(claimed)

    def _claim(self):
        query = ClaimLineDeliveryTasksQuery(
            self._worker_identity,
            self._now(),
            self._batch_size,
        )
        with self._unit_of_work_factory() as unit_of_work:
            tasks = unit_of_work.delivery_tasks.claim(query)
            unit_of_work.commit()
        return tasks

    def _send(self, task: LineDeliveryTaskSnapshot) -> LineProviderOutcome:
        try:
            return self._provider.send(task.request)
        except Exception as error:
            return LineProviderOutcome(
                LineProviderOutcomeType.UNAVAILABLE,
                error_code="line_provider_exception",
                error_message=str(error)[:500] or "LINE provider exception",
            )

    def _still_sendable(self, task: LineDeliveryTaskSnapshot) -> bool:
        """Re-read the leased task so cancellation cannot race through to LINE."""
        if task.lease is None:
            return False
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.delivery_tasks.get(task.task_id)
        return (
            current is not None
            and current.status.value == "processing"
            and current.lease is not None
            and current.lease.owner == task.lease.owner
            and current.lease.acquired_at == task.lease.acquired_at
        )

    def _record(self, task, outcome: LineProviderOutcome) -> None:
        if task.lease is None:
            raise RuntimeError("claimed LINE delivery task has no lease")
        command = RecordLineDeliveryAttemptCommand(
            task,
            task.lease,
            outcome,
            self._now(),
            _attempt_key(task),
            task.request.correlation_id,
        )
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.delivery_tasks.record_attempt(command)
            if outcome.outcome_type is LineProviderOutcomeType.SUCCESS:
                notification_rules = getattr(unit_of_work, "notification_rules", None)
                mark_accepted = getattr(
                    notification_rules, "mark_delivery_task_provider_accepted", None
                )
                if callable(mark_accepted):
                    mark_accepted(task.task_id.value)
            unit_of_work.commit()


def _attempt_key(task: LineDeliveryTaskSnapshot) -> IdempotencyKey:
    attempt_number = task.completed_attempts + 1
    return IdempotencyKey(
        f"line-delivery-attempt:{task.task_id.value}:{attempt_number}"
    )


__all__ = ["LineDeliveryWorker"]
