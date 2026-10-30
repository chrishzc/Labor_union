"""Human-approved receipt notices over committed Finance facts; no automatic send."""
from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Literal, Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from shared_kernel.identities import ActorContext, IdempotencyKey, CorrelationId
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.deposit_notifications import SETTLED, payment_source
from subsystems.line.message_copy_catalog import configured_payload

MANUAL_RECEIPT = 'manual_client_payment_receipt'


class PaymentReceiptConflict(ValueError): pass


@dataclass(frozen=True, slots=True)
class PaymentReceiptSnapshot:
    case_no: str
    payment_stage: Literal['deposit','second']
    settlement_identity: str
    amount_ntd: int
    source_version: int
    source_reference: str


@dataclass(frozen=True, slots=True)
class PaymentReceiptTodo:
    payment: PaymentReceiptSnapshot
    can_send: bool
    unavailable_reason: str | None
    delivery_status: str | None


@dataclass(frozen=True, slots=True)
class PaymentReceiptCandidate:
    event_id: int
    case_no: str
    stage: Literal['deposit','second']
    settlement_identity: str


@dataclass(frozen=True, slots=True)
class PaymentReceiptHistory:
    status: str
    attempts: int


class PaymentReceiptPort(Protocol):
    def candidates(self, after: int, limit: int) -> tuple[PaymentReceiptCandidate,...]: ...
    def payment(self, case_no, stage, settlement_identity, *, lock=False): ...
    def recipient(self, case_no, *, lock=False): ...
    def history(self, payment, *, lock=False) -> PaymentReceiptHistory | None: ...


def receipt_snapshot(payment, stage):
    if stage=='deposit':
        return PaymentReceiptSnapshot(payment.case_no,stage,payment.settlement_identity,payment.amount_ntd,
                                      payment.obligation_version,payment_source(payment))
    return PaymentReceiptSnapshot(payment.case_no,stage,payment.settlement_identity,payment.settled_amount,
                                  payment.account_version,
                                  sha256(canonical_line_payload_json({**asdict(payment),'due_date':str(payment.due_date)}).encode()).hexdigest())


def receipt_reference(snapshot, recipient):
    return snapshot.case_no+':'+sha256(canonical_line_payload_json({'payment':asdict(snapshot),'recipient':recipient}).encode()).hexdigest()


def receipt_blocker(history, recipient):
    if not recipient: return '客戶尚未綁定 LINE，請先聯絡客戶完成綁定。'
    if history and (history.status in ('pending','processing','retryable_failed','sent') or history.attempts>0):
        return '已建立或已嘗試寄送，請至寄送紀錄確認結果，避免重複通知。'
    return None


class PaymentReceiptNotificationApplication:
    def __init__(self, units, now, deposit):
        self._units,self._now,self._deposit=units,now,deposit

    def list(self,page=1,page_size=25):
        result=[];total=0;after=0;seen=set()
        with self._units() as unit:
            repo=unit.payment_receipt_notifications
            while True:
                rows=repo.candidates(after,100)
                if not rows: break
                for event in rows:
                    payment=repo.payment(event.case_no,event.stage,event.settlement_identity)
                    if payment is None: continue
                    snapshot=receipt_snapshot(payment,event.stage)
                    identity=(snapshot.case_no,snapshot.payment_stage,snapshot.settlement_identity)
                    if identity in seen: continue
                    seen.add(identity)
                    history=repo.history(snapshot)
                    if history and history.status=='sent': continue
                    recipient=repo.recipient(snapshot.case_no)
                    blocker=receipt_blocker(history,recipient)
                    if snapshot.payment_stage=='deposit' and self._deposit._liff_id in ('','your_liff_id_here'):
                        blocker='LINE 繳費頁面尚未設定，請先完成設定。'
                    if (page-1)*page_size<=total<page*page_size:
                        result.append(PaymentReceiptTodo(snapshot,blocker is None,blocker,history.status if history else None))
                    total+=1
                after=rows[-1].event_id
                if len(rows)<100: break
        return tuple(result),total

    def send(self,expected,actor):
        from subsystems.line.ports import LineAuditIntent
        require_line_capability(actor,LineCapability.TASK_SEND)
        with self._units() as unit:
            repo=unit.payment_receipt_notifications
            payment=repo.payment(expected.case_no,expected.payment_stage,expected.settlement_identity,lock=True)
            if payment is None or receipt_snapshot(payment,expected.payment_stage)!=expected:
                raise PaymentReceiptConflict('payment_receipt_changed')
            recipient=repo.recipient(expected.case_no,lock=True)
            if not recipient: raise PaymentReceiptConflict('payment_receipt_recipient_unavailable')
            reference=receipt_reference(expected,recipient)
            key=IdempotencyKey('manual-receipt:'+sha256(reference.encode()).hexdigest())
            existing=unit.deposit_notifications.existing_delivery(key)
            if existing is not None:
                if existing.status.value=='cancelled': raise PaymentReceiptConflict('payment_receipt_cancelled')
                return existing.task_id.value,existing.status.value
            if receipt_blocker(repo.history(expected,lock=True),recipient):
                raise PaymentReceiptConflict('payment_receipt_already_attempted')
            if expected.payment_stage=='deposit':
                original=self._deposit._request(payment,recipient,SETTLED,key,unit)
                kind,payload=original.message_kind,original.payload_json
            else:
                kind=LineMessageKind.TEXT
                from subsystems.line.message_copy import message_definition
                from subsystems.line.message_configuration import render_message_template
                rendered=render_message_template(message_definition(unit),'LINE-SECOND-PAYMENT-SETTLED-TEXT-V1',
                    {'case_no':expected.case_no,'second_payment_amount':f'{expected.amount_ntd:,}'})
                kind,payload=rendered.message_kind,rendered.payload_json
            result=unit.delivery_tasks.enqueue(LineDeliveryRequest(LineRecipient(LineRecipientType.USER,LineUserId(recipient)),
                kind,payload,self._now(),key,CorrelationId(reference),MANUAL_RECEIPT,
                expected.payment_stage+':'+expected.settlement_identity))
            unit.audit.append(LineAuditIntent('payment_receipt_manually_queued',actor.actor_id,MANUAL_RECEIPT,str(result.task_id.value)))
            unit.commit()
            return result.task_id.value,result.status.value


def payment_receipt_delivery_is_current(unit,task,now):
    from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
    automatic=(task.request.source_aggregate_type=='client_finance_account'
        and unit.payment_receipt_notifications.automatic_receipt(task))
    if task.request.source_aggregate_type!=MANUAL_RECEIPT and not automatic: return True
    if automatic:
        unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('line-receipt-worker'),
            IdempotencyKey(f'payment-receipt-auto-stop:{task.task_id.value}'),task.request.correlation_id))
        unit.commit()
        return False
    stage,_,identity=task.request.source_aggregate_identity.partition(':')
    case=task.request.correlation_id.value.partition(':')[0]
    repo=unit.payment_receipt_notifications
    payment=repo.payment(case,stage,identity,lock=True)
    recipient=repo.recipient(case,lock=True)
    valid=bool(payment and recipient and task.request.recipient==LineRecipient(LineRecipientType.USER,LineUserId(recipient))
        and task.request.correlation_id.value==receipt_reference(receipt_snapshot(payment,stage),recipient))
    if not valid:
        unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('line-receipt-worker'),
            IdempotencyKey(f'payment-receipt-stale:{task.task_id.value}'),task.request.correlation_id))
        unit.commit()
    return valid
