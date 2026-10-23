"""Customer assistance retains acceptance; reminders never expire a recommendation."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from types import SimpleNamespace

import pytest

from domains.line.identities import LineUserId
from domains.scheduling.matching_communication import (
    CaregiverWillingness, CustomerMatchingDecision, MatchingCommunicationConflictError,
    MatchingCommunicationStaleError, MatchingPlanReference, MatchingRecipientMismatchError,
)
from infrastructure.mysql.matching_notification_repository import MySqlMatchingNotificationRepository
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.matching_postback_application import LineMatchingPostbackApplication
from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication
from subsystems.scheduling.matching_notification_contracts import (
    MatchingContactState, MatchingResponseResult, MatchingSegmentContact,
)

NOW = datetime(2026, 10, 22, 4, tzinfo=timezone.utc)
CUSTOMER = LineUserId("U-synthetic-customer")


class _Repository:
    def __init__(self):
        self.state = MatchingContactState(
            MatchingPlanReference("CASE-SYNTHETIC", 10, 0), "proposed", True, "洽談中",
            CUSTOMER, CustomerMatchingDecision.PENDING, None,
            (MatchingSegmentContact(20, 1, 30, "測試月嫂", LineUserId("U-synthetic-caregiver"),
                                   "2026-11-01", "2026-11-10", CaregiverWillingness.WILLING),),
        )
        self.action = dict(case_no="CASE-SYNTHETIC", plan_id=10, segment_id=None,
                           recipient_line_user_id=CUSTOMER.value, interaction_status="active",
                           expires_at_utc=NOW - timedelta(days=30), action_scope="customer_decision")
        self.events = {}

    def interaction(self, token):
        return self.action

    def get_contact_state(self, case_no, plan_id, *, lock=False):
        assert lock
        return self.state

    def append_response(self, **args):
        key = args["idempotency_key"].value
        if key in self.events:
            old, result = self.events[key]
            assert old["fingerprint"] == args["fingerprint"]
            return result
        plan = replace(self.state.plan, version=self.state.plan.version + 1)
        decision = CustomerMatchingDecision(args["response_value"])
        self.state = replace(self.state, plan=plan, customer_decision=decision)
        result = MatchingResponseResult(len(self.events) + 1, plan, args["source"],
                                        customer_decision=decision, idempotency_key=args["idempotency_key"])
        self.events[key] = (args, result)
        if args["token_hash"] is not None:
            self.action["interaction_status"] = "consumed"
        return result


class _Tickets:
    def __init__(self):
        self.messages = {}
        self.ticket = None

    def create_or_append(self, command):
        self.messages.setdefault(command.event_key, command)
        self.ticket = SimpleNamespace(ticket_id=55, category=command.category, case_no=command.case_no)
        return self.ticket

    def active_matching_assistance(self, line_user_id):
        assert line_user_id == CUSTOMER.value
        return self.ticket


class _Uow:
    def __init__(self):
        self.matching_notifications = _Repository()
        self.customer_service = _Tickets()
        self.deliveries = {}
        self.delivery_tasks = SimpleNamespace(enqueue=self.enqueue)
        self.runtime_monitor = SimpleNamespace(find_active_group_targets=self.group_forbidden)
        self.commits = 0

    def enqueue(self, request):
        self.deliveries.setdefault(request.idempotency_key.value, request)

    def group_forbidden(self, **kwargs):
        raise AssertionError("Recommendation responses must not look up notification groups")

    def __enter__(self):
        self.before = deepcopy((self.matching_notifications, self.customer_service, self.deliveries))
        return self

    def __exit__(self, kind, *_):
        if kind:
            self.matching_notifications, self.customer_service, self.deliveries = self.before

    def commit(self):
        self.commits += 1


def _app(uow):
    return MatchingNotificationApplication(lambda: uow, lambda: NOW, availability_validator=lambda _: None)


def _reply(uow, decision, key="one", user=CUSTOMER):
    return _app(uow).record_line_response(token="synthetic-recommendation-token", decision=decision,
        line_user_id=user, idempotency_key=IdempotencyKey(key), correlation_id=CorrelationId(key), occurred_at=NOW)


def test_assistance_then_acceptance_after_7_days_keeps_original_card_and_unique_staff_request():
    uow = _Uow()
    _reply(uow, "contact_requested")
    _reply(uow, "contact_requested")
    assert len(uow.customer_service.messages) == 1
    assert len(uow.deliveries) == 1
    assert uow.matching_notifications.action["interaction_status"] == "active"
    assert json.loads(next(iter(uow.deliveries.values())).payload_json)["text"] == "已收到您的聯絡需求，請留下您的疑問。"
    _reply(uow, "accepted", "two")
    assert uow.matching_notifications.state.customer_decision is CustomerMatchingDecision.ACCEPTED
    assert uow.matching_notifications.action["interaction_status"] == "consumed"
    assert len(uow.deliveries) == 2
    assert json.loads(list(uow.deliveries.values())[-1].payload_json)["text"] == "已收到您接受配對的回覆，後續由工會安排簽約。"
    with pytest.raises(MatchingCommunicationStaleError):
        _reply(uow, "accepted", "three")


def test_old_consumed_assistance_card_remains_usable_after_7_days():
    uow = _Uow()
    uow.matching_notifications.action["interaction_status"] = "consumed"
    uow.matching_notifications.state = replace(uow.matching_notifications.state, customer_decision=CustomerMatchingDecision.CONTACT_REQUESTED)
    assert _reply(uow, "accepted").customer_decision is CustomerMatchingDecision.ACCEPTED
    assert uow.matching_notifications.events["one"][0]["token_hash"] is None


def test_previously_time_expired_customer_card_can_accept_but_revoked_card_cannot():
    uow = _Uow()
    uow.matching_notifications.action["interaction_status"] = "expired"
    assert _reply(uow, "accepted").customer_decision is CustomerMatchingDecision.ACCEPTED
    uow = _Uow()
    uow.matching_notifications.action["interaction_status"] = "revoked"
    with pytest.raises(MatchingCommunicationStaleError):
        _reply(uow, "accepted")


@pytest.mark.parametrize("boundary,error", [
    ("recipient", MatchingRecipientMismatchError), ("binding", MatchingRecipientMismatchError),
    ("cancelled", MatchingCommunicationStaleError), ("inactive", MatchingCommunicationStaleError),
    ("closed", MatchingCommunicationStaleError), ("declined", MatchingCommunicationConflictError),
])
def test_time_does_not_block_but_current_identity_and_plan_still_do(boundary, error):
    uow = _Uow()
    repository = uow.matching_notifications
    if boundary == "recipient":
        repository.action["recipient_line_user_id"] = "U-other"
    elif boundary == "binding":
        repository.state = replace(repository.state, customer_line_user_id=LineUserId("U-other"))
    elif boundary == "cancelled":
        repository.action["interaction_status"] = "cancelled"
    elif boundary == "inactive":
        repository.state = replace(repository.state, plan_is_active=False)
    elif boundary == "closed":
        repository.state = replace(repository.state, order_status="已取消")
    else:
        repository.state = replace(repository.state, customer_decision=CustomerMatchingDecision.DECLINED)
    with pytest.raises(error):
        _reply(uow, "accepted")
    assert not uow.matching_notifications.events and not uow.deliveries and uow.commits == 0


def test_leaving_question_reuses_customer_service_ticket_without_auto_reply_or_group():
    uow = _Uow()
    _reply(uow, "contact_requested")
    uow.matching_schedule_confirmations = SimpleNamespace(confirm_line_rejection_reason=lambda *_: False)
    adapter = LineMatchingPostbackApplication(_app(uow))
    inbox = SimpleNamespace(event=SimpleNamespace(event_id=SimpleNamespace(value="question-1")))
    assert adapter.handle_message(inbox, uow, CUSTOMER, "請問月嫂是否有照顧雙胞胎的經驗？")
    message = uow.customer_service.messages["matching-assistance-message:question-1"]
    assert message.message == "請問月嫂是否有照顧雙胞胎的經驗？"
    assert message.case_no == "CASE-SYNTHETIC"
    assert len(uow.deliveries) == 1


def test_help_ticket_and_response_roll_back_when_acknowledgement_queue_fails(monkeypatch):
    uow = _Uow()
    def fail(_):
        raise RuntimeError("synthetic queue failure")
    monkeypatch.setattr(uow.delivery_tasks, "enqueue", fail)
    with pytest.raises(RuntimeError):
        _reply(uow, "contact_requested")
    assert not uow.matching_notifications.events
    assert not uow.customer_service.messages and uow.commits == 0


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def execute(self, sql, args):
        args = tuple(value.isoformat(" ") if isinstance(value, datetime) else value for value in args)
        self.result = self.connection.execute(sql.replace("%s", "?").replace("%%", "%").replace(" FOR UPDATE", ""), args)
    def fetchone(self):
        row = self.result.fetchone()
        return dict(row) if row else None
    @property
    def rowcount(self):
        return self.result.rowcount
    def fetchall(self):
        rows = [dict(row) for row in self.result.fetchall()]
        for row in rows:
            if isinstance(row.get("sent_at_utc"), str):
                row["sent_at_utc"] = datetime.fromisoformat(row["sent_at_utc"])
        return rows


@pytest.fixture
def followups():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.create_function("CONCAT", -1, lambda *args: "".join(map(str, args)))
    connection.executescript("""
    CREATE TABLE orders(case_no TEXT,status TEXT);
    CREATE TABLE caregiver_matching_plans(id INTEGER,case_no TEXT,is_active INTEGER,status TEXT);
    CREATE TABLE caregiver_matching_plan_segments(id INTEGER,plan_id INTEGER);
    CREATE TABLE matching_response_events(id INTEGER,plan_id INTEGER,response_type TEXT,response_value TEXT,occurred_at_utc TIMESTAMP);
    CREATE TABLE matching_notification_intents(plan_id INTEGER,notification_kind TEXT,delivery_task_id INTEGER);
    CREATE TABLE line_delivery_tasks(id INTEGER,processing_status TEXT,sent_at_utc TIMESTAMP);
    CREATE TABLE customer_service_tickets(id INTEGER,status TEXT DEFAULT 'waiting');
    CREATE TABLE customer_service_ticket_events(ticket_id INTEGER,event_key TEXT);
    CREATE TABLE contract_document_versions(id INTEGER,document_scope TEXT);
    CREATE TABLE contract_signing_events(document_version_id INTEGER,matching_plan_id INTEGER,matching_segment_id INTEGER,event_type TEXT);
    INSERT INTO orders VALUES('CASE-SYNTHETIC','洽談中');
    INSERT INTO caregiver_matching_plans VALUES(10,'CASE-SYNTHETIC',1,'proposed');
    INSERT INTO caregiver_matching_plan_segments VALUES(20,10);
    INSERT INTO matching_notification_intents VALUES(10,'customer_profiles',41);
    """)
    connection.execute("INSERT INTO line_delivery_tasks VALUES(41,'sent',?)", ((NOW - timedelta(days=7)).replace(tzinfo=None).isoformat(" "),))
    repository = MySqlMatchingNotificationRepository(SimpleNamespace(cursor=lambda: _Cursor(connection)))
    yield connection, lambda: repository.customer_recommendation_followups(NOW)
    connection.close()


def test_reminder_uses_actual_delivery_and_replaces_help_with_signing_until_both_sides_signed(followups):
    connection, query = followups
    assert query()[0].status == "reply_reminder"
    connection.execute("UPDATE line_delivery_tasks SET sent_at_utc=?", ((NOW - timedelta(days=6)).replace(tzinfo=None).isoformat(" "),))
    assert query() == ()
    connection.execute("INSERT INTO matching_response_events VALUES(1,10,'customer_decision','contact_requested',?)", (NOW.replace(tzinfo=None).isoformat(" "),))
    connection.execute("INSERT INTO customer_service_tickets(id) VALUES(55)")
    connection.execute("INSERT INTO customer_service_ticket_events VALUES(55,'matching-assistance:10:1')")
    assert query()[0].status == "contact_requested" and query()[0].ticket_id == 55
    connection.execute("INSERT INTO matching_response_events VALUES(2,10,'customer_decision','accepted',?)", (NOW.replace(tzinfo=None).isoformat(" "),))
    assert len(query()) == 1 and query()[0].status == "awaiting_signing"
    connection.executescript("INSERT INTO contract_document_versions VALUES(1,'client_contract'); INSERT INTO contract_signing_events VALUES(1,10,NULL,'signed_received');")
    assert query()[0].status == "awaiting_signing"
    connection.executescript("INSERT INTO contract_document_versions VALUES(2,'staff_segment'); INSERT INTO contract_signing_events VALUES(2,10,20,'signed_received');")
    assert query() == ()


@pytest.mark.parametrize("sql", [
    "UPDATE line_delivery_tasks SET processing_status='pending'",
    "UPDATE caregiver_matching_plans SET is_active=0",
    "UPDATE orders SET status='已取消'",
    "INSERT INTO matching_response_events VALUES(1,10,'customer_decision','declined','2026-10-22')",
])
def test_unsent_cancelled_replaced_or_declined_recommendations_do_not_create_reminders(followups, sql):
    connection, query = followups
    connection.execute(sql)
    assert query() == ()


def test_resolved_assistance_leaves_contact_todo_and_only_returns_when_reminder_is_due(followups):
    connection, query = followups
    connection.execute("UPDATE line_delivery_tasks SET sent_at_utc=?", ((NOW - timedelta(days=1)).replace(tzinfo=None).isoformat(' '),))
    connection.execute("INSERT INTO matching_response_events VALUES(1,10,'customer_decision','contact_requested',?)", (NOW.replace(tzinfo=None).isoformat(' '),))
    connection.execute("INSERT INTO customer_service_tickets VALUES(55,'waiting')")
    connection.execute("INSERT INTO customer_service_ticket_events VALUES(55,'matching-assistance:10:1')")
    assert query()[0].status == 'contact_requested'
    connection.execute("UPDATE customer_service_tickets SET status='resolved'")
    assert query() == ()
    connection.execute("UPDATE line_delivery_tasks SET sent_at_utc=?", ((NOW - timedelta(days=7)).replace(tzinfo=None).isoformat(' '),))
    assert len(query()) == 1 and query()[0].status == 'reply_reminder'


def test_recommendation_pages_cover_more_than_one_hundred_without_truncating_total(followups):
    connection, _ = followups
    for index in range(100):
        plan_id = 100 + index
        connection.execute("INSERT INTO orders VALUES (?,'洽談中')", (f'PUBLIC-{index:03d}',))
        connection.execute("INSERT INTO caregiver_matching_plans VALUES (?,?,1,'proposed')", (plan_id, f'PUBLIC-{index:03d}'))
        connection.execute("INSERT INTO matching_notification_intents VALUES (?,'customer_profiles',41)", (plan_id,))
    repository = MySqlMatchingNotificationRepository(SimpleNamespace(cursor=lambda: _Cursor(connection)))
    seen = []
    for page in range(5):
        assert repository.customer_recommendation_followup_count(NOW) == 101
        items = repository.customer_recommendation_followups(NOW, limit=25, offset=page * 25)
        seen.extend(item.plan_id for item in items)
    assert len(seen) == len(set(seen)) == 101
    assert repository.customer_recommendation_followups(NOW, limit=25, offset=125) == ()


def test_question_routing_only_uses_the_requesters_open_assistance_ticket():
    from infrastructure.mysql.customer_service_repository import MySqlCustomerServiceRepository
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
    CREATE TABLE customer_service_tickets(id INTEGER,line_user_id TEXT,category TEXT,status TEXT,version INTEGER,case_no TEXT);
    CREATE TABLE customer_service_ticket_events(ticket_id INTEGER,event_key TEXT);
    INSERT INTO customer_service_tickets VALUES(1,'U-synthetic-customer','other','waiting',1,'CASE-SYNTHETIC');
    INSERT INTO customer_service_ticket_events VALUES(1,'matching-assistance:10:1');
    INSERT INTO customer_service_tickets VALUES(2,'U-other','other','waiting',1,'OTHER');
    INSERT INTO customer_service_ticket_events VALUES(2,'matching-assistance:11:2');
    """)
    try:
        repository = MySqlCustomerServiceRepository(SimpleNamespace(cursor=lambda: _Cursor(connection)))
        assert repository.active_matching_assistance(CUSTOMER.value).ticket_id == 1
        assert repository.active_matching_assistance("U-unrelated") is None
        connection.execute("UPDATE customer_service_tickets SET status='resolved' WHERE id=1")
        assert repository.active_matching_assistance(CUSTOMER.value) is None
    finally:
        connection.close()


def test_ticket_failure_rolls_back_response_and_queued_acknowledgement(monkeypatch):
    uow = _Uow()
    def fail(_):
        raise RuntimeError("synthetic ticket failure")
    monkeypatch.setattr(uow.customer_service, "create_or_append", fail)
    with pytest.raises(RuntimeError):
        _reply(uow, "contact_requested")
    assert not uow.matching_notifications.events and not uow.deliveries and uow.commits == 0


@pytest.mark.parametrize("scope,status,allowed", [
    ("customer_decision", "expired", True), ("customer_decision", "active", True),
    ("customer_decision", "revoked", False), ("caregiver_willingness", "expired", False),
])
def test_actual_consume_sql_allows_time_expired_customer_action_only(scope, status, allowed):
    connection = sqlite3.connect(":memory:")
    connection.executescript("CREATE TABLE matching_line_interactions(token_hash TEXT,action_scope TEXT,interaction_status TEXT,consumed_at_utc TEXT,consumed_by_line_user_id TEXT);")
    connection.execute("INSERT INTO matching_line_interactions VALUES('token',?,?,NULL,NULL)", (scope, status))
    repository = MySqlMatchingNotificationRepository(SimpleNamespace(cursor=lambda: _Cursor(connection)))
    try:
        if allowed:
            repository._consume_interaction("token", CUSTOMER, NOW)
            assert connection.execute("SELECT interaction_status FROM matching_line_interactions").fetchone()[0] == "consumed"
        else:
            with pytest.raises(MatchingCommunicationConflictError):
                repository._consume_interaction("token", CUSTOMER, NOW)
    finally:
        connection.close()
