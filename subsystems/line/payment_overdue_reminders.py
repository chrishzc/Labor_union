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

SOURCE_TYPE = 'manual_payment_overdue_reminder'
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


class PaymentOverdueReminderPort(Protocol):
    def list(self, day: date, page: int, page_size: int) -> tuple[tuple[PaymentOverdueTodo, ...], int]: ...
    def payment(self, identity: str, *, lock: bool = False) -> OverdueClientPayment | None: ...
    def recipient(self, payment: OverdueClientPayment, *, lock: bool = False) -> ReminderRecipient | None: ...
    def existing(self, key: IdempotencyKey): ...
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

    def send(self, expected: OverdueClientPayment, key: str, actor: ActorContext):
        from subsystems.line.ports import LineAuditIntent

        key = IdempotencyKey('payment-overdue:'+key)
        with self._unit() as unit:
            repository = unit.payment_overdue_reminders
            existing = repository.existing(key)
            if existing is not None:
                if (existing.request.source_aggregate_type != SOURCE_TYPE
                        or existing.request.source_aggregate_identity != expected.obligation_identity
                        or not existing.request.correlation_id.value.startswith(payment_reference(expected)+':')):
                    raise PaymentOverdueReminderConflict('payment_overdue_idempotency_conflict')
                return existing.task_id.value, existing.status.value
            current = repository.payment(expected.obligation_identity,lock=True)
            now = self._now()
            if current != expected or not current.overdue_on(now.astimezone(TAIPEI_TIME_ZONE).date()):
                raise PaymentOverdueReminderConflict('payment_overdue_changed')
            recipient = repository.recipient(current,lock=True)
            if recipient is None:
                raise PaymentOverdueReminderConflict('payment_overdue_recipient_unavailable')
            result = unit.delivery_tasks.enqueue(LineDeliveryRequest(recipient.recipient,LineMessageKind.TEXT,
                canonical_line_payload_json({'type':'text','text':reminder_text(current)}),now,key,
                CorrelationId(payment_reference(current)+f':{recipient.binding_version}'),SOURCE_TYPE,current.obligation_identity))
            unit.audit.append(LineAuditIntent('payment_overdue_reminder_queued',actor.actor_id,SOURCE_TYPE,str(result.task_id.value)))
            unit.commit()
            return result.task_id.value, result.status.value


def payment_overdue_delivery_is_current(unit, task, now):
    if task.request.source_aggregate_type != SOURCE_TYPE:
        return True
    if unit.payment_overdue_reminders.delivery_is_current(task,now):
        return True
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('line-payment-overdue'),
        IdempotencyKey(f'payment-overdue-stale:{task.task_id.value}'),task.request.correlation_id))
    unit.commit()
    return False
