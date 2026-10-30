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
        outcome = command.provider_outcome.outcome_type
        assert outcome in {LineProviderOutcomeType.SUCCESS, LineProviderOutcomeType.REJECTED}
        status = LineDeliveryStatus.SENT if outcome is LineProviderOutcomeType.SUCCESS else LineDeliveryStatus.FAILED
        self.attempts.append(command)
        self.task = LineDeliveryTaskSnapshot(
            self.task.task_id,
            self.task.request,
            status,
            self.task.completed_attempts + 1,
        )
        return RecordLineDeliveryAttemptResult(
            self.task.task_id,
            LineAttemptPlan(status, None),
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
            "recipient_type": "user",
            "recipient_identity": "U-admin-test",
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


def test_retired_admin_outbox_completes_without_task_or_provider_outcome():
    outbox, delivery, escalations = _Outbox(_work_item()), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    worker = HumanEscalationDeliveryWorker(lambda: uow, "task96", lambda: NOW)
    assert worker.run_once() == 1 and worker.failures == ()
    assert len(outbox.completed) == 1
    assert delivery.task is None and delivery.attempts == []
    assert escalations.task_ref is None and escalations.outcome_ref is None and escalations.status is None


@pytest.mark.parametrize('trigger', ['complaint', 'runtime_critical'])
def test_retired_alert_never_reads_saved_copy_or_recipient_configuration(trigger):
    payload = json.loads(_work_item().payload_json); payload['trigger_code'] = trigger
    outbox, delivery, escalations = _Outbox(_work_item(payload=payload)), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    uow.configurations = SimpleNamespace(get=lambda kind: pytest.fail('retired Push must not read content'))
    assert HumanEscalationDeliveryWorker(lambda: uow, 'copy-check', lambda: NOW).run_once() == 1
    assert delivery.task is None and len(outbox.completed) == 1


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
    assert delivery.task is None and len(outbox.completed) == 1


def test_old_alert_without_target_is_drained_without_retry_or_fake_failure():
    item = _work_item(payload={'urgency': 'high', 'hold_state': 'active'})
    outbox, delivery, escalations = _Outbox(item), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    worker = HumanEscalationDeliveryWorker(lambda: uow, 'task96', lambda: NOW)
    assert worker.run_once() == 1 and worker.failures == ()
    assert len(outbox.completed) == 1 and delivery.task is None and escalations.status is None


def test_old_group_alert_intent_is_rejected_before_delivery():
    from subsystems.line.human_escalation_delivery import _request, _item, HumanEscalationDeliveryError
    payload = json.loads(_work_item().payload_json)
    payload["target_snapshot"]["recipient_type"] = "group"
    with pytest.raises(HumanEscalationDeliveryError, match="line_alert_group_retired"):
        _request(_item(_work_item(payload=payload)), NOW)


@pytest.mark.parametrize('source,recipient_type', [('customer_service_escalation','user'), ('runtime_health_event','user'), ('customer_service_escalation','group')])
def test_already_queued_admin_push_is_cancelled_before_provider(source, recipient_type):
    from dataclasses import replace
    from domains.line.delivery import LineRecipient, LineRecipientType
    from domains.line.identities import LineGroupId
    from subsystems.line.human_escalation_delivery import _request, _item
    with patch.dict(os.environ, {'LINE_PUBLIC_BASE_URL':'https://example.test'}):
        request, _ = _request(_item(_work_item()), NOW)
    if recipient_type == 'group':
        request = replace(request, recipient=LineRecipient(LineRecipientType.GROUP, LineGroupId('C-retired')))
    request = replace(request, source_aggregate_type=source)
    outbox, delivery, escalations = _Outbox(_work_item()), _Delivery(), _Escalations()
    delivery.enqueue(request)
    cancelled = []
    def cancel(command):
        cancelled.append(command)
        delivery.task = replace(delivery.task, status=LineDeliveryStatus.CANCELLED, lease=None)
    delivery.cancel = cancel
    uow = _Uow(outbox, delivery, escalations)
    provider = _Provider()
    assert LineDeliveryWorker(lambda: uow, provider, 'retirement-check', lambda: NOW).run_once() == 1
    assert provider.requests == [] and delivery.attempts == [] and len(cancelled) == 1
    assert delivery.task.status is LineDeliveryStatus.CANCELLED
    assert escalations.outcome_ref is None
