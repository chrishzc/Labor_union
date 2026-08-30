"""
File: application.py
Description: 協調客服查詢、結案與回覆 Preview／Apply，並在單一交易保存 receipt 與 delivery task。
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Callable

from domains.customer_service.ticket import (
    CustomerServiceStatus,
    CustomerServiceTicketNotFoundError,
    CustomerServiceTransitionError,
    CustomerServiceVersionConflictError,
    transition_ticket,
)
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyReceipt
from subsystems.customer_service.contracts import (
    ApplyCustomerServiceTicketReply,
    ApplyCustomerServiceTicketUpdate,
    CustomerServiceListQuery,
    CustomerServiceTicketReplyPreview,
    CustomerServiceTicketReplyResult,
    CustomerServiceTicketUpdatePreview,
    CustomerServiceTicketUpdateResult,
    PreviewCustomerServiceTicketReply,
    PreviewCustomerServiceTicketUpdate,
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
        return CustomerServiceTicketUpdateResult(
            ticket_id=result.ticket_id,
            resulting_status=result.status,
            resulting_version=result.version,
            preview_fingerprint=candidate.fingerprint,
            replayed=False,
            readback=detail,
        )

    def preview_reply(
        self, command: PreviewCustomerServiceTicketReply
    ) -> CustomerServiceTicketReplyPreview:
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.customer_service.get(command.ticket_id)
            candidate = _reply_candidate(current, command)
            return CustomerServiceTicketReplyPreview(
                ticket_id=current.ticket_id,
                before_status=current.status,
                after_status=candidate.target_status,
                current_version=current.version,
                expected_version=command.expected_version.value,
                reply_character_count=len(candidate.normalized_reply_text),
                will_enqueue_delivery=True,
                preview_fingerprint=candidate.fingerprint,
                apply_ready=True,
            )

    def apply_reply(
        self, command: ApplyCustomerServiceTicketReply
    ) -> CustomerServiceTicketReplyResult:
        with self._unit_of_work_factory() as unit_of_work:
            replay = unit_of_work.receipts.get(command.idempotency_key)
            if replay is not None:
                return _replay_reply(unit_of_work, command, replay)
            current = unit_of_work.customer_service.get(command.ticket_id, lock=True)
            candidate = _reply_candidate(current, command)
            if candidate.fingerprint != command.preview_fingerprint:
                raise CustomerServicePreviewFingerprintConflictError(
                    "客服回覆 Preview 已過期，請重新預覽"
                )
            event_key = f"customer-service-reply-apply:{command.idempotency_key.value}"
            unit_of_work.customer_service.append_agent_reply(
                command.ticket_id,
                event_key,
                candidate.normalized_reply_text,
                command.actor_id,
            )
            result = unit_of_work.customer_service.update(
                command.ticket_id,
                command.expected_version.value,
                candidate.target_status,
                candidate.normalized_internal_note,
                command.admin_user_id,
            )
            unit_of_work.delivery_tasks.enqueue(
                _reply_delivery(command, current.line_user_id, self._now())
            )
            unit_of_work.receipts.append(
                IdempotencyReceipt(
                    command.idempotency_key,
                    candidate.fingerprint,
                    _reply_result_reference(current, candidate),
                )
            )
            unit_of_work.audit.append(
                _audit("reply.apply", command.actor_id, result.ticket_id)
            )
            detail = unit_of_work.customer_service.detail(result.ticket_id)
            unit_of_work.commit()
        return _reply_result(command, candidate, result.version, detail, replayed=False)

    def _read(self, operation):
        with self._unit_of_work_factory() as unit_of_work:
            result = operation(unit_of_work.customer_service)
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


@dataclass(frozen=True, slots=True)
class _ReplyCandidate:
    target_status: CustomerServiceStatus
    normalized_reply_text: str
    normalized_internal_note: str | None
    fingerprint: PreviewFingerprint


def _update_candidate(current, status, internal_note, expected_version):
    if current.version != expected_version.value:
        raise CustomerServiceVersionConflictError(
            "客服需求已更新，請重新載入"
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


def _reply_candidate(current, command) -> _ReplyCandidate:
    if current.version != command.expected_version.value:
        raise CustomerServiceVersionConflictError(
            "客服需求已更新，請重新載入"
        )
    target = (
        CustomerServiceStatus.RESOLVED
        if command.resolve
        else CustomerServiceStatus.HANDLING
    )
    target = transition_ticket(current.status, target)
    normalized_reply = command.reply_text.strip()
    if not normalized_reply:
        raise ValueError("reply_text must not be blank")
    normalized_note = _optional_text(command.internal_note)
    fingerprint = _reply_fingerprint(
        command.ticket_id,
        normalized_reply,
        command.resolve,
        normalized_note,
        current.status,
        target,
        current.version,
    )
    return _ReplyCandidate(target, normalized_reply, normalized_note, fingerprint)


def _reply_fingerprint(
    ticket_id: int,
    reply_text: str,
    resolve: bool,
    internal_note: str | None,
    current_status: CustomerServiceStatus,
    target_status: CustomerServiceStatus,
    current_version: int,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "ticket_id": ticket_id,
            "reply_text": reply_text,
            "resolve": resolve,
            "normalized_internal_note": internal_note,
            "current_status": current_status.value,
            "target_status": target_status.value,
            "current_version": current_version,
        }
    )


def _reply_result_reference(current, candidate: _ReplyCandidate) -> str:
    return (
        f"customer-service-reply:{current.ticket_id}:{current.status.value}:"
        f"{current.version}:{candidate.target_status.value}"
    )


def _reply_result(
    command,
    candidate: _ReplyCandidate,
    resulting_version: int,
    readback: dict,
    *,
    replayed: bool,
) -> CustomerServiceTicketReplyResult:
    return CustomerServiceTicketReplyResult(
        ticket_id=command.ticket_id,
        resulting_status=candidate.target_status,
        resulting_version=resulting_version,
        preview_fingerprint=candidate.fingerprint,
        delivery_enqueued=True,
        delivery_delivered=False,
        replayed=replayed,
        readback=readback,
    )


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
    readback = unit_of_work.customer_service.detail(command.ticket_id)
    return CustomerServiceTicketUpdateResult(
        ticket_id=command.ticket_id,
        resulting_status=CustomerServiceStatus(readback["ticket"]["status"]),
        resulting_version=readback["ticket"]["version"],
        preview_fingerprint=command.preview_fingerprint,
        replayed=True,
        readback=readback,
    )


def _replay_reply(unit_of_work, command, receipt):
    reference = receipt.result_reference.split(":")
    if (
        len(reference) != 5
        or reference[:2] != ["customer-service-reply", str(command.ticket_id)]
        or reference[3] != str(command.expected_version.value)
    ):
        raise CustomerServiceIdempotencyMismatchError(
            "相同冪等鍵已用於不同客服回覆"
        )
    try:
        before_status = CustomerServiceStatus(reference[2])
        target_status = CustomerServiceStatus(reference[4])
    except ValueError as error:
        raise CustomerServiceIdempotencyMismatchError(
            "客服回覆冪等收據格式不符"
        ) from error
    normalized_reply = command.reply_text.strip()
    normalized_note = _optional_text(command.internal_note)
    expected_target = (
        CustomerServiceStatus.RESOLVED
        if command.resolve
        else CustomerServiceStatus.HANDLING
    )
    candidate = _ReplyCandidate(
        target_status,
        normalized_reply,
        normalized_note,
        _reply_fingerprint(
            command.ticket_id,
            normalized_reply,
            command.resolve,
            normalized_note,
            before_status,
            target_status,
            command.expected_version.value,
        ),
    )
    if (
        target_status is not expected_target
        or receipt.payload_fingerprint != candidate.fingerprint
        or receipt.payload_fingerprint != command.preview_fingerprint
    ):
        raise CustomerServiceIdempotencyMismatchError(
            "相同冪等鍵已用於不同客服回覆內容"
        )
    readback = unit_of_work.customer_service.detail(command.ticket_id)
    return _reply_result(
        command,
        candidate,
        command.expected_version.value + 1,
        readback,
        replayed=True,
    )


__all__ = [
    "CustomerServiceApplication",
    "CustomerServiceIdempotencyMismatchError",
    "CustomerServicePreviewFingerprintConflictError",
    "CustomerServiceTicketNotFoundError",
    "CustomerServiceVersionConflictError",
]
