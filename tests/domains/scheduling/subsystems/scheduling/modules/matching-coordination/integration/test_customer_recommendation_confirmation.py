"""Customer assistance retains acceptance; reminders never expire a recommendation."""
from copy import deepcopy
from hashlib import sha256
import re
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import matches
from domains.line.identities import LineSourceType, LineUserId
from domains.orders.terms import ServiceTimeTerms
from domains.scheduling.matching_communication import (
    CaregiverWillingness, CustomerMatchingDecision, MatchingCommunicationConflictError,
    MatchingCommunicationStaleError, MatchingPlanReference, MatchingRecipientMismatchError,
)
from infrastructure.mysql.matching_notification_repository import MySqlMatchingNotificationRepository
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.line.matching_postback_application import LineMatchingPostbackApplication
from subsystems.line.webhook_event_consumer import TerminalLineEventError
from subsystems.scheduling.matching_notification_application import (
    MatchingNotificationApplication, MatchingOccupancyConflictError, MatchingOccupancyTimePendingError,
)
from subsystems.scheduling.matching_notification_contracts import (
    MatchingContactState, MatchingResponseResult, MatchingSegmentContact, RequestCustomerProfilesCommand,
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

    def interaction(self, token, *, lock=True):
        return self.action

    def get_contact_state(self, case_no, plan_id, *, lock=False):
        return self.state

    def pending_customer_assistance(self, *_args):
        return False

    def customer_confirmation_snapshot(self, *_args):
        return None

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


def _postback(decision, event_id="customer-event"):
    data = f"matching:synthetic-recommendation-token:{decision}"
    return SimpleNamespace(event=SimpleNamespace(
        source=SimpleNamespace(source_type=LineSourceType.USER, user_id=CUSTOMER),
        occurred_at=NOW, event_id=SimpleNamespace(value=event_id),
        payload_json=json.dumps({"postback": {"data": data}}),
    ))


@pytest.mark.parametrize(("decision", "text"), [
    ("accepted", "已收到您接受配對的回覆，後續由工會安排簽約。"),
    ("contact_requested", "已收到您的聯絡需求，請留下您的疑問"),
])
def test_customer_receipt_defers_business_and_background_never_adds_reply(decision, text):
    uow = _Uow()
    handler = LineMatchingPostbackApplication(_app(uow))
    event = _postback(decision)
    assert handler.handle(event, uow, reply_only=True) is False
    assert handler.handle(event, uow, reply_only=True) is False
    assert uow.matching_notifications.events == {}
    assert uow.customer_service.messages == {}
    [reply] = uow.deliveries.values()
    assert reply.source_aggregate_type == "line_webhook_reply"
    assert json.loads(reply.payload_json)["text"] == text
    assert handler.handle(event, uow) is True
    assert uow.matching_notifications.state.customer_decision.value == decision
    assert len(uow.deliveries) == 1
    assert len(uow.customer_service.messages) == (1 if decision == "contact_requested" else 0)


@pytest.mark.parametrize("error_type,message", [
    (MatchingOccupancyConflictError,
     "正式方案中的月嫂目前檔期已有衝突：測試月嫂（服務班次）2026-11-03 09:00 至 2026-11-03 17:00。請重新確認。"),
    (MatchingOccupancyTimePendingError, "時段待確認：既有占用缺少可追溯的服務時段，請核對月嫂檔期。"),
])
def test_background_conflict_preserves_receipt_without_accepting_or_adding_reply(error_type, message):
    uow = _Uow()
    def occupied(_state):
        raise error_type(message)
    application = MatchingNotificationApplication(lambda: uow, lambda: NOW, availability_validator=occupied)
    handler = LineMatchingPostbackApplication(application)
    event = _postback("accepted")
    assert handler.handle(event, uow, reply_only=True) is False
    with pytest.raises(TerminalLineEventError, match=f"^{re.escape(message)}$"):
        handler.handle(event, uow)
    assert uow.matching_notifications.state.customer_decision is CustomerMatchingDecision.PENDING
    assert uow.matching_notifications.events == {}
    assert len(uow.deliveries) == 1


def test_background_cannot_accept_a_package_after_its_customer_terms_changed():
    uow = _Uow()
    original = {"order_information_1": ({"payment": 48000},), "order_information_2": (), "weekly_service_rows": ()}
    uow.matching_notifications.customer_confirmation_snapshot = lambda *_: original
    uow.matching_notifications.customer_confirmation_package = lambda *_: {
        **original, "order_information_1": ({"payment": 52000},),
    }
    handler = LineMatchingPostbackApplication(_app(uow))
    event = _postback("accepted")
    assert handler.handle(event, uow, reply_only=True) is False
    with pytest.raises(TerminalLineEventError, match="客戶確認內容已變更"):
        handler.handle(event, uow)
    assert uow.matching_notifications.events == {}
    assert len(uow.deliveries) == 1


@pytest.mark.parametrize("scenario,expected_hint", [
    ("occupancy", "測試月嫂（服務班次）2026-11-03 11:00 至 2026-11-03 15:00"),
    ("unknown_time", "時段待確認"),
    ("date_mismatch", "正式方案日期或分段與目前案件服務日期不一致，請重新確認服務日期與分段。"),
])
def test_customer_confirmation_http_preview_and_send_share_blocker(monkeypatch, scenario, expected_hint):
    uow = _Uow()
    repository = uow.matching_notifications
    plan = repository.state.plan
    repository.get_intent_result = lambda *args, **kwargs: None
    repository.customer_confirmation_package = lambda *args: pytest.fail("blocked confirmation cannot build a package")
    repository.customer_confirmation_preview = lambda *args: {
        "order_information_1_ready": True, "order_information_2_ready": True,
        "weekly_service_ready": True, "weekly_service_row_count": 1,
        "order_information_1": (), "order_information_2": (), "weekly_service_rows": (),
        "caregiver_resumes": ({"staff_id": 30, "staff_name": "測試月嫂", "ready": True,
                               "filename": "synthetic.pdf", "version": 1, "blocker": None},),
        "blockers": (),
    }
    day = "2026-11-03"
    schedule_rows = []
    if scenario != "date_mismatch":
        occupied_time = ServiceTimeTerms(time(11), time(15), 0) if scenario == "occupancy" else None
        schedule_rows.append({
            "assignment_id": 9, "staff_id": 30, "work_date": day, "service_time": occupied_time,
        })
    facts = SimpleNamespace(load_case_facts=lambda _: {
        "order": {"case_no": plan.case_no, "status": "洽談中", "start_date": day, "end_date": day,
                  "service_days": 2 if scenario == "date_mismatch" else 1,
                  "service_time": ServiceTimeTerms(time(8), time(12), 0)},
        "confirmed_service_dates": [{"service_date": day}],
        "staff_rows": [{"id": 30, "name": "測試月嫂"}],
        "schedule_rows": schedule_rows,
        "assignments": [], "legacy_schedule_rows": [], "buffer_rows": [],
        "active_lock_rows": [], "waiting_buffer_rows": [],
    })
    application = MatchingNotificationApplication(lambda: uow, lambda: NOW, availability_facts_port=facts)
    monkeypatch.setattr(matches, "matching_notifications", application)
    principal = SimpleNamespace(
        id=1, username="operator",
        effective_capabilities=lambda: frozenset({"line.matching.read", "line.matching.send"}),
    )
    api = FastAPI()
    api.include_router(matches.router)
    api.dependency_overrides[matches.require_line_matching_reader] = lambda: principal
    api.dependency_overrides[matches.require_line_matching_sender] = lambda: principal
    path = f"/api/v1/orders/{plan.case_no}/matching-plans/{plan.plan_id}/customer-confirmation"
    with TestClient(api) as client:
        preview = client.get(f"{path}/preview", params={"expected_version": plan.version})
        send = client.post(path, json={
            "actor": "operator", "note": "確認資訊", "expected_version": plan.version, "event_key": "blocked",
        })

    assert preview.status_code == 200, preview.text
    data = preview.json()["data"]
    [blocker] = data["blockers"]
    assert expected_hint in blocker
    assert data["send_allowed"] is False
    assert send.status_code == 409, send.text
    assert send.json()["detail"] == blocker
    assert uow.deliveries == {} and uow.commits == 0


def test_background_accepts_a_package_after_only_its_resume_changed():
    uow = _Uow()
    original = {"confirmation_reference": "sent", "order_information_1": (),
                "order_information_2": (), "weekly_service_rows": (),
                "caregiver_resumes": ({"staff_id": 30, "file_id": "cf_previous"},)}
    uow.matching_notifications.customer_confirmation_snapshot = lambda *_: original
    uow.matching_notifications.customer_confirmation_package = lambda *_: {
        **original, "caregiver_resumes": ({"staff_id": 30, "file_id": "cf_current"},),
    }
    handler = LineMatchingPostbackApplication(_app(uow))
    event = _postback("accepted")
    assert handler.handle(event, uow, reply_only=True) is False
    handler.handle(event, uow)
    assert uow.matching_notifications.state.customer_decision is CustomerMatchingDecision.ACCEPTED
    assert len(uow.matching_notifications.events) == 1
    assert len(uow.deliveries) == 1


def test_revoked_package_cannot_acknowledge_or_commit_acceptance():
    uow = _Uow()
    uow.matching_notifications.action["interaction_status"] = "revoked"
    handler = LineMatchingPostbackApplication(_app(uow))
    event = _postback("accepted")
    assert handler.handle(event, uow, reply_only=True) is True
    with pytest.raises(TerminalLineEventError, match="no longer active"):
        handler.handle(event, uow)
    assert not uow.deliveries and not uow.matching_notifications.events


def test_resend_uses_current_snapshot_and_replay_does_not_revoke_again(monkeypatch):
    uow = _Uow()
    repository = uow.matching_notifications
    receipts = {}
    revocations = []
    repository.get_intent_result = lambda key, fingerprint, **_: receipts.get((key.value, fingerprint))
    repository.revoke_customer_interactions = revocations.append
    snapshots = []
    current = {"fee": 48000}
    repository.customer_confirmation_package = lambda *_: {
        "profiles": ({"id": 30},), "order_information_1": ({"fee": current["fee"]},),
        "order_information_2": (), "weekly_service_rows": (), "caregiver_resumes": ({"staff_id": 30, "file_id": "cf_demo"},),
    }
    app = _app(uow)
    rendered = []
    app._resume_page_renderer = lambda file, budget: rendered.append((file, budget)) or (b"page",)
    def append(_unit, command, _recipient, _segment, _kind, snapshot, *_args, resume_pages):
        assert resume_pages == (b"page",)
        snapshots.append(snapshot)
        receipt = object()
        receipts[command.idempotency_key.value, command.fingerprint.value] = receipt
        return receipt
    monkeypatch.setattr(app, "_append_notification", append)
    def command(key):
        return RequestCustomerProfilesCommand(repository.state.plan, "確認資訊",
            ActorContext("admin:1", ("line.matching.send",)),
            ExpectedVersion(0), IdempotencyKey(key), CorrelationId(key))
    original = app.request_customer_confirmation(command("original"))
    current["fee"] = 52000
    assert app.request_customer_confirmation(command("original")) is original
    assert app.request_customer_confirmation(command("updated")) is not original
    assert [snapshot["order_information_1"][0]["fee"] for snapshot in snapshots] == [48000, 52000]
    assert revocations == [10, 10]
    assert rendered == [("cf_demo", 4), ("cf_demo", 4)]
    original_package = repository.customer_confirmation_package
    repository.customer_confirmation_package = lambda *args: {**original_package(*args), "caregiver_resumes": ()}
    with pytest.raises(ValueError, match="皆須上傳履歷 PDF"):
        app.request_customer_confirmation(command("missing-resume"))
    assert revocations == [10, 10] and len(snapshots) == 2
    repository = uow.matching_notifications
    repository.state = replace(repository.state, customer_decision=CustomerMatchingDecision.ACCEPTED)
    with pytest.raises(MatchingCommunicationConflictError, match="already decided"):
        app.request_customer_confirmation(command("after-acceptance"))


def test_assistance_then_acceptance_after_7_days_keeps_original_card_and_unique_staff_request():
    uow = _Uow()
    _reply(uow, "contact_requested")
    _reply(uow, "contact_requested")
    assert len(uow.customer_service.messages) == 1
    assert len(uow.deliveries) == 1
    assert uow.matching_notifications.action["interaction_status"] == "active"
    assert json.loads(next(iter(uow.deliveries.values())).payload_json)["text"] == "已收到您的聯絡需求，請留下您的疑問"
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
    inbox = SimpleNamespace(event=SimpleNamespace(event_id=SimpleNamespace(value="question-1"), occurred_at=NOW))
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
    connection.create_function("REGEXP", 2, lambda pattern, value: bool(value and re.search(pattern, value)))
    connection.create_function("SHA2", 2, lambda value, _: sha256(value.encode()).hexdigest() if value else None)
    connection.create_function("JSON_UNQUOTE", 1, lambda value: value)
    connection.create_function("SUBSTRING_INDEX", 3, lambda value, separator, count:
        separator.join(value.split(separator)[:count] if count > 0 else value.split(separator)[count:]) if value else None)
    connection.executescript("""
    CREATE TABLE orders(case_no TEXT,status TEXT);
    CREATE TABLE caregiver_matching_plans(id INTEGER,case_no TEXT,is_active INTEGER,status TEXT);
    CREATE TABLE caregiver_matching_plan_segments(id INTEGER,plan_id INTEGER);
    CREATE TABLE matching_response_events(id INTEGER,plan_id INTEGER,response_type TEXT,response_value TEXT,occurred_at_utc TIMESTAMP);
    CREATE TABLE matching_notification_intents(plan_id INTEGER,notification_kind TEXT,delivery_task_id INTEGER);
    CREATE TABLE line_delivery_tasks(id INTEGER,processing_status TEXT,sent_at_utc TIMESTAMP);
    CREATE TABLE matching_line_interactions(plan_id INTEGER,recipient_line_user_id TEXT,token_hash TEXT,action_scope TEXT,interaction_status TEXT);
    CREATE TABLE line_inbox_events(id INTEGER,source_user_id TEXT,event_type TEXT,payload_snapshot TEXT,processing_status TEXT,error_message TEXT);
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


@pytest.mark.parametrize("inbox_error,expected_hint", [
    ("automatic_waiting_deposit_occupancy_conflict", "檔期已被占用"),
    ("正式方案中的月嫂目前檔期已有衝突，請重新確認。", "檔期已被占用"),
    ("正式方案中的月嫂目前檔期已有衝突：測試月嫂（服務班次）2026-11-03 09:00 至 2026-11-03 17:00。請重新確認。",
     "測試月嫂（服務班次）2026-11-03 09:00 至 2026-11-03 17:00"),
    ("時段待確認：既有占用缺少可追溯的服務時段，請核對月嫂檔期。", "時段待確認"),
    ("正式方案日期或分段與目前案件服務日期不一致，請重新確認服務日期與分段。", "重新確認服務日期與分段"),
])
def test_failed_customer_response_is_an_immediate_staff_todo(followups, inbox_error, expected_hint):
    connection, query = followups
    connection.execute("UPDATE line_delivery_tasks SET sent_at_utc=?", ((NOW - timedelta(days=1)).replace(tzinfo=None).isoformat(" "),))
    token = "synthetic-recommendation-token"
    connection.execute("INSERT INTO matching_line_interactions VALUES(10,?,?,'customer_decision','active')",
                       (CUSTOMER.value, sha256(token.encode()).hexdigest()))
    payload = json.dumps({"postback": {"data": f"matching:{token}:accepted"}})
    connection.execute("INSERT INTO line_inbox_events VALUES(1,?,'postback',?,'terminal_failed',?)",
                       (CUSTOMER.value, payload, inbox_error))
    [todo] = query()
    assert todo.status == "response_failed"
    assert expected_hint in todo.failure_reason
    connection.execute("UPDATE matching_line_interactions SET interaction_status='revoked'")
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


def test_resend_replaces_only_target_customer_actions_and_sent_pdf_is_recipient_scoped():
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.create_function("JSON_UNQUOTE", 1, lambda value: value)
        connection.executescript("""
        CREATE TABLE matching_line_interactions(
            token_hash TEXT, plan_id INTEGER, segment_id INTEGER, action_scope TEXT,
            recipient_line_user_id TEXT, expires_at_utc TEXT, interaction_status TEXT DEFAULT 'active'
        );
        CREATE TABLE matching_notification_intents(
            plan_id INTEGER, notification_kind TEXT, recipient_line_user_id TEXT,
            payload_snapshot TEXT, delivery_task_id INTEGER
        );
        CREATE TABLE line_delivery_tasks(id INTEGER, processing_status TEXT);
        INSERT INTO line_delivery_tasks VALUES (1,'sent'),(2,'pending');
        """)
        repository = MySqlMatchingNotificationRepository(SimpleNamespace(cursor=lambda: _Cursor(connection)))
        for token, plan_id, scope in (("old", 10, "customer_decision"),
                                      ("caregiver", 10, "caregiver_willingness"),
                                      ("other", 11, "customer_decision")):
            repository.open_interaction(token_hash=token, plan_id=plan_id, segment_id=None,
                                        action_scope=scope, recipient=CUSTOMER, expires_at=NOW)
        repository.revoke_customer_interactions(10)
        repository.open_interaction(token_hash="new", plan_id=10, segment_id=None,
                                    action_scope="customer_decision", recipient=CUSTOMER, expires_at=NOW)
        statuses = dict(connection.execute("SELECT token_hash, interaction_status FROM matching_line_interactions"))
        assert statuses == {"old": "revoked", "caregiver": "active", "other": "active", "new": "active"}
        for task, ref, file_id in ((1, "old", "old-pdf"), (2, "new", "new-pdf")):
            snapshot = {("resume_reference" if ref == "old" else "confirmation_reference"): ref, "caregiver_resumes": [{"staff_id": 30, "file_id": file_id}]}
            connection.execute("INSERT INTO matching_notification_intents VALUES (10,'customer_profiles',?,?,?)",
                               (CUSTOMER.value, json.dumps(snapshot), task))
        assert repository.customer_confirmation_snapshot(10, "new", CUSTOMER)["caregiver_resumes"][0]["file_id"] == "new-pdf"
        assert repository.customer_confirmation_snapshot(10, "old", CUSTOMER)["caregiver_resumes"][0]["file_id"] == "old-pdf"
        assert repository.customer_confirmation_snapshot(10, "new", LineUserId("U-other")) is None
