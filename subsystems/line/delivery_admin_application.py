"""Canonical query and control service for durable LINE delivery tasks."""

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
from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort


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
            if existing is not None:
                if (
                    existing.payload_fingerprint != fingerprint
                    or existing.result_reference != result_reference
                ):
                    raise LineDeliveryTaskStateConflictError(
                        "LINE delivery control idempotency conflict"
                    )
                task = unit_of_work.delivery_tasks.get(command.task_id)
                if task is None:
                    raise LineDeliveryTaskNotFoundError(
                        f"找不到 LINE 發送任務 #{command.task_id.value}"
                    )
                return task
            if unit_of_work.delivery_tasks.get(command.task_id) is None:
                raise LineDeliveryTaskNotFoundError(
                    f"找不到 LINE 發送任務 #{command.task_id.value}"
                )
            try:
                task = self._apply_action(unit_of_work, action, command)
            except (ValueError, RuntimeError) as error:
                raise LineDeliveryTaskStateConflictError(str(error)) from error
            unit_of_work.receipts.append(
                IdempotencyReceipt(
                    command.idempotency_key,
                    fingerprint,
                    result_reference,
                )
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
