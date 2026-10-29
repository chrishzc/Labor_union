"""Execute the real reminder SQL and reader transport against isolated owner facts."""
from contextlib import contextmanager
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_customer_service_reader
from api.routes import customer_service as routes
from api.schemas.customer_service import CustomerServiceReminderPageView
from infrastructure.mysql.customer_service_repository import MySqlCustomerServiceRepository
from subsystems.customer_service.application import CustomerServiceApplication
from subsystems.customer_service.contracts import CustomerServiceReminderQuery, CustomerServiceReminderSource


class ReadConnection:
    def __init__(self, db):
        self.db = db
        self.statements = []

    @contextmanager
    def cursor(self):
        cursor = self.db.cursor()
        connection = self

        class Cursor:
            def execute(self, sql, params=()):
                assert sql.lstrip().upper().startswith("SELECT"), "reminder attempted a write"
                connection.statements.append((sql, params))
                cursor.execute(sql.replace("%s", "?"), params)

            def fetchone(self):
                row = cursor.fetchone()
                return dict(row) if row is not None else None

            def fetchall(self):
                return [dict(row) for row in cursor.fetchall()]

        yield Cursor()
        cursor.close()

    def commit(self):
        raise AssertionError("reminder must not commit")


@pytest.fixture
def facts():
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE clients(id INTEGER PRIMARY KEY,name TEXT);
    CREATE TABLE admin_users(id INTEGER PRIMARY KEY,display_name TEXT);
    CREATE TABLE customer_service_tickets(id INTEGER PRIMARY KEY,client_id INTEGER,case_no TEXT,status TEXT,assigned_to_admin_user_id INTEGER,updated_at_utc TEXT,version INTEGER DEFAULT 0,line_user_id TEXT,created_at_utc TEXT);
    CREATE TABLE customer_service_ticket_events(id INTEGER PRIMARY KEY,ticket_id INTEGER,event_key TEXT,event_type TEXT,message_text TEXT);
    CREATE TABLE customer_service_escalations(id INTEGER PRIMARY KEY,ticket_id INTEGER,source_event_identity TEXT,trigger_code TEXT,workflow_status TEXT,urgency TEXT);
    INSERT INTO clients VALUES(1,'測試客戶');
    INSERT INTO admin_users VALUES(7,'測試專員');
    """)
    for ticket_id, status in enumerate(("waiting", "waiting", "waiting", "handling", "handling", "waiting", "waiting", "handling", "resolved"), 1):
        db.execute("INSERT INTO customer_service_tickets(id,client_id,case_no,status,assigned_to_admin_user_id,updated_at_utc) VALUES(?,?,?,?,?,?)", (ticket_id, 1, f"ORD-TEST-{ticket_id:03}", status, 7 if status == "handling" else None, "2026-10-15T02:00:00Z"))
    events = [
        (1, 1, "line-service-help:other:a"), (2, 2, "line-complaint:b"),
        (3, 3, "line-feedback-ticket:c"), (4, 4, "line-order-change:d"),
        (5, 5, "line-service-help:contact_union:e"), (6, 6, "binding-failure:f:0"),
        (7, 7, "legacy-event"), (8, 8, "line-feedback-ticket:g"),
        (9, 8, "line-service-help:other:h"), (10, 8, "line-service-help:active-hold:i"),
        (11, 9, "line-complaint:closed"),
    ]
    for event_id, ticket_id, key in events:
        db.execute("INSERT INTO customer_service_ticket_events VALUES(?,?,?,?,?)", (event_id, ticket_id, key, "customer_message", "後續客戶留言" if "active-hold" in key else "我要客訴：原文不可成為來源判定或進入提醒回應"))
    db.executemany("INSERT INTO customer_service_escalations VALUES(?,?,?,?,?,?)", [
        (1, 1, "line-service-help:other:a", "explicit_human_request", "open", "high"),
        (2, 2, "line-complaint:b", "complaint", "open", "high"),
        (3, 6, "binding-failure:f:0", "binding_failure_threshold_2", "open", "high"),
        (4, 8, "line-service-help:other:h", "explicit_wrong_answer", "resolved", "high"),
    ])
    connection = ReadConnection(db)
    repository = MySqlCustomerServiceRepository(connection)
    yield db, connection, repository
    db.close()


def test_real_sql_projects_sources_and_priority_without_raw_content(facts):
    _, connection, repository = facts
    result = repository.list_reminders(CustomerServiceReminderQuery())
    assert result.total == 8
    assert (result.summary.waiting, result.summary.handling) == (5, 3)
    items = {item.ticket_id: item for item in result.items}
    assert {key: item.source.value for key, item in items.items()} == {
        1: "handoff", 2: "complaint", 3: "feedback", 4: "order", 5: "service", 6: "binding", 7: "unknown", 8: "handoff",
    }
    assert items[8].reason == "explicit_wrong_answer"
    assert set(items[8].sources) == {CustomerServiceReminderSource.HANDOFF, CustomerServiceReminderSource.FEEDBACK}
    assert not items[8].is_priority  # historical resolved escalation is not current urgency
    assert items[1].is_priority and items[2].is_priority and items[6].is_priority
    assert items[5].assigned_admin_name == "測試專員"
    payload = CustomerServiceReminderPageView.model_validate(result).model_dump_json()
    for forbidden in ("line_user_id", "message_text", "event_key", "fingerprint", "我要客訴", "internal_note"):
        assert forbidden not in payload
    assert len(connection.statements) == 4  # fixed reads, not one request per ticket


def test_start_day_group_assistance_appears_in_union_service_todos(facts):
    db, connection, repository = facts
    db.execute("INSERT INTO customer_service_ticket_events VALUES(12,7,?,'customer_message','服務開始日協助需求')",
               ('start-day-response:'+'0'*64+':U_SYNTHETIC:help',))
    result=repository.list_reminders(CustomerServiceReminderQuery(source=CustomerServiceReminderSource.SERVICE))
    item=next(item for item in result.items if item.ticket_id==7)
    assert item.source is CustomerServiceReminderSource.SERVICE
    assert item.reason=='service_referral'


@pytest.mark.parametrize("source, expected", [("feedback", {3, 8}), ("handoff", {1, 8}), ("unknown", {7}), ("order", {4})])
def test_source_filters_match_any_proven_origin_and_do_not_duplicate_tickets(facts, source, expected):
    _, _, repository = facts
    result = repository.list_reminders(CustomerServiceReminderQuery(source=CustomerServiceReminderSource(source)))
    assert result.total == len(expected)
    assert {item.ticket_id for item in result.items} == expected


def test_open_status_has_true_count_and_server_pagination_beyond_one_page(facts):
    db, connection, repository = facts
    for ticket_id in range(10, 41):
        db.execute("INSERT INTO customer_service_tickets(id,client_id,case_no,status,assigned_to_admin_user_id,updated_at_utc) VALUES(?,NULL,?,'waiting',NULL,?)", (ticket_id, f"ORD-PAGE-{ticket_id}", "2026-10-15T02:00:00Z"))
    first = repository.list_reminders(CustomerServiceReminderQuery(page_size=25))
    second = repository.list_reminders(CustomerServiceReminderQuery(page=2, page_size=25))
    assert first.total == second.total == 39
    assert len(first.items) == 25 and len(second.items) == 14
    assert not {x.ticket_id for x in first.items} & {x.ticket_id for x in second.items}
    assert all(x.status != "resolved" for x in (*first.items, *second.items))
    assert all(len(args) <= 25 for sql, args in connection.statements if "e.ticket_id IN" in sql)
    waiting = repository.list_reminders(CustomerServiceReminderQuery(status="waiting"))
    assert waiting.total == 36
    assert all(x.status == "waiting" for x in waiting.items)


def test_search_and_unknown_source_do_not_infer_from_category_or_message(facts):
    _, _, repository = facts
    result = repository.list_reminders(CustomerServiceReminderQuery(search="ORD-TEST-007"))
    assert result.total == 1 and result.items[0].source is CustomerServiceReminderSource.UNKNOWN
    assert repository.list_reminders(CustomerServiceReminderQuery(search="#8")).items[0].ticket_id == 8


def test_application_query_does_not_commit_or_enqueue(facts):
    _, _, repository = facts
    @contextmanager
    def factory():
        yield SimpleNamespace(customer_service=repository)  # no writer or provider port available
    result = CustomerServiceApplication(factory).reminders(CustomerServiceReminderQuery())
    assert len(result.items) == 8


def test_reader_route_is_bounded_and_preserves_existing_endpoints(facts, monkeypatch):
    _, _, repository = facts
    @contextmanager
    def factory():
        yield SimpleNamespace(customer_service=repository)
    monkeypatch.setattr(routes, "_application", lambda: CustomerServiceApplication(factory))
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_customer_service_reader] = lambda: SimpleNamespace()
    with TestClient(app) as client:
        response = client.get("/api/v1/customer-service/tickets/reminders?source=feedback&page_size=1")
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 2
        assert len(response.json()["data"]["items"]) == 1
        for invalid in ("status=resolved", "source=arbitrary", "page=0", "page_size=101", "user_id=identity"):
            assert client.get(f"/api/v1/customer-service/tickets/reminders?{invalid}").status_code == 422
    assert "/api/v1/customer-service/tickets/{ticket_id}/reply/apply" in app.openapi()["paths"]


def test_reader_route_requires_authorization(monkeypatch):
    monkeypatch.setenv('ENABLE_ADMIN_AUTH', 'true')
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        assert client.get("/api/v1/customer-service/tickets/reminders").status_code in (401, 403)


def test_profile_names_and_request_time_are_bounded_read_only_projections(facts):
    db, connection, repository = facts
    db.execute("UPDATE customer_service_tickets SET line_user_id='U_PROFILE_SYNTHETIC',version=3,created_at_utc='2026-10-15T01:00:00Z' WHERE id IN (1,2)")
    calls = []
    @contextmanager
    def factory():
        yield SimpleNamespace(customer_service=repository)
    def profiles(ids):
        calls.append(ids)
        return {'U_PROFILE_SYNTHETIC': '真實 LINE 名稱'}
    result=CustomerServiceApplication(factory,display_names=profiles).reminders(CustomerServiceReminderQuery())
    assert calls==[('U_PROFILE_SYNTHETIC',)]
    items={row.ticket_id:row for row in result.items}
    assert items[1].line_display_name=='真實 LINE 名稱'
    assert items[1].version==3 and str(items[1].requested_at).startswith('2026-10-15')
    assert items[8].messages==('後續客戶留言',)
    assert items[2].messages==()  # masked complaint is not re-exposed
    payload=CustomerServiceReminderPageView.model_validate(result).model_dump_json()
    assert 'U_PROFILE_SYNTHETIC' not in payload
    assert '真實 LINE 名稱' in payload


def test_profile_reader_only_uses_get_and_rejects_wrong_identity():
    from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
    class Session:
        def __init__(self):self.calls=[]
        def get(self,url,**kwargs):
            self.calls.append(url)
            return SimpleNamespace(status_code=200,json=lambda:{'userId':'U_OTHER','displayName':'不應顯示'})
    session=Session()
    assert LineMessagingApiAdapter('synthetic-token',session=session).display_names(('U_TEST','U_TEST'))=={'U_TEST':None}
    assert session.calls==['https://api.line.me/v2/bot/profile/U_TEST']


def test_profile_page_budget_skips_queued_requests_after_deadline(monkeypatch):
    from infrastructure.line import messaging_api_adapter as adapter
    ticks = iter((0.0, 3.0))
    monkeypatch.setattr(adapter.time, 'monotonic', lambda: next(ticks))
    # The supplied object deliberately has no GET method: expired work must not call it.
    assert adapter.LineMessagingApiAdapter('synthetic-token', session=object(), timeout_seconds=2).display_names(('U_TEST',)) == {'U_TEST': None}


@pytest.mark.parametrize('workflow', ['open','claimed','handling'])
def test_completion_releases_hold_with_one_commit_no_push_and_replay(workflow):
    from dataclasses import replace
    from domains.customer_service.ticket import CustomerServiceTicket,CustomerServiceStatus,CustomerServiceCategory
    from shared_kernel.identities import CorrelationId,ExpectedVersion,IdempotencyKey
    from subsystems.customer_service.contracts import PreviewCustomerServiceTicketUpdate,ApplyCustomerServiceTicketUpdate
    calls=[]
    class Tickets:
        row=CustomerServiceTicket(1,'U_SYNTHETIC',CustomerServiceCategory.OTHER,CustomerServiceStatus.WAITING,2)
        def get(self,ticket_id,lock=False):
            if lock:calls.append('ticket-lock')
            return self.row
        def append_management_event(self,*args):pass
        def update(self,ticket_id,version,status,note,admin):
            assert version==self.row.version
            self.row=replace(self.row,status=status,version=version+1)
            return self.row
        def detail(self,ticket_id):return {'ticket':{'status':self.row.status.value,'version':self.row.version},'events':[]}
    class Escalations:
        def __init__(self):
            self.row={'id':7,'ticket_id':1,'workflow_status':workflow,'workflow_version':0,'hold_version':0,'trigger_code':'explicit_human_request','hold_state':'active'}
            self.events=[]
        def active_for_ticket(self,ticket_id):calls.append('escalation-lock');return (self.row,)
        def transition(self,escalation_id,**changes):self.row.update(changes);return self.row
        def append_event(self,*args,**kwargs):self.events.append((args,kwargs))
    class Receipts:
        def __init__(self):self.rows={}
        def get(self,key):return self.rows.get(key)
        def append(self,receipt):self.rows[receipt.key]=receipt
    class Uow:
        def __init__(self):
            self.customer_service=Tickets();self.escalations=Escalations();self.receipts=Receipts();self.audit=[];self.commits=0
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def commit(self):self.commits+=1
    uow=Uow();app=CustomerServiceApplication(lambda:uow)
    preview=app.preview_update(PreviewCustomerServiceTicketUpdate(1,CustomerServiceStatus.RESOLVED,None,ExpectedVersion(2),CorrelationId('complete')))
    command=ApplyCustomerServiceTicketUpdate(1,CustomerServiceStatus.RESOLVED,None,ExpectedVersion(2),preview.preview_fingerprint,'admin:7',IdempotencyKey('complete'),CorrelationId('complete'))
    result=app.apply_update(command)
    assert result.resulting_status is CustomerServiceStatus.RESOLVED
    assert calls[:2]==['escalation-lock','ticket-lock']
    assert uow.escalations.row['workflow_status']=='resolved' and uow.escalations.row['hold_state']=='released'
    assert uow.escalations.row['hold_version']==1
    assert uow.commits==1  # no delivery port exists; any Push attempt fails the test
    assert len(uow.escalations.events)=={'open':4,'claimed':3,'handling':2}[workflow]
    assert app.apply_update(command).replayed is True and uow.commits==1
