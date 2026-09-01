"""M4 masked alert outbox -> existing delivery task -> local result contract."""

from datetime import datetime, timedelta, timezone
import json

from domains.line.delivery import LineDeliveryLease, LineDeliveryStatus, LineDeliveryTaskSnapshot
from domains.line.identities import LineDeliveryTaskId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import EnqueueLineDeliveryResult, LineDeliveryCommandOutcome
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
            self.task = LineDeliveryTaskSnapshot(LineDeliveryTaskId(91), request, LineDeliveryStatus.PENDING, 0)
            return EnqueueLineDeliveryResult(LineDeliveryCommandOutcome.CREATED, LineDeliveryTaskId(91), LineDeliveryStatus.PENDING)
        return EnqueueLineDeliveryResult(LineDeliveryCommandOutcome.EXISTING, self.task.task_id, self.task.status)

    def get(self, task_id):
        return self.task

    def claim_specific(self, task_id, query):
        lease = LineDeliveryLease(task_id, query.lease_owner, query.now, query.now + timedelta(seconds=60))
        self.task = LineDeliveryTaskSnapshot(task_id, self.task.request, LineDeliveryStatus.PROCESSING, self.task.completed_attempts, lease)
        return self.task

    def record_attempt(self, command):
        self.attempts.append(command)
        self.task = LineDeliveryTaskSnapshot(self.task.task_id, self.task.request, LineDeliveryStatus.SENT, 1)


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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        pass


def test_masked_alert_is_projected_and_completed_with_local_result():
    payload = {
        "escalation_ref": "escalation:7",
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
    item = LineOutboxWorkItem(
        17, "customer_service_escalation", "escalation:7", HUMAN_ESCALATION_INTENT,
        json.dumps(payload, ensure_ascii=False, sort_keys=True), 0, 3,
        "worker", NOW + timedelta(seconds=90),
    )
    outbox, delivery, escalations = _Outbox(item), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    worker = HumanEscalationDeliveryWorker(lambda: uow, "task96", lambda: NOW)

    assert worker.run_once() == 1
    assert delivery.task.status is LineDeliveryStatus.SENT
    assert len(delivery.attempts) == 1
    assert escalations.task_ref == ("escalation:7", 91)
    assert escalations.status == "sent"
    assert len(outbox.completed) == 1
    request_payload = json.loads(delivery.task.request.payload_json)
    assert request_payload["type"] == "text"
    assert "complaint_explicit" in request_payload["text"]
    assert "Ctask96M4Alert0901" in delivery.task.request.recipient.identity.value
    assert "source_digest" not in request_payload["text"]


def test_missing_target_is_a_durable_manual_fallback():
    item = LineOutboxWorkItem(
        18, "customer_service_escalation", "escalation:8", HUMAN_ESCALATION_INTENT,
        json.dumps({"urgency": "high", "hold_state": "active"}), 0, 3,
        "worker", NOW + timedelta(seconds=90),
    )
    outbox, delivery, escalations = _Outbox(item), _Delivery(), _Escalations()
    uow = _Uow(outbox, delivery, escalations)
    worker = HumanEscalationDeliveryWorker(lambda: uow, "task96", lambda: NOW)

    assert worker.run_once() == 1
    assert worker.failures == (("escalation:8", "human_escalation_alert_target_missing"),)
    assert escalations.status == "failed"
    assert outbox.completed[0].retryable is True
    assert delivery.task is None
