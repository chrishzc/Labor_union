"""
File: delivery_admin_application.py
Description: 提供 LINE 投遞任務查詢與停用來源保護之重試／取消控制。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from domains.line.identities import LineDeliveryTaskId
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyReceipt
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.delivery_admin_contracts import (
    ControlLineDeliveryTaskCommand,
    LineDeliveryAdminQuery,
)
from subsystems.line.delivery_contracts import (
    CancelLineDeliveryTaskCommand,
    RETIRED_CONTRACT_DELIVERY_SOURCES,
    RETIRED_PAYMENT_RECEIPT_DELIVERY_SOURCES,
    customer_service_delivery_retired,
    retired_delivery_reason,
)
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort
from subsystems.line.notification_handling import delivery_handling, current_failure_target, failure_handling
from subsystems.line.notification_failure_current_fact import LineNotificationFailureCurrentFactQuery, LineNotificationFailureReason
from dataclasses import replace


class LineDeliveryTaskNotFoundError(LookupError):
    """Raised when an administrator addresses a missing canonical task."""


class LineDeliveryTaskStateConflictError(RuntimeError):
    """Raised when a task cannot accept the requested control action."""


class LineDeliveryTaskAdminApplication:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def summary(self, actor):
        require_line_capability(actor, LineCapability.TASK_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.delivery_tasks.summary(self._clock())

    def list(self, query: LineDeliveryAdminQuery, actor):
        require_line_capability(actor, LineCapability.TASK_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.delivery_tasks.list_admin(query)

    def get(self, task_id: LineDeliveryTaskId, actor):
        require_line_capability(actor, LineCapability.TASK_READ)
        with self._unit_of_work_factory() as unit_of_work:
            task = unit_of_work.delivery_tasks.get_admin(task_id)
            if task is None:
                raise LineDeliveryTaskNotFoundError(
                    f"找不到 LINE 發送任務 #{task_id.value}"
                )
            attempts = unit_of_work.delivery_tasks.attempts(task_id)
            return task, attempts

    def cancel(self, command: ControlLineDeliveryTaskCommand):
        return self._control("cancel", command)

    def handling(self, task, actor):
        with self._unit_of_work_factory() as unit:
            snapshot = unit.delivery_tasks.get(task.task_id)
            if snapshot is None:
                raise LineDeliveryTaskNotFoundError('找不到原寄送工作。')
            return self._handling(unit, task, actor, snapshot)

    def _handling(self, unit, task, actor, snapshot):
        target = current_failure_target(unit, task.task_id.value)
        result = delivery_handling(task, actor, target=target, request=snapshot.request)
        if target is None:
            return result
        projection = unit.anomaly_rechecks.query_current(target)
        if projection is None:
            raise LineDeliveryTaskStateConflictError('原通知異常已變動，請重新查詢。')
        subject = projection.candidate.subject_identity
        current = unit.notification_rules.current_failure_fact(LineNotificationFailureCurrentFactQuery(
            subject['case_no'], LineNotificationFailureReason(subject['notification_reason'])))
        records = [unit.delivery_tasks.get_admin(LineDeliveryTaskId(identity)) for identity in current.related_task_ids]
        if any(record is None for record in records):
            raise LineDeliveryTaskStateConflictError('原通知範圍尚未完整核對。')
        group = failure_handling(current, records, actor, target, can_replay=False)
        if group.blocked_reason:
            return replace(result, allowed_actions=(), blocked_reason=group.blocked_reason)
        if any(record.task_id != task.task_id and record.status.value in ('pending','processing','retryable_failed') for record in records):
            return replace(result, allowed_actions=tuple(action for action in result.allowed_actions if action!='retry'))
        return result

    def run_now(self, command: ControlLineDeliveryTaskCommand):
        return self._control("run_now", command)

    def retry(self, command: ControlLineDeliveryTaskCommand):
        return self._control("retry", command)

    def _control(self, action: str, command: ControlLineDeliveryTaskCommand):
        require_line_capability(command.actor, LineCapability.TASK_CONTROL)
        fingerprint = fingerprint_payload(
            {
                "action": action,
                "task_id": command.task_id.value,
                "reason": command.reason,
            }
        )
        result_reference = f"line-delivery:{command.task_id.value}:{action}"
        with self._unit_of_work_factory() as unit_of_work:
            existing = unit_of_work.receipts.get(command.idempotency_key)
            if existing is not None and (
                existing.payload_fingerprint != fingerprint
                or existing.result_reference != result_reference
            ):
                raise LineDeliveryTaskStateConflictError(
                    "LINE delivery control idempotency conflict"
                )
            current = unit_of_work.delivery_tasks.get(command.task_id, lock=True)
            if current is None:
                raise LineDeliveryTaskNotFoundError(
                    f"找不到 LINE 發送任務 #{command.task_id.value}"
                )
            if action != "cancel" and current.request.source_aggregate_type in RETIRED_CONTRACT_DELIVERY_SOURCES:
                raise LineDeliveryTaskStateConflictError("契約 LINE 投遞已停用，無法發送或重試。")
            if action != "cancel" and current.request.source_aggregate_type in RETIRED_PAYMENT_RECEIPT_DELIVERY_SOURCES:
                raise LineDeliveryTaskStateConflictError("入帳確認推播已停用，請改由官方帳號發送。")
            if action != "cancel" and customer_service_delivery_retired(current.request):
                raise LineDeliveryTaskStateConflictError("客服工單通知已停用，請於官方帳號處理對話。")
            if action != 'cancel' and retired_delivery_reason(current.request) is not None:
                raise LineDeliveryTaskStateConflictError('此通知來源已停用，無法發送或重試。')
            if existing is not None:
                return current
            if action == 'retry':
                record = unit_of_work.delivery_tasks.get_admin(command.task_id)
                handling = self._handling(unit_of_work, record, command.actor, current)
                if 'retry' not in handling.allowed_actions:
                    raise LineDeliveryTaskStateConflictError(handling.blocked_reason or '此來源已有其他工作或目前不允許重試。')
            if action == 'cancel':
                if current.status.value == 'processing':
                    raise LineDeliveryTaskStateConflictError('工作正在寄送，請先核對結果。')
                record = unit_of_work.delivery_tasks.get_admin(command.task_id)
                handling = delivery_handling(record, command.actor,
                    target=current_failure_target(unit_of_work, command.task_id.value), request=current.request)
                if handling.target_kind == 'notification_failure':
                    raise LineDeliveryTaskStateConflictError('請由原通知異常預覽並結清相關工作。')
                if current.status.value != 'cancelled' and 'cancel' not in handling.allowed_actions:
                    raise LineDeliveryTaskStateConflictError(handling.blocked_reason or '目前無法結清此工作。')
            try:
                task = self._apply_action(unit_of_work, action, command)
            except (ValueError, RuntimeError) as error:
                raise LineDeliveryTaskStateConflictError(str(error)) from error
            unit_of_work.receipts.append(
                IdempotencyReceipt(
                    command.idempotency_key,
                    fingerprint,
                    result_reference,
                ), result_snapshot={'action': f'line.delivery.{action}',
                    'task_ids': [command.task_id.value], 'reason': command.reason,
                    'actor_id': command.actor.actor_id, 'closed_at': self._clock().isoformat()}
            )
            unit_of_work.audit.append(
                LineAuditIntent(
                    f"line.delivery.{action}",
                    command.actor.actor_id,
                    "line_delivery_task",
                    str(command.task_id.value),
                )
            )
            unit_of_work.commit()
            return task

    def _apply_action(self, unit_of_work, action, command):
        if action == "cancel":
            return unit_of_work.delivery_tasks.cancel(
                CancelLineDeliveryTaskCommand(
                    command.task_id,
                    command.actor,
                    command.idempotency_key,
                    command.correlation_id,
                )
            )
        if action == "run_now":
            return unit_of_work.delivery_tasks.run_now(command.task_id, self._clock())
        if action == "retry":
            return unit_of_work.delivery_tasks.retry_failed(
                command.task_id,
                self._clock(),
            )
        raise ValueError("unsupported LINE delivery control action")


__all__ = [
    "LineDeliveryTaskAdminApplication",
    "LineDeliveryTaskNotFoundError",
    "LineDeliveryTaskStateConflictError",
]
