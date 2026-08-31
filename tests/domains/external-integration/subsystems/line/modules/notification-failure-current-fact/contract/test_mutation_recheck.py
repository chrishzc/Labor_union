from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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
    LineProviderMessageId,
    LineUserId,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import (
    LineProviderOutcome,
    LineProviderOutcomeType,
)
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.notification_failure_current_fact import (
    LineNotificationFailureCurrentFactReadback,
    LineNotificationFailureReason,
    LineNotificationFailureRecheckTarget,
    LineNotificationUnresolvedReason,
)
from subsystems.line.notification_manual_replay_application import (
    LineNotificationManualReplayApplication,
)
from infrastructure.mysql import line_notification_anomaly_worker


TARGET = LineNotificationFailureRecheckTarget(
    "CASE-006", LineNotificationFailureReason.RECIPIENT_UNAVAILABLE
)
READBACK = LineNotificationFailureCurrentFactReadback(
    "CASE-006",
    LineNotificationFailureReason.RECIPIENT_UNAVAILABLE,
    "owner-token",
    12,
    True,
    1,
    1,
    (LineNotificationUnresolvedReason.REPLAY_IN_PROGRESS,),
    True,
)


class _Uow:
    def __init__(self, events):
        self.events = events
        self.notification_rules = SimpleNamespace(
            manual_replay_source=self._manual_replay_source,
            line006_recheck_targets_for_source=lambda source_id: (TARGET,),
            line006_recheck_targets_for_delivery_task=lambda task_id: (TARGET,),
            current_failure_fact=lambda query: READBACK,
            mark_delivery_task_provider_accepted=lambda task_id: events.append(
                ("accepted", task_id)
            ),
        )
        self.delivery_tasks = SimpleNamespace(
            record_attempt=lambda command: events.append(("attempt", command.task.task_id.value))
        )
        self.anomaly_rechecks = SimpleNamespace(
            append_recheck_intent=lambda intent: events.append(("recheck", intent))
        )
        self.audit = SimpleNamespace(
            append=lambda intent: events.append(("audit", intent.action))
        )

    def _manual_replay_source(self, source_id, identity, occurred_at):
        self.events.append(("replay", source_id, identity, occurred_at))
        return 21

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.events.append("commit")


def test_manual_replay_appends_bounded_recheck_before_existing_commit() -> None:
    now = datetime(2026, 8, 31, 10, tzinfo=UTC)
    events = []
    app = LineNotificationManualReplayApplication(lambda: _Uow(events), lambda: now)

    replay_id = app.apply(
        11,
        ActorContext("admin-1", ("line.config.manage",)),
        "recipient corrected",
        IdempotencyKey("replay-11"),
        CorrelationId("replay-11"),
    )

    assert replay_id == 21
    assert [event[0] if isinstance(event, tuple) else event for event in events] == [
        "replay",
        "recheck",
        "audit",
        "commit",
    ]
    intent = events[1][1]
    assert intent.scope.subject_type == "recipient_unavailable"
    assert intent.scope.subject_ids == ("CASE-006",)


def test_delivery_attempt_appends_recheck_after_delivery_owner_result_before_commit() -> None:
    now = datetime(2026, 8, 31, 10, tzinfo=UTC)
    task = LineDeliveryTaskSnapshot(
        LineDeliveryTaskId(31),
        LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, LineUserId("U-recipient")),
            LineMessageKind.TEXT,
            canonical_line_payload_json({"text": "retry"}),
            now,
            IdempotencyKey("delivery-31"),
            CorrelationId("delivery-31"),
            "case",
            "CASE-006",
        ),
        LineDeliveryStatus.PROCESSING,
        0,
        LineDeliveryLease(
            LineDeliveryTaskId(31), "worker", now, now + timedelta(minutes=1)
        ),
    )
    events = []
    worker = LineDeliveryWorker(
        lambda: _Uow(events), SimpleNamespace(), "worker", lambda: now
    )

    worker._record(
        task,
        LineProviderOutcome(
            LineProviderOutcomeType.SUCCESS, LineProviderMessageId("message-31")
        ),
    )

    assert [event[0] if isinstance(event, tuple) else event for event in events] == [
        "attempt",
        "accepted",
        "recheck",
        "commit",
    ]


def test_replay_task_failing_fresh_validation_never_calls_provider() -> None:
    now = datetime(2026, 8, 31, 10, tzinfo=UTC)
    task = LineDeliveryTaskSnapshot(
        LineDeliveryTaskId(32),
        LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, LineUserId("U-old")),
            LineMessageKind.TEXT,
            canonical_line_payload_json({"text": "retry"}),
            now,
            IdempotencyKey("delivery-32"),
            CorrelationId("delivery-32"),
            "case",
            "CASE-006",
        ),
        LineDeliveryStatus.PROCESSING,
        0,
        LineDeliveryLease(
            LineDeliveryTaskId(32), "worker", now, now + timedelta(minutes=1)
        ),
    )
    events = []

    class Repository:
        def __init__(self):
            self.claimed = False

        def claim(self, _query):
            if self.claimed:
                return ()
            self.claimed = True
            return (task,)

        def get(self, _task_id):
            return task

        def record_attempt(self, command):
            events.append(("outcome", command.provider_outcome.outcome_type.value))

    repository = Repository()

    class Uow(_Uow):
        def __init__(self):
            super().__init__(events)
            self.delivery_tasks = repository
            self.notification_rules.manual_replay_delivery_validation_failure = (
                lambda _task_id: "recipient_binding_changed"
            )

    class Provider:
        def send(self, _request):
            raise AssertionError("provider must not be called")

    worker = LineDeliveryWorker(lambda: Uow(), Provider(), "worker", lambda: now)

    assert worker.run_once() == 1
    assert ("outcome", "rejected") in events


def test_existing_notification_anomaly_worker_entry_enqueues_current_recheck(
    monkeypatch,
) -> None:
    events = []

    class Connection:
        def close(self):
            events.append("close")

    class Notifications:
        def list_line006_recheck_targets(self, *, limit):
            assert limit == 5
            return (TARGET,)

        def current_failure_fact(self, _query):
            return READBACK

    class Unit:
        def __init__(self, connection):
            self.notification_rules = Notifications()
            self.anomaly_rechecks = SimpleNamespace(
                append_recheck_intent=lambda intent: events.append(("recheck", intent))
            )

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            events.append("commit")

    monkeypatch.setattr(line_notification_anomaly_worker, "LineMySqlUnitOfWork", Unit)

    processed = line_notification_anomaly_worker.MySqlLineNotificationAnomalyWorker(
        Connection
    ).run_once(limit=5)

    assert processed == 1
    assert [event[0] if isinstance(event, tuple) else event for event in events] == [
        "recheck",
        "commit",
        "close",
    ]
