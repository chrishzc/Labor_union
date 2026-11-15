"""
File: test_service_help_manual_fallback.py
Description: 驗證聊天室自助服務保留，舊客服指令不建立工單或變更歷史暫停狀態。
"""

from datetime import datetime, timezone
import json
import os
from types import SimpleNamespace

import pytest

from domains.line.identities import LineSourceType, LineUserId
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


def _inbox(event_id="event-1"):
    return SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value=event_id),
            source=SimpleNamespace(source_type=LineSourceType.USER, user_id=LineUserId("U123456789")),
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
    "message", ["呼叫專員", "轉真人客服", "幫我轉真人", "聯絡工會專員", "答錯，我要找客服"],
)
def test_retired_handoff_text_never_replies_or_writes(message):
    unit = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc))
    assert not application.handle(_inbox(), unit, LineUserId("U123456789"), message)
    assert not unit.customer_service.messages
    assert not unit.audit.intents
    assert not unit.delivery_tasks.requests


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
        "一般市民（最高40小時）",
        "補助市民（最高120小時）",
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
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc))
    assert application.handle(_inbox(), unit, LineUserId('U123456789'), message)
    assert not unit.customer_service.messages
    payload = json.loads(unit.delivery_tasks.requests[0].payload_json)
    assert payload['type'] == 'flex' and '服務與問答' in str(payload)


@pytest.mark.parametrize('message', [
    '服務流程', '流程', '怎麼申請', '如何登記', '怎麼媒合', '1',
    '收費與補助', '收費', '費用', '價格', '補助', '政府補助', '要付多少', '2',
    '一般市民（最高40小時）', '補助市民（最高120小時）',
])
def test_explanatory_commands_open_ai_liff_without_ticket_or_old_copy(message, monkeypatch):
    monkeypatch.setenv('LINE_LIFF_ID', '1234567890-service-help')
    unit = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc))
    assert application.handle(_inbox(), unit, LineUserId('U123456789'), message)
    assert len(unit.delivery_tasks.requests) == 1
    payload = json.loads(unit.delivery_tasks.requests[0].payload_json)
    assert payload['type'] == 'flex'
    assert payload['contents']['body']['contents'][0]['action'] == {
        'type': 'uri', 'label': '開啟 AI 客服',
        'uri': 'https://liff.line.me/1234567890-service-help?target=ai_assistant',
    }
    assert '最高40小時' not in json.dumps(payload, ensure_ascii=False)
    assert '最高120小時' not in json.dumps(payload, ensure_ascii=False)
    assert not unit.customer_service.messages and not unit.audit.intents


@pytest.mark.parametrize('message', ['服務流程', '收費與補助'])
def test_legacy_handler_uses_the_same_ai_liff_navigation(message, monkeypatch):
    from subsystems.line.webhook_identity_handlers import _handle_service_help_text
    from subsystems.line.service_help_application import _ai_assistant_payload
    monkeypatch.setenv('LINE_LIFF_ID', '1234567890-service-help')
    unit = _unit_of_work()
    assert _handle_service_help_text(_inbox(), unit, LineUserId('U123456789'), message, datetime.now(timezone.utc))
    assert json.loads(unit.delivery_tasks.requests[0].payload_json) == _ai_assistant_payload()
    assert not unit.customer_service.messages


def test_legacy_menu_opens_explanations_in_liff(monkeypatch):
    from subsystems.line.webhook_identity_handlers import _handle_service_help_text
    monkeypatch.setenv('LINE_LIFF_ID', '1234567890-service-help')
    unit = _unit_of_work()
    assert _handle_service_help_text(_inbox(), unit, LineUserId('U123456789'), '服務說明', datetime.now(timezone.utc))
    payload = json.loads(unit.delivery_tasks.requests[0].payload_json)
    actions = [item['action'] for item in payload['quickReply']['items']]
    assert [action['label'] for action in actions[:2]] == ['服務流程', '收費與補助']
    assert all(action['type'] == 'uri' and action['uri'] == 'https://liff.line.me/1234567890-service-help?target=ai_assistant' for action in actions[:2])
    assert actions[3]['text'] == '修改登記資料'


def test_profile_update_opens_verified_liff_without_ticket(monkeypatch):
    monkeypatch.setenv("LINE_LIFF_ID", "synthetic-liff")
    unit = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc))
    assert application.handle(_inbox(), unit, LineUserId("U123456789"), "修改登記資料")
    assert not unit.customer_service.messages
    [request] = unit.delivery_tasks.requests
    assert request.source_aggregate_type == "line_webhook_reply"
    assert "https://liff.line.me/synthetic-liff?target=profile_update" in request.payload_json


def test_service_help_menu_opens_liff_for_explanations_and_preserves_service_actions(monkeypatch) -> None:
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
        f"https://liff.line.me/{liff_id}?target=ai_assistant",
        f"https://liff.line.me/{liff_id}?target=ai_assistant",
        "查詢服務進度",
        "修改登記資料",
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
        "詢問其他問題",
    ]
    assert "月嫂身分認證" not in service_request.payload_json


def test_order_update_menu_and_legacy_text_open_same_form(monkeypatch) -> None:
    monkeypatch.setenv('LINE_LIFF_ID', '1234567890-order')
    menu_uow = _unit_of_work()
    request_uow = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 21, tzinfo=timezone.utc))

    assert application.handle(
        _inbox("event-order-menu"), menu_uow, LineUserId("U123456789"), "修改訂單資訊"
    ) is True

    menu_request = menu_uow.delivery_tasks.requests[0]
    payload = json.loads(menu_request.payload_json)
    assert payload["contents"]["header"]["contents"][1]["text"] == "修改訂單資訊"
    actions = [button['action'] for button in payload['contents']['body']['contents']]
    assert actions == [{'type': 'uri', 'label': '開啟訂單異動表單',
                        'uri': 'https://liff.line.me/1234567890-order?target=order_update'}]
    assert not menu_uow.customer_service.messages

    assert application.handle(
        _inbox("event-order-request"), request_uow, LineUserId("U123456789"), "修改服務地址"
    ) is True
    assert not request_uow.customer_service.messages
    assert not request_uow.audit.intents
    [redirect] = request_uow.delivery_tasks.requests
    assert redirect.source_aggregate_type == "line_webhook_reply"
    assert json.loads(redirect.payload_json) == payload


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


@pytest.mark.parametrize("postback", [
    "customer-service:handoff:continue-ai",
    "customer-service:handoff:confirm:answer-rejected",
    "customer-service:handoff:resume-ai",
])
def test_old_ai_postback_only_guides_direct_chat(postback):
    unit = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc))
    assert application.handle_postback(_inbox(), unit, LineUserId("U123456789"), postback)
    [request] = unit.delivery_tasks.requests
    assert request.source_aggregate_type == "line_webhook_reply"
    assert json.loads(request.payload_json) == {
        "type": "text", "text": "此功能已停用。如需協助，請直接在此聊天室留言。",
    }
    assert not unit.customer_service.messages
    assert not unit.audit.intents


@pytest.mark.parametrize("command", ["恢復ai", "恢復機器人", "恢復機器人回答", "繼續讓機器人回答"])
def test_old_resume_text_only_guides_direct_chat(command):
    unit = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime.now(timezone.utc))
    assert application.handle(_inbox(), unit, LineUserId("U123456789"), command)
    [request] = unit.delivery_tasks.requests
    assert request.source_aggregate_type == "line_webhook_reply"
    assert "直接在此聊天室留言" in request.payload_json
    assert not unit.customer_service.messages
    assert not unit.audit.intents


@pytest.mark.parametrize('liff_id', ['', 'your_liff_id_here'])
def test_order_update_menu_without_configured_liff_has_no_invented_link(liff_id, monkeypatch):
    from subsystems.line.service_help_application import _order_update_menu_payload
    monkeypatch.setenv('LINE_LIFF_ID', liff_id)
    payload = _order_update_menu_payload()
    assert payload['contents']['body']['contents'] == []
    assert '入口尚未完成設定' in payload['contents']['header']['contents'][2]['text']
    assert '修改服務天數' not in json.dumps(payload, ensure_ascii=False)
