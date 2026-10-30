"""Staff-initiated payment reminders and committed settlement notifications."""
from __future__ import annotations

from subsystems.line.message_copy_catalog import configured_payload

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, Protocol
from urllib.parse import urlencode

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.delivery import LineDeliveryRequest, LineDeliveryTaskSnapshot, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from domains.line.canonical_payload import canonical_line_payload_json
from shared_kernel.identities import CorrelationId, IdempotencyKey, ActorContext
from subsystems.client_finance.deposit_payment_query import DepositPayment
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
from subsystems.line.capabilities import LineCapability, require_line_capability

REMINDER = 'client_deposit_reminder'
SETTLED = 'client_deposit_settled'
ASSISTANCE_ACK = '已收到您的聯絡需求，請留下您的疑問。'


class DepositNotificationConflict(ValueError):
    pass


class DepositPaymentForbidden(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DepositSettlementIntent:
    intent_id: int
    case_no: str
    settlement_identity: str


@dataclass(frozen=True, slots=True)
class DepositNotificationTodo:
    payment: DepositPayment
    line_bound: bool
    delivery_status: str | None


@dataclass(frozen=True, slots=True)
class DepositNotificationTodoPage:
    items: tuple[DepositNotificationTodo, ...]
    total: int
    unpaid_total: int
    settled_total: int
    page_total: int
    has_next: bool


class DepositNotificationPort(Protocol):
    def contract_completed(self, case_no: str, *, lock: bool = False) -> bool: ...
    def customer_line_user_id(self, case_no: str, *, lock: bool = False) -> str | None: ...
    def next_settlement(self) -> DepositSettlementIntent | None: ...
    def existing_delivery(self, key: IdempotencyKey) -> LineDeliveryTaskSnapshot | None: ...
    def followups(self, *, page: int = 1, page_size: int = 25, settled: bool | None = None, case_no: str | None = None) -> DepositNotificationTodoPage: ...


def payment_source(payment: DepositPayment) -> str:
    # This is a delivery source identity, not a human Preview/Confirm fingerprint.
    value = [payment.obligation_identity, payment.obligation_version, payment.amount_ntd,
             str(payment.due_date), payment.virtual_account, payment.settlement_identity]
    return payment.case_no + ':' + sha256(json.dumps(value).encode()).hexdigest()


def settlement_key(payment: DepositPayment) -> IdempotencyKey:
    return IdempotencyKey('deposit-settled:' + str(payment.settlement_identity))


class DepositNotificationApplication:
    run_before_delivery = True
    def __init__(self, uow_factory, now, *, liff_id: str, bank_code: str = ''):
        self._uow_factory, self._now = uow_factory, now
        self._liff_id, self._bank_code = liff_id.strip(), bank_code.strip()

    def query_customer(self, case_no: str, line_user_id: str) -> DepositPayment:
        with self._uow_factory() as uow:
            self._require_customer(uow, case_no, line_user_id)
            payment = uow.deposit_payments.get(case_no)
            if payment is None:
                raise DepositNotificationConflict('deposit_payment_not_available')
            return payment

    def ready(self, payment: DepositPayment) -> bool:
        return not self.missing_reminder_fields(payment)

    def missing_reminder_fields(self, payment: DepositPayment) -> tuple[Literal['due_date','virtual_account','bank_code','liff'], ...]:
        missing: list[Literal['due_date','virtual_account','bank_code','liff']] = []
        if not payment.due_date:
            missing.append('due_date')
        if not re.fullmatch(r'[0-9]{10,20}', payment.virtual_account or ''):
            missing.append('virtual_account')
        if not re.fullmatch(r'[0-9]{3}', self._bank_code):
            missing.append('bank_code')
        if not self._liff_id or self._liff_id == 'your_liff_id_here':
            missing.append('liff')
        return tuple(missing)

    @property
    def bank_code(self) -> str | None:
        return self._bank_code if re.fullmatch(r'[0-9]{3}', self._bank_code) else None

    def send_reminder(self, case_no, expected_version, idempotency_key, actor):
        from subsystems.line.ports import LineAuditIntent

        require_line_capability(actor, LineCapability.TASK_SEND)
        key = IdempotencyKey('deposit-reminder:' + sha256(f'{actor.actor_id}:{idempotency_key.value}'.encode()).hexdigest())
        with self._uow_factory() as uow:
            payment = uow.deposit_payments.get(case_no, lock=True)
            if payment is None:
                raise DepositNotificationConflict('deposit_payment_not_available')
            existing = uow.deposit_notifications.existing_delivery(key)
            if existing is not None:
                if (existing.request.source_aggregate_identity.split(':', 1)[0] != case_no
                        or existing.request.source_aggregate_type != REMINDER):
                    raise DepositNotificationConflict('deposit_reminder_idempotency_conflict')
                uow.commit()
                return existing.task_id.value, existing.status.value
            if payment.settled or payment.obligation_version != expected_version:
                raise DepositNotificationConflict('deposit_payment_changed')
            if not uow.deposit_notifications.contract_completed(case_no, lock=True):
                raise DepositNotificationConflict('deposit_contract_not_completed')
            if not self.ready(payment):
                raise DepositNotificationConflict('deposit_payment_details_incomplete')
            recipient = uow.deposit_notifications.customer_line_user_id(case_no, lock=True)
            if recipient is None:
                raise DepositNotificationConflict('deposit_customer_not_bound')
            if uow.payment_reminder_notifications.pending(payment.obligation_identity):
                raise DepositNotificationConflict('deposit_reminder_in_flight')
            result = uow.delivery_tasks.enqueue(self._request(payment, recipient, REMINDER, key, uow))
            uow.audit.append(LineAuditIntent('deposit_reminder_queued', actor.actor_id, REMINDER, str(result.task_id.value)))
            uow.commit()
            return result.task_id.value, result.status.value

    def run_once(self):
        """Committed receipts remain human-send todos; scanning never authorizes delivery."""
        return 0

    def _require_customer(self, uow, case_no, line_user_id):
        current = uow.deposit_notifications.customer_line_user_id(case_no)
        if not current or current != line_user_id:
            raise DepositPaymentForbidden('deposit_payment_forbidden')

    def _request(self, payment, recipient, kind, key, unit=None):
        if not self._liff_id or self._liff_id == 'your_liff_id_here':
            raise DepositNotificationConflict('deposit_liff_not_configured')
        url = f'https://liff.line.me/{self._liff_id}/?' + urlencode({'target': 'deposit_payment', 'case_no': payment.case_no})
        payload = deposit_notification_payload(payment.case_no, payment.amount_ntd, payment.due_date, kind, url)
        if unit is not None:
            payload = configured_payload(unit, 'deposit-settled' if kind == SETTLED else 'deposit-reminder', payload,
                {'case_no': payment.case_no, 'amount_ntd': f'{payment.amount_ntd:,}', 'due_date': str(payment.due_date)})
        return LineDeliveryRequest(LineRecipient(LineRecipientType.USER, LineUserId(recipient)), LineMessageKind.FLEX,
                                   canonical_line_payload_json(payload), self._now(), key,
                                   CorrelationId(key.value), kind, payment_source(payment))


def deposit_delivery_is_current(uow, task, now) -> bool:
    """Fresh provider-boundary guard; never sends old amounts, old bindings or reversed settlements."""
    request = task.request
    if request.source_aggregate_type not in (REMINDER, SETTLED):
        return True
    case_no = request.source_aggregate_identity.split(':', 1)[0]
    payment = uow.deposit_payments.get(case_no, lock=True)
    recipient = uow.deposit_notifications.customer_line_user_id(case_no, lock=True)
    valid = (request.source_aggregate_type != SETTLED
             and payment is not None and payment_source(payment) == request.source_aggregate_identity
             and recipient == request.recipient.identity.value
             and payment.settled == (request.source_aggregate_type == SETTLED)
             and (request.source_aggregate_type != REMINDER
                  or uow.deposit_notifications.contract_completed(case_no, lock=True)))
    if not valid:
        uow.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
            task.task_id, ActorContext('line-deposit-worker'),
            IdempotencyKey(f'deposit-stale:{task.task_id.value}'), request.correlation_id,
        ))
        uow.commit()
    return valid


def handle_deposit_assistance(data, event, uow) -> bool:
    if not data.startswith('deposit-assistance:'):
        return False
    case_no = data.removeprefix('deposit-assistance:')
    line_user_id = event.source.user_id
    if (line_user_id is None or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', case_no)
            or uow.deposit_notifications.customer_line_user_id(case_no, lock=True) != line_user_id.value
            or uow.deposit_payments.get(case_no, lock=True) is None):
        return True
    key = IdempotencyKey('deposit-assistance:' + sha256(event.event_id.value.encode()).hexdigest())
    ticket = uow.customer_service.create_or_append(CreateCustomerServiceMessage(
        line_user_id.value, CustomerServiceCategory.OTHER,
        f'客戶詢問訂金繳費；案件 {case_no}，請查看後續留言。', key.value, case_no=case_no,
    ))
    uow.delivery_tasks.enqueue(LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, line_user_id), LineMessageKind.TEXT,
        canonical_line_payload_json(configured_payload(uow, 'deposit-assistance', {'type': 'text', 'text': ASSISTANCE_ACK})),
        event.occurred_at, key, CorrelationId(f'line-event:{event.event_id.value}'),
        'customer_service_assistance_ack', str(ticket.ticket_id),
    ))
    return True


def deposit_notification_payload(case_no, amount_ntd, due_date, kind, url):
    paid = kind == SETTLED
    text = (f'案件〈{case_no}〉訂金 NT${amount_ntd:,}已確認入帳，謝謝您。' if paid else
            f'案件〈{case_no}〉訂金 NT${amount_ntd:,}，請於{due_date}前完成匯款。')
    actions = [{'type': 'button', 'action': {'type': 'uri', 'label': '查看繳費狀態' if paid else '查看繳費資訊', 'uri': url}}]
    if not paid:
        actions.append({'type': 'button', 'action': {'type': 'postback', 'label': '專人協助',
                                                  'data': f'deposit-assistance:{case_no}'}})
    payload = {'type': 'flex', 'altText': text, 'contents': {'type': 'bubble',
               'body': {'type': 'box', 'layout': 'vertical', 'contents': [{'type': 'text', 'text': text, 'wrap': True}]},
               'footer': {'type': 'box', 'layout': 'vertical', 'contents': actions}}}
    return payload
