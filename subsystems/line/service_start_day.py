"""
File: service_start_day.py
Description: 發送開工當天群組文字問候，並處理客戶的第一期款回覆。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from typing import Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineGroupId, LineSourceType
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey, IdempotencyReceipt
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.message_copy_catalog import configured_payload

SOURCE_TYPE = 'order_service_start_day'
GREETING_SOURCE = 'order_service_start_greeting'
GREETING_NO_GROUP_AUDIT = 'service_start_greeting_no_group'
_RETIRED_REPORT_REPLY_KEYS = ('ack:start-day-response:', 'ack:opening-greeting-response:')
_PAYMENT_COMMANDS = {'已經匯款': 'ack', '有疑問需要解決': 'assistance'}
GREETING_COPY = '案件 {case_no} 今天開始服務，祝服務順利！'
PAYMENT_COPY = (
    GREETING_COPY + '\n第一期款尚待確認入帳：NT$ {amount_ntd}，'
    '請於 {due_date} 前完成繳款。已匯款請勿重複繳納。'
)
GREETING_COPY_KEYS = frozenset({'payment-first-reminder', 'payment-first-greeting'})
PAYMENT_COPY_VARIABLES = ('{case_no}', '{amount_ntd}', '{due_date}')


def greeting_correlation_prefix(day: date, obligation_identity: str | None) -> str:
    payment_key = hashlib.sha256(obligation_identity.encode()).hexdigest() if obligation_identity else 'none'
    return f'opening-greeting:{day.isoformat()}:{payment_key}:'


def greeting_payload(unit, case_no, amount=0, due_date=None):
    key = 'payment-first-reminder' if amount > 0 else 'payment-first-greeting'
    default = PAYMENT_COPY if amount > 0 else GREETING_COPY
    variables = {'case_no': case_no, 'amount_ntd': f'{amount:,}', 'due_date': str(due_date or '')}
    return configured_payload(unit, key, {'type': 'text', 'text': default.format(**variables)}, variables)


def greeting_directions(key):
    return '\n客戶可輸入「已經匯款」或「有疑問需要解決」。' if key == 'payment-first-reminder' else ''


def render_greeting_text(key, text, variables):
    directions = greeting_directions(key)
    if len((text + directions).encode('utf-16-le')) > 10000:
        # Existing or expanded copy can exceed the limit. Keep the amount and instructions.
        default = PAYMENT_COPY if key == 'payment-first-reminder' else GREETING_COPY
        text = default.format(**variables)
    return text + directions


def greeting_attempt_key(case_no, day):
    return IdempotencyKey(f'opening-greeting-attempted:{case_no}:{day.isoformat()}')


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

class ServiceStartDayRepositoryPort(Protocol):
    def due_cases(self, day: date, after: str = '', limit: int = 100) -> tuple[str, ...]: ...
    def current(self, case_no, service_date, *, lock=False): ...
    def has_missing_group(self, case_no, day): ...
    def first_payment(self, case_no): ...
    def has_greeting(self, case_no, day): ...
    def payment_reply_context(self, group_id, day, line_user_id): ...
    def delivery_is_current(self, task: object, now: datetime) -> bool: ...


def greeting_reference(context, payment):
    payment_identity = payment.obligation_identity if payment else None
    facts = context.facts()
    # Retired instructions may still be present in a queued, unattempted greeting.
    facts['message_format'] = 'greeting_without_service_report'
    if payment:
        from subsystems.line.payment_overdue_reminders import payment_reference
        facts['payment'] = payment_reference(payment)
    return greeting_correlation_prefix(context.service_date, payment_identity) + fingerprint_payload(facts).value


class ServiceStartDayGreetingWorker:
    run_before_delivery = True

    def __init__(self, unit_of_work_factory, now):
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def run_once(self):
        from subsystems.line.payment_reminder_schedule import at_time, schedule_from_unit

        now = self._now()
        day = now.astimezone(TAIPEI_TIME_ZONE).date()
        after = ''
        result = 0
        while True:
            with self._unit_of_work_factory() as unit:
                if now < at_time(day, schedule_from_unit(unit).first_time):
                    return result
                cases = unit.service_start_days.due_cases(day, after)
            for case_no in cases:
                result += self._queue(case_no, now, day)
            if len(cases) < 100:
                return result
            after = cases[-1]

    def _queue(self, case_no, now, day):
        from subsystems.line.ports import LineAuditIntent

        with self._unit_of_work_factory() as unit:
            repository = unit.service_start_days
            context = repository.current(case_no, day, lock=True)
            if context is None:
                if repository.has_missing_group(case_no, day):
                    key = IdempotencyKey(f'opening-greeting-no-group:{case_no}:{day.isoformat()}')
                    if unit.receipts.get(key, for_update=True) is None:
                        receipt = IdempotencyReceipt(key, fingerprint_payload({'case_no': case_no, 'day': day.isoformat()}),
                                                     'service_start_greeting:missing_group')
                        unit.receipts.append(receipt)
                        unit.audit.append(LineAuditIntent(GREETING_NO_GROUP_AUDIT, 'service-start-day-worker', GREETING_SOURCE, case_no))
                        unit.commit()
                return 0
            if repository.has_greeting(case_no, day) or unit.receipts.get(greeting_attempt_key(case_no, day), for_update=True):
                return 0
            first = repository.first_payment(case_no)
            reference = greeting_reference(context, first)
            key = IdempotencyKey(f'opening-greeting:{case_no}:{reference.rsplit(":", 1)[1]}')
            if unit.delivery_tasks.exists_for_key(key):
                return 0
            payload = greeting_payload(unit, case_no, first.remaining_amount_ntd if first else 0, first.due_date if first else None)
            queued = unit.delivery_tasks.enqueue(LineDeliveryRequest(
                LineRecipient(LineRecipientType.GROUP, LineGroupId(context.group_id)),
                LineMessageKind.TEXT, canonical_line_payload_json(payload), now,
                key, CorrelationId(reference), GREETING_SOURCE, case_no,
            ))
            unit.audit.append(LineAuditIntent('service_start_greeting_queued', 'service-start-day-worker', GREETING_SOURCE, str(queued.task_id.value)))
            unit.commit()
            return 1


def is_retired_start_day_postback(inbox) -> bool:
    postback = json.loads(inbox.event.payload_json).get('postback')
    data = postback.get('data') if isinstance(postback, dict) else None
    return isinstance(data, str) and data.startswith('start-day:')


class ServiceStartDayPaymentReply:
    def handle_message(self, inbox, unit) -> bool:
        event = inbox.event
        source = event.source
        if source.source_type is not LineSourceType.GROUP or source.user_id is None:
            return False
        message = json.loads(event.payload_json).get('message')
        if not isinstance(message, dict) or message.get('type') != 'text':
            return False
        text = str(message.get('text', '')).strip()
        payment_action = _PAYMENT_COMMANDS.get(text)
        if payment_action is None:
            return False
        day = event.occurred_at.astimezone(TAIPEI_TIME_ZONE).date()
        result = unit.service_start_days.payment_reply_context(source.source_id, day, source.user_id.value)
        if result is None:
            return False
        context, greeting_task_id = result
        from subsystems.line.deposit_notifications import handle_payment_reminder_postback

        # Durable handoff of this first reminder blocks the private follow-up before Reply.
        from subsystems.line.payment_reminder_notifications import record_manual_handoff

        record_manual_handoff(unit, greeting_task_id)
        return handle_payment_reminder_postback(f'payment-{payment_action}:first:{context.case_no}', event, unit)

def start_day_delivery_is_current(unit, task, now):
    from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
    from shared_kernel.identities import ActorContext

    request = task.request
    key = getattr(getattr(request, 'idempotency_key', None), 'value', '')
    retired = (
        request.correlation_id.value.startswith('line-notification:order-pre-start-reminder:')
        or request.source_aggregate_type in {SOURCE_TYPE, 'order_service_start_day_response'}
        or (request.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE and key.startswith(_RETIRED_REPORT_REPLY_KEYS))
    )
    if not retired and request.source_aggregate_type != GREETING_SOURCE:
        return True
    if not retired and unit.service_start_days.delivery_is_current(task, now):
        # Persist the selected task before the provider call. Replacing it
        # after a crash could resend under a different provider retry key.
        case_no = request.source_aggregate_identity
        day = now.astimezone(TAIPEI_TIME_ZONE).date()
        key = greeting_attempt_key(case_no, day)
        attempt = unit.receipts.get(key, for_update=True)
        if attempt is None:
            unit.receipts.append(IdempotencyReceipt(
                key, fingerprint_payload({'case_no': case_no, 'day': day.isoformat()}), str(task.task_id.value),
            ))
            unit.commit()
            return True
        if attempt.result_reference == str(task.task_id.value):
            return True
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
        task.task_id, ActorContext('service-start-day-worker'),
        IdempotencyKey(f'start-day-stale:{task.task_id.value}'), task.request.correlation_id,
    ))
    unit.commit()
    return False
