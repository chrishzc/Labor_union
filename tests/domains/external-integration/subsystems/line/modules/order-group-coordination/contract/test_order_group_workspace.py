"""Execute the observation SQL and HTTP contracts without a database or provider effect."""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_order_group_reader
from api.routes import line_order_groups
from infrastructure.mysql.line_media_order_group_repository import MySqlLineOrderGroupBindingRepository
from shared_kernel.identities import ActorContext
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.capabilities import LineCapabilityDeniedError
from subsystems.line.order_group_application import LineOrderGroupQueryApplication


def prepare_paid_group_todos(connection):
    connection.db.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT '訂單成立'")
    connection.db.execute('CREATE TABLE client_deposit_settlement_projection (case_no TEXT PRIMARY KEY,settlement_state TEXT,contracted_amount_ntd INT)')
    for case, order_status, state, amount, group in (
        ('PAID-1','訂單成立','settled',12000,None),
        ('PAID-2','洽談中','settled',18000,None),
        ('UNPAID','洽談中','unsettled',12000,None),
        ('ZERO','洽談中','settled',0,None),
        ('BOUND','訂單成立','settled',12000,'C-bound'),
        ('CANCELLED','訂單取消','settled',12000,None),
        ('COMPLETED','訂單完成','settled',12000,None),
    ):
        connection.db.execute('INSERT INTO orders(case_no,status) VALUES (?,?)',(case,order_status))
        connection.db.execute('INSERT INTO client_deposit_settlement_projection VALUES (?,?,?)',(case,state,amount))
        if group:
            connection.db.execute("INSERT INTO line_order_group_bindings VALUES (?,?,'active',1,'2026-10-22',NULL)",(case,group))
    connection.db.execute("INSERT INTO orders(case_no,status) VALUES ('NO-SETTLEMENT','訂單成立')")
    connection.db.execute("INSERT INTO line_order_group_bindings VALUES ('PAID-2',NULL,'unbound',0,'2026-10-22',NULL)")


def test_paid_uncreated_todos_only_include_unfinished_paid_cases_without_a_group(store):
    connection, repository=store
    prepare_paid_group_todos(connection)
    first=repository.paid_uncreated_todos(page=1,page_size=1)
    second=repository.paid_uncreated_todos(page=2,page_size=1)
    assert first.total==2 and first.total_pages==2
    assert [(item.case_no,item.deposit_amount_ntd) for item in first.items]==[('PAID-1',12000)]
    assert [item.case_no for item in second.items]==['PAID-2']
    assert repository.paid_uncreated_todos(page=3,page_size=1).items==()
    assert all(sql.lstrip().startswith('SELECT') for sql,_ in connection.executed)


def test_binding_or_deposit_reversal_removes_group_todo_on_readback(store):
    connection, repository=store
    prepare_paid_group_todos(connection)
    connection.db.execute("INSERT INTO line_order_group_bindings VALUES ('PAID-1','C-new','bound',1,'2026-10-22',NULL)")
    connection.db.execute("UPDATE client_deposit_settlement_projection SET settlement_state='unsettled' WHERE case_no='PAID-2'")
    page=repository.paid_uncreated_todos(page=1,page_size=25)
    assert page.total==0 and not page.items


def test_paid_group_todo_query_requires_capability_and_never_commits(store):
    connection, repository=store
    prepare_paid_group_todos(connection)
    application=make_application(repository)
    with pytest.raises(LineCapabilityDeniedError):
        application.paid_uncreated_todos(ActorContext('customer'),page=1,page_size=25)
    assert connection.executed==[]
    page=application.paid_uncreated_todos(ActorContext('admin:7',('line.order_group.read',)),page=1,page_size=25)
    assert page.total==2


def test_mobile_paid_group_todo_is_verified_paginated_and_read_only(monkeypatch,store):
    from api.routes import line_mobile_admin
    from fastapi import HTTPException
    from types import SimpleNamespace
    connection,repository=store
    prepare_paid_group_todos(connection)
    capabilities=[]
    @contextmanager
    def unit():
        yield SimpleNamespace(order_groups=repository)
    def context(token,capability):
        capabilities.append(capability.value)
        if token!='staff': raise HTTPException(403,'staff binding required')
        return None,ActorContext('admin:7',('line.order_group.read',))
    monkeypatch.setattr(line_mobile_admin,'open_line_unit_of_work',unit)
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',context)
    api=FastAPI();api.include_router(line_mobile_admin.router)
    client=TestClient(api)
    path='/api/v1/line/mobile-admin/order-group-todos'
    response=client.post(path,json={'line_id_token':'staff','page':1,'page_size':1})
    assert response.status_code==200
    page=response.json()['data']
    assert page['total']==2 and page['items']==[{'case_no':'PAID-1','deposit_amount_ntd':12000}]
    assert capabilities==['line.order_group.read']
    connection.executed.clear()
    assert client.post(path,json={'line_id_token':'customer'}).status_code==403
    assert client.post(path,json={'line_id_token':'staff','page':0}).status_code==422
    assert not connection.executed


class Connection:
    """SQLite executes real SELECTs; translate only MySQL's text cast and CONCAT."""
    def __init__(self):
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.create_function('CONCAT', -1, lambda *values: ''.join(str(value) for value in values))
        self.executed = []
        self.db.executescript('''
          CREATE TABLE orders (case_no TEXT PRIMARY KEY, client_id INT, staff_id INT);
          CREATE TABLE clients (id INT PRIMARY KEY, name TEXT, line_user_id TEXT);
          CREATE TABLE staff (id INT PRIMARY KEY, name TEXT, line_user_id TEXT, union_no TEXT);
          CREATE TABLE case_staff_assignments (case_no TEXT, staff_id INT, status TEXT);
          CREATE TABLE line_identity_role_bindings (subject_type TEXT, subject_reference TEXT, binding_status TEXT, line_user_id TEXT);
          CREATE TABLE line_order_group_bindings (case_no TEXT PRIMARY KEY, group_id TEXT, binding_status TEXT, aggregate_version INT, updated_at_utc TEXT, last_invitation_at_utc TEXT);
          CREATE TABLE line_order_group_binding_events (id INT PRIMARY KEY, case_no TEXT, action TEXT, resulting_group_id TEXT, resulting_version INT, occurred_at_utc TEXT);
          CREATE TABLE line_order_group_runtime_events (id INT PRIMARY KEY, case_no TEXT, event_type TEXT, line_user_id TEXT, occurred_at_utc TEXT);
        ''')

    @contextmanager
    def cursor(self):
        cursor = self.db.cursor()
        connection = self
        class Cursor:
            def execute(self, sql, args=()):
                assert sql.lstrip().startswith('SELECT'), 'workspace attempted a mutation'
                connection.executed.append((sql, tuple(args)))
                sql = sql.replace('%s', '?')
                sql = re.sub(r'CAST\((\w+\.id) AS CHAR CHARACTER SET utf8mb4\)\s*COLLATE utf8mb4_unicode_ci', r'CAST(\1 AS TEXT)', sql)
                cursor.execute(sql, args)

            def row(self, raw):
                if raw is None: return None
                return {key: datetime.fromisoformat(raw[key]) if key.endswith('_utc') and raw[key] is not None else raw[key] for key in raw.keys()}

            def fetchone(self): return self.row(cursor.fetchone())
            def fetchall(self): return [self.row(row) for row in cursor.fetchall()]
        try:
            yield Cursor()
        finally:
            cursor.close()


def seed(connection, index=1, *, status='bound'):
    case = f'CASE-{index:03d}'
    db = connection.db
    db.execute('INSERT INTO clients VALUES (?,?,?)', (index, f'客戶{index}', f'U-c{index}'))
    db.execute('INSERT INTO staff (id,name,line_user_id) VALUES (?,?,?)', (index, f'月嫂{index}', f'U-s{index}'))
    db.execute('UPDATE staff SET union_no=? WHERE id=?', (f'A{index:03d}', index))
    db.execute('INSERT INTO orders VALUES (?,?,?)', (case,index,index))
    db.executemany('INSERT INTO line_identity_role_bindings VALUES (?,?,?,?)', [('customer',str(index),'bound',f'U-c{index}'),('staff',str(index),'bound',f'U-s{index}')])
    db.execute('INSERT INTO line_order_group_bindings VALUES (?,?,?,?,?,?)', (case,f'C-group-{index}',status,1,'2026-10-15 01:00:00',None))
    db.execute('INSERT INTO line_order_group_binding_events VALUES (?,?,?,?,?,?)', (index,case,'bound',f'C-group-{index}',1,'2026-10-15 01:00:00'))
    return case


def event(connection, index, case, kind, identity, occurred='2026-10-15 02:00:00'):
    connection.db.execute('INSERT INTO line_order_group_runtime_events VALUES (?,?,?,?,?)', (index,case,kind,identity,occurred))


@pytest.fixture
def store():
    connection = Connection()
    try: yield connection, MySqlLineOrderGroupBindingRepository(connection)
    finally: connection.db.close()


def test_server_paging_search_and_attention_priority(store):
    connection, repository = store
    for index in range(1,42): seed(connection,index,status='attention' if index==41 else 'bound')
    first=repository.workspace_list(search=None,status=None,page=1,page_size=25)
    second=repository.workspace_list(search=None,status=None,page=2,page_size=25)
    assert (first.total,first.total_pages,len(first.items),len(second.items))==(41,2,25,16)
    assert first.items[0].case_no=='CASE-041'
    assert next(member for member in first.items[0].members if member.role == 'staff').staff_union_no == 'A041'
    assert {item.case_no for item in first.items}.isdisjoint(item.case_no for item in second.items)
    filtered=repository.workspace_list(search='041',status='attention',page=1,page_size=25)
    assert filtered.total==1 and filtered.items[0].customer_name=='客戶41'
    assert repository.workspace_list(search='CASE_%',status=None,page=1,page_size=25).total==0
    assert any('LIMIT %s OFFSET %s' in sql for sql,_ in connection.executed)


def test_current_canonical_audience_and_membership_are_read_without_mutation(store):
    connection,repository=store;case=seed(connection)
    event(connection,1,case,'member_joined','U-c1')
    event(connection,2,case,'member_joined','U-s1')
    event(connection,3,case,'member_left','U-s1','2026-10-15 03:00:00')
    record=repository.workspace_get(case)
    assert [(member.role,member.name,member.membership_status) for member in record.members]==[('customer','客戶1','joined'),('staff','月嫂1','left')]
    assert record.latest_event.event_type=='member_left' and record.latest_event.participant_name=='月嫂1'
    assert record.latest_event.participant_union_no == 'A001'
    assert record.last_invitation_at is None
    connection.db.execute("UPDATE clients SET line_user_id='U-spoof' WHERE id=1")
    assert repository.workspace_get(case).members[0].membership_status=='unknown'


def test_rebinding_never_reuses_old_group_membership_or_invitation(store):
    connection,repository=store;case=seed(connection,status='inviting')
    event(connection,1,case,'member_joined','U-c1')
    event(connection,2,case,'member_joined','U-s1')
    connection.db.execute("UPDATE line_order_group_bindings SET group_id='C-new',aggregate_version=2,last_invitation_at_utc='2026-10-15 01:30:00' WHERE case_no=?",(case,))
    connection.db.execute('INSERT INTO line_order_group_binding_events VALUES (?,?,?,?,?,?)',(2,case,'replaced','C-new',2,'2026-10-16 01:00:00'))
    record=repository.workspace_get(case)
    assert {member.membership_status for member in record.members}=={'pending'}
    assert record.last_invitation_at is None and record.latest_event.event_type=='replaced'
    event(connection,3,case,'member_joined','U-s1','2026-10-16 02:00:00')
    assert [member.membership_status for member in repository.workspace_get(case).members]==['pending','joined']


def test_current_assignments_include_multiple_staff_and_exclude_ended_assignment(store):
    connection,repository=store;case=seed(connection)
    connection.db.executemany('INSERT INTO staff (id,name,line_user_id) VALUES (?,?,?)',[(2,'支援月嫂','U-s2'),(3,'已結束月嫂','U-s3')])
    connection.db.executemany('INSERT INTO case_staff_assignments VALUES (?,?,?)',[(case,2,'planned'),(case,1,'active'),(case,3,'ended')])
    connection.db.execute("INSERT INTO line_identity_role_bindings VALUES ('staff','2','bound','U-s2')")
    members=repository.workspace_get(case).members
    assert len(members)==3 and {member.name for member in members}=={'客戶1','月嫂1','支援月嫂'}
    assert {member.membership_status for member in members}=={'pending'}


def test_missing_binding_evidence_is_unknown_and_unknown_actor_remains_unidentified(store):
    connection,repository=store;case=seed(connection)
    connection.db.execute('DELETE FROM line_order_group_binding_events')
    event(connection,1,case,'member_joined','U-unrelated')
    record=repository.workspace_get(case)
    assert record.bound_at is None and {member.membership_status for member in record.members}=={'unknown'}
    assert record.latest_event.participant_name is None and record.latest_event.participant_role is None
    assert repository.workspace_get('missing') is None


def test_event_sources_have_unique_keys_and_database_paging(store):
    connection,repository=store;case=seed(connection)
    event(connection,1,case,'member_joined','U-c1')
    first=repository.workspace_events(case,page=1,page_size=1)
    second=repository.workspace_events(case,page=2,page_size=1)
    assert (first.total,first.total_pages)==(2,2)
    assert first.items[0].event_key=='runtime:1' and second.items[0].event_key=='binding:1'
    assert first.items[0].participant_role=='customer' and second.items[0].participant_role is None


def make_application(repository):
    class UnitOfWork:
        order_groups=repository
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def commit(self): raise AssertionError('workspace committed')
    return LineOrderGroupQueryApplication(UnitOfWork)


def make_client(monkeypatch,repository):
    app=FastAPI();app.include_router(line_order_groups.router)
    app.dependency_overrides[require_line_order_group_reader]=lambda:AdminPrincipal(7,'reader','工會人員','system_admin')
    monkeypatch.setattr(line_order_groups,'get_line_order_group_query_application',lambda:make_application(repository))
    return TestClient(app)


def test_http_workspace_is_typed_minimal_and_readonly(monkeypatch,store):
    connection,repository=store;case=seed(connection)
    event(connection,1,case,'invitation_relayed',None)
    client=make_client(monkeypatch,repository)
    listing=client.get('/api/v1/line/order-groups/workspace/numbered?search=001&status=bound&page_size=25')
    assert listing.status_code==200 and listing.json()['total']==1
    detail=client.get(f'/api/v1/line/order-groups/workspace/{case}')
    assert detail.status_code==200 and detail.json()==listing.json()['items'][0]
    events=client.get(f'/api/v1/line/order-groups/workspace/{case}/events/numbered')
    assert events.status_code==200 and events.json()['total']==2
    payload=listing.text+detail.text+events.text
    assert not any(value in payload for value in ['U-c1','U-s1','C-group-1','group_id','line_user_id','actor_id','fingerprint','invitation_url'])
    assert client.get('/api/v1/line/order-groups/workspace/missing').status_code==404
    assert client.get('/api/v1/line/order-groups/workspace/missing/events/numbered').status_code==404


@pytest.mark.parametrize('suffix',['numbered?page=0','numbered?page_size=201','numbered?status=unknown','numbered?search='+('x'*51),'CASE-001/events/numbered?page=0'])
def test_http_rejects_invalid_query_before_read(monkeypatch,store,suffix):
    connection,repository=store
    response=make_client(monkeypatch,repository).get('/api/v1/line/order-groups/workspace/'+suffix)
    assert response.status_code==422 and not connection.executed


def test_unprivileged_reader_cannot_open_workspace(store):
    connection,repository=store
    application=make_application(repository)
    actor=ActorContext('admin:7',())
    with pytest.raises(LineCapabilityDeniedError): application.workspace_list(actor,search=None,status=None,page=1,page_size=25)
    with pytest.raises(LineCapabilityDeniedError): application.workspace_get(actor,'CASE-001')
    with pytest.raises(LineCapabilityDeniedError): application.workspace_events(actor,'CASE-001',page=1,page_size=25)
    assert not connection.executed
