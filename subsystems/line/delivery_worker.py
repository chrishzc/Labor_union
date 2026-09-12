"""
File: delivery_worker.py
Description: 執行 LINE 耐久投遞，並在 provider 呼叫前重新確認任務未被取消。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

from domains.line.delivery import LineDeliveryStatus, LineDeliveryTaskSnapshot
from shared_kernel.identities import IdempotencyKey
from subsystems.line.delivery_contracts import (
    ClaimLineDeliveryTasksQuery,
    LineProviderOutcome,
    LineProviderOutcomeType,
    LineReplyOpportunity,
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
        processed = 0
        # Do not spend later tasks' leases waiting for earlier provider calls.
        for _ in range(self._batch_size):
            claimed = self._claim()
            if not claimed:
                break
            task, = claimed
            processed += 1
            validation_failure = self._manual_replay_validation_failure(task)
            if not self._still_sendable(task):
                continue
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
        return processed

    def _claim(self):
        query = ClaimLineDeliveryTasksQuery(
            self._worker_identity,
            self._now(),
            1,
        )
        with self._unit_of_work_factory() as unit_of_work:
            tasks = unit_of_work.delivery_tasks.claim(query)
            unit_of_work.commit()
        return tasks

    def _send(self, task: LineDeliveryTaskSnapshot) -> LineProviderOutcome:
        reply = self._reply_opportunity(task)
        if reply is not None and self._now() < reply.expires_at:
            return self._reply(task, reply)
        try:
            return self._provider.send(task.request)
        except Exception as error:
            return LineProviderOutcome(
                LineProviderOutcomeType.UNAVAILABLE,
                error_code="line_provider_exception",
                error_message=str(error)[:500] or "LINE provider exception",
            )

    def _reply_opportunity(
        self,
        task: LineDeliveryTaskSnapshot,
    ) -> LineReplyOpportunity | None:
        if (
            task.request.source_aggregate_type != "knowledge_answer_request"
            or task.completed_attempts != 0
        ):
            return None
        with self._unit_of_work_factory() as unit_of_work:
            resolver = getattr(unit_of_work.delivery_tasks, "reply_opportunity", None)
            return (
                resolver(task.request.correlation_id)
                if callable(resolver)
                else None
            )

    def _reply(
        self,
        task: LineDeliveryTaskSnapshot,
        opportunity: LineReplyOpportunity,
    ) -> LineProviderOutcome:
        try:
            message = json.loads(task.request.payload_json)
            outcome = self._provider.reply(opportunity.reply_token, message)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            return LineProviderOutcome(
                LineProviderOutcomeType.REJECTED,
                error_code="line_reply_payload_invalid",
                error_message=str(error)[:500] or "LINE reply payload is invalid",
            )
        except Exception as error:
            return LineProviderOutcome(
                LineProviderOutcomeType.UNAVAILABLE,
                error_code="line_reply_outcome_uncertain",
                error_message=str(error)[:500] or "LINE reply outcome is uncertain",
            )
        if outcome.outcome_type is LineProviderOutcomeType.RATE_LIMITED:
            return self._send_push(task)
        # A 5xx response can follow an accepted reply.  A push retry key cannot
        # deduplicate that separate reply request, so do not fall back to push.
        if outcome.outcome_type in {
            LineProviderOutcomeType.TIMEOUT,
            LineProviderOutcomeType.UNAVAILABLE,
        }:
            return LineProviderOutcome(
                outcome.outcome_type,
                error_code="line_reply_outcome_uncertain",
                error_message="LINE reply outcome is uncertain; push fallback suppressed",
            )
        return outcome

    def _send_push(self, task: LineDeliveryTaskSnapshot) -> LineProviderOutcome:
        try:
            return self._provider.send(task.request)
        except Exception as error:
            return LineProviderOutcome(
                LineProviderOutcomeType.UNAVAILABLE,
                error_code="line_provider_exception",
                error_message=str(error)[:500] or "LINE provider exception",
            )

    def _still_sendable(self, task: LineDeliveryTaskSnapshot) -> bool:
        """Confirm the current task still holds the same unexpired lease."""
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
            and current.lease.expires_at == task.lease.expires_at
            and self._now() < current.lease.expires_at
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
            retry_allowed=outcome.error_code != "line_reply_outcome_uncertain",
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
