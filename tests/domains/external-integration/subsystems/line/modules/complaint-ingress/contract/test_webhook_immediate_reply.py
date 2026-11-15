"""
File: test_webhook_immediate_reply.py
Description: 驗證舊專員按鈕只回留言指引，殘留客服受理工作不呼叫 LINE。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryLease, LineDeliveryRequest, LineDeliveryStatus,
    LineDeliveryTaskSnapshot, LineMessageKind, LineRecipient, LineRecipientType,
)
from domains.line.identities import (
    LineDeliveryTaskId,
    LineProviderMessageId,
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
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.line.delivery_contracts import LineProviderOutcome, LineProviderOutcomeType
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_immediate_reply import enqueue_retired_handoff_reply


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


class _MockUnitOfWork:
    def __init__(self):
        self.delivery_tasks = _MockDeliveryTasks()
        self.customer_service = _MockCustomerService()
        self.audit = _MockAudit()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def commit(self):
        self.committed = True


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


def test_handoff_postback_only_guides_direct_chat():
    uow = _MockUnitOfWork()
    postback = {"type": "postback", "postback": {"data": "customer-service:handoff:confirm"}}
    inbox = _make_inbox(postback)
    assert enqueue_retired_handoff_reply(inbox, uow)
    [reply] = uow.delivery_tasks.requests
    assert reply.source_aggregate_type == "line_webhook_reply"
    assert json.loads(reply.payload_json) == {
        "type": "text", "text": "如需協助，請直接在此官方帳號聊天室留言。",
    }
    assert not uow.customer_service.messages

    app = LineServiceHelpApplication(lambda: datetime(2026, 10, 29, tzinfo=timezone.utc))
    assert not app.handle_postback(inbox, uow, LineUserId("U123456789"), "customer-service:handoff:confirm")
    assert not uow.customer_service.messages
    assert not uow.audit.intents
    assert uow.delivery_tasks.requests == [reply]


@pytest.mark.parametrize("text", ["服務說明", "你好", "我要客訴：請聯絡專人", "呼叫專員", "專人客服"])
def test_handoff_reply_does_not_take_general_or_complaint_messages(text):
    uow = _MockUnitOfWork()
    assert not enqueue_retired_handoff_reply(_make_inbox({"type": "message", "message": {"type": "text", "text": text}}), uow)
    assert not uow.delivery_tasks.requests


def test_already_queued_handoff_ack_cancels_but_menu_keeps_push():
    now = datetime(2026, 10, 30, tzinfo=timezone.utc)
    def task(index, suffix):
        request = LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, LineUserId("U-synthetic")), LineMessageKind.TEXT,
            canonical_line_payload_json({"type": "text", "text": "synthetic configured copy"}), now,
            IdempotencyKey(f"service-help:{suffix}:event-{index}"), CorrelationId(f"line-event:event-{index}"),
            "line_webhook_event", f"event-{index}",
        )
        return LineDeliveryTaskSnapshot(LineDeliveryTaskId(index), request, LineDeliveryStatus.PENDING, 0, None)

    class Deliveries:
        def __init__(self):
            self.tasks = {1: task(1, "ticket"), 2: task(2, "menu")}
            self.cancelled = []
        def claim(self, query):
            for identifier, current in self.tasks.items():
                if current.status is LineDeliveryStatus.PENDING:
                    lease = LineDeliveryLease(current.task_id, query.lease_owner, now, now + timedelta(seconds=60))
                    self.tasks[identifier] = replace(current, status=LineDeliveryStatus.PROCESSING, lease=lease)
                    return (self.tasks[identifier],)
            return ()
        def get(self, task_id):
            return self.tasks[task_id.value]
        def cancel(self, command):
            self.cancelled.append(command)
            current = self.tasks[command.task_id.value]
            self.tasks[command.task_id.value] = replace(current, status=LineDeliveryStatus.CANCELLED, lease=None)
        def record_attempt(self, command):
            self.tasks[command.task.task_id.value] = replace(command.task, status=LineDeliveryStatus.SENT, lease=None)

    uow = _MockUnitOfWork()
    deliveries = Deliveries()
    uow.delivery_tasks = deliveries
    provider = Mock()
    provider.send.return_value = LineProviderOutcome(LineProviderOutcomeType.SUCCESS, provider_message_id=LineProviderMessageId("synthetic-message-id"))
    worker = LineDeliveryWorker(lambda: uow, provider, "worker:reply-only", lambda: now)
    assert worker.run_once() == 2
    assert deliveries.tasks[1].status is LineDeliveryStatus.CANCELLED
    assert len(deliveries.cancelled) == 1 and uow.committed
    assert deliveries.tasks[2].status is LineDeliveryStatus.SENT
    provider.send.assert_called_once_with(deliveries.tasks[2].request)
    provider.reply.assert_not_called()
