"""
File: test_line_customer_service_first_release.py
Description: 驗證客服、Rich Menu、LIFF 與 durable LINE delivery 第一版 canonical 邊界。
"""

from datetime import datetime, timezone
from contextlib import nullcontext
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routes import line_identity
from api.routes import line_mobile_admin
from api.routes.customer_service import router as customer_service_router
from api.schemas.line_identity import LineIdentityFlowOpenRequest
from domains.customer_service.ticket import (
    CustomerServiceCategory,
    CustomerServiceStatus,
    CustomerServiceTransitionError,
    transition_ticket,
)
from domains.line.faq_chat_layout import FaqButton, FaqCardView, FaqLayout, FaqPreview
from domains.line.identities import LineSourceType, LineUserId
from shared_kernel.migration_release import load_migration_release_manifest
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers


PROJECT_ROOT = Path(__file__).resolve().parents[6]


class DeliveryTasks:
    def __init__(self):
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)


class CustomerServiceRepository:
    def __init__(self):
        self.messages = []

    def create_or_append(self, command):
        self.messages.append(command)
        return SimpleNamespace(ticket_id=31)

    def latest_client_case(self, _line_user_id):
        return None


class Audit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


class ReplyProvider:
    def __init__(self):
        self.calls = []

    def reply(self, reply_token, message):
        self.calls.append((reply_token, message))
        raise AssertionError("service-help must not call LINE provider before commit")


def _inbox(event_id="event-1"):
    return SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value=event_id),
            source=SimpleNamespace(
                source_type=LineSourceType.USER, user_id=LineUserId("U123456789"),
            ),
            payload_json=json.dumps({"replyToken": f"reply-{event_id}"}),
        )
    )


def _unit_of_work():
    return SimpleNamespace(
        delivery_tasks=DeliveryTasks(),
        customer_service=CustomerServiceRepository(),
        audit=Audit(),
    )


def test_customer_service_ticket_state_machine_rejects_backwards_transition():
    assert transition_ticket(CustomerServiceStatus.WAITING, CustomerServiceStatus.HANDLING) is CustomerServiceStatus.HANDLING
    with pytest.raises(CustomerServiceTransitionError):
        transition_ticket(CustomerServiceStatus.RESOLVED, CustomerServiceStatus.HANDLING)
    with pytest.raises(CustomerServiceTransitionError):
        transition_ticket(CustomerServiceStatus.HANDLING, CustomerServiceStatus.WAITING)


def test_service_help_menu_is_a_canonical_flex_delivery():
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 11, tzinfo=timezone.utc),
        faq_layout=SimpleNamespace(published_layout=FaqLayout),
    )

    handled = application.handle(_inbox(), unit_of_work, LineUserId("U123456789"), "服務說明")

    assert handled is True
    assert len(unit_of_work.delivery_tasks.requests) == 1
    request = unit_of_work.delivery_tasks.requests[0]
    assert request.message_kind.value == "flex"
    assert request.idempotency_key.value == "service-help:menu:event-1"
    assert "customer-service:handoff:confirm" not in request.payload_json
    assert "target=ai_assistant" in request.payload_json
    assert "月嫂身分認證" not in request.payload_json


def test_service_help_never_uses_reply_token_before_durable_delivery():
    unit_of_work = _unit_of_work()
    provider = ReplyProvider()
    assert "reply_provider" not in inspect.signature(LineServiceHelpApplication).parameters
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 11, tzinfo=timezone.utc),
        faq_layout=SimpleNamespace(published_layout=FaqLayout),
    )

    handled = application.handle(_inbox(), unit_of_work, LineUserId("U123456789"), "服務說明")

    assert handled is True
    assert provider.calls == []
    assert len(unit_of_work.delivery_tasks.requests) == 1
    request = unit_of_work.delivery_tasks.requests[0]
    assert request.message_kind.value == "flex"
    assert request.idempotency_key.value == "service-help:menu:event-1"


def test_old_handoff_postback_background_path_is_inert():
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 11, tzinfo=timezone.utc)
    )

    handled = application.handle_postback(
        _inbox("event-2"),
        unit_of_work,
        LineUserId("U123456789"),
        "customer-service:handoff:confirm",
    )

    assert handled is False
    assert unit_of_work.customer_service.messages == []
    assert unit_of_work.audit.intents == []
    assert unit_of_work.delivery_tasks.requests == []


def test_service_help_accepts_rulebook_progress_alias_and_uses_approved_copy():
    def preview(category_id):
        assert category_id == "payment_subsidy"
        return FaqPreview(FaqCardView(
            category_id, "費用與補助", "", "詢問 AI 客服",
            (FaqButton("qa-fee", "費用說明", "正式問題", "正式答案"),),
        ), ())

    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 11, tzinfo=timezone.utc),
        faq_layout=SimpleNamespace(preview_published=preview),
    )

    handled = application.handle(_inbox("event-4"), unit_of_work, LineUserId("U123456789"), "訂單進度")

    assert handled is True
    assert "服務登記" in unit_of_work.delivery_tasks.requests[0].payload_json

    application.handle(_inbox("event-5"), unit_of_work, LineUserId("U123456789"), "收費與補助")

    fee_payload = json.loads(unit_of_work.delivery_tasks.requests[1].payload_json)
    [button] = fee_payload["contents"]["body"]["contents"]
    assert button["action"] == {"type": "postback", "data": "faq:v1:question:qa-fee", "label": "費用說明"}


def test_service_registration_text_returns_the_non_expiring_liff_entrypoint(monkeypatch):
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-AbCdEf")
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 11, tzinfo=timezone.utc))

    handled = application.handle(_inbox("event-registration"), unit_of_work, LineUserId("U123456789"), "服務登記")

    assert handled is True
    payload = unit_of_work.delivery_tasks.requests[0].payload_json
    assert "https://liff.line.me/1234567890-AbCdEf?entry=registration" in payload
    assert "target=registration" not in payload


def test_unbound_progress_creates_a_canonical_customer_binding_flow():
    unit_of_work = _unit_of_work()
    unit_of_work.identity_flows = _IdentityFlows()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 11, tzinfo=timezone.utc),
        lambda purpose, flow_id: f"https://example.test/{purpose}/{flow_id}",
    )

    handled = application.handle(_inbox("event-6"), unit_of_work, LineUserId("U123456789"), "查詢進度")

    assert handled is True
    assert unit_of_work.identity_flows.commands[0].idempotency_key.value == "service-help-binding:event-6"
    assert "https://example.test/customer_binding/flow-1" in unit_of_work.delivery_tasks.requests[0].payload_json


def test_webhook_handler_delegates_service_help_to_the_injected_owner_workflow():
    service_help = _RecordingServiceHelpApplication()
    handler = LineWebhookIdentityHandlers(
        lambda: datetime(2026, 8, 11, tzinfo=timezone.utc),
        lambda _purpose, _flow_id: "https://example.test/identity",
        service_help_application=service_help,
    )
    inbox = SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value="event-3"),
            occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            payload_json='{"message":{"type":"text","text":"服務說明"}}',
            source=SimpleNamespace(
                source_type=SimpleNamespace(value="user"),
                user_id=LineUserId("U123456789"),
            ),
        )
    )
    unit_of_work = SimpleNamespace(platform_users=SimpleNamespace(apply_friend_event=lambda _event: None))

    handler.handle_message(inbox, unit_of_work)

    assert service_help.calls == [("U123456789", "服務說明")]


class _RecordingServiceHelpApplication:
    def __init__(self):
        self.calls = []

    def handle(self, _inbox, _unit_of_work, line_user_id, text):
        self.calls.append((line_user_id.value, text))
        return True


class _IdentityFlows:
    def __init__(self):
        self.commands = []

    def open(self, command):
        self.commands.append(command)
        return SimpleNamespace(
            purpose=command.purpose,
            flow_id=SimpleNamespace(value="flow-1"),
        )


def test_first_release_schema_has_versioned_ticket_and_append_only_events():
    schema = (PROJECT_ROOT / "db/schema_parts/185_customer_service_runtime.sql").read_text(encoding="utf-8")
    assert "version BIGINT NOT NULL" in schema
    assert "customer_service_ticket_events" in schema
    assert "UNIQUE KEY uq_customer_service_event_key" in schema
    assert "active_marker" in schema


def test_stage11_migration_manifest_hashes_customer_service_artifacts():
    path = PROJECT_ROOT / "db/migration_releases/labor_union_2026_08_11_line_stage11_v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = [*manifest["artifacts"], manifest["descriptor_artifact"]]
    for artifact in artifacts:
        content = (PROJECT_ROOT / artifact["relative_path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]


def test_stage11_manifest_is_accepted_by_the_canonical_loader():
    path = (
        PROJECT_ROOT
        / "db/migration_releases/labor_union_2026_08_11_line_stage11_v1.json"
    )
    manifest = load_migration_release_manifest(path, PROJECT_ROOT)
    artifact_names = [item.artifact.name for item in manifest.schema_artifacts]
    assert artifact_names == ["185_customer_service_runtime.sql"]


def test_customer_context_uses_canonical_identity_binding_ssot():
    repository = (
        PROJECT_ROOT / "infrastructure/mysql/customer_service_repository.py"
    ).read_text(encoding="utf-8")
    assert "FROM line_identity_role_bindings b" in repository
    assert "FROM line_identity_bindings b" not in repository
    assert "WHERE c.line_user_id=%s" not in repository


def test_merge_menu_copy_uses_canonical_entry_and_verified_staff_liff_targets():
    menu = json.loads(
        (PROJECT_ROOT / "config/line_menu.json").read_text(encoding="utf-8")
    )
    identity = (PROJECT_ROOT / "line/static/identity.html").read_text(encoding="utf-8")
    staff_orders = (PROJECT_ROOT / "line/static/staff_order_search.html").read_text(encoding="utf-8")
    action_uris = {
        button["action"]["uri"]
        for menu_definition in menu["menus"]
        for button in menu_definition["buttons"]
        if button.get("action", {}).get("type") == "uri"
    }
    message_texts = {
        button["action"]["text"]
        for menu_definition in menu["menus"]
        for button in menu_definition["buttons"]
        if button.get("action", {}).get("type") == "message"
    }
    customer_menu = next(item for item in menu["menus"] if item["id"] == "customer_menu")
    customer_quadrants = [
        (
            button["label"],
            button["action"]["type"],
            button["action"].get("text"),
            button["action"].get("uri") or button["action"].get("data"),
        )
        for button in customer_menu["buttons"]
    ]
    assert "?entry=gateway" in action_uris or "?entry=registration" in action_uris
    assert "?target=registration" not in action_uris
    assert "?target=faq" not in action_uris  # FAQ is a tab of the merged LIFF entry.
    assert "常見問題" in message_texts
    assert "服務說明" not in message_texts
    assert "常見問答" not in message_texts
    assert customer_menu["size"] == {"width": 2500, "height": 843}
    assert customer_quadrants == [
        ("案件資訊", "postback", None, "customer:case-information"),
        ("常見問題", "message", "常見問題", None),
    ]
    assert "?target=staff_order_search" in action_uris
    assert "?target=staff_schedule" in action_uris
    assert "?target=staff_baby_log" not in action_uris
    assert "?target=staff_payout" in action_uris
    assert "flow_id=${encodeURIComponent(flowId)}" in identity
    assert "development_line_user_id" not in staff_orders
    assert "userId" not in staff_orders


def test_staff_self_service_exposes_leave_flow_and_retires_baby_log():
    schedule = (
        PROJECT_ROOT / "line/static/staff_schedule.html"
    ).read_text(encoding="utf-8")
    assert not (PROJECT_ROOT / "line/static/staff_baby_log.html").exists()

    assert "/api/v1/line/staff-self-service/leave-results/" in schedule
    assert "leaveResultPost('propose'," in schedule
    assert "submitPostponeProposal" in schedule
    assert '/leave-requests/preview' not in schedule
    assert 'confirmLeave' not in schedule
    assert "LINE provider" not in schedule
    assert 'params.get("userId")' not in schedule
    assert 'searchParams.get("userId")' not in schedule
    assert 'development_line_user_id: ""' in schedule


def test_identity_flow_requires_and_forwards_client_idempotency_key(monkeypatch):
    recorded = {}

    class _IdentityApplication:
        def open_flow(self, purpose, line_user_id, idempotency_key, correlation_id):
            recorded.update(
                purpose=purpose.value,
                line_user_id=line_user_id.value,
                idempotency_key=idempotency_key.value,
                correlation_id=correlation_id.value,
            )
            return SimpleNamespace(
                flow_id=SimpleNamespace(value="flow-1"),
                purpose=purpose,
                expires_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )

    monkeypatch.setattr(
        line_identity,
        "_verified_line_user_id",
        lambda _payload: LineUserId("U123456789"),
    )
    monkeypatch.setattr(
        line_identity,
        "get_line_identity_application",
        lambda: _IdentityApplication(),
    )
    payload = LineIdentityFlowOpenRequest(
        purpose="staff_self_service",
        idempotency_key="staff-self-service:browser-session-1",
    )

    response = line_identity.open_identity_flow(payload)

    assert response.data.flow_id == "flow-1"
    assert recorded["idempotency_key"] == "staff-self-service:browser-session-1"
    with pytest.raises(ValidationError):
        LineIdentityFlowOpenRequest(purpose="staff_self_service")


def test_deferred_history_records_legacy_paths_that_must_not_return():
    history = (PROJECT_ROOT / "document/架構重整/03_追蹤清單與證據/LINE_merge功能未移植_history_20260811.md").read_text(encoding="utf-8")
    assert "query string `userId`" in history
    assert "人工 Preview／Apply" in history
    assert "直接 UPDATE clients" in history


def test_mobile_admin_actor_comes_from_verified_current_line_binding(monkeypatch):
    monkeypatch.setattr(
        line_mobile_admin,
        "get_liff_token_verifier",
        lambda: SimpleNamespace(
            verify=lambda _: SimpleNamespace(line_user_id=LineUserId("U-admin"))
        ),
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "open_line_unit_of_work",
        lambda: nullcontext(SimpleNamespace(admins=SimpleNamespace(
            get_linked_admin=lambda _: SimpleNamespace(
                admin_user_id=7,
                display_name="Reviewer",
                role="line_viewer",
            )
        ))),
    )

    principal, actor = line_mobile_admin._mobile_admin_context("verified-token")

    assert principal.id == 7
    assert principal.username == "admin:7"
    assert principal.linked_line_user_id == "U-admin"
    assert actor.actor_id == "admin:7"
    assert "line.identity.review" in actor.permission_scope
    assert "line_viewer" not in actor.permission_scope


def test_customer_service_preview_apply_routes_keep_legacy_patch_as_retired_guard():
    routes = {
        (route.path, method)
        for route in customer_service_router.routes
        for method in route.methods
    }

    assert ("/api/v1/customer-service/tickets/{ticket_id}", "PATCH") in routes
    assert (
        "/api/v1/customer-service/tickets/{ticket_id}/update/preview",
        "POST",
    ) in routes
    assert (
        "/api/v1/customer-service/tickets/{ticket_id}/update/apply",
        "POST",
    ) in routes


def test_customer_menu_case_information_postback_replies_flex_card():
    """驗證客戶選單點擊【案件資訊】或傳送「案件資訊」文字，直接以 Flex 卡片回傳服務條件與費用約定。"""
    from domains.line.identities import LineWebhookEventId, LineSourceType
    from domains.line.delivery import LineMessageKind

    now = datetime(2026, 11, 16, 8, 30, tzinfo=timezone.utc)
    handlers = LineWebhookIdentityHandlers(lambda: now, lambda p, f: f"https://example.com/liff?p={p}&f={f}")

    def make_inbox(postback_data=None, text_msg=None, user_id="U-customer-test"):
        if postback_data:
            payload = {"postback": {"data": postback_data}}
        else:
            payload = {"message": {"type": "text", "text": text_msg}}
        event = SimpleNamespace(
            event_id=LineWebhookEventId("evt-case-info-test"),
            source=SimpleNamespace(source_type=LineSourceType.USER, user_id=LineUserId(user_id)),
            occurred_at=now,
            payload_json=json.dumps(payload),
        )
        return SimpleNamespace(event=event)

    card_payload = {
        "type": "flex",
        "altText": "案件 115000179 服務條件與費用約定",
        "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": []}},
    }
    uow = SimpleNamespace(
        delivery_tasks=DeliveryTasks(),
        customer_case_information=lambda uid: {"card": card_payload},
        platform_users=SimpleNamespace(apply_friend_event=lambda _: None),
    )

    # 1. Postback 點擊【案件資訊】
    inbox_pb = make_inbox(postback_data="customer:case-information")
    assert handlers.handle_reply_postback(inbox_pb, uow) is True
    assert len(uow.delivery_tasks.requests) == 1
    req1 = uow.delivery_tasks.requests[0]
    assert req1.message_kind is LineMessageKind.FLEX
    assert "115000179" in req1.payload_json

    # 2. 聊天室打字「案件資訊」
    inbox_msg = make_inbox(text_msg="案件資訊")
    assert handlers.handle_reply_message(inbox_msg, uow) is True
    assert len(uow.delivery_tasks.requests) == 2
    req2 = uow.delivery_tasks.requests[1]
    assert req2.message_kind is LineMessageKind.FLEX


def test_customer_menu_case_information_unbound_and_no_case_guidance():
    """驗證未綁定或無案件時回覆友善引導文字。"""
    from domains.line.identities import LineWebhookEventId, LineSourceType
    from domains.line.delivery import LineMessageKind

    now = datetime(2026, 11, 16, 8, 30, tzinfo=timezone.utc)
    handlers = LineWebhookIdentityHandlers(lambda: now, lambda p, f: f"https://example.com/liff?p={p}&f={f}")

    event = SimpleNamespace(
        event_id=LineWebhookEventId("evt-unbound-test"),
        source=SimpleNamespace(source_type=LineSourceType.USER, user_id=LineUserId("U-unbound")),
        occurred_at=now,
        payload_json=json.dumps({"postback": {"data": "customer:case-information"}}),
    )
    inbox = SimpleNamespace(event=event)

    uow_unbound = SimpleNamespace(
        delivery_tasks=DeliveryTasks(),
        customer_case_information=lambda uid: "您好！目前尚未連結您的客戶身分資料。\n若您已在工會或市府完成登記，請先點選下方【服務申請入口】完成身分連結；或直接在此留言由專員為您查詢。",
    )
    assert handlers.handle_reply_postback(inbox, uow_unbound) is True
    assert len(uow_unbound.delivery_tasks.requests) == 1
    req = uow_unbound.delivery_tasks.requests[0]
    assert req.message_kind is LineMessageKind.TEXT
    assert "服務申請入口" in req.payload_json


def test_case_bank_account_resolution_by_year_rules():
    """驗證案件專屬匯款帳號之年度分水嶺規則：115年度前查匯入表，116年度後走內建流水。"""
    from subsystems.line.service_start_messages import resolve_case_bank_account_info

    class FakeCursor:
        def __init__(self, mappings):
            self.mappings = mappings
            self._current_result = None

        def execute(self, query, params):
            case_no = params[0]
            val = self.mappings.get(case_no)
            self._current_result = {"virtual_account": val} if val else None

        def fetchone(self):
            return self._current_result

    # 1. 115年度前：查得匯入帳號
    cur = FakeCursor({"115000001": "99781699000123", "A115001": "99781699000555"})
    info_115_found = resolve_case_bank_account_info(cur, "115000001")
    assert info_115_found["bank_name"] == "永豐銀行"
    assert info_115_found["bank_code"] == "807"
    assert info_115_found["virtual_account"] == "99781699000123"
    assert "匯入" in info_115_found["account_note"]

    # 2. 115年度前（非市民）：查得匯入帳號
    info_a115_found = resolve_case_bank_account_info(cur, "A115001")
    assert info_a115_found["virtual_account"] == "99781699000555"

    # 3. 115年度前：未匯入帳號（查無）
    info_115_missing = resolve_case_bank_account_info(cur, "115000999")
    assert info_115_missing["virtual_account"] == "尚未匯入（請洽工會專員）"
    assert "待匯入" in info_115_missing["account_note"]

    # 4. 116年度起：市民內建流水帳號（前綴 99781699 + 116 + 3碼流水號）
    info_116_citizen = resolve_case_bank_account_info(cur, "116000001")
    assert info_116_citizen["virtual_account"] == "99781699116001"
    assert "內建流水" in info_116_citizen["account_note"]

    # 5. 116年度起：非市民內建流水帳號（A116001 -> 流水號+500 -> 99781699116501）
    info_116_non_citizen = resolve_case_bank_account_info(cur, "A116001")
    assert info_116_non_citizen["virtual_account"] == "99781699116501"
    assert "內建流水" in info_116_non_citizen["account_note"]


def test_case_information_card_renders_bank_account_box():
    """驗證案件資訊 Flex Bubble 在傳入 bank_account_info 時正確呈現匯款銀行與專屬帳號。"""
    from subsystems.line.service_start_messages import case_information_card

    sections = [
        SimpleNamespace(
            title="客戶付款約定",
            rows=[
                ("訂金金額", "NT$ 6,000"),
                ("客戶應付總額", "NT$ 12,000"),
            ],
        ),
    ]

    bank_info = {
        "bank_name": "永豐銀行",
        "bank_code": "807",
        "virtual_account": "99781699116001",
        "account_note": "116年度起案件（內建流水帳號）",
    }

    card = case_information_card(
        "116000001",
        "陳月嫂",
        sections,
        client_name="王小美",
        bank_account_info=bank_info,
    )
    card_json = json.dumps(card, ensure_ascii=False)

    assert "案件專屬匯款帳號" in card_json
    assert "永豐銀行（807）" in card_json
    assert "99781699116001" in card_json
    assert "ATM／網銀轉帳請輸入銀行代碼 807" in card_json
    assert "clipboard" in card_json
    assert "📋 複製帳號 (永豐807)" in card_json

    # 驗證即使無 sections 也能正常呈現帳號區塊
    empty_card = case_information_card(
        "116000001",
        "陳月嫂",
        [],
        bank_account_info=bank_info,
    )
    empty_card_json = json.dumps(empty_card, ensure_ascii=False)
    assert "案件專屬匯款帳號" in empty_card_json
    assert "99781699116001" in empty_card_json
    assert "clipboard" in empty_card_json


def test_all_payment_reminder_cards_render_bank_account_box_and_clipboard():
    """驗證所有繳費提醒卡片（訂金繳費提醒、第二期款繳費提醒、各期逾期提醒）均包含匯款帳號與一鍵複製按鈕。"""
    from subsystems.line.deposit_notifications import deposit_notification_payload, REMINDER
    from subsystems.line.payment_reminder_notifications import payment_reminder_card_payload

    # 1. 訂金繳費提醒卡
    deposit_card = deposit_notification_payload("116000001", 6000, "2027-01-15", REMINDER)
    dep_json = json.dumps(deposit_card, ensure_ascii=False)
    assert "案件專屬匯款帳號" in dep_json
    assert "永豐銀行（807）" in dep_json
    assert "99781699116001" in dep_json
    assert "clipboard" in dep_json
    assert "📋 複製帳號 (永豐807)" in dep_json

    # 2. 第二期款繳費提醒卡
    second_card = payment_reminder_card_payload("second", "116000001", 12000, "2027-04-10", "reminder")
    sec_json = json.dumps(second_card, ensure_ascii=False)
    assert "案件專屬匯款帳號" in sec_json
    assert "永豐銀行（807）" in sec_json
    assert "99781699116001" in sec_json
    assert "clipboard" in sec_json
    assert "📋 複製帳號 (永豐807)" in sec_json

    # 3. 逾期提醒卡（第一期款逾期）
    overdue_card = payment_reminder_card_payload("first", "116000001", 8000, "2027-03-01", "overdue")
    od_json = json.dumps(overdue_card, ensure_ascii=False)
    assert "案件專屬匯款帳號" in od_json
    assert "永豐銀行（807）" in od_json
    assert "99781699116001" in od_json
    assert "clipboard" in od_json
    assert "📋 複製帳號 (永豐807)" in od_json

    # 4. 驗證 115 年度歷史匯入帳號亦正確整合至繳費提醒卡
    info_115 = {
        "bank_name": "永豐銀行",
        "bank_code": "807",
        "virtual_account": "99781699000179",
        "account_note": "115年度前案件（匯入專屬帳號）",
    }
    dep_115_card = deposit_notification_payload("115000179", 6000, "2026-11-20", REMINDER, bank_account_info=info_115)
    dep_115_json = json.dumps(dep_115_card, ensure_ascii=False)
    assert "99781699000179" in dep_115_json
    assert "clipboard" in dep_115_json
    assert "📋 複製帳號 (永豐807)" in dep_115_json
