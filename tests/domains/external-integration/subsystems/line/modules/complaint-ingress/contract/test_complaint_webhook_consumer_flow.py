"""M4 complaint direct-flow acceptance from claimed LINE inbox to masked escalation."""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from domains.customer_service.escalation import AutomationHoldState, EscalationWorkflowStatus, TriggerCode
from domains.line.identities import (
    LineDestinationId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
)
from domains.line.webhook import (
    LineWebhookInboxSnapshot,
    LineWebhookLease,
    LineWebhookProcessingStatus,
    build_line_webhook_event,
)
from shared_kernel.identities import ExpectedVersion
from subsystems.customer_service.escalation_application import HumanEscalationApplication
from subsystems.line.event_dispatcher import LineEventDispatcher
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_event_consumer import LineWebhookEventConsumer
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers
from subsystems.line.webhook_immediate_reply import LineWebhookImmediateReplyService


class _WebhookInbox:
    def __init__(self, event):
        self._event = event
        self._claimed = False
        self.completions = []

    def claim(self, _query):
        if self._claimed:
            return []
        self._claimed = True
        return [self._event]

    def complete(self, command):
        self.completions.append(command)


class _PlatformUsers:
    def __init__(self):
        self.events = []

    def apply_friend_event(self, event):
        self.events.append(event)


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


class _Audit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


class _Escalations:
    def __init__(self):
        self.commands = []
        self.alerts = []
        self.events = []
        self.receipts = []
        self.rows = []
        self.by_key = {}

    def get_by_idempotency(self, key, *, lock=False):
        del lock
        return self.by_key.get(key)

    def get_by_source(self, source_event_identity, *, lock=False):
        del lock
        return next((row for row in self.rows if row["source_event_identity"] == source_event_identity), None)

    def get_active_by_scope(self, _hold_scope, *, lock=False):
        del lock
        return None

    def active_hold(self, _hold_scope):
        return None

    def create(self, command, ticket):
        self.commands.append(command)
        row = {
            "id": 41,
            "ticket_id": ticket.ticket_id,
            "source_event_identity": command.source_event_identity,
            "source_fingerprint": command.source_fingerprint,
            "trigger_code": command.trigger_code.value,
            "urgency": "high",
            "context": command.context.as_dict(),
            "workflow_status": "open",
            "workflow_version": 0,
            "hold_state": "active",
            "hold_version": 0,
        }
        self.rows.append(row)
        return row

    def enqueue_alert(self, intent):
        self.alerts.append(intent)

    def append_event(self, escalation_id, event_type, **values):
        self.events.append((escalation_id, event_type, values))

    def save_receipt(self, key, fingerprint, receipt):
        self.receipts.append((key, fingerprint, receipt))
        row = next(row for row in self.rows if row["id"] == receipt.escalation_id)
        self.by_key[key] = {**row, "request_fingerprint": fingerprint, "receipt": receipt}


class _State:
    def __init__(self, event):
        self.webhook_inbox = _WebhookInbox(event)
        self.platform_users = _PlatformUsers()
        self.delivery_tasks = _DeliveryTasks()
        self.customer_service = _CustomerService()
        self.audit = _Audit()
        self.escalations = _Escalations()
        self.commits = 0


class _UnitOfWork:
    def __init__(self, state):
        self.webhook_inbox = state.webhook_inbox
        self.platform_users = state.platform_users
        self.delivery_tasks = state.delivery_tasks
        self.customer_service = state.customer_service
        self.audit = state.audit
        self.escalations = state.escalations
        self._state = state

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self._state.commits += 1


class _UnitOfWorkFactory:
    def __init__(self, state):
        self._state = state

    def __call__(self):
        return _UnitOfWork(self._state)


def _complaint_event(now):
    line_user_id = LineUserId("U123456789")
    event = build_line_webhook_event(
        provider_event_id="event-complaint-direct-flow",
        destination_id=LineDestinationId("destination-1"),
        event_type="message",
        source=LineSourceIdentity(
            LineSourceType.USER,
            line_user_id.value,
            line_user_id,
        ),
        occurred_at=now,
        canonical_payload={
            "replyToken": "reply-event-complaint-direct-flow",
            "message": {
                "type": "text",
                "text": "我要客訴：姓名 王小美，電話 0912345678",
            },
        },
    )
    lease = LineWebhookLease(
        event.event_id,
        "line-worker:test",
        now,
        now + timedelta(minutes=1),
    )
    return LineWebhookInboxSnapshot(
        event,
        LineWebhookProcessingStatus.PROCESSING,
        ExpectedVersion(1),
        attempt_count=1,
        lease=lease,
        max_attempts=5,
    )


def _handoff_postback_event(now, *, raw_payload=None):
    line_user_id = LineUserId("U123456789")
    event = build_line_webhook_event(
        provider_event_id="event-handoff-confirm-postback",
        destination_id=LineDestinationId("destination-1"),
        event_type="postback",
        source=LineSourceIdentity(
            LineSourceType.USER,
            line_user_id.value,
            line_user_id,
        ),
        occurred_at=now,
        canonical_payload=raw_payload if raw_payload is not None else {
            "replyToken": "reply-event-handoff-confirm-postback",
            "postback": {"data": "customer-service:handoff:confirm"},
        },
    )
    lease = LineWebhookLease(
        event.event_id,
        "line-worker:test",
        now,
        now + timedelta(minutes=1),
    )
    return LineWebhookInboxSnapshot(
        event,
        LineWebhookProcessingStatus.PROCESSING,
        ExpectedVersion(1),
        attempt_count=1,
        lease=lease,
        max_attempts=5,
    )


def test_complaint_claimed_inbox_reaches_high_masked_escalation_in_one_business_uow():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    event = _complaint_event(now)
    state = _State(event)
    unit_of_work_factory = _UnitOfWorkFactory(state)
    escalation = HumanEscalationApplication(unit_of_work_factory, lambda: now)
    service_help = LineServiceHelpApplication(
        lambda: now,
        escalation_gateway=escalation,
    )

    def unexpected_knowledge_fallback(*_args):
        raise AssertionError("complaint ingress must precede Knowledge fallback")

    handlers = LineWebhookIdentityHandlers(
        lambda: now,
        lambda _purpose, _flow_id: "https://example.test/identity",
        knowledge_question_scheduler=unexpected_knowledge_fallback,
        service_help_application=service_help,
    )
    consumer = LineWebhookEventConsumer(
        unit_of_work_factory,
        LineEventDispatcher(handlers.registry()),
        "line-worker:test",
        lambda: now,
    )

    assert consumer.run_once() == 1

    assert state.commits == 2
    assert len(state.webhook_inbox.completions) == 1
    assert (
        state.webhook_inbox.completions[0].target_status
        is LineWebhookProcessingStatus.PROCESSED
    )

    assert len(state.escalations.commands) == 1
    command = state.escalations.commands[0]
    assert command.trigger_code is TriggerCode.COMPLAINT
    assert command.trigger_policy_version == "complaint.v1"
    assert command.context.as_dict() == {
        "summary_code": "complaint_explicit",
        "policy_version": "complaint.v1",
        "category": "other",
        "redaction_version": "m4-mask.v1",
    }

    # Admin automatic alerts retired; the HIGH escalation and hold still exist.
    assert state.escalations.alerts == []
    assert len(state.escalations.rows) == len(state.escalations.receipts) == 1
    stored = state.escalations.rows[0]
    receipt = state.escalations.receipts[0][2]
    assert stored["trigger_code"] == TriggerCode.COMPLAINT.value
    assert stored["urgency"] == "high"
    assert stored["context"]["summary_code"] == "complaint_explicit"
    assert receipt.resulting_hold_state is AutomationHoldState.ACTIVE
    assert receipt.resulting_workflow_status is EscalationWorkflowStatus.OPEN
    assert "王小美" not in repr(stored)
    assert "0912345678" not in repr(stored)

    assert len(state.customer_service.messages) == 1
    assert state.customer_service.messages[0].message == (
        "客訴訊息已遮罩；請查看客服 escalation 的去敏摘要。"
    )
    assert "王小美" not in repr(state.customer_service.messages[0])
    assert "0912345678" not in repr(state.customer_service.messages[0])

    assert len(state.delivery_tasks.requests) == 1
    delivery = state.delivery_tasks.requests[0]
    assert delivery.source_aggregate_type == "line_webhook_event"
    assert delivery.source_aggregate_identity == "event-complaint-direct-flow"
    assert delivery.idempotency_key.value == (
        "service-help:complaint-empathy:event-complaint-direct-flow"
    )
    empathy = json.loads(delivery.payload_json)["text"]
    assert "很抱歉讓您有不好的感受" in empathy
    assert "AI" not in empathy

    before = (len(state.escalations.commands), len(state.escalations.events), len(state.escalations.receipts),
              len(state.customer_service.messages), len(state.delivery_tasks.requests), len(state.audit.intents), state.commits)
    replay = escalation.create_for_ticket(command, SimpleNamespace(ticket_id=31), _UnitOfWork(state))
    assert replay.replayed is True and replay.receipt_id == receipt.receipt_id
    assert replay.committed_at == receipt.committed_at
    assert (len(state.escalations.commands), len(state.escalations.events), len(state.escalations.receipts),
            len(state.customer_service.messages), len(state.delivery_tasks.requests), len(state.audit.intents), state.commits) == before
    assert state.escalations.alerts == []


def test_call_postback_reaches_ticket_hold_and_short_acknowledgement():
    """The webhook owns the short Reply; this consumer creates no background ack."""
    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    state = _State(_handoff_postback_event(now))
    unit_of_work_factory = _UnitOfWorkFactory(state)
    escalation = HumanEscalationApplication(unit_of_work_factory, lambda: now)
    handlers = LineWebhookIdentityHandlers(
        lambda: now,
        lambda _purpose, _flow_id: "https://example.test/identity",
        service_help_application=LineServiceHelpApplication(
            lambda: now, escalation_gateway=escalation
        ),
    )
    consumer = LineWebhookEventConsumer(
        unit_of_work_factory,
        LineEventDispatcher(handlers.registry()),
        "line-worker:test",
        lambda: now,
    )

    assert consumer.run_once() == 1
    assert len(state.customer_service.messages) == 1
    assert len(state.escalations.commands) == 1
    assert state.escalations.receipts[0][2].resulting_hold_state is AutomationHoldState.ACTIVE
    assert state.escalations.alerts == []
    assert state.delivery_tasks.requests == []
    assert state.commits == 2 and len(state.webhook_inbox.completions) == 1


@pytest.mark.parametrize("reply_mode", ["success", "missing", "timeout"])
def test_webhook_reply_outcome_never_changes_ticket_persistence_or_enqueues_push(reply_mode):
    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    class ReplyPort:
        def __init__(self):
            self.replies = []
            self.pushes = []

        def reply(self, token, payload):
            self.replies.append((token, payload))
            if reply_mode == "timeout":
                raise TimeoutError("synthetic Reply uncertainty")
            return SimpleNamespace(outcome_type=SimpleNamespace(value="success"))

        def push(self, *args):
            self.pushes.append(args)
            raise AssertionError("manual acknowledgement must never fall back to Push")

    raw_event = {"type": "postback", "postback": {"data": "customer-service:handoff:confirm"}}
    if reply_mode != "missing":
        raw_event["replyToken"] = "synthetic-reply-token"
    reply_port = ReplyPort()
    reply = LineWebhookImmediateReplyService(reply_port)
    assert reply.try_immediate_reply(raw_event) is (reply_mode == "success")
    if reply_mode == "success":
        assert reply.try_immediate_reply(raw_event) is True
    assert len(reply_port.replies) == (0 if reply_mode == "missing" else 1)
    if reply_port.replies:
        assert reply_port.replies[0][1] == {
            "type": "text", "text": "已收到您的聯絡需求，請留言說明問題，專員將盡快回覆。",
        }
    assert reply_port.pushes == []

    state = _State(_handoff_postback_event(now, raw_payload=raw_event))
    factory = _UnitOfWorkFactory(state)
    handlers = LineWebhookIdentityHandlers(
        lambda: now, lambda _purpose, _flow_id: "https://example.test/identity",
        service_help_application=LineServiceHelpApplication(
            lambda: now, escalation_gateway=HumanEscalationApplication(factory, lambda: now),
        ),
    )
    consumer = LineWebhookEventConsumer(factory, LineEventDispatcher(handlers.registry()), "line-worker:test", lambda: now)
    assert consumer.run_once() == 1
    assert len(state.customer_service.messages) == len(state.escalations.rows) == 1
    assert state.escalations.receipts[0][2].resulting_hold_state is AutomationHoldState.ACTIVE
    assert state.delivery_tasks.requests == state.escalations.alerts == []
    before = (len(state.customer_service.messages), len(state.escalations.events), len(state.escalations.receipts),
              len(state.delivery_tasks.requests), len(state.audit.intents), len(state.webhook_inbox.completions))
    assert consumer.run_once() == 0
    # The original consumer may commit its empty claim transaction; no business
    # event, acknowledgement or completion may be created by that empty cycle.
    assert (len(state.customer_service.messages), len(state.escalations.events), len(state.escalations.receipts),
            len(state.delivery_tasks.requests), len(state.audit.intents), len(state.webhook_inbox.completions)) == before
    assert reply_port.pushes == []
