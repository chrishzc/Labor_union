"""
File: payment_receipt_notifications.py
Description: 管理各期帳款入帳待辦查詢與「已於官方帳號發送／標記已通知」確認消除。
"""
from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Literal, Protocol, TYPE_CHECKING

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, IdempotencyKey, IdempotencyReceipt
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.deposit_notifications import payment_source

if TYPE_CHECKING:
    from subsystems.line.cancellation_notifications import CancellationNoticeDelivery, CancellationNoticeSource

MANUAL_RECEIPT = 'manual_client_payment_receipt'


class PaymentReceiptConflict(ValueError): pass


@dataclass(frozen=True, slots=True)
class PaymentReceiptSnapshot:
    case_no: str
    payment_stage: Literal['deposit','first','second']
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
    stage: Literal['deposit','first','second']
    settlement_identity: str


@dataclass(frozen=True, slots=True)
class PaymentReceiptHistory:
    status: str
    attempts: int


class PaymentReceiptPort(Protocol):
    def cancellation_source(self, case_no: str, *, lock: bool = False) -> "CancellationNoticeSource | None": ...
    def cancellation_recipient(self, case_no: str, *, lock: bool = False) -> str | None: ...
    def cancellation_delivery(self, reference: str, *, lock: bool = False) -> "CancellationNoticeDelivery | None": ...
    def mark_cancellation_notice_provider_started(self, task_id: int) -> None: ...
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


def first_receipt_message(case_no,amount_ntd):
    return {'type':'text','text':f'案件 {case_no} 第一期款 {amount_ntd:,} 元已確認入帳，謝謝。'}


def receipt_ack_key(payment):
    return IdempotencyKey(f'payment-receipt-ack:{payment.payment_stage}:{payment.settlement_identity}')


class PaymentReceiptNotificationApplication:
    def __init__(self, units, now, deposit=None):
        self._units,self._now,self._deposit=units,now,deposit

    def list(self,page=1,page_size=25,*,case_no=None,payment_stage=None,settlement_identity=None):
        result=[];total=0;after=0;seen=set()
        with self._units() as unit:
            repo=unit.payment_receipt_notifications
            while True:
                rows=repo.candidates(after,100)
                if not rows: break
                for event in rows:
                    if (case_no and event.case_no!=case_no or payment_stage and event.stage!=payment_stage
                            or settlement_identity and event.settlement_identity!=settlement_identity): continue
                    payment=repo.payment(event.case_no,event.stage,event.settlement_identity)
                    if payment is None: continue
                    snapshot=receipt_snapshot(payment,event.stage)
                    identity=(snapshot.case_no,snapshot.payment_stage,snapshot.settlement_identity)
                    if identity in seen: continue
                    seen.add(identity)
                    history=repo.history(snapshot)
                    if history and history.status in ('sent','acknowledged'): continue
                    if (page-1)*page_size<=total<page*page_size:
                        result.append(PaymentReceiptTodo(snapshot,True,None,None))
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
            key=receipt_ack_key(expected)
            if unit.receipts.get(key,for_update=True) is not None:
                return 1,'completed'
            history=repo.history(expected,lock=True)
            if history and history.status in ('sent','acknowledged'):
                return 1,'completed'
            unit.receipts.append(IdempotencyReceipt(
                key,
                fingerprint_payload({
                    'case_no':expected.case_no,
                    'payment_stage':expected.payment_stage,
                    'settlement_identity':expected.settlement_identity,
                }),
                f'{expected.payment_stage}:{expected.settlement_identity}',
            ))
            unit.audit.append(LineAuditIntent(
                'payment_receipt_acknowledged',
                actor.actor_id,
                MANUAL_RECEIPT,
                f'{expected.payment_stage}:{expected.settlement_identity}',
            ))
            unit.commit()
            return 1,'completed'


def payment_receipt_delivery_is_current(unit,task,now):
    from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
    automatic=(task.request.source_aggregate_type=='client_finance_account'
        and unit.payment_receipt_notifications.automatic_receipt(task))
    if task.request.source_aggregate_type!=MANUAL_RECEIPT and not automatic: return True
    key=IdempotencyKey(
        f'payment-receipt-auto-stop:{task.task_id.value}' if automatic else f'payment-receipt-retired:{task.task_id.value}'
    )
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('line-receipt-worker'),
        key,task.request.correlation_id))
    unit.commit()
    return False
