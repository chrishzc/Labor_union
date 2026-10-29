"""
File: test_webhook_immediate_reply.py
Description: 驗證 LINE 客服手動呼叫的 Webhook 即時回傳（方案 2：0 額度消耗、零延遲反饋）與後端排隊非同步處理。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.identities import (
    LineDestinationId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
    LineWebhookEventId,
)
from domains.line.webhook import (
    CanonicalLineWebhookEvent,
    LineWebhookInboxSnapshot,
    LineWebhookProcessingStatus,
    build_line_webhook_event,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ExpectedVersion, IdempotencyKey
from subsystems.line.message_copy import CONTACT_RECEIVED
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_immediate_reply import (
    IMMEDIATE_REPLY_SENT_KEY,
    LineWebhookImmediateReplyService,
    is_immediate_reply_sent,
)
from subsystems.line.webhook_intake import LineWebhookIntake


class _MockReplyAdapter:
    def __init__(self, succeed: bool = True):
        self.calls = []
        self._succeed = succeed

    def reply(self, reply_token: str, message: dict):
        self.calls.append({"reply_token": reply_token, "message": message})
        if self._succeed:
            return SimpleNamespace(outcome_type=SimpleNamespace(value="success"))
        return SimpleNamespace(outcome_type=SimpleNamespace(value="rejected"))


class _SignatureVerifier:
    def verify(self, raw_body: bytes, signature: str | None) -> bool:
        return True


class _MockDeliveryTasks:
    def __init__(self):
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)


class _MockCustomerService:
    def __init__(self):
        self.messages = []

    def create_or_append(self, command):
        self.messages.append(command)
        return SimpleNamespace(ticket_id=42)

    def latest_client_case(self, _line_user_id):
        return None


class _MockAudit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


class _MockWebhookInbox:
    def __init__(self):
        self.registered = []

    def register(self, event):
        self.registered.append(event)
        from subsystems.line.webhook_contracts import LineWebhookRegistrationOutcome
        return SimpleNamespace(outcome=LineWebhookRegistrationOutcome.CREATED)


class _MockUnitOfWork:
    def __init__(self):
        self.delivery_tasks = _MockDeliveryTasks()
        self.customer_service = _MockCustomerService()
        self.audit = _MockAudit()
        self.webhook_inbox = _MockWebhookInbox()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def commit(self):
        self.committed = True


class _MockWakeupPublisher:
    def __init__(self):
        self.published = False

    def publish(self):
        self.published = True


def _make_inbox(raw_event: dict, event_id: str = "evt-123") -> LineWebhookInboxSnapshot:
    source = LineSourceIdentity(LineSourceType.USER, "U123456789", LineUserId("U123456789"))
    canonical_event = CanonicalLineWebhookEvent(
        event_id=LineWebhookEventId(event_id),
        destination_id=LineDestinationId("dest-1"),
        event_type=raw_event.get("type", "postback"),
        source=source,
        occurred_at=datetime.now(timezone.utc),
        payload_fingerprint=PreviewFingerprint("a" * 64),
        payload_json=canonical_line_payload_json(raw_event),
    )
    return LineWebhookInboxSnapshot(
        event=canonical_event,
        status=LineWebhookProcessingStatus.PENDING,
        version=ExpectedVersion(1),
    )


def test_immediate_reply_for_postback():
    adapter = _MockReplyAdapter(succeed=True)
    service = LineWebhookImmediateReplyService(adapter)

    raw_event = {
        "type": "postback",
        "replyToken": "token-postback-123",
        "postback": {"data": "customer-service:handoff:confirm"},
    }

    assert service.try_immediate_reply(raw_event) is True
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["reply_token"] == "token-postback-123"
    assert adapter.calls[0]["message"]["text"] == CONTACT_RECEIVED
    assert raw_event.get(IMMEDIATE_REPLY_SENT_KEY) is True


@pytest.mark.parametrize("human_text", ["聯絡專人服務", "呼叫專員", "專人客服", "轉接真人客服"])
def test_immediate_reply_for_confirmed_human_message(human_text: str):
    adapter = _MockReplyAdapter(succeed=True)
    service = LineWebhookImmediateReplyService(adapter)

    raw_event = {
        "type": "message",
        "replyToken": "token-msg-456",
        "message": {"type": "text", "text": human_text},
    }

    assert service.try_immediate_reply(raw_event) is True
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["reply_token"] == "token-msg-456"
    assert adapter.calls[0]["message"]["text"] == CONTACT_RECEIVED
    assert raw_event.get(IMMEDIATE_REPLY_SENT_KEY) is True


def test_no_immediate_reply_for_general_message():
    adapter = _MockReplyAdapter(succeed=True)
    service = LineWebhookImmediateReplyService(adapter)

    raw_event = {
        "type": "message",
        "replyToken": "token-msg-789",
        "message": {"type": "text", "text": "請問如何收費？"},
    }

    assert service.try_immediate_reply(raw_event) is False
    assert len(adapter.calls) == 0
    assert IMMEDIATE_REPLY_SENT_KEY not in raw_event


def test_no_immediate_reply_without_reply_token():
    adapter = _MockReplyAdapter(succeed=True)
    service = LineWebhookImmediateReplyService(adapter)

    raw_event = {
        "type": "postback",
        "postback": {"data": "customer-service:handoff:confirm"},
    }

    assert service.try_immediate_reply(raw_event) is False
    assert len(adapter.calls) == 0


def test_intake_invokes_immediate_reply_and_marks_inbox_event():
    uow = _MockUnitOfWork()
    adapter = _MockReplyAdapter(succeed=True)
    reply_service = LineWebhookImmediateReplyService(adapter)
    publisher = _MockWakeupPublisher()

    intake = LineWebhookIntake(
        signature_verifier=_SignatureVerifier(),
        unit_of_work_factory=lambda: uow,
        wakeup_publisher=publisher,
        immediate_reply_service=reply_service,
    )

    payload = {
        "destination": "dest-1",
        "events": [
            {
                "type": "postback",
                "timestamp": 1700000000000,
                "replyToken": "token-webhook-intake",
                "source": {"type": "user", "userId": "U123456789"},
                "postback": {"data": "customer-service:handoff:confirm"},
            }
        ],
    }

    raw_body = json.dumps(payload).encode("utf-8")
    from shared_kernel.identities import CorrelationId
    result = intake.accept(raw_body, "sig", CorrelationId("corr-1"))

    assert result.created_count == 1
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["reply_token"] == "token-webhook-intake"

    # 驗證存入 inbox 的 event 包含 immediate_reply_sent: True
    assert len(uow.webhook_inbox.registered) == 1
    stored_event = uow.webhook_inbox.registered[0]
    payload_data = json.loads(stored_event.payload_json)
    assert payload_data.get(IMMEDIATE_REPLY_SENT_KEY) is True
    assert is_immediate_reply_sent(stored_event) is True


def test_service_help_skips_enqueue_when_immediate_reply_already_sent():
    uow = _MockUnitOfWork()
    app = LineServiceHelpApplication(lambda: datetime(2026, 10, 29, tzinfo=timezone.utc))

    raw_event = {
        "type": "postback",
        "replyToken": "token-1",
        "postback": {"data": "customer-service:handoff:confirm"},
        IMMEDIATE_REPLY_SENT_KEY: True,
    }
    inbox = _make_inbox(raw_event, event_id="evt-immediate-1")

    handled = app.handle_postback(
        inbox,
        uow,
        LineUserId("U123456789"),
        "customer-service:handoff:confirm",
    )

    assert handled is True
    # 後端工單正常建立
    assert len(uow.customer_service.messages) == 1
    assert len(uow.audit.intents) == 1
    # 關鍵：因已在 Webhook 階段即時 reply 回傳，不重複推播，delivery_tasks 為空（0 Push 額度消耗！）
    assert len(uow.delivery_tasks.requests) == 0


def test_service_help_fallbacks_to_enqueue_when_immediate_reply_not_sent():
    uow = _MockUnitOfWork()
    app = LineServiceHelpApplication(lambda: datetime(2026, 10, 29, tzinfo=timezone.utc))

    raw_event = {
        "type": "postback",
        "postback": {"data": "customer-service:handoff:confirm"},
        # 未標記 immediate_reply_sent (例如 fallback 重試或無 replyToken)
    }
    inbox = _make_inbox(raw_event, event_id="evt-fallback-2")

    handled = app.handle_postback(
        inbox,
        uow,
        LineUserId("U123456789"),
        "customer-service:handoff:confirm",
    )

    assert handled is True
    # 後端工單正常建立
    assert len(uow.customer_service.messages) == 1
    # 保底：因未在 Webhook 階段即時 reply，背景 Worker 正常 enqueue 推播任務
    assert len(uow.delivery_tasks.requests) == 1
    delivery_request = uow.delivery_tasks.requests[0]
    payload = json.loads(delivery_request.payload_json)
    assert payload["text"] == CONTACT_RECEIVED
