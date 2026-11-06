"""Manual LINE notices over a committed cancellation and its live reconciliation."""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Literal

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.client_finance.case_accounting_query import ClientAccountingItem, ClientCancellationAccounting
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.message_configuration import LineMessageConfigurationError
from subsystems.line.message_copy_catalog import configured_payload
from subsystems.line.ports import LineAuditIntent


NoticeKind = Literal["settlement", "refund", "collection"]
SOURCE = "manual_client_cancellation_notice"
PROVIDER_STARTED = "cancellation_notice_provider_started"
DEFAULT_COPY: dict[NoticeKind, str] = {
    "settlement": "您好，以下是本案的取消結算明細。",
    "refund": "您好，本案的取消結算退款已完成。",
    "collection": "您好，本案的取消結算補收款已全額入帳，謝謝。",
}


class CancellationNoticeConflict(ValueError):
    pass


@dataclass(frozen=True)
class CancellationNoticeSource:
    case_no: str
    event_id: int
    accounting: ClientCancellationAccounting
    item: ClientAccountingItem | None
    collection_account: str | None = None

    @property
    def completion(self) -> NoticeKind | None:
        item, facts = self.item, self.accounting
        if item is None or not item.settled or item.remaining_ntd != 0:
            return None
        if facts.refund_due_ntd and facts.bank_refunded_ntd is not None and facts.transfer_fee_ntd is not None:
            if facts.bank_refunded_ntd >= 0 and facts.bank_refunded_ntd + facts.transfer_fee_ntd == facts.refund_due_ntd:
                return "refund"
        if facts.additional_charge_due_ntd and item.has_payment and item.actual_ntd >= facts.additional_charge_due_ntd:
            return "collection"
        return None

    def reference(self, kind: NoticeKind) -> str:
        return f"{self.case_no}:{self.event_id}:{kind}"

    def key(self, kind: NoticeKind, replaced_task: int | None = None) -> IdempotencyKey:
        parts = (self.reference(kind),) if replaced_task is None else (self.reference(kind), replaced_task)
        return IdempotencyKey("manual-cancellation:" + _digest(*parts))

    def blocker(self, kind: NoticeKind) -> str | None:
        if kind != "settlement":
            return None if kind == self.completion else "全額核銷結果待確認。"
        facts, item = self.accounting, self.item
        if (facts.refund_due_ntd or facts.additional_charge_due_ntd) and item is None:
            return "取消結算的核銷來源待確認。"
        if facts.additional_charge_due_ntd and item and item.remaining_ntd and not self.collection_account:
            return "本案繳款資訊待確認，請先核對專屬虛擬帳號。"
        return None


@dataclass(frozen=True)
class CancellationNoticePreview:
    kind: NoticeKind
    text: str | None
    fingerprint: str | None
    unavailable_reason: str | None
    delivery_status: str | None


@dataclass(frozen=True)
class CancellationNoticeDelivery:
    task_id: int
    status: str
    can_replace: bool = False


def _digest(*parts) -> str:
    return sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _money(amount: int) -> str:
    return f"NT$ {amount:,}"


def notice_details(source: CancellationNoticeSource, kind: NoticeKind) -> str:
    facts, item = source.accounting, source.item
    lines = [f"案件編號：{source.case_no}"]
    if kind == "refund":
        lines.extend([f"原應退金額：{_money(facts.refund_due_ntd)}",
                      f"銀行實退金額：{_money(facts.bank_refunded_ntd)}"])
        if facts.transfer_fee_ntd:
            lines.append(f"匯款手續費：{_money(facts.transfer_fee_ntd)}")
        lines.append("剩餘待退：NT$ 0")
    elif kind == "collection":
        lines.extend([f"本案補收已核銷：{_money(facts.additional_charge_due_ntd)}", "剩餘待收：NT$ 0"])
    else:
        lines.extend([f"服務費應付：{_money(facts.service_due_ntd)}",
                      f"取消違約金：{_money(facts.fee_ntd)}",
                      f"取消時淨實收：{_money(facts.net_received_ntd)}"])
        if item is None:
            lines.append("本案已結清，無待收付差額。")
        elif facts.refund_due_ntd:
            lines.extend([f"原應退金額：{_money(facts.refund_due_ntd)}",
                          f"剩餘待退：{_money(item.remaining_ntd)}"])
        elif facts.additional_charge_due_ntd:
            lines.extend([f"原應補收金額：{_money(facts.additional_charge_due_ntd)}",
                          f"剩餘待收：{_money(item.remaining_ntd)}"])
            if item.remaining_ntd and source.collection_account:
                lines.append(f"繳款方式：轉帳至永豐銀行（807）本案專屬虛擬帳號 {source.collection_account}")
                if item.due_date:
                    lines.append(f"繳款期限：{item.due_date}")
                lines.append("若已轉帳，請勿重複繳納，待公會核對入帳。")
    return "\n".join(lines)


def _source_fingerprint(source: CancellationNoticeSource, kind: NoticeKind, recipient: str, details: str) -> str:
    return _digest(source.reference(kind), source.item.version if source.item else None, recipient, details)


def _preview(unit, source, kind, recipient, existing):
    status = existing.status if existing else None
    blocker = source.blocker(kind)
    if blocker:
        return CancellationNoticePreview(kind, None, None, blocker, status)
    details = notice_details(source, kind)
    try:
        copy = configured_payload(unit, f"cancellation-notice-{kind}", {"type": "text", "text": DEFAULT_COPY[kind]})
        message = f"{copy['text']}\n\n{details}"
    except LineMessageConfigurationError:
        return CancellationNoticePreview(kind, None, None, "請先確認 LINE 通知範本。", status)
    if len(message.encode("utf-16-le")) // 2 > 5000:
        return CancellationNoticePreview(kind, None, None, "LINE 通知過長，請先縮短範本。", status)
    if not recipient:
        return CancellationNoticePreview(kind, message, None, "本案客戶的 LINE 綁定待確認。", status)
    fingerprint = None
    if existing is None or existing.can_replace:
        fingerprint = _digest(_source_fingerprint(source, kind, recipient, details), message,
                              existing.task_id if existing else None)
    return CancellationNoticePreview(kind, message, fingerprint, None, status)


class CancellationNotificationApplication:
    def __init__(self, units, now):
        self._units = units
        self._now = now

    def previews(self, case_no, actor):
        require_line_capability(actor, LineCapability.TASK_SEND)
        with self._units() as unit:
            repo = unit.payment_receipt_notifications
            source = repo.cancellation_source(case_no)
            if source is None:
                return ()
            recipient = repo.cancellation_recipient(case_no)
            kinds = ("settlement", source.completion) if source.completion else ("settlement",)
            return tuple(_preview(unit, source, kind, recipient, repo.cancellation_delivery(source.reference(kind)))
                         for kind in kinds)

    def send(self, case_no, kind, fingerprint, actor):
        require_line_capability(actor, LineCapability.TASK_SEND)
        with self._units() as unit:
            repo = unit.payment_receipt_notifications
            source = repo.cancellation_source(case_no, lock=True)
            if source is None or source.blocker(kind):
                raise CancellationNoticeConflict("cancellation_notice_source_changed")
            recipient = repo.cancellation_recipient(case_no, lock=True)
            existing = repo.cancellation_delivery(source.reference(kind), lock=True)
            if existing and not existing.can_replace:
                return existing.task_id, existing.status
            preview = _preview(unit, source, kind, recipient, existing)
            if not preview.fingerprint or preview.fingerprint != fingerprint:
                raise CancellationNoticeConflict("cancellation_notice_preview_changed")
            details = notice_details(source, kind)
            request = LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, LineUserId(recipient)),
                LineMessageKind.TEXT, canonical_line_payload_json({"type": "text", "text": preview.text}),
                self._now(), source.key(kind, existing.task_id if existing else None),
                CorrelationId(_source_fingerprint(source, kind, recipient, details)),
                SOURCE, source.reference(kind),
            )
            result = unit.delivery_tasks.enqueue(request)
            unit.audit.append(LineAuditIntent("cancellation_notice_manually_queued", actor.actor_id, SOURCE,
                                             str(result.task_id.value)))
            unit.commit()
            return result.task_id.value, result.status.value


def cancellation_notice_delivery_is_current(unit, task):
    case_no, _, suffix = task.request.source_aggregate_identity.partition(":")
    _, _, kind = suffix.partition(":")
    repo = unit.payment_receipt_notifications
    source = repo.cancellation_source(case_no, lock=True)
    recipient = repo.cancellation_recipient(case_no, lock=True) if source else None
    return bool(
        source and kind in DEFAULT_COPY and not source.blocker(kind) and recipient
        and task.request.source_aggregate_identity == source.reference(kind)
        and task.request.recipient == LineRecipient(LineRecipientType.USER, LineUserId(recipient))
        and task.request.correlation_id.value == _source_fingerprint(source, kind, recipient, notice_details(source, kind))
    )
