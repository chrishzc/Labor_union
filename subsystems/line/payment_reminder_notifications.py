"""Automatic private reminders; current facts and replies are rechecked at egress."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey, IdempotencyReceipt
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.client_finance.payment_reminder_query import ClientPaymentReminderFacts
from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
from subsystems.line.message_copy_catalog import configured_payload
from subsystems.line.payment_overdue_reminders import ReminderRecipient, STAGE_LABELS, payment_reference, reminder_text
from subsystems.line.payment_reminder_schedule import at_time, followup_at, followup_earliest, schedule_from_unit

INITIAL='client_payment_initial_reminder'
FOLLOWUP='client_payment_automatic_followup'


@dataclass(frozen=True, slots=True)
class OriginalPaymentReminder:
    task_id: int
    status: str
    sent_at: datetime | None
    recipient_id: str


class PaymentReminderNotificationPort(Protocol):
    def candidates(self, day, after='', limit=100) -> tuple[ClientPaymentReminderFacts, ...]: ...
    def payment(self, identity, *, lock=False) -> ClientPaymentReminderFacts | None: ...
    def recipient(self, case_no, *, lock=False) -> ReminderRecipient | None: ...
    def original(self, payment, *, lock=False) -> OriginalPaymentReminder | None: ...
    def has_followup(self, identity) -> bool: ...
    def replied(self, user_id, since) -> bool: ...
    def pending(self, identity) -> bool: ...


def source_reference(facts, recipient):
    return payment_reference(facts.payment)+f':{recipient.binding_version}:{facts.service_start_date or "-"}'


def initial_qualifies(facts, now):
    payment=facts.payment
    local=now.astimezone(TAIPEI_TIME_ZONE)
    if facts.case_status=='訂單完成':
        return False
    if payment.payment_stage=='deposit':
        return facts.contract_completed and payment.remaining_amount_ntd>0
    if payment.payment_stage=='first':
        return facts.service_start_date==local.date()
    return payment.remaining_amount_ntd>0 and payment.due_date==local.date()


def initial_eligible(facts, now, schedule):
    if not initial_qualifies(facts,now):
        return False
    stage=facts.payment.payment_stage
    if stage=='deposit':
        return True
    local=now.astimezone(TAIPEI_TIME_ZONE)
    return local>=at_time(local.date(),schedule.first_time if stage=='first' else schedule.second_time)


def followup_eligible(repository, facts, recipient, original, now, schedule, *, queued=False):
    return bool(facts.contract_completed and original and original.sent_at
        and original.recipient_id==recipient.recipient.identity.value
        and facts.payment.overdue_on(now.astimezone(TAIPEI_TIME_ZONE).date())
        and now>=(followup_earliest(facts.payment.due_date,original.sent_at) if queued else followup_at(facts.payment.due_date,original.sent_at,schedule)))


def _manual_handoff(unit,repository,original):
    if original is None or original.sent_at is None:
        return False
    key=IdempotencyKey(f'payment-reminder-replied:{original.task_id}')
    expected=IdempotencyReceipt(key,fingerprint_payload({'original_task_id':original.task_id}),'payment_reminder:manual')
    existing=unit.receipts.get(key,for_update=True)
    if existing is not None:
        if existing!=expected:
            raise RuntimeError('payment_reminder_handoff_receipt_conflict')
        return True
    if not repository.replied(original.recipient_id,original.sent_at):
        return False
    # A workflow receipt, not a payment/settlement fact. Keep the handoff durable
    # even when the inbox payload is subsequently retired by its own lifecycle.
    unit.receipts.append(expected)
    return True


def initial_payload(unit, facts):
    payment=facts.payment
    variables={'case_no':payment.case_no,'amount_ntd':f'{payment.remaining_amount_ntd:,}', 'due_date':str(payment.due_date)}
    if payment.payment_stage=='first':
        key='payment-first-reminder' if payment.remaining_amount_ntd>0 else 'payment-first-greeting'
        text=(f'案件 {payment.case_no} 今天開始服務，祝服務順利！'
            +(f'第一期款尚待確認入帳：{payment.remaining_amount_ntd:,} 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。' if payment.remaining_amount_ntd>0 else ''))
    else:
        key='payment-second-reminder'
        text=f'案件 {payment.case_no} 第二期款尚待確認入帳 {payment.remaining_amount_ntd:,} 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。'
    return LineMessageKind.TEXT,canonical_line_payload_json(configured_payload(unit,key,{'type':'text','text':text},variables))


class PaymentReminderNotificationWorker:
    run_before_delivery=True

    def __init__(self, unit_of_work_factory, now, deposit_application):
        self._unit=unit_of_work_factory
        self._now=now
        self._deposit=deposit_application

    def run_once(self):
        processed=0
        after=''
        # Keyset pages bound memory without letting old unpaid cases starve new ones.
        while True:
            with self._unit() as unit:
                rows=unit.payment_reminder_notifications.candidates(self._now().astimezone(TAIPEI_TIME_ZONE).date(),after,100)
            if not rows:
                break
            for row in rows:
                processed+=self._queue(row.payment.obligation_identity)
            after=rows[-1].payment.obligation_identity
            if len(rows)<100:
                break
        return processed

    def _queue(self, identity):
        from subsystems.line.ports import LineAuditIntent
        with self._unit() as unit:
            repository=unit.payment_reminder_notifications
            facts=repository.payment(identity,lock=True)
            if facts is None:
                return 0
            now=self._now()
            schedule=schedule_from_unit(unit)
            recipient=repository.recipient(facts.payment.case_no,lock=True)
            if recipient is None:
                return 0
            original=repository.original(facts.payment,lock=True)
            if _manual_handoff(unit,repository,original):
                unit.commit()
                return 0
            if repository.pending(identity):
                return 0
            if original is None:
                if not initial_eligible(facts,now,schedule):
                    return 0
                source=INITIAL
                scheduled_at=now
                if facts.payment.payment_stage=='deposit' and schedule.deposit_mode=='daily':
                    scheduled_at=at_time(now.astimezone(TAIPEI_TIME_ZONE).date(),schedule.deposit_time)
                    if scheduled_at<now:
                        scheduled_at+=timedelta(days=1)
                if facts.payment.payment_stage=='deposit':
                    payment=unit.deposit_payments.get(facts.payment.case_no,lock=True)
                    if payment is None or payment.settled or not self._deposit.ready(payment):
                        return 0
                    request=self._deposit._request(payment,recipient.recipient.identity.value,'client_deposit_reminder',IdempotencyKey('payment-deposit-composition'),unit)
                    kind,payload=request.message_kind,request.payload_json
                else:
                    kind,payload=initial_payload(unit,facts)
                reference=source_reference(facts,recipient)
                if facts.payment.payment_stage=='deposit':
                    from subsystems.line.deposit_notifications import payment_source
                    reference+=':deposit:'+payment_source(payment).rsplit(':',1)[1]
                # Distinguish only replaced, never-attempted immutable source snapshots.
                key='payment-initial:'+sha256((identity+reference+recipient.recipient.identity.value).encode()).hexdigest()
            else:
                if repository.has_followup(identity) or not followup_eligible(repository,facts,recipient,original,now,schedule):
                    return 0
                source=FOLLOWUP
                scheduled_at=now
                variables={'payment_stage':STAGE_LABELS[facts.payment.payment_stage], 'remaining_amount':f'{facts.payment.remaining_amount_ntd:,}'}
                kind=LineMessageKind.TEXT
                payload=canonical_line_payload_json(configured_payload(unit,'payment-overdue-'+facts.payment.payment_stage,{'type':'text','text':reminder_text(facts.payment)},variables))
                reference=source_reference(facts,recipient)+f':original:{original.task_id}'
                key=f'payment-followup:{original.task_id}'
            operation_key=IdempotencyKey(key)
            if unit.delivery_tasks.exists_for_key(operation_key):
                return 0  # A cancelled unchanged snapshot is not a new operation.
            result=unit.delivery_tasks.enqueue(LineDeliveryRequest(recipient.recipient,kind,payload,scheduled_at,operation_key,CorrelationId(reference),source,identity))
            unit.audit.append(LineAuditIntent('payment_reminder_queued','line-payment-reminders',source,str(result.task_id.value)))
            unit.commit()
            return 1


def payment_reminder_delivery_is_current(unit,task,now):
    request=task.request
    if request.source_aggregate_type not in (INITIAL,FOLLOWUP):
        return True
    repository=unit.payment_reminder_notifications
    facts=repository.payment(request.source_aggregate_identity,lock=True)
    recipient=repository.recipient(facts.payment.case_no,lock=True) if facts else None
    valid=bool(facts and recipient and recipient.recipient==request.recipient)
    if valid:
        reference=source_reference(facts,recipient)
        if request.source_aggregate_type==INITIAL:
            if facts.payment.payment_stage=='deposit':
                payment=unit.deposit_payments.get(facts.payment.case_no,lock=True)
                from subsystems.line.deposit_notifications import payment_source
                if payment is not None and not payment.settled:
                    reference+=':deposit:'+payment_source(payment).rsplit(':',1)[1]
                else:
                    valid=False
            valid=valid and request.correlation_id.value==reference and initial_qualifies(facts,now)
        else:
            original=repository.original(facts.payment,lock=True)
            valid=bool(original and request.correlation_id.value==reference+f':original:{original.task_id}'
                and not _manual_handoff(unit,repository,original)
                and followup_eligible(repository,facts,recipient,original,now,schedule_from_unit(unit),queued=True))
    if not valid:
        unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('line-payment-reminders'),IdempotencyKey(f'payment-reminder-stale:{task.task_id.value}'),request.correlation_id))
        unit.commit()
    return valid
