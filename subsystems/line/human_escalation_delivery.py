"""Project bounded Customer Service alert intents into canonical LINE delivery.

This bounded worker validates the bounded alert, creates the durable canonical
LINE delivery task, and records the Customer Service task readback. Provider
I/O and delivery retries remain owned by LineDeliveryWorker.

Timeout/5xx retry and retry exhaustion remain the existing delivery-task
semantics from LINE Access §3.3: only the task retries, then becomes failed
with a manual fallback; the Customer Service ticket and automation hold are
not rolled back. Customer Service §20 defines no separate escalation timeout
state, so this worker does not invent one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineGroupId, LineRoomId, LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.outbox_contracts import ClaimLineOutboxQuery, CompleteLineOutboxCommand, LineOutboxWorkItem


HUMAN_ESCALATION_INTENT = "line.customer_service.human_escalation"
_SOURCE_TYPE = "customer_service_escalation"


class HumanEscalationDeliveryError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class HumanEscalationOutboxItem:
    outbox_id: int
    aggregate_identity: str
    payload: Mapping[str, Any]
    attempt_count: int
    maximum_attempts: int
    lease_owner: str
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class HumanEscalationDeliveryReceipt:
    escalation_ref: str
    task_id: int
    task_status: LineDeliveryStatus
    recipient_snapshot: Mapping[str, Any]
    provider_status: str
    outcome_ref: str | None
    replayed: bool


class HumanEscalationDeliveryApplication:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], object],
        now: Callable[[], datetime],
        worker_identity: str,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now
        del worker_identity

    def consume(self, item: HumanEscalationOutboxItem) -> HumanEscalationDeliveryReceipt:
        request, target = _request(item, self._now())
        with self._unit_of_work_factory() as uow:
            result = uow.delivery_tasks.enqueue(request)
            task = uow.delivery_tasks.get(result.task_id)
            if task is None:
                raise HumanEscalationDeliveryError("human_escalation_delivery_task_readback_missing")
            escalations = getattr(uow, "escalations", None)
            if escalations is None:
                raise HumanEscalationDeliveryError("human_escalation_escalation_repository_missing")
            escalations.record_alert_delivery_task(item.aggregate_identity, task.task_id.value)
            outcome_ref = None
            if task.status in {LineDeliveryStatus.SENT, LineDeliveryStatus.FAILED}:
                outcome_ref = f"delivery-task:{task.task_id.value}:{task.status.value}"
                escalations.record_alert_delivery_outcome(
                    item.aggregate_identity,
                    outcome_ref,
                    task.status.value,
                )
            uow.outbox.complete(CompleteLineOutboxCommand(item_to_work(item), self._now()))
            uow.commit()
        return HumanEscalationDeliveryReceipt(
            item.aggregate_identity,
            task.task_id.value,
            task.status,
            target,
            task.status.value,
            outcome_ref,
            result.outcome.value == "existing",
        )


class HumanEscalationDeliveryWorker:
    def __init__(self, unit_of_work_factory, worker_identity: str, now: Callable[[], datetime], *, batch_size: int = 25):
        self._unit_of_work_factory = unit_of_work_factory
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size
        self._failures: tuple[tuple[str, str], ...] = ()

    @property
    def failures(self) -> tuple[tuple[str, str], ...]:
        return self._failures

    def run_once(self) -> int:
        with self._unit_of_work_factory() as uow:
            items = uow.outbox.claim(ClaimLineOutboxQuery(
                self._worker_identity, self._now(), self._batch_size, HUMAN_ESCALATION_INTENT
            ))
            uow.commit()
        failures = []
        app = HumanEscalationDeliveryApplication(self._unit_of_work_factory, self._now, self._worker_identity)
        for raw in items:
            item = _item(raw)
            try:
                app.consume(item)
            except HumanEscalationDeliveryError as error:
                failures.append((item.aggregate_identity, error.code))
                self._fail(item, error.code)
        self._failures = tuple(failures)
        return len(items)

    def _fail(self, item: HumanEscalationOutboxItem, code: str) -> None:
        terminal = item.attempt_count + 1 >= item.maximum_attempts
        with self._unit_of_work_factory() as uow:
            try:
                uow.escalations.record_alert_delivery_outcome(
                    item.aggregate_identity, "manual-fallback:" + code, "failed"
                )
            except Exception:
                pass
            uow.outbox.complete(CompleteLineOutboxCommand(
                item_to_work(item), self._now(), code, "bounded alert delivery requires manual recovery",
                retryable=not terminal,
            ))
            uow.commit()


def _request(item: HumanEscalationOutboxItem, now: datetime) -> tuple[LineDeliveryRequest, dict[str, Any]]:
    payload = item.payload
    if payload.get("urgency") != "high" or payload.get("hold_state") != "active":
        raise HumanEscalationDeliveryError("human_escalation_bounded_intent_invalid")
    target = payload.get("target_snapshot")
    if not isinstance(target, Mapping):
        raise HumanEscalationDeliveryError("human_escalation_alert_target_missing")
    if target.get("active") is not True or not isinstance(target.get("configuration"), Mapping):
        raise HumanEscalationDeliveryError("human_escalation_alert_target_snapshot_invalid")
    recipient_type = str(target.get("recipient_type", ""))
    identity = str(target.get("recipient_identity", ""))
    try:
        kind = LineRecipientType(recipient_type)
        recipient_identity = {
            LineRecipientType.USER: LineUserId,
            LineRecipientType.GROUP: LineGroupId,
            LineRecipientType.ROOM: LineRoomId,
        }[kind](identity)
    except (KeyError, TypeError, ValueError) as error:
        raise HumanEscalationDeliveryError("human_escalation_alert_recipient_invalid") from error
    safe_summary = str(payload.get("safe_summary", ""))
    category = str(payload.get("category", ""))
    if not safe_summary or not category or "line_user_id" in safe_summary.lower():
        raise HumanEscalationDeliveryError("human_escalation_bounded_payload_invalid")
    message = canonical_line_payload_json({
        "type": "text",
        "text": f"客服人工升級（{category}）：{safe_summary}",
    })
    request = LineDeliveryRequest(
        LineRecipient(kind, recipient_identity), LineMessageKind.TEXT, message, now,
        IdempotencyKey("human-escalation-delivery:" + item.aggregate_identity),
        CorrelationId(str(payload.get("correlation_id", "human-escalation-delivery"))),
        _SOURCE_TYPE, item.aggregate_identity,
    )
    return request, dict(target)


def _item(raw: LineOutboxWorkItem) -> HumanEscalationOutboxItem:
    try:
        payload = json.loads(raw.payload_json)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise HumanEscalationDeliveryError("human_escalation_bounded_payload_invalid") from error
    if not isinstance(payload, Mapping):
        raise HumanEscalationDeliveryError("human_escalation_bounded_payload_invalid")
    return HumanEscalationOutboxItem(
        raw.outbox_id, raw.aggregate_identity, payload, raw.attempt_count,
        raw.maximum_attempts, raw.lease_owner, raw.lease_expires_at,
    )


def item_to_work(item: HumanEscalationOutboxItem) -> LineOutboxWorkItem:
    return LineOutboxWorkItem(
        item.outbox_id, _SOURCE_TYPE, item.aggregate_identity, HUMAN_ESCALATION_INTENT,
        json.dumps(item.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        item.attempt_count, item.maximum_attempts, item.lease_owner, item.lease_expires_at,
    )


__all__ = [
    "HUMAN_ESCALATION_INTENT", "HumanEscalationDeliveryApplication", "HumanEscalationDeliveryError",
    "HumanEscalationDeliveryReceipt", "HumanEscalationDeliveryWorker", "HumanEscalationOutboxItem",
]
