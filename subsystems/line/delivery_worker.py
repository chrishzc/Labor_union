"""
File: delivery_worker.py
Description: 執行 LINE 耐久投遞，並在 provider 呼叫前重新確認任務未被取消。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from domains.line.delivery import LineDeliveryStatus, LineDeliveryTaskSnapshot
from shared_kernel.identities import IdempotencyKey
from subsystems.line.delivery_contracts import (
    ClaimLineDeliveryTasksQuery,
    LineProviderOutcome,
    LineProviderOutcomeType,
    RecordLineDeliveryAttemptCommand,
)
from subsystems.line.ports import LineMessagingProviderPort, LineUnitOfWorkPort
from subsystems.line.notification_failure_current_fact import (
    append_line_notification_failure_rechecks,
)


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
            validation_failure = self._manual_replay_validation_failure(task)
            outcome = (
                LineProviderOutcome(
                    LineProviderOutcomeType.REJECTED,
                    error_code=validation_failure,
                    error_message="manual replay fresh validation failed",
                )
                if validation_failure is not None
                else self._send(task)
            )
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

    def _manual_replay_validation_failure(
        self, task: LineDeliveryTaskSnapshot
    ) -> str | None:
        with self._unit_of_work_factory() as unit_of_work:
            notification_rules = getattr(unit_of_work, "notification_rules", None)
            validator = getattr(
                notification_rules,
                "manual_replay_delivery_validation_failure",
                None,
            )
            return validator(task.task_id.value) if callable(validator) else None

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
            result = unit_of_work.delivery_tasks.record_attempt(command)
            if task.request.source_aggregate_type == "customer_service_escalation":
                status = result.plan.resulting_status
                if status in {LineDeliveryStatus.SENT, LineDeliveryStatus.FAILED}:
                    escalations = getattr(unit_of_work, "escalations", None)
                    if escalations is None:
                        raise RuntimeError("customer service escalation repository is required")
                    escalations.record_alert_delivery_outcome(
                        task.request.source_aggregate_identity,
                        command.idempotency_key.value,
                        status.value,
                    )
            notification_rules = getattr(unit_of_work, "notification_rules", None)
            if outcome.outcome_type is LineProviderOutcomeType.SUCCESS:
                mark_accepted = getattr(
                    notification_rules, "mark_delivery_task_provider_accepted", None
                )
                if callable(mark_accepted):
                    mark_accepted(task.task_id.value)
            target_reader = getattr(
                notification_rules,
                "line006_recheck_targets_for_delivery_task",
                None,
            )
            targets = (
                target_reader(task.task_id.value)
                if callable(target_reader)
                else ()
            )
            append_line_notification_failure_rechecks(
                unit_of_work,
                targets,
                cause_identity=command.idempotency_key.value,
            )
            unit_of_work.commit()


def _attempt_key(task: LineDeliveryTaskSnapshot) -> IdempotencyKey:
    attempt_number = task.completed_attempts + 1
    return IdempotencyKey(
        f"line-delivery-attempt:{task.task_id.value}:{attempt_number}"
    )


__all__ = ["LineDeliveryWorker"]
