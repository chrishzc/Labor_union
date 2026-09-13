"""
File: test_line_runtime_stage3.py
Description: 驗證 LINE intake、dispatch failure transaction、delivery 與 wake timing。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import replace
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
    LineReplyOpportunity,
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


def test_dispatch_failure_rolls_back_business_then_records_failure_separately() -> None:
    event = _claimed_webhook_event()
    repository = ConsumerInbox(event)
    factory = IsolatedConsumerUowFactory(repository)
    consumer = LineWebhookEventConsumer(
        factory,
        PartialFailureDispatcher(),
        "worker:1",
        lambda: NOW,
    )

    assert consumer.run_once() == 1
    assert len(factory.units) == 3
    assert factory.units[0].committed is True
    assert factory.units[1].rolled_back is True
    assert factory.units[1].committed is False
    assert factory.units[2].committed is True
    assert factory.persisted_business_writes == []
    assert repository.completed.target_status is LineWebhookProcessingStatus.RETRYABLE_FAILED
    assert repository.completed.error_code == "RuntimeError"
    assert repository.completed.retry_after_seconds == 15


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
        batch_size=1,
    )

    assert worker.run_once() == 1
    assert actions == ["claim", "commit", "provider", "record", "commit"]
    assert repository.recorded.idempotency_key.value == "line-delivery-attempt:1:1"


def test_fresh_knowledge_answer_uses_free_reply_instead_of_push() -> None:
    task = _claimed_knowledge_delivery_task()
    actions: list[str] = []
    repository = DeliveryRepository(
        task,
        actions,
        reply_opportunity=LineReplyOpportunity("reply-token", NOW + timedelta(seconds=45)),
    )
    provider = ReplyCapableProvider(actions)
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions),
        provider,
        "worker:1",
        lambda: NOW + timedelta(seconds=1),
        batch_size=1,
    )

    assert worker.run_once() == 1
    assert actions == ["claim", "commit", "reply", "record", "commit"]
    assert provider.reply_token == "reply-token"
    assert provider.reply_message == {"type": "text", "text": "answer"}


def test_expired_knowledge_reply_opportunity_uses_push_fallback() -> None:
    task = _claimed_knowledge_delivery_task()
    actions: list[str] = []
    repository = DeliveryRepository(
        task,
        actions,
        reply_opportunity=LineReplyOpportunity("reply-token", NOW),
    )
    provider = ReplyCapableProvider(actions)
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions),
        provider,
        "worker:1",
        lambda: NOW + timedelta(seconds=1),
        batch_size=1,
    )

    assert worker.run_once() == 1
    assert actions == ["claim", "commit", "push", "record", "commit"]


def test_rejected_reply_does_not_duplicate_a_possibly_already_used_token() -> None:
    task = _claimed_knowledge_delivery_task()
    actions: list[str] = []
    repository = DeliveryRepository(
        task,
        actions,
        reply_opportunity=LineReplyOpportunity("reply-token", NOW + timedelta(seconds=45)),
    )
    provider = ReplyCapableProvider(
        actions,
        reply_outcome=LineProviderOutcome(
            LineProviderOutcomeType.REJECTED,
            error_code="line_http_400",
            error_message="Invalid reply token",
        ),
    )
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions),
        provider,
        "worker:1",
        lambda: NOW + timedelta(seconds=1),
        batch_size=1,
    )

    assert worker.run_once() == 1
    assert actions == ["claim", "commit", "reply", "record", "commit"]


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_reply_http_server_error_does_not_push_or_retry(status_code) -> None:
    task = _claimed_knowledge_delivery_task()
    actions: list[str] = []
    repository = DeliveryRepository(
        task,
        actions,
        reply_opportunity=LineReplyOpportunity("reply-token", NOW + timedelta(seconds=45)),
    )
    provider = ReplyCapableProvider(
        actions,
        reply_outcome=LineProviderOutcome(
            LineProviderOutcomeType.UNAVAILABLE,
            error_code=f"line_http_{status_code}",
            error_message=f"LINE provider returned HTTP {status_code}",
        ),
    )
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions),
        provider,
        "worker:1",
        lambda: NOW + timedelta(seconds=1),
        batch_size=1,
    )

    assert worker.run_once() == 1
    assert actions == ["claim", "commit", "reply", "record", "commit"]
    assert repository.recorded.provider_outcome.error_code == "line_reply_outcome_uncertain"
    assert repository.recorded.retry_allowed is False


def test_uncertain_reply_does_not_push_a_possibly_duplicate_answer() -> None:
    task = _claimed_knowledge_delivery_task()
    actions: list[str] = []
    repository = DeliveryRepository(
        task,
        actions,
        reply_opportunity=LineReplyOpportunity("reply-token", NOW + timedelta(seconds=45)),
    )
    provider = ReplyCapableProvider(
        actions,
        reply_outcome=LineProviderOutcome(
            LineProviderOutcomeType.TIMEOUT,
            error_code="line_provider_timeout",
            error_message="LINE provider timeout",
        ),
    )
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions),
        provider,
        "worker:1",
        lambda: NOW + timedelta(seconds=1),
        batch_size=1,
    )

    assert worker.run_once() == 1
    assert actions == ["claim", "commit", "reply", "record", "commit"]
    assert repository.recorded.provider_outcome.outcome_type is LineProviderOutcomeType.TIMEOUT
    assert repository.recorded.retry_allowed is False


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


class IsolatedConsumerUowFactory:
    def __init__(self, webhook_inbox) -> None:
        self.webhook_inbox = webhook_inbox
        self.units = []
        self.persisted_business_writes = []

    def __call__(self):
        unit = IsolatedConsumerUow(self)
        self.units.append(unit)
        return unit


class IsolatedConsumerUow(FakeUow):
    def __init__(self, factory: IsolatedConsumerUowFactory) -> None:
        super().__init__(webhook_inbox=factory.webhook_inbox)
        self._factory = factory
        self.pending_business_writes = []

    def commit(self) -> None:
        self._factory.persisted_business_writes.extend(self.pending_business_writes)
        super().commit()


class PartialFailureDispatcher:
    def dispatch(self, _event, unit_of_work):
        unit_of_work.pending_business_writes.append("partial-ticket")
        raise RuntimeError("dispatch unavailable")


class DeliveryRepository:
    def __init__(self, task, actions, reply_opportunity=None) -> None:
        self.task = task
        self.actions = actions
        self._reply_opportunity = reply_opportunity
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

    def reply_opportunity(self, correlation_id):
        return self._reply_opportunity

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


class ReplyCapableProvider:
    def __init__(self, actions, reply_outcome=None) -> None:
        self.actions = actions
        self.reply_outcome = reply_outcome or LineProviderOutcome(
            LineProviderOutcomeType.SUCCESS,
            provider_message_id=LineProviderMessageId("reply:message:1"),
        )
        self.reply_token = None
        self.reply_message = None

    def send(self, request):
        self.actions.append("push")
        return LineProviderOutcome(
            LineProviderOutcomeType.SUCCESS,
            provider_message_id=LineProviderMessageId("push:message:1"),
        )

    def reply(self, reply_token, message):
        self.actions.append("reply")
        self.reply_token = reply_token
        self.reply_message = message
        return self.reply_outcome


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


def _claimed_knowledge_delivery_task():
    task_id = LineDeliveryTaskId(2)
    request = LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId("U-user")),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": "answer"}),
        NOW,
        IdempotencyKey("knowledge-answer-delivery:1"),
        CorrelationId("line-event:event:knowledge:1"),
        "knowledge_answer_request",
        "1",
    )
    lease = LineDeliveryLease(task_id, "worker:1", NOW, NOW + timedelta(minutes=1))
    return LineDeliveryTaskSnapshot(task_id, request, LineDeliveryStatus.PROCESSING, 0, lease)


def test_serial_delivery_uses_fresh_leases_and_preserves_cycle_budget() -> None:
    clock = [NOW]
    actions = []

    class QueueRepository:
        def __init__(self):
            self.pending = list(range(1, 31))
            self.current = {}
            self.records = []
            self.queries = []

        def claim(self, query):
            self.queries.append(query)
            selected = self.pending[:query.batch_size]
            del self.pending[:query.batch_size]
            tasks = []
            for value in selected:
                task_id = LineDeliveryTaskId(value)
                task = replace(
                    _claimed_delivery_task(),
                    task_id=task_id,
                    lease=LineDeliveryLease(
                        task_id, query.lease_owner, query.now,
                        query.now + timedelta(seconds=60),
                    ),
                )
                self.current[task_id] = task
                tasks.append(task)
            return tuple(tasks)

        def get(self, task_id):
            return self.current.get(task_id)

        def record_attempt(self, command):
            assert command.completed_at <= command.lease.expires_at
            self.records.append(command)
            self.current[command.task.task_id] = replace(
                command.task, status=LineDeliveryStatus.SENT,
            )

    class SlowProvider:
        def send(self, request):
            clock[0] += timedelta(seconds=9)
            return LineProviderOutcome(
                LineProviderOutcomeType.SUCCESS,
                provider_message_id=LineProviderMessageId("sent"),
            )

    repository = QueueRepository()
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions),
        SlowProvider(), "worker:1", lambda: clock[0], batch_size=25,
    )

    assert worker.run_once() == 25
    assert len(repository.records) == 25
    assert repository.pending == list(range(26, 31))
    assert all(query.batch_size == 1 for query in repository.queries)
    assert clock[0] == NOW + timedelta(seconds=225)
    assert [record.lease.acquired_at for record in repository.records] == [
        NOW + timedelta(seconds=9 * index) for index in range(25)
    ]


@pytest.mark.parametrize("elapsed", [60, 61])
def test_expired_delivery_lease_never_calls_provider(elapsed) -> None:
    task = _claimed_delivery_task()
    actions = []
    repository = DeliveryRepository(task, actions)
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions),
        SuccessfulProvider(actions), "worker:1",
        lambda: NOW + timedelta(seconds=elapsed), batch_size=1,
    )

    assert worker.run_once() == 1
    assert "provider" not in actions
    assert repository.recorded is None


def test_cancellation_during_fresh_validation_prevents_delivery() -> None:
    task = _claimed_delivery_task()
    actions = []
    repository = DeliveryRepository(task, actions)

    def validate(_task_id):
        repository.task = replace(task, status=LineDeliveryStatus.CANCELLED)
        return None

    def unit_of_work():
        unit = TrackingUow(repository, actions)
        unit.notification_rules = SimpleNamespace(
            manual_replay_delivery_validation_failure=validate,
        )
        return unit

    worker = LineDeliveryWorker(
        unit_of_work, SuccessfulProvider(actions), "worker:1",
        lambda: NOW + timedelta(seconds=1), batch_size=1,
    )
    assert worker.run_once() == 1
    assert "provider" not in actions
    assert repository.recorded is None


def test_reply_rate_limit_retains_existing_push_behavior() -> None:
    task = _claimed_knowledge_delivery_task()
    actions = []
    repository = DeliveryRepository(
        task, actions,
        LineReplyOpportunity("reply-token", NOW + timedelta(seconds=45)),
    )
    provider = ReplyCapableProvider(
        actions, LineProviderOutcome(
            LineProviderOutcomeType.RATE_LIMITED, error_code="line_http_429",
        ),
    )
    worker = LineDeliveryWorker(
        lambda: TrackingUow(repository, actions), provider, "worker:1",
        lambda: NOW + timedelta(seconds=1), batch_size=1,
    )
    assert worker.run_once() == 1
    assert actions == ["claim", "commit", "reply", "push", "record", "commit"]
