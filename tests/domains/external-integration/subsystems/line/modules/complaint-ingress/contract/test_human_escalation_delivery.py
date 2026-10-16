"""M4 masked alert outbox -> canonical delivery task -> provider outcome contract."""

from datetime import datetime, timedelta, timezone
import json
import os
import pytest
from unittest.mock import patch
from types import SimpleNamespace
from domains.line.configuration import LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from domains.line.canonical_payload import canonical_line_payload_json

from domains.line.delivery import (
    LineAttemptPlan,
    LineDeliveryLease,
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
)
from domains.line.identities import LineDeliveryTaskId, LineProviderMessageId
from subsystems.line.delivery_contracts import (
    EnqueueLineDeliveryResult,
    LineDeliveryCommandOutcome,
    LineProviderOutcome,
    LineProviderOutcomeType,
    RecordLineDeliveryAttemptResult,
)
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.human_escalation_delivery import (
    HUMAN_ESCALATION_INTENT,
    HumanEscalationDeliveryWorker,
)
from subsystems.line.outbox_contracts import LineOutboxWorkItem


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


class _Delivery:
    def __init__(self):
        self.task = None
        self.attempts = []

    def enqueue(self, request):
        if self.task is None:
            self.task = LineDeliveryTaskSnapshot(
                LineDeliveryTaskId(91),
                request,
                LineDeliveryStatus.PENDING,
                0,
            )
            return EnqueueLineDeliveryResult(
                LineDeliveryCommandOutcome.CREATED,
                LineDeliveryTaskId(91),
                LineDeliveryStatus.PENDING,
            )
        return EnqueueLineDeliveryResult(
            LineDeliveryCommandOutcome.EXISTING,
            self.task.task_id,
            self.task.status,
        )

    def get(self, task_id):
        return self.task if self.task is not None and self.task.task_id == task_id else None

    def claim(self, query):
        if self.task is None or self.task.status is not LineDeliveryStatus.PENDING:
            return ()
        lease = LineDeliveryLease(
            self.task.task_id,
            query.lease_owner,
            query.now,
            query.now + timedelta(seconds=60),
        )
        self.task = LineDeliveryTaskSnapshot(
            self.task.task_id,
            self.task.request,
            LineDeliveryStatus.PROCESSING,
            self.task.completed_attempts,
            lease,
        )
        return (self.task,)

    def record_attempt(self, command):
        if command.provider_outcome.outcome_type is not LineProviderOutcomeType.SUCCESS:
            raise AssertionError("focused delivery fake only models provider success")
        self.attempts.append(command)
        self.task = LineDeliveryTaskSnapshot(
            self.task.task_id,
            self.task.request,
            LineDeliveryStatus.SENT,
            self.task.completed_attempts + 1,
        )
        return RecordLineDeliveryAttemptResult(
            self.task.task_id,
            LineAttemptPlan(LineDeliveryStatus.SENT, None),
        )


class _Provider:
    def __init__(self):
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return LineProviderOutcome(
            LineProviderOutcomeType.SUCCESS,
            provider_message_id=LineProviderMessageId("provider-message-91"),
        )


class _Outbox:
    def __init__(self, item):
        self.item = item
        self.completed = []

    def claim(self, query):
        return (self.item,) if query.intent_type == HUMAN_ESCALATION_INTENT else ()

    def complete(self, command):
        self.completed.append(command)


class _Escalations:
    def __init__(self):
        self.task_ref = None
        self.outcome_ref = None
        self.status = None

    def record_alert_delivery_task(self, escalation_ref, task_id):
        self.task_ref = (escalation_ref, task_id)

    def record_alert_delivery_outcome(self, escalation_ref, outcome_ref, alert_status):
        self.outcome_ref = (escalation_ref, outcome_ref)
        self.status = alert_status


class _Uow:
    def __init__(self, outbox, delivery, escalations):
        self.outbox, self.delivery_tasks, self.escalations = outbox, delivery, escalations
        self.configurations = SimpleNamespace(get=lambda kind: LineConfigurationSnapshot(kind, LineConfigurationRevision(0), '{}'))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        pass


def _work_item(outbox_id=17, escalation_ref="escalation:7", payload=None):
    payload = payload or {
        "escalation_ref": escalation_ref,
        "ticket_ref": "ticket:21",
        "trigger_code": "complaint",
        "category": "other",
        "safe_summary": "complaint_explicit",
        "hold_state": "active",
        "urgency": "high",
        "correlation_id": "line-event:task96",
        "source_digest": "a" * 64,
        "target_snapshot": {
            "target_id": 3,
            "recipient_type": "group",
            "recipient_identity": "Ctask96M4Alert0901",
            "active": True,
            "configuration": {"minimum_status": "warning", "revision": "v1"},
        },
    }
    return LineOutboxWorkItem(
        outbox_id,
        "customer_service_escalation",
        escalation_ref,
        HUMAN_ESCALATION_INTENT,
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        0,
        3,
        "worker",
        NOW + timedelta(seconds=90),
    )


@patch.dict(os.environ, {"LINE_PUBLIC_BASE_URL": "https://example.test"})
def test_masked_alert_is_projected_then_canonical_delivery_records_provider_outcome():
    item = _work_item()
    outbox, delivery, escalations = _Outbox(item), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    projection_worker = HumanEscalationDeliveryWorker(
        lambda: uow,
        "task96",
        lambda: NOW,
    )

    assert projection_worker.run_once() == 1
    assert delivery.task.status is LineDeliveryStatus.PENDING
    assert delivery.attempts == []
    assert escalations.task_ref == ("escalation:7", 91)
    assert escalations.outcome_ref is None
    assert escalations.status is None
    assert len(outbox.completed) == 1

    request_payload = json.loads(delivery.task.request.payload_json)
    assert request_payload["type"] == "text"
    assert "complaint_explicit" in request_payload["text"]
    assert "https://example.test/line-mobile-admin?target=customer_service" in request_payload["text"]
    assert "Ctask96M4Alert0901" in delivery.task.request.recipient.identity.value
    assert "source_digest" not in request_payload["text"]

    provider = _Provider()
    delivery_worker = LineDeliveryWorker(
        lambda: uow,
        provider,
        "task96-delivery",
        lambda: NOW,
    )

    assert delivery_worker.run_once() == 1
    assert delivery.task.status is LineDeliveryStatus.SENT
    assert len(delivery.attempts) == 1
    assert provider.requests == [delivery.task.request]
    assert escalations.outcome_ref == (
        "escalation:7",
        "line-delivery-attempt:91:1",
    )
    assert escalations.status == "sent"


@patch.dict(os.environ, {"LINE_PUBLIC_BASE_URL": "https://example.test"})
@pytest.mark.parametrize('trigger,template_id', [
    ('complaint', 'LU96-M4-COMPLAINT-HIGH-CARD-V1'),
    ('runtime_critical', 'LU96-M4-SAFE-ALERT-CARD-V1'),
])
def test_configured_alert_copy_preserves_masked_facts_recipient_and_management_entry(trigger, template_id):
    payload = json.loads(_work_item().payload_json)
    payload['trigger_code'] = trigger
    outbox, delivery, escalations = _Outbox(_work_item(payload=payload)), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    uow.configurations = SimpleNamespace(get=lambda kind: LineConfigurationSnapshot(
        kind, LineConfigurationRevision(4), canonical_line_payload_json({'templates': [{
            'id': template_id, 'message_type': 'text',
            'content': '請由工會專員接手確認本次客訴。', 'variables': [],
        }]}),
    ))
    assert HumanEscalationDeliveryWorker(lambda: uow, 'copy-check', lambda: NOW).run_once() == 1
    text = json.loads(delivery.task.request.payload_json)['text']
    assert text.startswith('請由工會專員接手確認本次客訴。\n\n')
    assert 'complaint_explicit' in text
    assert 'https://example.test/line-mobile-admin?target=customer_service' in text
    assert delivery.task.request.recipient.identity.value == 'Ctask96M4Alert0901'
    assert delivery.task.status is LineDeliveryStatus.PENDING


@patch.dict(os.environ, {"LINE_PUBLIC_BASE_URL": "https://example.test"})
def test_general_human_request_does_not_read_or_use_complaint_copy():
    payload = json.loads(_work_item().payload_json)
    payload['trigger_code'] = 'explicit_human_request'
    outbox, delivery, escalations = _Outbox(_work_item(payload=payload)), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    def unexpected_read(_kind):
        raise AssertionError('ordinary handoff must not consume complaint templates')
    uow.configurations = SimpleNamespace(get=unexpected_read)
    assert HumanEscalationDeliveryWorker(lambda: uow, 'handoff-check', lambda: NOW).run_once() == 1
    assert json.loads(delivery.task.request.payload_json)['text'].startswith('客服人工升級（other）：')


def test_missing_target_is_a_durable_manual_fallback():
    item = _work_item(
        outbox_id=18,
        escalation_ref="escalation:8",
        payload={"urgency": "high", "hold_state": "active"},
    )
    outbox, delivery, escalations = _Outbox(item), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    worker = HumanEscalationDeliveryWorker(lambda: uow, "task96", lambda: NOW)

    assert worker.run_once() == 1
    assert worker.failures == (
        ("escalation:8", "human_escalation_alert_target_missing"),
    )
    assert escalations.status == "failed"
    assert outbox.completed[0].retryable is True
    assert delivery.task is None
