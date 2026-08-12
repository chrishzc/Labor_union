"""Customer Service management application with atomic LINE delivery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from domains.customer_service.ticket import CustomerServiceStatus, transition_ticket
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from infrastructure.mysql.customer_service_repository import (
    CustomerServiceTicketNotFoundError,
    CustomerServiceVersionConflictError,
)
from subsystems.customer_service.contracts import (
    CustomerServiceListQuery,
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


__all__ = [
    "CustomerServiceApplication",
    "CustomerServiceTicketNotFoundError",
    "CustomerServiceVersionConflictError",
]
