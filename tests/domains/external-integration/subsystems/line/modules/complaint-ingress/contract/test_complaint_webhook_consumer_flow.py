"""M4 complaint direct-flow acceptance from claimed LINE inbox to masked escalation."""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from domains.customer_service.escalation import AutomationHoldState, TriggerCode
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

    def get_by_idempotency(self, _key, *, lock=False):
        del lock
        return None

    def get_by_source(self, _source_event_identity, *, lock=False):
        del lock
        return None

    def get_active_by_scope(self, _hold_scope, *, lock=False):
        del lock
        return None

    def create(self, command, ticket):
        self.commands.append(command)
        return {
            "id": 41,
            "ticket_id": ticket.ticket_id,
            "workflow_status": "open",
            "workflow_version": 0,
            "hold_state": "active",
            "hold_version": 0,
        }

    def enqueue_alert(self, intent):
        self.alerts.append(intent)

    def append_event(self, escalation_id, event_type, **values):
        self.events.append((escalation_id, event_type, values))

    def save_receipt(self, key, fingerprint, receipt):
        self.receipts.append((key, fingerprint, receipt))


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

    assert len(state.escalations.alerts) == 1
    alert = state.escalations.alerts[0]
    assert alert.trigger_code is TriggerCode.COMPLAINT
    assert alert.hold_state is AutomationHoldState.ACTIVE
    assert alert.urgency == "high"
    assert alert.safe_summary == "complaint_explicit"
    assert "王小美" not in repr(alert)
    assert "0912345678" not in repr(alert)

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
    assert "暫停自動回覆" in empathy
