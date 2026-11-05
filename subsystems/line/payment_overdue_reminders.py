"""Union decides each overdue reminder; reads never enqueue or change Finance facts."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.client_finance.overdue_payment_query import OverdueClientPayment
from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
from subsystems.line.message_copy_catalog import configured_payload

SOURCE_TYPE = 'manual_payment_overdue_reminder'
CASE_SOURCE_TYPE = 'manual_case_payment_reminder'
STAGE_LABELS = {'deposit':'訂金','first':'第一期款','second':'第二期款'}


def reminder_text(payment: OverdueClientPayment) -> str:
    return f'本案{STAGE_LABELS[payment.payment_stage]}尚有 NT$ {payment.remaining_amount_ntd:,} 未確認入帳，請協助確認繳款，謝謝。'


def payment_reference(payment: OverdueClientPayment) -> str:
    # Frozen delivery provenance, not a new Preview/Confirm fingerprint.
    return (f'payment-overdue:{payment.payment_stage}:{payment.projection_version}:'
            f'{payment.obligation_event_id}:{payment.due_date.isoformat()}:{payment.remaining_amount_ntd}')


@dataclass(frozen=True, slots=True)
class ReminderRecipient:
    recipient: LineRecipient
    binding_version: int


@dataclass(frozen=True, slots=True)
class LastPaymentReminder:
    requested_at: datetime
    status: str


@dataclass(frozen=True, slots=True)
class PaymentOverdueTodo:
    payment: OverdueClientPayment
    overdue_days: int
    recipient_label: str
    can_send: bool
    unavailable_reason: str | None
    last_reminder: LastPaymentReminder | None


@dataclass(frozen=True, slots=True)
class CaseReminderRecord:
    task_id: int
    requested_at: datetime
    sent_at: datetime | None
    status: str
    content: str | None
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class CasePaymentReminder:
    case_no: str
    payment_stage: str
    payment: OverdueClientPayment | None
    recipient_label: str
    can_send: bool
    unavailable_reason: str | None
    message: str | None
    history: tuple[CaseReminderRecord, ...]


class PaymentOverdueReminderPort(Protocol):
    def case_facts(self, case_no: str): ...
    def history(self, case_no: str, stage: str) -> tuple[CaseReminderRecord, ...]: ...
    def list(self, day: date, page: int, page_size: int) -> tuple[tuple[PaymentOverdueTodo, ...], int]: ...
    def payment(self, identity: str, *, lock: bool = False) -> OverdueClientPayment | None: ...
    def recipient(self, payment: OverdueClientPayment, *, lock: bool = False) -> ReminderRecipient | None: ...
    def existing(self, key: IdempotencyKey): ...
    def has_pending(self, identity: str, *, lock: bool = False) -> bool: ...
    def delivery_is_current(self, task: object, now: datetime) -> bool: ...


class PaymentOverdueReminderConflict(ValueError):
    pass


class PaymentOverdueReminderApplication:
    def __init__(self, unit_of_work_factory, now):
        self._unit = unit_of_work_factory
        self._now = now

    def list(self, page=1, page_size=25):
        with self._unit() as unit:
            return unit.payment_overdue_reminders.list(self._now().astimezone(TAIPEI_TIME_ZONE).date(),page,page_size)

    def case(self, case_no: str):
        with self._unit() as unit:
            repo = unit.payment_overdue_reminders
            facts = repo.case_facts(case_no)
            result = []
            for stage in STAGE_LABELS:
                matches = [row for row in facts if row.payment.payment_stage == stage]
                fact = matches[0] if len(matches) == 1 else None
                payment = fact.payment if fact else None
                recipient = repo.recipient(payment) if payment and fact.contract_completed and payment.remaining_amount_ntd > 0 else None
                pending = bool(payment and repo.has_pending(payment.obligation_identity))
                reason = ("本期期款或日期來源待確認／已無待收款" if payment is None else
                    "本期已繳齊，無需繳款提醒" if payment.remaining_amount_ntd <= 0 else
                    "本案雙方簽約尚未完成" if not fact.contract_completed else
                    "尚未綁定客戶 LINE" if recipient is None else
                    "本期已有寄送工作，請先確認原工作結果" if pending else None)
                message = self._payload(unit,payment).get('text') if payment is not None else None
                result.append(CasePaymentReminder(case_no,stage,payment,'客戶私人聊天室',reason is None,
                    reason,message,repo.history(case_no,stage)))
            return tuple(result)

    @staticmethod
    def _payload(unit, payment):
        return configured_payload(unit, 'payment-overdue-' + payment.payment_stage,
            {'type':'text','text':reminder_text(payment)},
            {'payment_stage': STAGE_LABELS[payment.payment_stage], 'remaining_amount': f'{payment.remaining_amount_ntd:,}'})

    def send_case(self, expected: OverdueClientPayment, key: str, actor: ActorContext):
        return self._send(expected,key,actor,case_scope=True)

    def send(self, expected: OverdueClientPayment, key: str, actor: ActorContext):
        return self._send(expected,key,actor,case_scope=False)

    def _send(self, expected: OverdueClientPayment, key: str, actor: ActorContext, *, case_scope: bool):
        from subsystems.line.ports import LineAuditIntent

        source = CASE_SOURCE_TYPE if case_scope else SOURCE_TYPE
        key = IdempotencyKey(('payment-case:' if case_scope else 'payment-overdue:')+key)
        with self._unit() as unit:
            repository = unit.payment_overdue_reminders
            # Serialize sends for this obligation before inspecting queue state.
            current = repository.payment(expected.obligation_identity,lock=True)
            existing = repository.existing(key)
            if existing is not None:
                if (existing.request.source_aggregate_type != source
                        or existing.request.source_aggregate_identity != expected.obligation_identity
                        or not existing.request.correlation_id.value.startswith(payment_reference(expected)+':')):
                    raise PaymentOverdueReminderConflict('payment_overdue_idempotency_conflict')
                return existing.task_id.value, existing.status.value
            now = self._now()
            if current != expected or current.remaining_amount_ntd <= 0 or (not case_scope and not current.overdue_on(now.astimezone(TAIPEI_TIME_ZONE).date())):
                raise PaymentOverdueReminderConflict('payment_overdue_changed')
            if case_scope:
                matches=[row for row in repository.case_facts(current.case_no) if row.payment.payment_stage==current.payment_stage]
                if len(matches)!=1 or not matches[0].contract_completed or matches[0].payment!=current:
                    raise PaymentOverdueReminderConflict('payment_case_source_changed')
            if repository.has_pending(current.obligation_identity,lock=True):
                raise PaymentOverdueReminderConflict('payment_overdue_reminder_in_flight')
            recipient = repository.recipient(current,lock=True)
            if recipient is None:
                raise PaymentOverdueReminderConflict('payment_overdue_recipient_unavailable')
            result = unit.delivery_tasks.enqueue(LineDeliveryRequest(recipient.recipient,LineMessageKind.TEXT,
                canonical_line_payload_json(self._payload(unit,current)),now,key,
                CorrelationId(payment_reference(current)+f':{recipient.binding_version}'),source,current.obligation_identity))
            unit.audit.append(LineAuditIntent('payment_overdue_reminder_queued',actor.actor_id,source,str(result.task_id.value)))
            unit.commit()
            return result.task_id.value, result.status.value


def payment_overdue_delivery_is_current(unit, task, now):
    if task.request.source_aggregate_type not in {SOURCE_TYPE,CASE_SOURCE_TYPE}:
        return True
    if unit.payment_overdue_reminders.delivery_is_current(task,now):
        return True
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('line-payment-overdue'),
        IdempotencyKey(f'payment-overdue-stale:{task.task_id.value}'),task.request.correlation_id))
    unit.commit()
    return False
