"""P5 contract tests for M3 committed intents and LINE delivery tasks."""

from datetime import datetime, timezone

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
)
from domains.line.identities import LineDeliveryTaskId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import (
    EnqueueLineDeliveryResult,
    LineDeliveryCommandOutcome,
)
from subsystems.line.matching_coordination_delivery import (
    LocalLineDeliveryAdapter,
    MatchingCoordinationDeliveryApplication,
    MatchingCoordinationDeliveryError,
    MatchingCoordinationOutboxItem,
    MatchingDeliveryProviderStatus,
    normalize_matching_coordination_intent,
)
from subsystems.line.matching_coordination_delivery_worker import (
    MatchingCoordinationDeliveryWorker,
)
from subsystems.customer_service.matching_coordination_worker import (
    MatchingCoordinationCustomerServiceWorker,
)
from subsystems.line.notification_failure_current_fact import (
    LineNotificationFailureCurrentFactQuery,
    LineNotificationFailureReason,
    evaluate_line_notification_failure_current_fact,
)


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


class _DeliveryTasks:
    def __init__(self, *, outcome=LineDeliveryCommandOutcome.CREATED):
        self.outcome = outcome
        self.task = None
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)
        self.task = LineDeliveryTaskSnapshot(
            LineDeliveryTaskId(41), request, LineDeliveryStatus.PENDING, 0
        )
        return EnqueueLineDeliveryResult(self.outcome, self.task.task_id, self.task.status)

    def get(self, _task_id):
        return self.task


class _NotificationRules:
    def __init__(self):
        self.queries = []

    def current_failure_fact(self, query):
        self.queries.append(query)
        return evaluate_line_notification_failure_current_fact(
            query, (), owner_version=0, authoritative_complete=True
        )


class _Uow:
    def __init__(self, delivery_tasks):
        self.delivery_tasks = delivery_tasks
        self.notification_rules = _NotificationRules()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class _MatchingNotifications:
    def __init__(self):
        self.rows = {}

    def interaction(self, token_hash):
        return self.rows.get(token_hash)

    def open_interaction(self, **values):
        self.rows[values["token_hash"]] = values


class _CustomerService:
    def __init__(self):
        self.commands = []

    def create_or_append(self, command):
        self.commands.append(command)


class _CustomerServiceUow:
    def __init__(self, source=None, customer_service=None):
        self.matching_coordination_customer_service = source
        self.customer_service = customer_service or _CustomerService()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


def _item(**payload_overrides):
    payload = {
        "source_identity": "LU96-M3-MATCH-SUCCESS-CLIENT-SOURCE-V1",
        "source_event_identity": "matching:case-96:decision",
        "recipient_selector": "assignment.client_snapshot",
        "recipient_snapshot": {
            "recipient_type": "user",
            "recipient_identity": "U-client-96",
        },
        "binding": {"active": True, "revision": 3},
        "configuration": {"active": True, "revision": 7},
        "message_kind": "text",
        "message": {"type": "text", "text": "媒合結果已更新"},
        "notification_reason": "recipient_unavailable",
    }
    payload.update(payload_overrides)
    return MatchingCoordinationOutboxItem(
        "match-96:notify:customer",
        101,
        "match-96:receipt",
        "CASE-96",
        "line_client_decision",
        "line_integration",
        payload,
        IdempotencyKey("match-96:notify:customer"),
        CorrelationId("match-96"),
    )


def test_committed_m3_intent_projects_to_existing_task_and_typed_line006_readback():
    delivery_tasks = _DeliveryTasks()
    uow = _Uow(delivery_tasks)
    receipt = MatchingCoordinationDeliveryApplication(
        lambda: uow, lambda: NOW
    ).consume(_item())

    assert receipt.task_id == 41
    assert receipt.task_status is LineDeliveryStatus.PENDING
    assert receipt.provider_status is MatchingDeliveryProviderStatus.NOT_RUN
    assert receipt.line006_readback is not None
    assert receipt.line006_readback.predicate_active is False
    assert uow.committed is True
    assert delivery_tasks.requests[0].recipient.identity.value == "U-client-96"
    assert delivery_tasks.requests[0].source_aggregate_identity == "match-96:notify:customer"
    assert uow.notification_rules.queries == [
        LineNotificationFailureCurrentFactQuery(
            "CASE-96", LineNotificationFailureReason.RECIPIENT_UNAVAILABLE
        )
    ]


def test_replaying_same_m3_outbox_row_reuses_idempotent_task():
    delivery_tasks = _DeliveryTasks(outcome=LineDeliveryCommandOutcome.EXISTING)
    uow = _Uow(delivery_tasks)
    receipt = MatchingCoordinationDeliveryApplication(
        lambda: uow, lambda: NOW
    ).consume(_item())

    assert receipt.replayed is True
    assert len(delivery_tasks.requests) == 1


def test_zero_pool_delivery_opens_recipient_bound_interaction_once():
    delivery_tasks = _DeliveryTasks()
    uow = _Uow(delivery_tasks)
    interactions = _MatchingNotifications()
    uow.matching_notifications = interactions
    item = _item(
        interaction={
            "token": "p6zeroabcdefghijklmnopqrstuvwxyz",
            "plan_id": 96,
            "segment_id": None,
            "action_scope": "customer_decision",
            "expires_at_utc": "2026-09-08T12:00:00+00:00",
        }
    )
    MatchingCoordinationDeliveryApplication(lambda: uow, lambda: NOW).consume(item)
    assert len(interactions.rows) == 1
    row = next(iter(interactions.rows.values()))
    assert row["plan_id"] == 96
    assert row["action_scope"] == "customer_decision"
    MatchingCoordinationDeliveryApplication(lambda: uow, lambda: NOW).consume(item)
    assert len(interactions.rows) == 1


def test_customer_service_owner_worker_consumes_typed_m3_handoff():
    item = type(
        "Item",
        (),
        {
            "reference_id": "matching:case-96:customer-service",
            "case_no": "CASE-96",
            "line_user_id": "U-client-96",
            "category": "service_flow",
            "message": "請客服協助",
        },
    )()
    source = type(
        "Source",
        (),
        {"list_customer_service_intents": lambda self, *, limit: (item,)},
    )()
    customer_service = _CustomerService()
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return _CustomerServiceUow(
            source if calls == 1 else None,
            customer_service,
        )

    worker = MatchingCoordinationCustomerServiceWorker(factory, "line-worker-96")
    assert worker.run_once() == 1
    assert worker.failures == ()
    assert customer_service.commands[0].line_user_id == "U-client-96"
    assert customer_service.commands[0].event_key == item.reference_id


@pytest.mark.parametrize(
    ("override", "error_code"),
    [
        ({"recipient_snapshot": None}, "line_matching_recipient_snapshot_missing"),
        ({"binding": {"active": False}}, "line_matching_recipient_binding_invalid"),
        ({"configuration": {"active": False}}, "line_matching_configuration_invalid"),
        ({"message": None}, "line_matching_delivery_message_missing"),
    ],
)
def test_missing_p5_precondition_fails_closed(override, error_code):
    with pytest.raises(MatchingCoordinationDeliveryError) as error:
        normalize_matching_coordination_intent(_item(**override), now=NOW)
    assert error.value.code == error_code


def test_non_line_owner_is_not_projected_to_a_line_task():
    item = _item()
    item = MatchingCoordinationOutboxItem(
        item.reference_id,
        item.event_id,
        item.receipt_id,
        item.case_no,
        "customer_service_ticket",
        "customer_service",
        item.intent_payload,
        item.idempotency_key,
        item.correlation_id,
    )
    with pytest.raises(MatchingCoordinationDeliveryError) as error:
        normalize_matching_coordination_intent(item, now=NOW)
    assert error.value.code == "line_matching_outbox_owner_mismatch"


def test_local_adapter_has_deterministic_success_without_provider_effect():
    request, _ = normalize_matching_coordination_intent(_item(), now=NOW)
    first = LocalLineDeliveryAdapter().send(request)
    second = LocalLineDeliveryAdapter().send(request)

    assert first == second
    assert first.outcome_type.value == "success"
    assert first.provider_message_id.value.startswith("local:")


def test_worker_reads_committed_m3_rows_and_reuses_line_task_owner():
    delivery_tasks = _DeliveryTasks()
    item = _item()
    item_source = type("Source", (), {"list_line_intents": lambda self, *, limit: (item,)})()
    uow = _Uow(delivery_tasks)
    uow.matching_coordination_delivery = item_source

    count = MatchingCoordinationDeliveryWorker(
        lambda: uow, "line-worker-96", lambda: NOW
    ).run_once()

    assert count == 1
    assert len(delivery_tasks.requests) == 1


def test_worker_records_typed_failure_and_continues_after_one_immutable_bad_row():
    good = _item()
    bad = _item(message=None)
    bad = MatchingCoordinationOutboxItem(
        "match-96:notify:bad",
        102,
        "match-96:receipt:bad",
        "CASE-96-BAD",
        bad.intent_type,
        bad.target_owner,
        bad.intent_payload,
        IdempotencyKey("match-96:notify:bad"),
        bad.correlation_id,
    )
    item_source = type(
        "Source",
        (),
        {"list_line_intents": lambda self, *, limit: (bad, good)},
    )()
    delivery_tasks = _DeliveryTasks()
    uow = _Uow(delivery_tasks)
    uow.matching_coordination_delivery = item_source

    worker = MatchingCoordinationDeliveryWorker(lambda: uow, "line-worker-96", lambda: NOW)
    assert worker.run_once() == 2
    assert len(delivery_tasks.requests) == 1
    assert worker.failures[0].reference_id == "match-96:notify:bad"
    assert worker.failures[0].code == "line_matching_delivery_message_missing"
    assert worker.failures[0].fallback == "manual_review"
