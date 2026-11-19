"""
File: deposit_notifications.py
Description: 協調訂金提醒卡片、匯款回報與舊繳費求助按鈕的留言指引。
"""
from __future__ import annotations

from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.message_copy_catalog import configured_payload

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, Protocol
from urllib.parse import urlencode

from domains.line.delivery import LineDeliveryRequest, LineDeliveryTaskSnapshot, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineGroupId, LineSourceType, LineUserId
from domains.line.canonical_payload import canonical_line_payload_json
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey, IdempotencyReceipt, ActorContext
from subsystems.client_finance.deposit_payment_query import DepositPayment
from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
from subsystems.line.capabilities import LineCapability, require_line_capability

REMINDER = 'client_deposit_reminder'
SETTLED = 'client_deposit_settled'
ASSISTANCE_ACK = '如有繳款疑問，請直接在此官方帳號聊天室留言。'
PAYMENT_ACK_REPLY = '已收到您的回覆，感謝您。工會將於核對後通知，請耐心等候不需重複繳款。'
PAYMENT_ASSISTANCE_ACK = ASSISTANCE_ACK


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
            continuation = payment.notification_continuation
            if not continuation.eligible:
                raise DepositNotificationConflict('deposit_historical_continuation_not_ready')
            if not (continuation.historical or uow.deposit_notifications.contract_completed(case_no, lock=True)):
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
        if kind == SETTLED:
            raise DepositNotificationConflict('deposit_settled_push_retired')
        if not self._liff_id or self._liff_id == 'your_liff_id_here':
            raise DepositNotificationConflict('deposit_liff_not_configured')
        url = f'https://liff.line.me/{self._liff_id}/?' + urlencode({'target': 'deposit_payment', 'case_no': payment.case_no})
        payload = deposit_notification_payload(
            payment.case_no,
            payment.amount_ntd,
            payment.due_date,
            kind,
            url,
            virtual_account=payment.virtual_account,
        )
        if unit is not None:
            payload = configured_payload(unit, 'deposit-reminder', payload,
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
             and payment.notification_continuation.eligible
             and (payment.notification_continuation.allows_automatic_payment(payment.due_date)
                  or request.idempotency_key.value.startswith('deposit-reminder:'))
             and recipient == request.recipient.identity.value
             and payment.settled == (request.source_aggregate_type == SETTLED)
             and (request.source_aggregate_type != REMINDER
                  or payment.notification_continuation.historical
                  or uow.deposit_notifications.contract_completed(case_no, lock=True)))
    if not valid:
        uow.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
            task.task_id, ActorContext('line-deposit-worker'),
            IdempotencyKey(f'deposit-stale:{task.task_id.value}'), request.correlation_id,
        ))
        uow.commit()
    return valid


def handle_payment_reminder_postback(data: str, event, uow, *, reply_only: bool = False) -> bool:
    match_ack = re.fullmatch(r"^payment-ack:(deposit|first|second):([A-Za-z0-9_-]{1,50})$", data)
    match_ast = re.fullmatch(r"^(?:payment-assistance:(deposit|first|second)|deposit-assistance):([A-Za-z0-9_-]{1,50})$", data)
    if match_ack is None and match_ast is None:
        return False
    if match_ack is None and not reply_only:
        return True
    stage = match_ack.group(1) if match_ack else (match_ast.group(1) or 'deposit')
    case_no = match_ack.group(2) if match_ack else match_ast.group(2)

    source = event.source
    line_user_id = source.user_id
    if line_user_id is None:
        return True

    source_type = getattr(source, 'source_type', LineSourceType.USER)
    source_id = getattr(source, 'source_id', getattr(line_user_id, 'value', ''))
    if source_type is LineSourceType.GROUP and source_id:
        reply_recipient = LineRecipient(LineRecipientType.GROUP, LineGroupId(str(source_id)))
    else:
        customer_id = uow.deposit_notifications.customer_line_user_id(case_no, lock=True)
        if customer_id and customer_id != line_user_id.value:
            return True
        reply_recipient = LineRecipient(LineRecipientType.USER, line_user_id)

    event_digest = sha256(event.event_id.value.encode()).hexdigest()
    reply_action = 'ack' if match_ack is not None else 'assistance-directions'
    key = IdempotencyKey(f'payment-{reply_action}:{stage}:{event_digest}')
    if match_ack is None:
        text = '如有繳款疑問，請直接在此案件群組留言。' if source_type is LineSourceType.GROUP else ASSISTANCE_ACK
        payload = {'type': 'text', 'text': text}
    else:
        payload = configured_payload(uow, 'payment-reminder-ack', {'type': 'text', 'text': PAYMENT_ACK_REPLY})
    if match_ack is not None and not reply_only:
        from subsystems.line.ports import LineAuditIntent

        receipt_key = IdempotencyKey(f'payment-ack:{stage}:{case_no}')
        receipt_expected = IdempotencyReceipt(
            receipt_key,
            fingerprint_payload({'case_no': case_no, 'stage': stage, 'user_id': line_user_id.value}),
            json.dumps({'case_no': case_no, 'stage': stage, 'action': 'paid_reported'}, ensure_ascii=False),
        )
        if uow.receipts.get(receipt_key, for_update=True) is None:
            uow.receipts.append(receipt_expected)
        uow.audit.append(LineAuditIntent('payment_reminder_acknowledged', line_user_id.value, f'payment_{stage}', case_no))
        if uow.delivery_tasks.exists_for_key(key):
            return True

    uow.delivery_tasks.enqueue(LineDeliveryRequest(
        reply_recipient, LineMessageKind.TEXT,
        canonical_line_payload_json(payload),
        event.occurred_at, key, CorrelationId(f'line-event:{event.event_id.value}'),
        REPLY_ONLY_WEBHOOK_SOURCE, event.event_id.value,
    ))
    return True


def handle_deposit_assistance(data, event, uow, *, reply_only=False) -> bool:
    if data.startswith(('deposit-assistance:', 'payment-assistance:', 'payment-ack:')):
        return handle_payment_reminder_postback(data, event, uow, reply_only=reply_only)
    return False


def deposit_notification_payload(
    case_no,
    amount_ntd,
    due_date,
    kind,
    url=None,
    *,
    bank_account_info=None,
    virtual_account=None,
):
    if kind == SETTLED:
        raise DepositNotificationConflict('deposit_settled_push_retired')
    amount_str = f'{amount_ntd:,}' if isinstance(amount_ntd, int) else str(amount_ntd)
    text = f'案件〈{case_no}〉訂金 NT${amount_str}，請於{due_date}前完成匯款。若已完成匯款，請點選下方「已經匯款」，工會將於核對後通知。'
    actions = [
        {'type': 'button', 'style': 'primary', 'action': {'type': 'postback', 'label': '已經匯款', 'data': f'payment-ack:deposit:{case_no}', 'displayText': '已經匯款'}},
    ]

    from subsystems.line.service_start_messages import resolve_case_bank_account_info, build_bank_account_box

    if bank_account_info is None:
        if virtual_account:
            import os

            b_name = os.getenv("CLIENT_DEPOSIT_BANK_NAME", "永豐銀行")
            b_code = os.getenv("CLIENT_DEPOSIT_BANK_CODE", "807")
            bank_account_info = {
                "bank_name": b_name,
                "bank_code": b_code,
                "virtual_account": str(virtual_account),
                "account_note": "案件專屬帳號",
            }
        elif case_no and not str(case_no).startswith("{"):
            bank_account_info = resolve_case_bank_account_info(None, case_no)

    bank_box = build_bank_account_box(bank_account_info)
    body_contents = [
        {'type': 'text', 'text': text, 'wrap': True},
    ]
    if bank_box:
        body_contents.append(bank_box)
    body_contents.append({'type': 'text', 'text': ASSISTANCE_ACK, 'size': 'sm', 'wrap': True})

    payload = {'type': 'flex', 'altText': f'案件〈{case_no}〉訂金繳費提醒：NT${amount_str}', 'contents': {'type': 'bubble',
               'header': {'type': 'box', 'layout': 'vertical', 'contents': [{'type': 'text', 'text': '訂金繳費提醒', 'weight': 'bold', 'size': 'lg'}]},
               'body': {'type': 'box', 'layout': 'vertical', 'spacing': 'sm', 'contents': body_contents},
               'footer': {'type': 'box', 'layout': 'vertical', 'contents': actions}}}
    return payload
