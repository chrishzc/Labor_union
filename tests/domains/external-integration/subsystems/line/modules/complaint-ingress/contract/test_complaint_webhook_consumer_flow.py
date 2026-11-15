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

    def active_hold(self, _hold_scope):
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


def _handoff_postback_event(now):
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
        canonical_payload={
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


def test_claimed_complaint_is_processed_without_support_side_effects():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    event = _complaint_event(now)
    state = _State(event)
    unit_of_work_factory = _UnitOfWorkFactory(state)
    service_help = LineServiceHelpApplication(lambda: now)

    handlers = LineWebhookIdentityHandlers(
        lambda: now,
        lambda _purpose, _flow_id: "https://example.test/identity",
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

    assert state.escalations.commands == []
    assert state.escalations.alerts == []
    assert state.escalations.receipts == []
    assert state.customer_service.messages == []
    assert state.delivery_tasks.requests == []


def test_replayed_old_call_postback_is_processed_without_ticket_hold_or_reply():
    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    state = _State(_handoff_postback_event(now))
    unit_of_work_factory = _UnitOfWorkFactory(state)
    handlers = LineWebhookIdentityHandlers(
        lambda: now,
        lambda _purpose, _flow_id: "https://example.test/identity",
        service_help_application=LineServiceHelpApplication(lambda: now),
    )
    consumer = LineWebhookEventConsumer(
        unit_of_work_factory,
        LineEventDispatcher(handlers.registry()),
        "line-worker:test",
        lambda: now,
    )

    assert consumer.run_once() == 1
    assert state.customer_service.messages == []
    assert state.escalations.commands == []
    assert state.delivery_tasks.requests == []
