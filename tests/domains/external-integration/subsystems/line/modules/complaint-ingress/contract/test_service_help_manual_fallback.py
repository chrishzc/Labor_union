"""
File: test_service_help_manual_fallback.py
Description: 驗證客服 referral 的 typed escalation、同一 UoW、去敏 command、active hold 與 durable delivery 邊界。
"""

from datetime import datetime, timezone
import json
import os
import re
from types import SimpleNamespace

import pytest

from domains.customer_service.escalation import TriggerCode
from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.identities import LineUserId
from subsystems.customer_service.escalation_contracts import CreateHumanEscalation, HumanEscalationError
from subsystems.line.service_help_application import LineServiceHelpApplication


class _DeliveryTasks:
    def __init__(self):
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)


class _CustomerService:
    def __init__(self):
        self.messages = []

    def create_or_append(self, command):
        self.messages.append(command)
        return SimpleNamespace(ticket_id=31)

    def latest_client_case(self, _line_user_id):
        return None


class _Audit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


class _EscalationGateway:
    def __init__(self, hold_error=None, resume_receipt=None):
        self.hold_error = hold_error
        self.resume_receipt = resume_receipt
        self.hold_calls = []
        self.create_calls = []
        self.resume_calls = []

    def hold_guard(self, hold_scope, unit_of_work):
        self.hold_calls.append((hold_scope, unit_of_work))
        if self.hold_error is not None:
            raise self.hold_error

    def create_for_ticket(self, command, ticket, unit_of_work):
        self.create_calls.append((command, ticket, unit_of_work))
        return SimpleNamespace(escalation_id=41)

    def resume_by_requester_in_unit_of_work(self, command, unit_of_work):
        self.resume_calls.append((command, unit_of_work))
        return self.resume_receipt


def _inbox(event_id="event-1"):
    return SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value=event_id),
            payload_json=json.dumps({"replyToken": f"reply-{event_id}"}),
        )
    )


def _unit_of_work():
    return SimpleNamespace(
        delivery_tasks=_DeliveryTasks(),
        customer_service=_CustomerService(),
        audit=_Audit(),
    )


@pytest.mark.parametrize(
    "message_text",
    ("呼叫專員", "轉真人客服", "幫我轉真人", "聯絡工會專員"),
)
def test_human_request_directly_creates_ticket_without_confirmation(message_text: str) -> None:
    unit_of_work = _unit_of_work()
    gateway = _EscalationGateway()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc), escalation_gateway=gateway,
    )
    assert application.handle(_inbox(), unit_of_work, LineUserId("U123456789"), message_text) is True
    assert len(unit_of_work.customer_service.messages) == 1
    assert len(gateway.create_calls) == 1
    payload = json.loads(unit_of_work.delivery_tasks.requests[0].payload_json)
    assert payload == {"type": "text", "text": "已收到您的聯絡需求，請留言說明問題，專員將盡快回覆。"}


def test_unscoped_subsidy_amount_asks_which_program_the_customer_means() -> None:
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc)
    )

    assert application.handle(
        _inbox("event-subsidy-scope"),
        unit_of_work,
        LineUserId("U123456789"),
        "補助多少",
    ) is True

    assert unit_of_work.customer_service.messages == []
    payload = json.loads(unit_of_work.delivery_tasks.requests[0].payload_json)
    assert payload["text"] == "為了正確協助您，請選擇較接近的項目。"
    assert [item["action"]["label"] for item in payload["quickReply"]["items"]] == [
        "補助市民（最高40小時）",
        "社福（最高120小時）",
    ]


def test_reply_token_is_never_used_as_a_precommit_provider_call() -> None:
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 21, tzinfo=timezone.utc))

    application.handle(_inbox("event-2"), unit_of_work, LineUserId("U123456789"), "服務說明")

    assert len(unit_of_work.delivery_tasks.requests) == 1
    assert "reply-event-2" not in unit_of_work.delivery_tasks.requests[0].payload_json


@pytest.mark.parametrize('message', ['問題', '其他問題', '詢問其他問題', '其他', '5', '6'])
def test_general_questions_open_self_service_without_creating_ticket(message):
    unit = _unit_of_work()
    gateway = _EscalationGateway()
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc), escalation_gateway=gateway)
    assert application.handle(_inbox(), unit, LineUserId('U123456789'), message)
    assert not unit.customer_service.messages and not gateway.create_calls
    payload = json.loads(unit.delivery_tasks.requests[0].payload_json)
    assert payload['type'] == 'flex' and '服務與問答' in str(payload)


@pytest.mark.parametrize('message', ['問題', '其他問題', '6'])
def test_general_question_during_active_ticket_is_appended_without_auto_reply(message):
    unit = _unit_of_work()
    gateway = _EscalationGateway(HumanEscalationError('domain_blocked', 'automation_hold_active', '自動化暫停中'))
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc), escalation_gateway=gateway)
    assert application.handle(_inbox(), unit, LineUserId('U123456789'), message)
    assert len(unit.customer_service.messages) == 1
    assert unit.customer_service.messages[0].message == message
    assert not unit.delivery_tasks.requests and not gateway.create_calls


@pytest.mark.parametrize('message', ['收費與補助', '補助市民（最高40小時）', '社福（最高120小時）'])
def test_current_subsidy_copy_and_clarification_choices_do_not_open_ticket(message):
    unit = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc))
    assert application.handle(_inbox(), unit, LineUserId('U123456789'), message)
    payload = json.loads(unit.delivery_tasks.requests[0].payload_json)
    assert '補助市民（最高40小時）' in payload['text']
    assert '社福（最高120小時）' in payload['text']
    assert '實際補助金額依本案服務資料計算' in payload['text']
    assert '資格需' not in payload['text'] and not unit.customer_service.messages


def test_service_help_menu_keeps_all_six_approved_categories(monkeypatch) -> None:
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-service-help")
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 21, tzinfo=timezone.utc))

    assert application.handle(
        _inbox("event-menu"), unit_of_work, LineUserId("U123456789"), "服務說明"
    ) is True

    payload = json.loads(unit_of_work.delivery_tasks.requests[0].payload_json)
    assert payload["contents"]["header"]["contents"][1]["text"] == "服務與問答"
    buttons = payload["contents"]["body"]["contents"]
    liff_id = os.getenv("LINE_LIFF_ID") or "ai-assistant"
    assert [
        button["action"].get("text")
        or button["action"].get("data")
        or button["action"].get("uri")
        for button in buttons
    ] == [
        "服務流程",
        "收費與補助",
        "查詢服務進度",
        "修改登記資料",
        "customer-service:handoff:confirm",
        f"https://liff.line.me/{liff_id}?target=ai_assistant",
    ]
    assert "月嫂身分認證" not in unit_of_work.delivery_tasks.requests[0].payload_json


def test_service_help_and_faq_aliases_share_one_card() -> None:
    service_uow = _unit_of_work()
    faq_uow = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 21, tzinfo=timezone.utc))

    assert application.handle(
        _inbox("event-service"), service_uow, LineUserId("U123456789"), "服務與問答"
    ) is True
    assert application.handle(
        _inbox("event-faq"), faq_uow, LineUserId("U123456789"), "常見問答"
    ) is True

    service_request = service_uow.delivery_tasks.requests[0]
    faq_request = faq_uow.delivery_tasks.requests[0]
    service_payload = json.loads(service_request.payload_json)
    faq_payload = json.loads(faq_request.payload_json)
    assert service_request.idempotency_key.value == "service-help:menu:event-service"
    assert faq_request.idempotency_key.value == "service-help:menu:event-faq"
    assert service_payload == faq_payload
    assert service_payload["contents"]["header"]["contents"][1]["text"] == "服務與問答"
    assert [button["action"]["label"] for button in service_payload["contents"]["body"]["contents"]] == [
        "如何申請服務？",
        "費用與補助怎麼算？",
        "如何查詢目前進度？",
        "登記資料填錯怎麼辦？",
        "呼叫專員",
        "詢問其他問題",
    ]
    assert "月嫂身分認證" not in service_request.payload_json


def test_order_update_menu_creates_human_review_request_without_mutating_order() -> None:
    menu_uow = _unit_of_work()
    request_uow = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 21, tzinfo=timezone.utc))

    assert application.handle(
        _inbox("event-order-menu"), menu_uow, LineUserId("U123456789"), "修改訂單資訊"
    ) is True

    menu_request = menu_uow.delivery_tasks.requests[0]
    payload = json.loads(menu_request.payload_json)
    assert payload["contents"]["header"]["contents"][1]["text"] == "修改訂單資訊"
    assert [button["action"]["label"] for button in payload["contents"]["body"]["contents"]] == [
        "修改服務地址",
        "修改下廚需求",
        "修改服務天數",
        "修改每日服務時段",
        "其他訂單內容",
    ]

    assert application.handle(
        _inbox("event-order-request"), request_uow, LineUserId("U123456789"), "修改服務地址"
    ) is True
    ticket_command = request_uow.customer_service.messages[0]
    assert ticket_command.category is CustomerServiceCategory.OTHER
    assert ticket_command.message == "修改服務地址"
    assert ticket_command.event_key == "line-service-help:order-update:event-order-request"
    assert "尚未直接變更正式訂單" in request_uow.delivery_tasks.requests[0].payload_json
    assert len(request_uow.audit.intents) == 1


def test_unknown_text_falls_through_to_canonical_knowledge_scheduler() -> None:
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 21, tzinfo=timezone.utc))

    assert application.handle(
        _inbox("event-knowledge"), unit_of_work, LineUserId("U123456789"), "育兒問題"
    ) is False
    assert unit_of_work.delivery_tasks.requests == []


def test_exact_replay_keeps_the_same_durable_delivery_identity() -> None:
    first_uow = _unit_of_work()
    second_uow = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 21, tzinfo=timezone.utc))

    application.handle(_inbox("event-3"), first_uow, LineUserId("U123456789"), "服務說明")
    application.handle(_inbox("event-3"), second_uow, LineUserId("U123456789"), "服務說明")

    assert first_uow.delivery_tasks.requests[0].idempotency_key == second_uow.delivery_tasks.requests[0].idempotency_key


def test_explicit_human_referral_maps_masked_escalation_in_same_unit_of_work() -> None:
    unit_of_work = _unit_of_work()
    gateway = _EscalationGateway()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
        escalation_gateway=gateway,
    )

    assert application.handle(_inbox("event-escalate"), unit_of_work, LineUserId("U123456789"), "專人客服") is True

    command, ticket, gateway_uow = gateway.create_calls[0]
    assert isinstance(command, CreateHumanEscalation)
    assert ticket.ticket_id == 31
    assert gateway_uow is unit_of_work
    assert command.source_kind == "ticket_referral"
    assert command.trigger_code is TriggerCode.EXPLICIT_HUMAN_REQUEST
    assert set(command.context.as_dict()) == {"summary_code", "policy_version", "category", "redaction_version"}
    assert "我要找客服" not in repr(command.context)
    assert "U123456789" not in repr(command.context)
    assert re.fullmatch(r"[0-9a-f]{64}", command.hold_scope)
    assert re.fullmatch(r"[0-9a-f]{64}", command.source_fingerprint)


def test_wrong_answer_with_explicit_human_request_directly_creates_escalation() -> None:
    unit_of_work = _unit_of_work()
    gateway = _EscalationGateway()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc), escalation_gateway=gateway,
    )
    application.handle(_inbox("event-wrong"), unit_of_work, LineUserId("U123456789"), "答錯，我要找客服")
    assert len(gateway.create_calls) == 1
    assert "quickReply" not in json.loads(unit_of_work.delivery_tasks.requests[0].payload_json)


@pytest.mark.parametrize('postback', [
    'customer-service:handoff:continue-ai',
    'customer-service:handoff:confirm:answer-rejected',
])
def test_old_continue_ai_postback_does_not_resume_or_close_ticket(postback) -> None:
    unit_of_work = _unit_of_work()
    gateway = _EscalationGateway(resume_receipt=SimpleNamespace(escalation_id=41))
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc), escalation_gateway=gateway,
    )
    assert application.handle_postback(
        _inbox("event-continue-ai"), unit_of_work, LineUserId("U123456789"),
        postback,
    ) is True
    assert gateway.resume_calls == []
    assert gateway.create_calls == []
    assert unit_of_work.customer_service.messages == []
    payload = json.loads(unit_of_work.delivery_tasks.requests[0].payload_json)
    assert payload == {"type": "text", "text": "此功能已停用。如需協助，請輸入「呼叫專員」。"}


def test_call_postback_directly_creates_ticket_with_short_acknowledgement() -> None:
    unit_of_work = _unit_of_work()
    gateway = _EscalationGateway()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc), escalation_gateway=gateway,
    )
    assert application.handle_postback(
        _inbox("event-confirm"), unit_of_work, LineUserId("U123456789"),
        "customer-service:handoff:confirm",
    ) is True
    assert len(gateway.create_calls) == 1
    assert json.loads(unit_of_work.delivery_tasks.requests[0].payload_json) == {
        "type": "text", "text": "已收到您的聯絡需求，請留言說明問題，專員將盡快回覆。",
    }


def test_old_resume_postback_preserves_active_ticket() -> None:
    unit_of_work = _unit_of_work()
    gateway = _EscalationGateway(resume_receipt=SimpleNamespace(escalation_id=41))
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc), escalation_gateway=gateway,
    )
    assert application.handle_postback(
        _inbox("event-resume"), unit_of_work, LineUserId("U123456789"),
        "customer-service:handoff:resume-ai",
    ) is True
    assert gateway.resume_calls == []
    assert gateway.create_calls == []
    assert unit_of_work.customer_service.messages == []
    assert "quickReply" not in json.loads(unit_of_work.delivery_tasks.requests[0].payload_json)


@pytest.mark.parametrize(
    "resume_text", ("恢復ai", "恢復機器人", "恢復機器人回答", "繼續讓機器人回答"),
)
def test_old_resume_message_does_not_release_active_ticket(resume_text: str) -> None:
    unit_of_work = _unit_of_work()
    gateway = _EscalationGateway(
        HumanEscalationError("domain_blocked", "automation_hold_active", "自動化暫停中"),
        resume_receipt=SimpleNamespace(escalation_id=41),
    )
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc), escalation_gateway=gateway,
    )
    assert application.handle(
        _inbox("event-lowercase-resume"), unit_of_work, LineUserId("U123456789"), resume_text,
    ) is True
    assert gateway.resume_calls == []
    assert gateway.create_calls == []
    assert unit_of_work.customer_service.messages == []
    assert json.loads(unit_of_work.delivery_tasks.requests[0].payload_json) == {
        "type": "text", "text": "此功能已停用。如需協助，請輸入「呼叫專員」。",
    }


def test_active_hold_appends_to_existing_ticket_without_auto_reply() -> None:
    unit_of_work = _unit_of_work()
    hold_error = HumanEscalationError("domain_blocked", "automation_hold_active", "自動化暫停中")
    gateway = _EscalationGateway(hold_error)
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
        escalation_gateway=gateway,
    )

    assert application.handle(
        _inbox("event-held"),
        unit_of_work,
        LineUserId("U123456789"),
        "我想要真人回答",
    ) is True

    assert len(unit_of_work.customer_service.messages) == 1
    assert unit_of_work.delivery_tasks.requests == []
    assert len(unit_of_work.audit.intents) == 1
    assert gateway.create_calls == []


def test_explicit_preview_manual_fallback_can_reuse_active_hold_ticket() -> None:
    unit_of_work = _unit_of_work()
    gateway = _EscalationGateway(
        HumanEscalationError("domain_blocked", "automation_hold_active", "自動化暫停中")
    )
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
        escalation_gateway=gateway,
    )

    ticket_id = application.apply_manual_fallback(
        _inbox("event-preview-fallback"),
        unit_of_work,
        LineUserId("U123456789"),
        "高信心但沒有已發布答案",
    )

    assert ticket_id == 31
    assert gateway.hold_calls == []
    assert len(gateway.create_calls) == 1
