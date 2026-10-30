"""New informational replies use Reply; business results and old queues keep Push.

All delivery and webhook ports are synthetic; no database or LINE API is used.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock
from pymysql.err import IntegrityError

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (LineDeliveryLease, LineDeliveryRequest, LineDeliveryStatus,
    LineDeliveryTaskSnapshot, LineMessageKind, LineRecipient, LineRecipientType)
from domains.line.identities import LineDeliveryTaskId, LineGroupId, LineRoomId, LineProviderMessageId, LineSourceType, LineUserId, LineWebhookEventId
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE, LineProviderOutcome, LineProviderOutcomeType, LineReplyOpportunity
from subsystems.line.delivery_contracts import EnqueueLineDeliveryResult, LineDeliveryCommandOutcome
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.menu_command_application import LineMenuCommandApplication
from subsystems.line.order_group_application import LineOrderGroupApplication
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers
from subsystems.line.webhook_event_consumer import LineWebhookEventConsumer
from subsystems.line.event_dispatcher import LineEventDispatchStatus

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)
USER = LineUserId("U_SYNTHETIC")
GROUP = LineGroupId("C_SYNTHETIC")


class Deliveries:
    def __init__(self):
        self.tasks = {}
        self.attempts = []
        self.opportunity = LineReplyOpportunity("synthetic-token", NOW + timedelta(seconds=45))
        self.reply_reads = []
        self.new_reply_ids = []

    def enqueue(self, request):
        identifier = len(self.tasks) + 1
        task = LineDeliveryTaskSnapshot(LineDeliveryTaskId(identifier), request, LineDeliveryStatus.PENDING, 0, None)
        self.tasks[identifier] = task
        if request.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE:
            self.new_reply_ids.append(task.task_id)
        return SimpleNamespace(task_id=task.task_id)

    def new_reply_task_ids(self):
        return tuple(self.new_reply_ids)

    def claim_specific(self, task_id, query):
        task = self.tasks[task_id.value]
        if task.status is not LineDeliveryStatus.PENDING:
            return None
        lease = LineDeliveryLease(task.task_id, query.lease_owner, query.now, query.now + timedelta(seconds=60))
        self.tasks[task_id.value] = replace(task, status=LineDeliveryStatus.PROCESSING, lease=lease)
        return self.tasks[task_id.value]

    def claim(self, query):
        for identifier, task in self.tasks.items():
            if task.status is LineDeliveryStatus.PENDING:
                lease = LineDeliveryLease(task.task_id, query.lease_owner, query.now, query.now + timedelta(seconds=60))
                self.tasks[identifier] = replace(task, status=LineDeliveryStatus.PROCESSING, lease=lease)
                return (self.tasks[identifier],)
        return ()

    def get(self, task_id):
        return self.tasks[task_id.value]

    def reply_opportunity(self, correlation_id, *, recipient=None):
        self.reply_reads.append((correlation_id, recipient))
        return self.opportunity

    def cancel(self, command):
        raise AssertionError("The approved change must not cancel existing queued messages")

    def record_attempt(self, command):
        self.attempts.append(command)
        status = LineDeliveryStatus.SENT if command.provider_outcome.outcome_type is LineProviderOutcomeType.SUCCESS else LineDeliveryStatus.FAILED
        self.tasks[command.task.task_id.value] = replace(command.task, status=status, lease=None)


class Unit:
    def __init__(self):
        self.delivery_tasks = Deliveries()
        self.audit = []
        self.customer_service = SimpleNamespace(
            create_or_append=Mock(return_value=SimpleNamespace(ticket_id=42)),
            latest_client_case=Mock(return_value=None),
        )
        self.identity_flows = SimpleNamespace(open=Mock(return_value=SimpleNamespace(flow_id=SimpleNamespace(value="synthetic-flow"))))
        self.platform_users = SimpleNamespace(apply_friend_event=lambda event: SimpleNamespace(last_event_at=NOW))
        self.identities = SimpleNamespace(list_by_user=lambda user: (
            SimpleNamespace(status=LineIdentityBindingStatus.BOUND, subject_type=LineBindingSubjectType.ADMIN),))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        pass


def inbox(text="服務說明", *, group=False, kind="message"):
    source = SimpleNamespace(source_type=LineSourceType.GROUP if group else LineSourceType.USER,
        user_id=USER, group_id=GROUP if group else None, source_id=GROUP.value if group else USER.value)
    payload = {"type": kind, "message": {"type": "text", "text": text}}
    event = SimpleNamespace(event_id=LineWebhookEventId("synthetic-event"), source=source,
        event_type=kind, occurred_at=NOW, payload_json=json.dumps(payload))
    return SimpleNamespace(event=event)


def request(source=REPLY_ONLY_WEBHOOK_SOURCE, *, key="new-information"):
    return LineDeliveryRequest(LineRecipient(LineRecipientType.USER, USER), LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": "synthetic copy"}), NOW, IdempotencyKey(key),
        CorrelationId("line-event:synthetic-event"), source, "synthetic-event")


def provider():
    result = Mock()
    result.reply.return_value = result.send.return_value = LineProviderOutcome(LineProviderOutcomeType.SUCCESS,
        provider_message_id=LineProviderMessageId("synthetic-message"))
    return result


@pytest.mark.parametrize("text", ["服務說明", "服務流程", "收費與補助", "查詢服務進度", "服務登記", "其他問題", "恢復AI"])
def test_information_and_disabled_prompts_are_new_reply_only_work(text):
    unit = Unit()
    assert LineServiceHelpApplication(lambda: NOW).handle(inbox(text), unit, USER, text)
    assert len(unit.delivery_tasks.tasks) == 1
    task = unit.delivery_tasks.tasks[1]
    assert task.request.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE
    unit.customer_service.create_or_append.assert_not_called()
    sender = provider()
    assert LineDeliveryWorker(lambda: unit, sender, "synthetic-worker", lambda: NOW).run_once() == 1
    sender.reply.assert_called_once_with("synthetic-token", json.loads(task.request.payload_json))
    sender.send.assert_not_called()
    assert unit.delivery_tasks.reply_reads[0][1] == task.request.recipient


@pytest.mark.parametrize("text", ["修改登記資料", "修改服務地址", "我要客訴：需要專員處理"])
def test_business_intake_acknowledgements_still_use_push(text):
    unit = Unit()
    gateway = SimpleNamespace(hold_guard=lambda *args: None, create_for_ticket=lambda *args: None)
    assert LineServiceHelpApplication(lambda: NOW, escalation_gateway=gateway).handle(inbox(text), unit, USER, text)
    unit.customer_service.create_or_append.assert_called_once()
    assert unit.delivery_tasks.tasks[1].request.source_aggregate_type == "line_webhook_event"
    sender = provider()
    assert LineDeliveryWorker(lambda: unit, sender, "synthetic-worker", lambda: NOW).run_once() == 1
    sender.send.assert_called_once()
    sender.reply.assert_not_called()


@pytest.mark.parametrize("kind,text", [("follow", ""), ("message", "綁定訂單"), ("message", "我是月嫂"), ("message", "綁定後台帳號")])
def test_welcome_and_binding_entries_use_reply_without_changing_flow(kind, text):
    unit = Unit()
    handlers = LineWebhookIdentityHandlers(lambda: NOW, lambda purpose, flow: "https://example.invalid/identity")
    if kind == "follow":
        handlers.handle_follow(inbox(kind=kind), unit)
    else:
        handlers.handle_message(inbox(text), unit)
    assert unit.identity_flows.open.call_count == 1
    assert unit.delivery_tasks.tasks[1].request.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE


def test_menu_help_uses_reply():
    unit = Unit()
    assert LineMenuCommandApplication().handle(inbox("切換選單"), unit, USER, "切換選單")
    assert unit.delivery_tasks.tasks[1].request.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE


def test_private_reply_to_a_group_participant_keeps_existing_cross_chat_push():
    unit, sender = Unit(), provider()
    text = "服務說明"
    application = LineServiceHelpApplication(lambda: NOW)
    assert application.handle(inbox(text, group=True), unit, USER, text)
    task = unit.delivery_tasks.tasks[1]
    assert task.request.source_aggregate_type == "line_webhook_event"
    assert task.request.recipient == LineRecipient(LineRecipientType.USER, USER)
    assert LineDeliveryWorker(lambda: unit, sender, "synthetic-worker", lambda: NOW).run_once() == 1
    sender.send.assert_called_once()
    sender.reply.assert_not_called()


def test_menu_help_in_group_remains_unhandled_without_delivery():
    unit = Unit()
    assert not LineMenuCommandApplication().handle(inbox("切換選單", group=True), unit, USER, "切換選單")
    assert not unit.delivery_tasks.tasks


@pytest.mark.parametrize("suffix", ["error", "bound", "invite-queued"])
def test_group_errors_change_but_group_success_confirmations_stay_push(suffix):
    unit = Unit()
    LineOrderGroupApplication(lambda: NOW)._reply_to_group(inbox(group=True), unit, "same group copy", suffix)
    task = unit.delivery_tasks.tasks[1]
    assert task.request.recipient == LineRecipient(LineRecipientType.GROUP, GROUP)
    assert task.request.source_aggregate_type == (REPLY_ONLY_WEBHOOK_SOURCE if suffix == "error" else "line_webhook_event")


@pytest.mark.parametrize("outcome", [LineProviderOutcomeType.REJECTED, LineProviderOutcomeType.RATE_LIMITED,
    LineProviderOutcomeType.TIMEOUT, LineProviderOutcomeType.UNAVAILABLE, "exception", "missing", "expired", "retried", "wrong_event"])
def test_reply_only_failures_never_push_or_automatically_retry(outcome):
    unit, sender = Unit(), provider()
    new = request()
    if outcome == "wrong_event":
        new = replace(new, correlation_id=CorrelationId("line-event:another-event"))
    unit.delivery_tasks.enqueue(new)
    if outcome == "retried":
        unit.delivery_tasks.tasks[1] = replace(unit.delivery_tasks.tasks[1], completed_attempts=1)
    if outcome == "missing":
        unit.delivery_tasks.opportunity = None
    elif outcome == "expired":
        unit.delivery_tasks.opportunity = LineReplyOpportunity("synthetic-token", NOW - timedelta(seconds=1))
    elif outcome == "exception":
        sender.reply.side_effect = RuntimeError("synthetic failure")
    elif isinstance(outcome, LineProviderOutcomeType):
        sender.reply.return_value = LineProviderOutcome(outcome, error_code="synthetic-error", error_message="synthetic failure")
    assert LineDeliveryWorker(lambda: unit, sender, "synthetic-worker", lambda: NOW).run_once() == 1
    sender.send.assert_not_called()
    assert sender.reply.call_count <= 1
    assert unit.delivery_tasks.tasks[1].status is LineDeliveryStatus.FAILED
    assert unit.delivery_tasks.attempts[0].retry_allowed is False


@pytest.mark.parametrize("source,key", [("line_webhook_event", "service-help:menu:synthetic-event"),
    ("line_webhook_event", "service-help:ticket:synthetic-event"), ("matching_response_event", "matching-confirmation"),
    ("line_identity", "identity-result"), ("customer_service_assistance_ack", "deposit-assistance")])
def test_old_queue_and_business_result_sources_keep_their_push_policy(source, key):
    unit, sender = Unit(), provider()
    unit.delivery_tasks.enqueue(request(source, key=key))
    assert LineDeliveryWorker(lambda: unit, sender, "synthetic-worker", lambda: NOW).run_once() == 1
    sender.send.assert_called_once()
    sender.reply.assert_not_called()
    assert unit.delivery_tasks.attempts[0].retry_allowed is True


@pytest.mark.parametrize("source,recipient,already_sent,allowed", [
    ({"type": "user", "userId": USER.value}, LineRecipient(LineRecipientType.USER, USER), False, True),
    ({"type": "group", "groupId": GROUP.value}, LineRecipient(LineRecipientType.GROUP, GROUP), False, True),
    ({"type": "user", "userId": "U_OTHER"}, LineRecipient(LineRecipientType.USER, USER), False, False),
    ({"type": "group", "groupId": GROUP.value}, LineRecipient(LineRecipientType.USER, USER), False, False),
    ({"type": "group", "groupId": "C_OTHER"}, LineRecipient(LineRecipientType.GROUP, GROUP), False, False),
    ({}, LineRecipient(LineRecipientType.USER, USER), False, False),
    ({"type": "user", "userId": USER.value}, LineRecipient(LineRecipientType.USER, USER), True, False),
])
def test_reply_opportunity_is_bound_to_original_chat_and_unused_token(source, recipient, already_sent, allowed):
    payload = {"replyToken": "synthetic-token", "source": source, "immediate_reply_sent": already_sent}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, *args): pass
        def fetchone(self): return {"payload_snapshot": json.dumps(payload), "received_at_utc": NOW.replace(tzinfo=None)}
    repository = MySqlLineDeliveryTaskRepository(SimpleNamespace(cursor=Cursor))
    assert (repository.reply_opportunity(CorrelationId("line-event:synthetic-event"), recipient=recipient) is not None) is allowed


def test_router_readback_keeps_old_and_new_sources_and_original_recipient_scope():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.create_function("JSON_UNQUOTE", 1, lambda value: value)
    db.execute("CREATE TABLE line_notification_source_events (id INTEGER,source_event_identity TEXT,facts_snapshot TEXT,source_domain TEXT,event_code TEXT,occurred_at_utc TEXT)")
    db.execute("CREATE TABLE line_delivery_tasks (source_aggregate_type TEXT,source_aggregate_identity TEXT,recipient_type TEXT,recipient_identity TEXT)")
    for index, source, user in [(1, "line_webhook_event", USER.value), (2, REPLY_ONLY_WEBHOOK_SOURCE, USER.value), (3, REPLY_ONLY_WEBHOOK_SOURCE, "U_OTHER")]:
        event = f"event-{index}"
        facts = {"source_event_id": event, "reply_kind": "menu", "reason_code": "service_help_menu",
                 "source_contract_id": "LU96-M2-ROUTER-REPLY-SOURCE-V1", "source_revision": 1}
        db.execute("INSERT INTO line_notification_source_events VALUES (?,?,?,?,?,?)", (index, f"router-reply:{event}:menu", json.dumps(facts), "line_router", "router.deterministic.reply_committed", NOW.isoformat()))
        db.execute("INSERT INTO line_delivery_tasks VALUES (?,?,?,?)", (source, event, "user", user))
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params): self.inner = db.execute(sql.replace("%s", "?"), params)
        def fetchall(self): return [dict(row) for row in self.inner.fetchall()]
    try:
        replies = MySqlLineNotificationRepository(SimpleNamespace(cursor=Cursor)).list_router_replies(USER.value)
        assert [reply.source_event_id for reply in replies] == ["event-2", "event-1"]
    finally:
        db.close()


@pytest.fixture
def sql_inbox():
    """Execute production SELECT predicates; the wrapper only adapts DB syntax/types."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE line_inbox_events (event_identity TEXT PRIMARY KEY, event_type TEXT, source_type TEXT, payload_snapshot TEXT, received_at_utc TEXT)")
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params): self.inner = db.execute(sql.replace("%s", "?"), params)
        def fetchone(self):
            row = self.inner.fetchone()
            if row is None: return None
            result = dict(row)
            result["received_at_utc"] = datetime.fromisoformat(result["received_at_utc"])
            return result
    repository = MySqlLineDeliveryTaskRepository(SimpleNamespace(cursor=Cursor))
    try:
        yield db, repository
    finally:
        db.close()


@pytest.mark.parametrize("event_type,source_type,allowed", [
    ("follow", "user", True), ("message", "user", True),
    ("message", "group", True), ("message", "room", True),
    ("postback", "user", True), ("postback", "group", True), ("postback", "room", True),
    ("unfollow", "user", False), ("memberJoined", "group", False),
    ("follow", "group", False), ("message", "unknown", False),
])
def test_production_reply_query_filters_event_type_source_and_event_identity(sql_inbox, event_type, source_type, allowed):
    db, repository = sql_inbox
    kind = source_type if source_type != "unknown" else "user"
    identity = {"user": USER, "group": GROUP, "room": LineRoomId("R_SYNTHETIC")}[kind]
    recipient = LineRecipient(LineRecipientType(kind), identity)
    source = {"type": kind, {"user": "userId", "group": "groupId", "room": "roomId"}[kind]: identity.value}
    payload = {"replyToken": "synthetic-token", "source": source}
    db.execute("INSERT INTO line_inbox_events VALUES (?,?,?,?,?)", ("synthetic-event", event_type, source_type, json.dumps(payload), NOW.replace(tzinfo=None).isoformat()))
    unit, sender = Unit(), provider()
    unit.delivery_tasks.reply_opportunity = repository.reply_opportunity
    unit.delivery_tasks.enqueue(replace(request(), recipient=recipient))
    assert LineDeliveryWorker(lambda: unit, sender, "synthetic-worker", lambda: NOW).run_once() == 1
    assert sender.reply.call_count == int(allowed)
    sender.send.assert_not_called()
    assert repository.reply_opportunity(CorrelationId("line-event:absent-event"), recipient=recipient) is None
    # The existing knowledge path keeps its original private-message restriction.
    assert (repository.reply_opportunity(CorrelationId("line-event:synthetic-event")) is not None) is (event_type == "message" and source_type == "user")


@pytest.mark.parametrize("payload", [
    {"replyToken": "synthetic-token", "source": {"type": "user", "userId": "U_OTHER"}},
    {"replyToken": "synthetic-token", "source": {"type": "group", "groupId": GROUP.value}},
    {"replyToken": "synthetic-token", "source": {"type": "user", "userId": USER.value}, "immediate_reply_sent": True},
    {"replyToken": "synthetic-token", "source": {"type": "user", "userId": USER.value}, "mode": "standby"},
    {"source": {"type": "user", "userId": USER.value}},
])
def test_production_query_never_borrows_other_chat_or_spent_reply(sql_inbox, payload):
    db, repository = sql_inbox
    db.execute("INSERT INTO line_inbox_events VALUES (?,?,?,?,?)", ("synthetic-event", "follow", "user", json.dumps(payload), NOW.replace(tzinfo=None).isoformat()))
    assert repository.reply_opportunity(CorrelationId("line-event:synthetic-event"), recipient=LineRecipient(LineRecipientType.USER, USER)) is None


def test_only_new_reply_inserts_are_expedited_not_duplicates_or_push(monkeypatch):
    repository = MySqlLineDeliveryTaskRepository(SimpleNamespace())
    monkeypatch.setattr(repository, "_insert", Mock(side_effect=[11, 12, IntegrityError(1062, "synthetic duplicate")]))
    monkeypatch.setattr(repository, "_existing_enqueue", lambda request: EnqueueLineDeliveryResult(LineDeliveryCommandOutcome.EXISTING, LineDeliveryTaskId(7), LineDeliveryStatus.PENDING))
    repository.enqueue(request())
    repository.enqueue(request("line_webhook_event"))
    repository.enqueue(request())
    assert repository.new_reply_task_ids() == (LineDeliveryTaskId(11),)


def test_commit_then_expedite_new_information_before_old_queue_with_bounded_budget():
    unit, sender = Unit(), provider()
    old_push = unit.delivery_tasks.enqueue(request("line_webhook_event", key="old-push")).task_id
    old_reply = unit.delivery_tasks.enqueue(request(key="old-reply")).task_id
    unit.delivery_tasks.new_reply_ids.clear()
    worker = LineDeliveryWorker(lambda: unit, sender, "synthetic-worker", lambda: NOW, batch_size=4)
    trace = []
    unit.commit = lambda: trace.append("commit")
    unit.webhook_inbox = SimpleNamespace(complete=lambda command: trace.append("complete"))
    def dispatch(event, uow):
        uow.delivery_tasks.new_reply_ids.clear()  # Each real UoW has a fresh repository.
        uow.delivery_tasks.enqueue(request(key=f"new-{len(uow.delivery_tasks.tasks)}"))
        return SimpleNamespace(status=LineEventDispatchStatus.PROCESSED)
    def reply(*args):
        assert "commit" in trace
        trace.append("reply")
        return LineProviderOutcome(LineProviderOutcomeType.SUCCESS, provider_message_id=LineProviderMessageId("synthetic-message"))
    sender.reply.side_effect = reply
    consumer = LineWebhookEventConsumer(lambda: unit, SimpleNamespace(dispatch=dispatch), "synthetic-worker", lambda: NOW,
        on_new_reply_tasks=worker.run_new_reply_tasks)
    event = inbox()
    event.lease = SimpleNamespace(event_id=event.event.event_id)
    event.attempt_count, event.max_attempts = 1, 3
    for _ in range(3):
        consumer._consume(event)
    assert trace[:3] == ["complete", "commit", "commit"]  # Business commit precedes fresh claim commit.
    assert sender.reply.call_count == 2  # Half the cycle remains available to the original queue.
    sender.send.assert_not_called()
    assert unit.delivery_tasks.tasks[old_push.value].status is LineDeliveryStatus.PENDING
    assert unit.delivery_tasks.tasks[old_reply.value].status is LineDeliveryStatus.PENDING
    assert worker.run_once() == 4  # Includes the two expedited replies in heartbeat/batch counts.
    sender.send.assert_called_once()
    assert unit.delivery_tasks.tasks[old_push.value].status is LineDeliveryStatus.SENT
    assert unit.delivery_tasks.tasks[old_reply.value].status is LineDeliveryStatus.SENT
    assert unit.delivery_tasks.tasks[5].status is LineDeliveryStatus.PENDING


def test_failed_business_commit_never_triggers_early_delivery():
    unit = Unit()
    callback = Mock()
    unit.delivery_tasks.enqueue(request())
    unit.webhook_inbox = SimpleNamespace(complete=Mock())
    unit.commit = Mock(side_effect=[RuntimeError("synthetic commit failure"), None])
    consumer = LineWebhookEventConsumer(lambda: unit,
        SimpleNamespace(dispatch=lambda *args: SimpleNamespace(status=LineEventDispatchStatus.PROCESSED)),
        "synthetic-worker", lambda: NOW, on_new_reply_tasks=callback)
    event = inbox()
    event.lease = SimpleNamespace(event_id=event.event.event_id)
    event.attempt_count, event.max_attempts = 1, 3
    consumer._consume(event)
    callback.assert_not_called()
    assert unit.webhook_inbox.complete.call_args.args[0].target_status.value == "retryable_failed"


def test_early_delivery_failure_cannot_retry_committed_webhook_business():
    unit = Unit()
    unit.delivery_tasks.enqueue(request())
    unit.webhook_inbox = SimpleNamespace(complete=Mock())
    consumer = LineWebhookEventConsumer(lambda: unit,
        SimpleNamespace(dispatch=lambda *args: SimpleNamespace(status=LineEventDispatchStatus.PROCESSED)),
        "synthetic-worker", lambda: NOW,
        on_new_reply_tasks=Mock(side_effect=RuntimeError("synthetic delivery failure")))
    event = inbox()
    event.lease = SimpleNamespace(event_id=event.event.event_id)
    with pytest.raises(RuntimeError, match="synthetic delivery failure"):
        consumer._consume(event)
    assert unit.webhook_inbox.complete.call_count == 1
    assert unit.webhook_inbox.complete.call_args.args[0].target_status.value == "processed"


def test_early_delivery_ignores_business_results_and_already_claimed_tasks():
    unit, sender = Unit(), provider()
    business_id = unit.delivery_tasks.enqueue(request("line_webhook_event")).task_id
    claimed_id = unit.delivery_tasks.enqueue(request()).task_id
    unit.delivery_tasks.tasks[claimed_id.value] = replace(unit.delivery_tasks.tasks[claimed_id.value], status=LineDeliveryStatus.PROCESSING)
    LineDeliveryWorker(lambda: unit, sender, "synthetic-worker", lambda: NOW).run_new_reply_tasks((business_id, claimed_id))
    sender.send.assert_not_called()
    sender.reply.assert_not_called()
    assert unit.delivery_tasks.tasks[business_id.value].status is LineDeliveryStatus.PENDING
