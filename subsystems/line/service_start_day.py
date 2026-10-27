"""Group-only start-day inquiry; the webhook consumer owns the transaction."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
from typing import Protocol

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineSourceType
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey, IdempotencyReceipt
from subsystems.customer_service.contracts import CreateCustomerServiceMessage

EVENT_CODE = 'order.service_start_day'
SOURCE_TYPE = 'order_service_start_day'
EVENT_PREFIX = 'order-service-start-day:'
_POSTBACK = re.compile(r'^start-day:([0-9a-f]{64}):(normal|help)$')


def start_day_response_text(decision: str) -> str:
    """The committed group acknowledgement and its display-only preview share copy."""
    return {
        'normal': '已收到，祝您服務順利。',
        'help': '已收到您的協助需求，請留下遇到的狀況。',
    }[decision]


@dataclass(frozen=True, slots=True)
class StartDayCaregiver:
    staff_id: int
    name: str


@dataclass(frozen=True, slots=True)
class ServiceStartDayCandidate:
    case_no: str
    service_date: date
    group_id: str
    generation_id: int
    first_payment_amount: int
    caregivers: tuple[StartDayCaregiver, ...]

    def facts(self) -> dict[str, object]:
        return {'case_no': self.case_no, 'service_date': self.service_date.isoformat(),
                'group_id': self.group_id, 'generation_id': self.generation_id,
                'first_payment_amount_ntd': self.first_payment_amount,
                'caregivers': [{'staff_id': item.staff_id, 'name': item.name} for item in self.caregivers]}

    @property
    def token(self) -> str:
        # Immutable source identity, never a client-supplied concurrency token.
        return hashlib.sha256(canonical_line_payload_json(self.facts()).encode('utf-8')).hexdigest()


class ServiceStartDayRepositoryPort(Protocol):
    def response_context(self, token: str, group_id: str, line_user_id: str) -> ServiceStartDayCandidate | None: ...
    def delivery_is_current(self, task: object, now: datetime) -> bool: ...


class ServiceStartDayPostbackApplication:
    def handle(self, inbox, unit) -> bool:
        payload = json.loads(inbox.event.payload_json)
        postback = payload.get('postback')
        data = postback.get('data', '') if isinstance(postback, dict) else ''
        if not isinstance(data, str) or not data.startswith('start-day:'):
            return False
        match = _POSTBACK.fullmatch(data)
        event = inbox.event
        source = event.source
        if (match is None or source.source_type is not LineSourceType.GROUP
                or source.user_id is None or source.group_id is None):
            return True
        token, decision = match.groups()
        context = unit.service_start_days.response_context(token, source.group_id.value, source.user_id.value)
        if context is None:
            return True
        # The context lock serializes different webhook IDs for the same case.
        # A later request for assistance remains possible after a normal reply.
        key = IdempotencyKey(f'start-day-response:{token}:{source.user_id.value}:{decision}')
        if unit.receipts.get(key, for_update=True) is not None:
            return True
        ticket_id = None
        if decision == 'help':
            ticket = unit.customer_service.create_or_append(CreateCustomerServiceMessage(
                line_user_id=source.user_id.value,
                category=CustomerServiceCategory.SERVICE_PROGRESS,
                message=f'服務開始日協助需求：案件 {context.case_no}，服務日期 {context.service_date.isoformat()}。請查看本案服務群組並協助處理。',
                event_key=key.value, case_no=context.case_no,
            ))
            ticket_id = ticket.ticket_id
        message = start_day_response_text(decision)
        unit.delivery_tasks.enqueue(LineDeliveryRequest(
            LineRecipient(LineRecipientType.GROUP, source.group_id), LineMessageKind.TEXT,
            canonical_line_payload_json({'type': 'text', 'text': message}), event.occurred_at,
            IdempotencyKey('ack:' + key.value), CorrelationId('start-day:' + event.event_id.value),
            'order_service_start_day_response', token,
        ))
        unit.receipts.append(IdempotencyReceipt(key, fingerprint_payload({
            'token': token, 'line_user_id': source.user_id.value, 'decision': decision,
        }), json.dumps({'decision': decision, 'ticket_id': ticket_id}, ensure_ascii=False)))
        return True


def start_day_delivery_is_current(unit, task, now):
    from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
    from shared_kernel.identities import ActorContext

    retired = task.request.correlation_id.value.startswith('line-notification:order-pre-start-reminder:')
    if not retired and task.request.source_aggregate_type not in {SOURCE_TYPE, 'order_service_start_day_response'}:
        return True
    if not retired and unit.service_start_days.delivery_is_current(task, now):
        return True
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
        task.task_id, ActorContext('service-start-day-worker'),
        IdempotencyKey(f'start-day-stale:{task.task_id.value}'), task.request.correlation_id,
    ))
    unit.commit()
    return False
