"""M4 complaint ingress: masked Customer Service escalation and durable empathy."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.identities import LineUserId
from domains.customer_service.escalation import EscalationEventType, TriggerCode
from infrastructure.mysql.customer_service_escalation_repository import (
    MySqlCustomerServiceEscalationRepository,
)
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


class _Audit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))


class _Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def cursor(self):
        return self.cursor_value


def _inbox(event_id="event-complaint"):
    return SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value=event_id),
            payload_json=json.dumps({"replyToken": f"reply-{event_id}"}),
        )
    )


def test_complaint_ingress_leaves_only_the_original_chat_message() -> None:
    unit_of_work = SimpleNamespace(
        delivery_tasks=_DeliveryTasks(),
        customer_service=_CustomerService(),
        audit=_Audit(),
    )
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
        )

    assert application.handle(
        _inbox(),
        unit_of_work,
        LineUserId("U123456789"),
        "我要客訴：姓名 王小美，電話 0912345678",
    ) is False

    assert unit_of_work.customer_service.messages == []
    assert unit_of_work.delivery_tasks.requests == []
    assert unit_of_work.audit.intents == []


def test_complaint_event_persists_hold_versions_with_nullable_ticket_versions() -> None:
    cursor = _Cursor()
    MySqlCustomerServiceEscalationRepository(_Connection(cursor)).append_event(
        41,
        EscalationEventType.CREATED,
        expected_escalation_version=0,
        resulting_escalation_version=0,
        expected_hold_version=0,
        resulting_hold_version=0,
        actor_ref="system:line-complaint-ingress",
        reason_code="complaint",
        reason_evidence_digest="a" * 64,
        receipt_id="receipt:complaint",
        idempotency_key="complaint:event",
        correlation_id="line-event:complaint",
    )

    sql, params = cursor.calls[0]
    assert "expected_hold_version" in sql
    assert "resulting_hold_version" in sql
    assert sql.count("%s") == len(params) == 14
    assert params[2:8] == (0, 0, None, None, 0, 0)
