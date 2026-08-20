"""Stage 3 tests for durable LINE intake, dispatch, delivery, and wake timing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryLease,
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import (
    LineDeliveryTaskId,
    LineDestinationId,
    LineProviderMessageId,
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
from infrastructure.line.signature_verifier import LineWebhookSignatureVerifier
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.line.delivery_contracts import (
    EnqueueLineDeliveryResult,
    LineDeliveryCommandOutcome,
    LineProviderOutcome,
    LineProviderOutcomeType,
)
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.event_dispatcher import LineEventDispatcher
from subsystems.line.webhook_contracts import (
    AcceptLineWebhookEventResult,
    LineWebhookRegistrationOutcome,
)
from subsystems.line.webhook_event_consumer import LineWebhookEventConsumer
from subsystems.line.webhook_intake import (
    InvalidLineWebhookSignatureError,
    LineWebhookIntake,
)
from subsystems.line.runtime_contracts import LineRuntimeMode, LineWorkerHeartbeat
from subsystems.line.runtime_health import classify_line_worker_health
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


class FakeWakePublisher:
    def __init__(self) -> None:
        self.calls = 0

    def publish(self) -> None:
        self.calls += 1


class FakeUow:
    def __init__(self, webhook_inbox=None, delivery_tasks=None) -> None:
        self.webhook_inbox = webhook_inbox
        self.delivery_tasks = delivery_tasks
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.rolled_back = exception_type is not None or not self.committed
        return False

    def commit(self) -> None:
        self.committed = True


class IntakeInbox:
    def __init__(self, *, fail_on: int | None = None) -> None:
        self.events = []
        self.fail_on = fail_on

    def register(self, event):
        self.events.append(event)
        if self.fail_on == len(self.events):
            raise RuntimeError("db unavailable")
        return AcceptLineWebhookEventResult(
            LineWebhookRegistrationOutcome.CREATED,
            event.event_id,
            LineWebhookProcessingStatus.PENDING,
            ExpectedVersion(0),
        )


def test_intake_stores_multi_event_atomically_then_wakes_once() -> None:
    inbox = IntakeInbox()
    unit_of_work = FakeUow(webhook_inbox=inbox)
    wakeup = FakeWakePublisher()
    intake = LineWebhookIntake(
        LineWebhookSignatureVerifier("secret"),
        lambda: unit_of_work,
        wakeup,
    )
    body = _webhook_body(event_count=2)

    result = intake.accept(body, _signature(body), CorrelationId("correlation:1"))

    assert result.created_count == 2
    assert unit_of_work.committed is True
    assert wakeup.calls == 1
    assert all(event.payload_json.startswith("{") for event in inbox.events)


def test_intake_rejects_signature_before_opening_transaction() -> None:
    opened = []
    intake = LineWebhookIntake(
        LineWebhookSignatureVerifier("secret"),
        lambda: opened.append(True),
        FakeWakePublisher(),
    )

    with pytest.raises(InvalidLineWebhookSignatureError):
        intake.accept(_webhook_body(), "wrong", CorrelationId("correlation:2"))

    assert opened == []


def test_intake_rolls_back_entire_envelope_when_second_insert_fails() -> None:
    inbox = IntakeInbox(fail_on=2)
    unit_of_work = FakeUow(webhook_inbox=inbox)
    intake = LineWebhookIntake(
        LineWebhookSignatureVerifier("secret"),
        lambda: unit_of_work,
        FakeWakePublisher(),
    )
    body = _webhook_body(event_count=2)

    with pytest.raises(RuntimeError, match="db unavailable"):
        intake.accept(body, _signature(body), CorrelationId("correlation:3"))

    assert unit_of_work.rolled_back is True


def test_unsupported_event_is_completed_as_ignored() -> None:
    event = _claimed_webhook_event()
    repository = ConsumerInbox(event)
    consumer = LineWebhookEventConsumer(
        lambda: FakeUow(webhook_inbox=repository),
        LineEventDispatcher(),
        "worker:1",
        lambda: NOW,
    )

    assert consumer.run_once() == 1
    assert repository.completed.target_status is LineWebhookProcessingStatus.IGNORED


def test_delivery_provider_call_occurs_between_claim_and_record_transactions() -> None:
    task = _claimed_delivery_task()
    actions: list[str] = []
    repository = DeliveryRepository(task, actions)
    provider = SuccessfulProvider(actions)
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions),
        provider,
        "worker:1",
        lambda: NOW + timedelta(seconds=1),
    )

    assert worker.run_once() == 1
    assert actions == ["claim", "commit", "provider", "record", "commit"]
    assert repository.recorded.idempotency_key.value == "line-delivery-attempt:1:1"


def test_runtime_waits_until_earlier_of_due_time_and_fallback() -> None:
    runtime = CanonicalLineWorkerRuntime(
        SimpleNamespace(run_once=lambda: 0),
        SimpleNamespace(run_once=lambda: 0),
        SimpleNamespace(wait=lambda timeout: False),
        lambda: NOW + timedelta(seconds=10),
        lambda heartbeat: None,
        "worker:1",
        fallback_scan_seconds=60,
    )

    assert runtime._wait_seconds(NOW) == 10


def test_persisted_heartbeat_distinguishes_healthy_stale_and_stopped() -> None:
    heartbeat = LineWorkerHeartbeat(
        "worker:1",
        123,
        "host-1",
        LineRuntimeMode.CANONICAL,
        "{}",
        NOW,
    )

    healthy = classify_line_worker_health(
        heartbeat,
        stale_after_seconds=90,
        now=NOW + timedelta(seconds=10),
    )
    stale = classify_line_worker_health(
        heartbeat,
        stale_after_seconds=90,
        now=NOW + timedelta(seconds=91),
    )
    stopped_heartbeat = LineWorkerHeartbeat(
        "worker:1",
        123,
        "host-1",
        LineRuntimeMode.CANONICAL,
        "{}",
        NOW,
        stopped_at=NOW,
    )
    stopped = classify_line_worker_health(
        stopped_heartbeat,
        stale_after_seconds=90,
        now=NOW,
    )

    assert healthy["status"] == "healthy"
    assert stale["status"] == "stale"
    assert stopped["status"] == "stopped"


class ConsumerInbox:
    def __init__(self, event) -> None:
        self.event = event
        self.claimed = False
        self.completed = None

    def claim(self, query):
        if self.claimed:
            return ()
        self.claimed = True
        return (self.event,)

    def complete(self, command):
        self.completed = command
        return command.event


class DeliveryRepository:
    def __init__(self, task, actions) -> None:
        self.task = task
        self.actions = actions
        self.claimed = False
        self.recorded = None

    def claim(self, query):
        self.actions.append("claim")
        if self.claimed:
            return ()
        self.claimed = True
        return (self.task,)

    def get(self, task_id):
        return self.task if task_id == self.task.task_id else None

    def record_attempt(self, command):
        self.actions.append("record")
        self.recorded = command


class TrackingUow(FakeUow):
    def __init__(self, repository, actions) -> None:
        super().__init__(delivery_tasks=repository)
        self.actions = actions

    def commit(self) -> None:
        self.actions.append("commit")
        super().commit()


class SuccessfulProvider:
    def __init__(self, actions) -> None:
        self.actions = actions

    def send(self, request):
        self.actions.append("provider")
        return LineProviderOutcome(
            LineProviderOutcomeType.SUCCESS,
            provider_message_id=LineProviderMessageId("message:1"),
        )


def _webhook_body(event_count: int = 1) -> bytes:
    events = []
    for index in range(event_count):
        events.append(
            {
                "type": "message",
                "timestamp": 1_786_118_400_000 + index,
                "webhookEventId": f"event-{index}",
                "source": {"type": "user", "userId": f"U-user-{index}"},
                "message": {"type": "text", "text": "hello"},
            }
        )
    return json.dumps({"destination": "destination:1", "events": events}).encode()


def _signature(body: bytes) -> str:
    digest = hmac.new(b"secret", body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _claimed_webhook_event():
    event = build_line_webhook_event(
        provider_event_id="event:1",
        destination_id=LineDestinationId("destination:1"),
        event_type="beacon",
        source=LineSourceIdentity(
            LineSourceType.USER,
            "U-user",
            LineUserId("U-user"),
        ),
        occurred_at=NOW,
        canonical_payload={"type": "beacon"},
    )
    lease = LineWebhookLease(event.event_id, "worker:1", NOW, NOW + timedelta(minutes=1))
    return LineWebhookInboxSnapshot(
        event,
        LineWebhookProcessingStatus.PROCESSING,
        ExpectedVersion(1),
        1,
        lease,
    )


def _claimed_delivery_task():
    task_id = LineDeliveryTaskId(1)
    request = LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId("U-user")),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": "hello"}),
        NOW,
        IdempotencyKey("delivery:1"),
        CorrelationId("correlation:delivery:1"),
        "review",
        "review:1",
    )
    lease = LineDeliveryLease(task_id, "worker:1", NOW, NOW + timedelta(minutes=1))
    return LineDeliveryTaskSnapshot(task_id, request, LineDeliveryStatus.PROCESSING, 0, lease)
