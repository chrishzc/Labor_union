"""Issue #311 focused acceptance for service-day reminder projection and scope."""

from datetime import datetime, timezone
from types import SimpleNamespace

from domains.line.delivery import LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineDeliveryTaskId, LineUserId
from infrastructure.mysql import line_delivery_task_repository as delivery_repository_module
from infrastructure.mysql import line_notification_repository as notification_repository_module
from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from subsystems.line.message_configuration import RenderedLineMessage
from subsystems.line.notification_source_adapters import (
    from_scheduling_service_day_checkpoint_outbox,
)


_OCCURRED_AT = datetime(2026, 9, 18, 2, 0, tzinfo=timezone.utc)
_RULE = {
    "id": "service-day-log-reminder",
    "event_code": "service_time_checkpoint",
    "recipient_selector": "assigned_caregiver",
    "template_id": "service-day-log-reminder",
    "enabled": True,
    "schedule": {"kind": "service_end"},
    "frequency": {"kind": "once"},
    "predicates": ["baby_log_missing"],
}
_TEMPLATE = {
    "templates": [
        {
            "id": "service-day-log-reminder",
            "message_type": "text",
            "enabled": True,
            "content": "請補寶寶日誌",
            "variables": [],
        }
    ]
}


def _event(*, baby_log_completed=False, requires_cooking=True, outbox_id=31):
    return from_scheduling_service_day_checkpoint_outbox(
        outbox_id=outbox_id,
        event_id=41,
        payload={
            "assignment_id": 8,
            "baby_log_completed": baby_log_completed,
            "case_no": "CASE-311",
            "requires_cooking": requires_cooking,
            "service_date": "2026-09-18",
            "staff_id": 4,
        },
        occurred_at=_OCCURRED_AT,
    )


class _ProjectionRepository(MySqlLineNotificationRepository):
    def __init__(self, *, rules=None, templates=None, existing_decision=False):
        super().__init__(object())
        self.rules = {"rules": [_RULE]} if rules is None else rules
        self.templates = _TEMPLATE if templates is None else templates
        self.existing_decision = existing_decision
        self.sources = []
        self.decisions = []
        self.intents = []

    def register_source_event(self, event):
        self.sources.append(event)
        return 51

    def _current_configuration(self, kind):
        if kind == "notification_rules":
            return (7, self.rules)
        if kind == "message_templates":
            return (9, self.templates)
        raise AssertionError(kind)

    def _source_has_decision(self, source_event_id):
        assert source_event_id == 51
        return self.existing_decision

    def _resolve_recipient(self, selector, facts, *, source_domain="unknown"):
        assert selector == "assigned_caregiver"
        assert facts["staff_id"] == 4
        assert source_domain == "scheduling"
        return LineRecipient(LineRecipientType.USER, LineUserId("U-caregiver-4"))

    def _record_decision(
        self,
        source_event_id,
        revision_id,
        rule_id,
        selector,
        recipient,
        status,
        reason,
        event,
    ):
        self.decisions.append(
            {
                "source_event_id": source_event_id,
                "revision_id": revision_id,
                "rule_id": rule_id,
                "selector": selector,
                "recipient": recipient,
                "status": status,
                "reason": reason,
                "event": event,
            }
        )
        return 61

    def _create_intent_if_absent(
        self,
        decision_id,
        occurrence_number,
        scheduled_at,
        template_revision_id,
        template_id,
        rendered,
        recipient,
        event,
    ):
        self.intents.append(
            {
                "decision_id": decision_id,
                "occurrence_number": occurrence_number,
                "scheduled_at": scheduled_at,
                "template_revision_id": template_revision_id,
                "template_id": template_id,
                "rendered": rendered,
                "recipient": recipient,
                "event": event,
            }
        )


def test_incomplete_service_day_projects_rule_matched_intent_for_assigned_caregiver():
    repository = _ProjectionRepository()
    event = _event(baby_log_completed=False, requires_cooking=True)

    source_id = repository.register_and_project(event)

    assert source_id == 51
    assert repository.sources == [event]
    assert len(repository.decisions) == 1
    decision = repository.decisions[0]
    assert decision["revision_id"] == 7
    assert decision["status"] == "intent_created"
    assert decision["reason"] == "rule_matched"
    assert decision["recipient"].recipient_type is LineRecipientType.USER
    assert decision["recipient"].identity == LineUserId("U-caregiver-4")
    assert len(repository.intents) == 1
    intent = repository.intents[0]
    assert intent["decision_id"] == 61
    assert intent["occurrence_number"] == 1
    assert intent["scheduled_at"] == _OCCURRED_AT
    assert intent["template_revision_id"] == 9
    assert intent["template_id"] == "service-day-log-reminder"
    assert intent["rendered"].message_kind is LineMessageKind.TEXT


def test_completed_service_day_is_legally_not_applicable_to_missing_log_rule():
    repository = _ProjectionRepository()

    repository.register_and_project(_event(baby_log_completed=True))

    assert [(item["status"], item["reason"]) for item in repository.decisions] == [
        ("suppressed", "prerequisite_not_satisfied")
    ]
    assert repository.intents == []


def test_disabled_service_day_rule_is_readable_shadow_suppression():
    repository = _ProjectionRepository(
        rules={"rules": [{**_RULE, "enabled": False}]}
    )

    repository.register_and_project(_event())

    assert [(item["status"], item["reason"]) for item in repository.decisions] == [
        ("suppressed", "rule_shadow_mode")
    ]
    assert repository.intents == []


def test_invalid_or_missing_template_is_readable_suppression():
    repository = _ProjectionRepository(templates={"templates": []})

    repository.register_and_project(_event())

    assert [(item["status"], item["reason"]) for item in repository.decisions] == [
        ("suppressed", "template_or_schedule_invalid")
    ]
    assert repository.intents == []


def test_replaying_source_with_existing_decision_does_not_create_second_intent():
    repository = _ProjectionRepository(existing_decision=True)

    repository.register_and_project(_event())

    assert len(repository.sources) == 1
    assert repository.decisions == []
    assert repository.intents == []


class _IntentCursor:
    def __init__(self, calls):
        self.calls = calls
        self.rowcount = 0
        self.lastrowid = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "INSERT IGNORE INTO line_notification_intents" in sql:
            self.rowcount = 1
            self.lastrowid = 71
        elif "UPDATE line_notification_intents SET delivery_task_id" in sql:
            self.rowcount = 1
        else:
            raise AssertionError("unexpected SQL in intent creation")


class _IntentConnection:
    def __init__(self):
        self.calls = []

    def cursor(self):
        return _IntentCursor(self.calls)


def test_intent_creation_enqueues_exact_delivery_task_and_links_lineage(monkeypatch):
    connection = _IntentConnection()
    requests = []

    class _DeliveryRepository:
        def __init__(self, actual_connection):
            assert actual_connection is connection

        def enqueue(self, request):
            requests.append(request)
            return SimpleNamespace(task_id=LineDeliveryTaskId(81))

    monkeypatch.setattr(
        delivery_repository_module,
        "MySqlLineDeliveryTaskRepository",
        _DeliveryRepository,
    )
    repository = MySqlLineNotificationRepository(connection)
    recipient = LineRecipient(LineRecipientType.USER, LineUserId("U-caregiver-4"))
    rendered = RenderedLineMessage(
        LineMessageKind.TEXT,
        '{"text":"請補寶寶日誌","type":"text"}',
    )
    event = _event()

    repository._create_intent_if_absent(
        61,
        1,
        _OCCURRED_AT,
        9,
        "service-day-log-reminder",
        rendered,
        recipient,
        event,
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.recipient == recipient
    assert request.scheduled_at == _OCCURRED_AT
    assert request.source_aggregate_type == "case_staff_assignment"
    assert request.source_aggregate_identity == "8"
    assert request.idempotency_key.value == "line-notification:61:1"
    assert request.correlation_id.value == (
        "line-notification:scheduling-service-day-checkpoint-outbox:31"
    )
    assert connection.calls[-1][1] == (81, 71)


class _CancellationCursor:
    def __init__(self, calls):
        self.calls = calls
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        self.rowcount = 2


class _CancellationConnection:
    def __init__(self):
        self.calls = []

    def cursor(self):
        return _CancellationCursor(self.calls)


def test_completion_cancellation_sql_is_exact_assignment_and_service_date_scope():
    connection = _CancellationConnection()
    repository = MySqlLineNotificationRepository(connection)

    cancelled = repository.cancel_service_day_log_reminders(8, "2026-09-18")

    assert cancelled == 2
    assert len(connection.calls) == 2
    for sql, params in connection.calls:
        assert params == (8, "2026-09-18")
        assert "source.event_code='service_time_checkpoint'" in sql
        assert "$.assignment_id" in sql
        assert "$.service_date" in sql
    assert "intent.intent_status='scheduled'" in connection.calls[0][0]
    assert "task.processing_status IN ('pending','retryable_failed','processing')" in (
        connection.calls[1][0]
    )
