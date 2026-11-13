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
    CancelLineDeliveryTaskCommand,
    ClaimLineDeliveryTasksQuery,
    LineProviderOutcome,
    LineProviderOutcomeType,
    LineReplyOpportunity,
    REPLY_ONLY_WEBHOOK_SOURCE,
    RETIRED_SIGNING_REMINDER_SOURCES,
    RecordLineDeliveryAttemptCommand,
    candidate_coordination_delivery_retired,
)
from shared_kernel.identities import ActorContext
from subsystems.line.ports import LineMessagingProviderPort, LineUnitOfWorkPort
from subsystems.line.deposit_notifications import deposit_delivery_is_current
from subsystems.line.service_start_day import start_day_delivery_is_current
from subsystems.line.second_payment_notifications import second_payment_delivery_is_current
from subsystems.line.service_completion_notifications import service_completion_delivery_is_current
from subsystems.line.service_day_log_reminders import service_day_log_reminder_delivery_is_current
from subsystems.line.payment_overdue_reminders import payment_overdue_delivery_is_current
from subsystems.line.payment_reminder_notifications import payment_reminder_delivery_is_current
from subsystems.line.payment_receipt_notifications import payment_receipt_delivery_is_current
from subsystems.line.cancellation_notifications import SOURCE as CANCELLATION_NOTICE_SOURCE, cancellation_notice_delivery_is_current
from subsystems.line.order_group_application import group_invitation_delivery_is_current
from subsystems.line.notification_failure_current_fact import (
    append_line_notification_failure_rechecks,
)


def service_start_delivery_is_current(unit, task):
    if task.request.source_aggregate_type=='matching_schedule_recipient':
        unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('service-start-worker'),
            IdempotencyKey(f'retired-schedule:{task.task_id.value}'),task.request.correlation_id))
        unit.commit()
        return False
    if task.request.source_aggregate_type not in {'service_start_inquiry','service_start_invitation','service_start_schedule'}:
        return True
    valid=unit.service_starts.delivery_is_current(task)
    if not valid:
        unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('service-start-worker'),
            IdempotencyKey(f'service-start-stale:{task.task_id.value}'),task.request.correlation_id))
        unit.commit()
    return valid


class LineDeliveryWorker:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        provider: LineMessagingProviderPort | None,
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
        # Preserve the existing claim contract's bounds for each cycle.
        budget = ClaimLineDeliveryTasksQuery(
            self._worker_identity, self._now(), self._batch_size
        )
        processed = 0
        # Do not spend later tasks' leases waiting for earlier provider calls.
        for _ in range(budget.batch_size):
            claimed = self._claim()
            if not claimed:
                break
            task, = claimed
            processed += 1
            self._deliver_claimed(task)
        return processed

    def deliver_webhook_reply(self, task: LineDeliveryTaskSnapshot) -> None:
        if task.request.source_aggregate_type != REPLY_ONLY_WEBHOOK_SOURCE or task.lease is None:
            raise ValueError("webhook Reply requires a Reply-only task")
        self._deliver_claimed(task, webhook_reply=True)

    def _deliver_claimed(self, task: LineDeliveryTaskSnapshot, *, webhook_reply: bool = False) -> None:
        validation_failure = self._manual_replay_validation_failure(task)
        if not self._still_sendable(task):
            return
        retired_key_prefix = {
            "line_admin_push_retired": "retired-admin-push",
            "candidate_coordination_retired": "retired-candidate-coordination",
            "contract_signing_reminder_retired": "retired-contract-signing-reminder",
        }.get(validation_failure)
        if retired_key_prefix is not None:
            with self._unit_of_work_factory() as unit:
                unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
                    task.task_id, ActorContext(self._worker_identity),
                    IdempotencyKey(f"{retired_key_prefix}:{task.task_id.value}"), task.request.correlation_id,
                ))
                unit.commit()
            return
        outcome = (
            LineProviderOutcome(
                LineProviderOutcomeType.REJECTED,
                error_code=validation_failure,
                error_message="manual replay fresh validation failed",
            )
            if validation_failure is not None
            else self._send(task, webhook_reply=webhook_reply)
        )
        self._record(task, outcome)

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

    def _send(self, task: LineDeliveryTaskSnapshot, *, webhook_reply: bool = False) -> LineProviderOutcome:
        if task.request.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE:
            if webhook_reply:
                reply = self._reply_opportunity(task)
                if reply is not None and self._now() < reply.expires_at:
                    return self._reply(task, reply)
            return LineProviderOutcome(
                LineProviderOutcomeType.REJECTED,
                error_code="line_reply_token_unavailable" if webhook_reply else "line_reply_webhook_window_closed",
                error_message="Reply opportunity unavailable in the webhook request",
            )
        if (task.request.source_aggregate_type == "knowledge_answer_request"
                and task.request.correlation_id.value.startswith("line-event:")):
            return LineProviderOutcome(
                LineProviderOutcomeType.REJECTED,
                error_code="line_chat_knowledge_reply_retired",
                error_message="Background knowledge answers cannot use a LINE webhook Reply",
            )
        return self._send_push(task)

    def _reply_opportunity(
        self,
        task: LineDeliveryTaskSnapshot,
    ) -> LineReplyOpportunity | None:
        if task.completed_attempts != 0:
            return None
        if task.request.correlation_id.value != f"line-event:{task.request.source_aggregate_identity}":
            return None
        with self._unit_of_work_factory() as unit_of_work:
            resolver = getattr(unit_of_work.delivery_tasks, "reply_opportunity", None)
            if not callable(resolver):
                return None
            return resolver(task.request.correlation_id, recipient=task.request.recipient)

    def _reply(
        self,
        task: LineDeliveryTaskSnapshot,
        opportunity: LineReplyOpportunity,
    ) -> LineProviderOutcome:
        if self._provider is None:
            return LineProviderOutcome(
                LineProviderOutcomeType.REJECTED,
                error_code="line_reply_provider_unavailable",
                error_message="LINE Reply provider is unavailable",
            )
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
            cancellation = task.request.source_aggregate_type == CANCELLATION_NOTICE_SOURCE
            if cancellation:
                # Read after locking Orders and Finance, before any snapshot read of the task.
                source_current = cancellation_notice_delivery_is_current(unit_of_work, task)
                current = unit_of_work.delivery_tasks.get(task.task_id, lock=True)
            else:
                current = unit_of_work.delivery_tasks.get(task.task_id)
            lease_valid = (
                current is not None
                and current.status.value == "processing"
                and current.lease is not None
                and current.lease.owner == task.lease.owner
                and current.lease.acquired_at == task.lease.acquired_at
                and current.lease.expires_at == task.lease.expires_at
                and self._now() < current.lease.expires_at
            )
            if cancellation:
                if lease_valid and not source_current:
                    unit_of_work.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
                        task.task_id, ActorContext(self._worker_identity),
                        IdempotencyKey(f"cancellation-notice-stale:{task.task_id.value}"), task.request.correlation_id,
                    ))
                    unit_of_work.commit()
                if lease_valid and source_current:
                    # A crash after this commit leaves evidence that the provider may have received the request.
                    unit_of_work.payment_receipt_notifications.mark_cancellation_notice_provider_started(task.task_id.value)
                    unit_of_work.commit()
                return lease_valid and source_current
            if (lease_valid and task.request.source_aggregate_type == "matching_notification_intent"
                    and not unit_of_work.matching_notifications.customer_confirmation_delivery_is_current(
                        task.request.source_aggregate_identity,
                    )):
                unit_of_work.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
                    task.task_id, ActorContext(self._worker_identity),
                    IdempotencyKey(f"matching-confirmation-stale:{task.task_id.value}"), task.request.correlation_id,
                ))
                unit_of_work.commit()
                return False
            return (lease_valid
                    and service_completion_delivery_is_current(unit_of_work, task)
                    and payment_overdue_delivery_is_current(unit_of_work, task, self._now())
                    and payment_reminder_delivery_is_current(unit_of_work, task, self._now())
                    and payment_receipt_delivery_is_current(unit_of_work, task, self._now())
                    and service_day_log_reminder_delivery_is_current(unit_of_work, task, self._now())
                    and second_payment_delivery_is_current(unit_of_work, task, self._now())
                    and start_day_delivery_is_current(unit_of_work, task, self._now())
                    and deposit_delivery_is_current(unit_of_work, task, self._now())
                    and group_invitation_delivery_is_current(unit_of_work, task)
                    and service_start_delivery_is_current(unit_of_work, task))

    def _manual_replay_validation_failure(
        self, task: LineDeliveryTaskSnapshot
    ) -> str | None:
        if task.request.source_aggregate_type in RETIRED_SIGNING_REMINDER_SOURCES:
            return "contract_signing_reminder_retired"
        if candidate_coordination_delivery_retired(task.request):
            return "candidate_coordination_retired"
        if task.request.source_aggregate_type in {"runtime_health_event", "customer_service_escalation"}:
            return "line_admin_push_retired"
        if task.request.source_aggregate_type in {'staff_leave_customer_coordination', 'staff_leave_customer_decision'}:
            return 'leave_customer_confirmation_retired'
        if task.request.source_aggregate_type=='matching_schedule_recipient':
            return 'schedule_confirmation_retired'
        if (task.request.source_aggregate_type == "matching_coordination_outbox"
                and task.request.source_aggregate_identity.endswith(":zero-candidate:client-decision")):
            return "matching_zero_pool_notification_retired"
        if (task.request.recipient.recipient_type.value == "group"
                and task.request.source_aggregate_type == "matching_plan_decision"):
            return "line_alert_group_retired"
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
            retry_allowed=(task.request.source_aggregate_type != REPLY_ONLY_WEBHOOK_SOURCE
                           and outcome.error_code != "line_reply_outcome_uncertain"),
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
