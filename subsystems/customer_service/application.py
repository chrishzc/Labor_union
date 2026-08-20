"""
File: application.py
Description: 協調客服查詢、結案 Preview／Apply 與既有 LINE 回覆的單一交易流程。
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Callable

from domains.customer_service.ticket import CustomerServiceStatus, transition_ticket
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from infrastructure.mysql.customer_service_repository import (
    CustomerServiceTicketNotFoundError,
    CustomerServiceVersionConflictError,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyReceipt
from subsystems.customer_service.contracts import (
    ApplyCustomerServiceTicketUpdate,
    CustomerServiceListQuery,
    CustomerServiceTicketUpdatePreview,
    PreviewCustomerServiceTicketUpdate,
    ReplyCustomerServiceTicket,
    UpdateCustomerServiceTicket,
)
from subsystems.line.ports import LineAuditIntent


class CustomerServiceApplication:
    def __init__(self, unit_of_work_factory: Callable, now: Callable[[], datetime] | None = None) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def summary(self):
        return self._read(lambda repository: repository.summary())

    def list(self, query: CustomerServiceListQuery):
        return self._read(lambda repository: repository.list(query))

    def detail(self, ticket_id: int):
        return self._read(lambda repository: repository.detail(ticket_id))

    def preview_update(
        self, command: PreviewCustomerServiceTicketUpdate
    ) -> CustomerServiceTicketUpdatePreview:
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.customer_service.get(command.ticket_id)
            candidate = _update_candidate(
                current,
                command.status,
                command.internal_note,
                command.expected_version,
            )
            return CustomerServiceTicketUpdatePreview(
                ticket_id=current.ticket_id,
                before_status=current.status,
                after_status=candidate.target_status,
                current_version=current.version,
                expected_version=command.expected_version.value,
                blockers=(),
                preview_fingerprint=candidate.fingerprint,
                apply_ready=True,
            )

    def apply_update(self, command: ApplyCustomerServiceTicketUpdate):
        with self._unit_of_work_factory() as unit_of_work:
            replay = unit_of_work.receipts.get(command.idempotency_key)
            if replay is not None:
                return _replay_update(unit_of_work, command, replay)
            current = unit_of_work.customer_service.get(command.ticket_id, lock=True)
            candidate = _update_candidate(
                current,
                command.status,
                command.internal_note,
                command.expected_version,
            )
            if candidate.fingerprint != command.preview_fingerprint:
                raise CustomerServicePreviewFingerprintConflictError(
                    "客服結案 Preview 已過期，請重新預覽"
                )
            result_reference = _update_result_reference(
                command.ticket_id,
                command.expected_version,
                current.status,
            )
            event_key = (
                "customer-service-update-apply:"
                f"{command.idempotency_key.value}"
            )
            unit_of_work.customer_service.append_management_event(
                command.ticket_id,
                event_key,
                "status_changed",
                candidate.target_status.value,
                command.actor_id,
            )
            result = unit_of_work.customer_service.update(
                command.ticket_id,
                command.expected_version.value,
                candidate.target_status,
                candidate.normalized_internal_note,
                _admin_id(command.actor_id),
            )
            unit_of_work.receipts.append(
                IdempotencyReceipt(
                    command.idempotency_key,
                    candidate.fingerprint,
                    result_reference,
                )
            )
            unit_of_work.audit.append(
                _audit("update.apply", command.actor_id, result.ticket_id)
            )
            detail = unit_of_work.customer_service.detail(result.ticket_id)
            unit_of_work.commit()
        return detail

    def update(self, command: UpdateCustomerServiceTicket):
        event_key = f"customer-service-update:{command.idempotency_key.value}"
        with self._unit_of_work_factory() as unit_of_work:
            replay = unit_of_work.customer_service.get_by_event_key(event_key)
            if replay is not None:
                unit_of_work.commit()
                return unit_of_work.customer_service.detail(replay.ticket_id)
            current = unit_of_work.customer_service.get(command.ticket_id, lock=True)
            target = transition_ticket(current.status, command.status)
            unit_of_work.customer_service.append_management_event(
                command.ticket_id, event_key, "status_changed", target.value, command.actor_id
            )
            result = unit_of_work.customer_service.update(
                command.ticket_id, command.expected_version.value, target,
                _optional_text(command.internal_note), _admin_id(command.actor_id),
            )
            unit_of_work.audit.append(_audit("update", command.actor_id, result.ticket_id))
            detail = unit_of_work.customer_service.detail(result.ticket_id)
            unit_of_work.commit()
        return detail

    def reply(self, command: ReplyCustomerServiceTicket):
        event_key = f"customer-service-reply:{command.idempotency_key.value}"
        with self._unit_of_work_factory() as unit_of_work:
            replay = unit_of_work.customer_service.get_by_event_key(event_key)
            if replay is not None:
                unit_of_work.commit()
                return unit_of_work.customer_service.detail(replay.ticket_id)
            current = unit_of_work.customer_service.get(command.ticket_id, lock=True)
            target = CustomerServiceStatus.RESOLVED if command.resolve else CustomerServiceStatus.HANDLING
            transition_ticket(current.status, target)
            result = self._persist_reply(unit_of_work, command, current, target, event_key)
            detail = unit_of_work.customer_service.detail(result.ticket_id)
            unit_of_work.commit()
        return detail

    def _persist_reply(self, unit_of_work, command, current, target, event_key):
        unit_of_work.customer_service.append_agent_reply(
            command.ticket_id, event_key, command.reply_text.strip(), command.actor_id
        )
        result = unit_of_work.customer_service.update(
            command.ticket_id, command.expected_version.value, target,
            _optional_text(command.internal_note), command.admin_user_id,
        )
        delivery = _reply_delivery(command, current.line_user_id, self._now())
        unit_of_work.delivery_tasks.enqueue(delivery)
        unit_of_work.audit.append(_audit("reply", command.actor_id, result.ticket_id))
        return result

    def _read(self, operation):
        with self._unit_of_work_factory() as unit_of_work:
            result = operation(unit_of_work.customer_service)
            unit_of_work.commit()
        return result


def _reply_delivery(command, line_user_id, now):
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId(line_user_id)), LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": command.reply_text.strip()}), now,
        command.idempotency_key, command.correlation_id, "customer_service_ticket", str(command.ticket_id),
    )


def _audit(action, actor_id, ticket_id):
    return LineAuditIntent(f"customer_service.ticket.{action}", actor_id, "customer_service_ticket", str(ticket_id))


def _admin_id(actor_id: str) -> int | None:
    value = actor_id.removeprefix("admin:")
    return int(value) if value.isdigit() else None


def _optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


class CustomerServicePreviewFingerprintConflictError(RuntimeError):
    """Raised when Apply no longer matches the authoritative Preview facts."""


class CustomerServiceIdempotencyMismatchError(RuntimeError):
    """Raised when one idempotency key is replayed with different content."""


@dataclass(frozen=True, slots=True)
class _UpdateCandidate:
    target_status: CustomerServiceStatus
    normalized_internal_note: str | None
    fingerprint: PreviewFingerprint


def _update_candidate(current, status, internal_note, expected_version):
    if current.version != expected_version.value:
        raise CustomerServiceVersionConflictError(
            "客服需求已更新，請重新載入"
        )
    if status is not CustomerServiceStatus.RESOLVED:
        raise CustomerServiceTransitionError(
            "purpose-specific customer-service update only accepts resolved"
        )
    target = transition_ticket(current.status, status)
    normalized_note = _optional_text(internal_note)
    fingerprint = fingerprint_payload(
        {
            "ticket_id": current.ticket_id,
            "status": target.value,
            "normalized_internal_note": normalized_note,
            "current_status": current.status.value,
            "current_version": current.version,
        }
    )
    return _UpdateCandidate(target, normalized_note, fingerprint)


def _update_result_reference(
    ticket_id: int,
    expected_version,
    before_status: CustomerServiceStatus,
) -> str:
    return (
        f"customer-service-ticket:{ticket_id}:"
        f"{before_status.value}:{expected_version.value}"
    )


def _replay_update(unit_of_work, command, receipt):
    reference = receipt.result_reference.split(":")
    expected_prefix = ["customer-service-ticket", str(command.ticket_id)]
    if (
        len(reference) != 4
        or reference[:2] != expected_prefix
        or reference[3] != str(command.expected_version.value)
    ):
        raise CustomerServiceIdempotencyMismatchError(
            "相同冪等鍵已用於不同客服操作"
        )
    try:
        before_status = CustomerServiceStatus(reference[2])
    except ValueError as error:
        raise CustomerServiceIdempotencyMismatchError(
            "客服操作冪等收據格式不符"
        ) from error
    candidate = fingerprint_payload(
        {
            "ticket_id": command.ticket_id,
            "status": command.status.value,
            "normalized_internal_note": _optional_text(command.internal_note),
            "current_status": before_status.value,
            "current_version": command.expected_version.value,
        }
    )
    if (
        receipt.payload_fingerprint != candidate
        or receipt.payload_fingerprint != command.preview_fingerprint
    ):
        raise CustomerServiceIdempotencyMismatchError(
            "相同冪等鍵已用於不同客服內容"
        )
    return unit_of_work.customer_service.detail(command.ticket_id)


__all__ = [
    "CustomerServiceApplication",
    "CustomerServiceIdempotencyMismatchError",
    "CustomerServicePreviewFingerprintConflictError",
    "CustomerServiceTicketNotFoundError",
    "CustomerServiceVersionConflictError",
]
