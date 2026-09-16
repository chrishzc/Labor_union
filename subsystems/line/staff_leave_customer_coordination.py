"""Customer-facing LINE coordination for accepted Scheduling staff leave requests.

This adapter owns no leave or scheduling facts. It projects the current accepted
leave context into the existing LINE delivery-task owner and records a verified
customer postback through the existing Staff Leave receipt owner.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Callable
from urllib.parse import parse_qs, urlencode

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineUserId
from domains.scheduling.staff_leave_intake import StaffLeaveRequestStatus
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
from subsystems.scheduling.staff_leave_intake_workflow import (
    RecordStaffLeaveCustomerDecision,
    ReviewStaffLeaveRequest,
    StaffLeaveRequestSnapshot,
    StaffLeaveCustomerDecisionReceipt,
    StaffLeaveIntakeWorkflow,
    StaffLeaveIntakeWorkflowError,
)


_POSTBACK_PREFIX = "leave_customer_decision:"
_ALLOWED_DECISIONS = frozenset({"agree_defer", "reject_substitution"})


class StaffLeaveCustomerCoordinationApplication:
    def __init__(
        self,
        connection_factory: Callable[[], object],
        line_unit_of_work_factory: Callable[[], object],
        now: Callable[[], datetime],
    ) -> None:
        self._connection_factory = connection_factory
        self._line_unit_of_work_factory = line_unit_of_work_factory
        self._now = now

    def review(self, command: ReviewStaffLeaveRequest) -> StaffLeaveRequestSnapshot:
        """Commit a new acceptance and its customer inquiries in one transaction."""
        with self._line_unit_of_work_factory() as unit_of_work:
            repository = MySqlStaffLeaveIntakeRepository(unit_of_work._connection)
            # Serialize acceptance with review/replay. The existing workflow
            # still owns validation, transition, event and receipt persistence.
            before = repository.load_for_update(command.request_id)
            result = StaffLeaveIntakeWorkflow(repository).review(command)
            if (
                before is not None
                and before.status is StaffLeaveRequestStatus.PENDING
                and result.status is StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING
            ):
                context = repository.coordination_context(result.request_id, result.version)
                self._enqueue_inquiries(context, unit_of_work)
            # Replayed reviews never recreate a request with a new scheduled_at
            # under an already-used delivery key, even if recipients changed.
            unit_of_work.commit()
            return result

    def _enqueue_inquiries(self, context, unit_of_work) -> None:
        request_id = context["request_id"]
        version = context["request_version"]
        for target in context["targets"]:
            case_no = str(target["case_no"])
            recipient_value = target.get("client_line_user_id")
            if not isinstance(recipient_value, str) or not recipient_value.strip():
                continue
            identity = _interaction_identity(request_id, version, case_no)
            unit_of_work.delivery_tasks.enqueue(
                LineDeliveryRequest(
                    LineRecipient(LineRecipientType.USER, LineUserId(recipient_value.strip())),
                    LineMessageKind.FLEX,
                    canonical_line_payload_json(_inquiry_payload(request_id, version, case_no)),
                    self._now(),
                    IdempotencyKey(f"leave-customer-inquiry:{identity}"),
                    CorrelationId(f"leave-request:{request_id}:v{version}"),
                    "staff_leave_customer_coordination",
                    identity,
                )
            )

    def handle_postback(self, inbox, unit_of_work) -> bool:
        parsed = parse_staff_leave_customer_postback(_postback_data(inbox))
        if parsed is None:
            return False
        request_id, expected_version, case_no, decision = parsed
        source = getattr(inbox.event, "source", None)
        line_user_id = getattr(source, "user_id", None)
        source_type = getattr(source, "source_type", None)
        if line_user_id is None or getattr(source_type, "value", None) != "user":
            return True

        identity = _interaction_identity(request_id, expected_version, case_no)
        # The webhook consumer owns the outer transaction. Decision, customer
        # service need and acknowledgement must commit or roll back together.
        try:
            workflow = StaffLeaveIntakeWorkflow(
                MySqlStaffLeaveIntakeRepository(unit_of_work._connection),
            )
            receipt = workflow.record_customer_decision(
                RecordStaffLeaveCustomerDecision(
                    request_id=request_id,
                    expected_version=expected_version,
                    case_no=case_no,
                    line_user_id=line_user_id.value,
                    decision=decision,
                    # One terminal choice per accepted leave version/case. The
                    # decision is deliberately absent from this key so a later
                    # conflicting click cannot create a second terminal fact.
                    idempotency_key=f"leave-customer-decision:{identity}",
                )
            )
        except StaffLeaveIntakeWorkflowError:
            # Stale, wrong-recipient and conflicting clicks are terminal input
            # outcomes. The canonical webhook inbox remains their event trace;
            # do not retry them as transient provider failures.
            return True
        ticket_id = None
        if receipt.decision == "reject_substitution":
            # Customer Service owns one active conversation per user/category.
            # The immutable event identifies this exact leave request and case;
            # do not create another ticket root or overwrite an existing case.
            ticket = unit_of_work.customer_service.create_or_append(
                CreateCustomerServiceMessage(
                    line_user_id=receipt.line_user_id,
                    category=CustomerServiceCategory.SERVICE_PROGRESS,
                    message=(
                        f"代班需求（leave_substitute_required）：案件 {receipt.case_no}，"
                        f"請假申請 #{receipt.request_id}／版本 {receipt.request_version}。"
                        "客戶不同意順延，請工會安排代班；正式班表尚未變更。"
                    ),
                    event_key=f"leave-substitute-required:{identity}",
                    case_no=receipt.case_no,
                )
            )
            ticket_id = ticket.ticket_id

        # A repeated click reuses the saved decision/need, not a new delivery
        # with a different scheduled_at under the same idempotency identity.
        if not receipt.replayed:
            unit_of_work.delivery_tasks.enqueue(
                _decision_acknowledgement(
                    receipt, line_user_id, inbox.event.event_id.value,
                    self._now(), ticket_id=ticket_id,
                )
            )
        return True


def parse_staff_leave_customer_postback(
    data: str,
) -> tuple[int, int, str, str] | None:
    if not isinstance(data, str) or not data.startswith(_POSTBACK_PREFIX):
        return None
    try:
        values = parse_qs(data[len(_POSTBACK_PREFIX):], strict_parsing=True)
        if set(values) != {"request_id", "version", "case_no", "decision"}:
            return None
        request_id = int(_single(values, "request_id"))
        version = int(_single(values, "version"))
        case_no = _single(values, "case_no").strip()
        decision = _single(values, "decision")
    except (KeyError, TypeError, ValueError):
        return None
    if request_id <= 0 or version <= 0 or not case_no or len(case_no) > 50:
        return None
    if decision not in _ALLOWED_DECISIONS:
        return None
    return request_id, version, case_no, decision


def _single(values: dict[str, list[str]], key: str) -> str:
    items = values[key]
    if len(items) != 1:
        raise ValueError("postback field must occur exactly once")
    return items[0]


def _interaction_identity(request_id: int, version: int, case_no: str) -> str:
    digest = hashlib.sha256(case_no.encode("utf-8")).hexdigest()[:24]
    return f"{request_id}:v{version}:{digest}"


def _postback_value(request_id: int, version: int, case_no: str, decision: str) -> str:
    return _POSTBACK_PREFIX + urlencode(
        {
            "request_id": str(request_id),
            "version": str(version),
            "case_no": case_no,
            "decision": decision,
        }
    )


def _inquiry_payload(request_id: int, version: int, case_no: str) -> dict[str, object]:
    return {
        "type": "flex",
        "altText": f"請確認月嫂請假後續安排（案件 {case_no}）",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "月嫂請假安排確認",
                        "weight": "bold",
                        "size": "lg",
                    },
                    {
                        "type": "text",
                        "text": f"案件：{case_no}",
                        "size": "sm",
                        "wrap": True,
                    },
                    {
                        "type": "text",
                        "text": "月嫂提出請假，請選擇是否同意將受影響服務順延；若不同意順延，工會將接手安排代班。",
                        "size": "sm",
                        "wrap": True,
                    },
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "postback",
                            "label": "同意順延",
                            "data": _postback_value(
                                request_id, version, case_no, "agree_defer"
                            ),
                            "displayText": "同意順延",
                        },
                    },
                    {
                        "type": "button",
                        "action": {
                            "type": "postback",
                            "label": "不同意順延，請安排代班",
                            "data": _postback_value(
                                request_id, version, case_no, "reject_substitution"
                            ),
                            "displayText": "不同意順延，請安排代班",
                        },
                    },
                ],
            },
        },
    }


def _decision_acknowledgement(
    receipt: StaffLeaveCustomerDecisionReceipt,
    recipient: LineUserId,
    event_identity: str,
    scheduled_at: datetime,
    *,
    ticket_id: int | None = None,
) -> LineDeliveryRequest:
    if receipt.decision == "agree_defer":
        text = "已記錄您同意順延的選擇，工會將依正式排班流程處理。"
    else:
        if ticket_id is None:
            raise ValueError("leave_substitution_ticket_required")
        text = f"已登記案件 {receipt.case_no} 的代班需求（客服單 #{ticket_id}），待工會安排；正式班表尚未變更。"
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, recipient),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": text}),
        scheduled_at,
        IdempotencyKey(f"leave-customer-decision-ack:{receipt.fingerprint}"),
        CorrelationId(f"line-event:{event_identity}"),
        "staff_leave_customer_decision",
        receipt.fingerprint,
    )


def _postback_data(inbox) -> str:
    try:
        payload = json.loads(inbox.event.payload_json)
    except (TypeError, ValueError):
        return ""
    postback = payload.get("postback") if isinstance(payload, dict) else None
    data = postback.get("data") if isinstance(postback, dict) else None
    return data.strip() if isinstance(data, str) else ""


__all__ = [
    "StaffLeaveCustomerCoordinationApplication",
    "parse_staff_leave_customer_postback",
]
