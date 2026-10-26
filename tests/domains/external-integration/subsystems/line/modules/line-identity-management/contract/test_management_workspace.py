"""Protect role-scoped management queries, same-role commands and reader transport."""
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_identity_binding_reader
from api.routes import line_identity_management as routes
from domains.line.identities import LineUserId
from domains.line.identity_binding import LineBindingSubjectType as Role
from domains.line.identity_binding import LineIdentityBindingSnapshot, LineIdentityBindingStatus as Status
from infrastructure.mysql.line_identity_management_repository import MySqlLineIdentityManagementRepository
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.line.identity_management_application import LineIdentityManagementApplication, _require_same_request
from subsystems.line.identity_management_contracts import LineIdentityBindingListQuery, LineIdentityCandidateQuery, RequestLineIdentityRevocationCommand, ReplaceLineIdentitySubjectCommand, LineIdentityRevocationRequest, LineIdentityRevocationStatus


class ReadCursor:
    def __init__(self, connection): self.cursor = connection.cursor()
    def __enter__(self): return self
    def __exit__(self, *args): self.cursor.close()
    def execute(self, sql, params=()):
        assert sql.strip().upper().startswith('SELECT'), 'query attempted a write'
        self.cursor.execute(sql.replace('%s', '?').replace(' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci', ' AS TEXT)').replace(' AS CHAR)', ' AS TEXT)'), params)
    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None
    def fetchall(self): return [dict(row) for row in self.cursor.fetchall()]


@pytest.fixture
def repository():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
      CREATE TABLE clients(id INTEGER PRIMARY KEY,name TEXT,line_user_id TEXT);
      CREATE TABLE staff(id INTEGER PRIMARY KEY,name TEXT,line_user_id TEXT);
      CREATE TABLE admin_users(id INTEGER PRIMARY KEY,display_name TEXT,linked_line_user_id TEXT);
      CREATE TABLE orders(case_no TEXT,client_id INTEGER,created_at TEXT);
      CREATE TABLE line_identity_role_bindings(line_user_id TEXT,subject_type TEXT,subject_reference TEXT,binding_status TEXT,aggregate_version INTEGER,updated_at_utc TEXT);
      CREATE TABLE line_identity_role_binding_events(line_user_id TEXT,subject_type TEXT,action TEXT,occurred_at_utc TEXT);
      CREATE TABLE line_identity_revocation_requests(id INTEGER,line_user_id TEXT,subject_type TEXT,active_marker INTEGER,request_status TEXT);
      CREATE TABLE line_platform_users(line_user_id TEXT,selected_identity_role TEXT);
      INSERT INTO clients VALUES(1,'已綁客戶','U-shared'),(2,'可選客戶',NULL),(3,'根事實已有綁定',NULL);
      INSERT INTO staff VALUES(1,'同帳號月嫂','U-shared'),(2,'可選月嫂',NULL);
      INSERT INTO admin_users VALUES(1,'可選內部人員',NULL);
      INSERT INTO orders VALUES('ORD-001',1,'2026-10-15'),('ORD-002',2,'2026-10-15');
      INSERT INTO line_identity_role_bindings VALUES('U-shared','customer','1','bound',7,'2026-10-15'),('U-shared','staff','1','bound',4,'2026-10-15'),('U-other','customer','3','bound',1,'2026-10-15');
      INSERT INTO line_identity_revocation_requests VALUES(9,'U-shared','staff',1,'menu_reset_failed');
    ''')
    repo = MySqlLineIdentityManagementRepository(SimpleNamespace(cursor=lambda: ReadCursor(conn)))
    yield repo
    conn.close()


def test_explicit_role_detail_never_follows_the_other_role_or_its_revocation(repository):
    customer = repository.detail(LineUserId('U-shared'), Role.CUSTOMER)
    staff = repository.detail(LineUserId('U-shared'), Role.STAFF)
    assert (customer.subject_name, customer.version, customer.subject_display_reference) == ('已綁客戶', 7, 'ORD-001')
    assert customer.revocation_request_id is None
    assert (staff.subject_name, staff.version, staff.revocation_request_id) == ('同帳號月嫂', 4, 9)


@pytest.fixture
def reminder_repository():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
      CREATE TABLE clients(id INTEGER PRIMARY KEY,name TEXT,phone TEXT,case_no TEXT,line_user_id TEXT);
      CREATE TABLE orders(case_no TEXT,client_id INTEGER,status TEXT);
      CREATE TABLE staff(id INTEGER PRIMARY KEY,name TEXT,phone TEXT,status TEXT,line_user_id TEXT);
      CREATE TABLE staff_lifecycle_states(staff_id INTEGER,lifecycle_state TEXT);
      CREATE TABLE line_identity_role_bindings(subject_type TEXT,subject_reference TEXT,binding_status TEXT);
    ''')
    for i, status in enumerate(('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消','歷史訂單－服務中'), 1):
        conn.execute('INSERT INTO clients VALUES(?,?,?,?,NULL)', (i,f'客戶{i}','0987654321',f'115{i:06}'))
        conn.execute('INSERT INTO orders VALUES(?,?,?)', (f'115{i:06}',i,status))
    for i, status in enumerate(('active','active','paused','retired'), 1):
        conn.execute('INSERT INTO staff VALUES(?,?,?,?,NULL)', (i,f'月嫂{i}','0987654321',status))
    repo = MySqlLineIdentityManagementRepository(SimpleNamespace(cursor=lambda: ReadCursor(conn)))
    yield repo, conn
    conn.close()


def test_binding_reminders_only_current_cases_and_active_staff_with_real_pagination(reminder_repository):
    repo, _ = reminder_repository
    first = repo.binding_reminders(LineIdentityCandidateQuery(Role.CUSTOMER, page_size=2))
    second = repo.binding_reminders(LineIdentityCandidateQuery(Role.CUSTOMER, page=2, page_size=2))
    assert first.total == second.total == 4
    assert [r.subject_reference for r in first.items + second.items] == ['1','2','3','4']
    assert first.items[0].phone == '0987654321' and first.items[0].case_no == '115000001'
    staff = repo.binding_reminders(LineIdentityCandidateQuery(Role.STAFF))
    assert staff.total == 2 and all(r.case_no is None for r in staff.items)


@pytest.mark.parametrize('role', [Role.CUSTOMER, Role.STAFF])
@pytest.mark.parametrize('status', ['pending_review','bound','revocation_pending','revoked'])
def test_binding_reminders_follow_canonical_claim_and_return_after_revocation(reminder_repository, role, status):
    repo, conn = reminder_repository
    conn.execute('INSERT INTO line_identity_role_bindings VALUES(?,?,?)', (role.value,'1',status))
    result = repo.binding_reminders(LineIdentityCandidateQuery(role))
    assert ('1' in {r.subject_reference for r in result.items}) is (status == 'revoked')


@pytest.mark.parametrize('role,table', [(Role.CUSTOMER,'clients'),(Role.STAFF,'staff')])
def test_binding_reminders_disappear_after_binding_and_read_does_not_mutate(reminder_repository, role, table):
    repo, conn = reminder_repository
    before = conn.total_changes
    assert '1' in {r.subject_reference for r in repo.binding_reminders(LineIdentityCandidateQuery(role)).items}
    assert conn.total_changes == before
    conn.execute(f"UPDATE {table} SET line_user_id='U-synthetic' WHERE id=1")
    assert '1' not in {r.subject_reference for r in repo.binding_reminders(LineIdentityCandidateQuery(role)).items}


@pytest.mark.parametrize('status', ['訂單取消','訂單完成','歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成'])
def test_customer_binding_reminder_disappears_when_case_no_longer_needs_service(reminder_repository, status):
    repo, conn = reminder_repository
    assert '2' in {r.subject_reference for r in repo.binding_reminders(LineIdentityCandidateQuery(Role.CUSTOMER)).items}
    conn.execute('UPDATE orders SET status=? WHERE client_id=2', (status,))
    page = repo.binding_reminders(LineIdentityCandidateQuery(Role.CUSTOMER))
    assert page.total == 3 and '2' not in {r.subject_reference for r in page.items}
    assert conn.execute('SELECT line_user_id FROM clients WHERE id=2').fetchone()[0] is None


@pytest.mark.parametrize('state', ['paused','retired'])
def test_staff_binding_reminders_follow_lifecycle_owner_even_if_legacy_status_active(reminder_repository, state):
    repo, conn = reminder_repository
    conn.execute('INSERT INTO staff_lifecycle_states VALUES(1,?)', (state,))
    assert '1' not in {r.subject_reference for r in repo.binding_reminders(LineIdentityCandidateQuery(Role.STAFF)).items}


def test_binding_search_and_real_pagination_are_server_owned(repository):
    result = repository.list(LineIdentityBindingListQuery(search='ORD-001', page=1, page_size=1))
    assert result.total == 1 and result.items[0].subject_type is Role.CUSTOMER
    second = repository.list(LineIdentityBindingListQuery(page=2, page_size=1))
    assert second.page == 2 and second.total == 3 and len(second.items) == 1


@pytest.mark.parametrize('role,name', [(Role.CUSTOMER,'可選客戶'),(Role.STAFF,'可選月嫂'),(Role.ADMIN,'可選內部人員')])
def test_candidates_exclude_both_owner_and_canonical_bound_subjects(repository, role, name):
    result = repository.replacement_candidates(LineIdentityCandidateQuery(role))
    assert [item.subject_name for item in result.items] == [name]
    assert result.total == 1 and result.items[0].subject_type is role
    assert result.items[0].current_line_user_id is None


def test_candidate_case_search_and_subject_context_are_readonly(repository):
    result = repository.replacement_candidates(LineIdentityCandidateQuery(Role.CUSTOMER, 'ORD-002'))
    assert result.total == 1 and result.items[0].subject_reference == '2'
    contexts = repository.subject_contexts(((Role.CUSTOMER,'1'),(Role.STAFF,'1')))
    assert contexts[(Role.CUSTOMER,'1')].current_line_user_id == 'U-shared'
    assert contexts[(Role.STAFF,'1')].subject_name == '同帳號月嫂'


def test_query_application_does_not_commit(repository):
    commits = []
    @contextmanager
    def uow(): yield SimpleNamespace(identity_management=repository,commit=lambda:commits.append(True))
    app = LineIdentityManagementApplication(uow, lambda: datetime.now(timezone.utc))
    assert app.detail(LineUserId('U-shared'), Role.STAFF).subject_type is Role.STAFF
    assert app.replacement_candidates(LineIdentityCandidateQuery(Role.CUSTOMER)).total == 1
    assert commits == []


def test_reused_revocation_key_cannot_cross_roles():
    command = RequestLineIdentityRevocationCommand(LineUserId('U-shared'),ExpectedVersion(7),ActorContext('admin:1',()),'確認解除',IdempotencyKey('key'),CorrelationId('corr'),Role.CUSTOMER)
    with pytest.raises(RuntimeError, match='idempotency_conflict'):
        _require_same_request(SimpleNamespace(line_user_id=command.line_user_id,subject_type=Role.STAFF),command)


@pytest.mark.parametrize('role', [Role.CUSTOMER, Role.STAFF])
@pytest.mark.parametrize('action', ['replace', 'revoke'])
def test_management_command_changes_only_the_explicit_role(role, action):
    user = LineUserId('U-dual-role')
    roots = {item:LineIdentityBindingSnapshot(user,Status.BOUND,ExpectedVersion(7),item,str(index)) for index,item in enumerate((Role.CUSTOMER,Role.STAFF),1)}
    other_role = Role.STAFF if role is Role.CUSTOMER else Role.CUSTOMER
    untouched = roots[other_role]
    writes = []; commits = []; audit = []; outbox = []
    def get(uid, selected_role):
        assert uid == user and selected_role is role
        return roots[selected_role]
    def replace_subject(claim, version, *args):
        assert claim.subject_type is role and version == roots[role].version
        roots[role] = replace(roots[role],subject_reference=claim.subject_reference,version=ExpectedVersion(8))
        return roots[role]
    def revoke(uid, version, actor, key, correlation, selected_role):
        assert uid == user and selected_role is role and version == roots[role].version
        roots[role] = replace(roots[role],status=Status.REVOCATION_PENDING,version=ExpectedVersion(8))
        return roots[role]
    def create_request(command, pending, publication):
        return LineIdentityRevocationRequest(91,user,role,pending.subject_reference,LineIdentityRevocationStatus.PENDING_MENU_RESET,command.expected_version,pending.version,5,'test-menu','admin:1',command.reason,command.idempotency_key.value,command.correlation_id.value,0,None,None)
    unit = SimpleNamespace(
        identities=SimpleNamespace(get=get,replace_subject=replace_subject,request_revocation=revoke),
        identity_management=SimpleNamespace(subject_candidate=lambda *args:{'subject_name':'更正對象','line_user_id':None},detail=lambda uid,selected_role:get(uid,selected_role),get_request_by_key=lambda key:None,default_menu_publication=lambda:{'id':5,'line_rich_menu_id':'test-menu'},create_request=create_request),
        customers=SimpleNamespace(clear_customer=lambda *args:writes.append(Role.CUSTOMER),bind_customer=lambda *args:writes.append(Role.CUSTOMER)),
        staff=SimpleNamespace(clear_staff=lambda *args:writes.append(Role.STAFF),bind_staff=lambda *args:writes.append(Role.STAFF)),
        audit=SimpleNamespace(append=audit.append),outbox=SimpleNamespace(append=outbox.append),commit=lambda:commits.append(True),
    )
    @contextmanager
    def uow(): yield unit
    app = LineIdentityManagementApplication(uow,lambda:datetime.now(timezone.utc))
    actor = ActorContext('admin:1',('line.identity.binding.manage',))
    if action == 'replace':
        app.replace_subject(ReplaceLineIdentitySubjectCommand(user,ExpectedVersion(7),'9',actor,'已核對',IdempotencyKey('replace'),CorrelationId('corr'),role))
        assert roots[role].subject_reference == '9' and writes == [role,role]
    else:
        app.request_revocation(RequestLineIdentityRevocationCommand(user,ExpectedVersion(7),actor,'已核對',IdempotencyKey('revoke'),CorrelationId('corr'),role))
        assert roots[role].status is Status.REVOCATION_PENDING and len(outbox) == 1
        assert writes == []  # Owner projection is retained until the existing menu-reset saga completes.
    assert roots[other_role] is untouched
    assert len(commits) == 1 and len(audit) == 1


def test_reader_route_forwards_explicit_role_and_bounds_candidates(monkeypatch, repository):
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_line_identity_binding_reader] = lambda: object()
    monkeypatch.setattr(routes,'_application',lambda:SimpleNamespace(detail=repository.detail,replacement_candidates=repository.replacement_candidates))
    with TestClient(app) as client:
        result = client.get('/api/v1/line/identity-bindings/U-shared?subject_type=staff')
        assert result.status_code == 200 and result.json()['data']['subject_type'] == 'staff'
        path = '/api/v1/line/identity-bindings/replacement-candidates'
        assert client.get(path+'?subject_type=customer').json()['data']['total'] == 1
        assert client.get(path+'?subject_type=invalid').status_code == 422
        assert client.get(path+'?subject_type=customer&page_size=101').status_code == 422
    app.dependency_overrides.clear()


def test_numbered_review_exposes_owner_backed_name_and_forwards_search(monkeypatch, repository):
    from api.routes import line_identity as review_routes
    from api.dependencies.admin_auth import require_line_identity_reader
    from domains.line.review import LineReviewType, LineReviewStatus
    queries = []
    snapshot = SimpleNamespace(request_id=SimpleNamespace(value=71),review_type=LineReviewType.CLIENT_REBIND,status=LineReviewStatus.PENDING,version=ExpectedVersion(3),subject_type=Role.CUSTOMER,subject_reference='1',assigned_admin_id=None,due_at=None,line_user_id=LineUserId('U-new'),decision_reason=None,reviewed_by_actor_id=None,reviewed_at=None,created_at=None)
    def list_reviews(query):
        queries.append(query)
        return SimpleNamespace(items=(snapshot,),page=1,page_size=25,total=1)
    monkeypatch.setattr(review_routes,'get_line_identity_review_application',lambda:SimpleNamespace(list=list_reviews))
    monkeypatch.setattr(review_routes,'get_line_identity_management_application',lambda:SimpleNamespace(subject_contexts=repository.subject_contexts))
    app = FastAPI();app.include_router(review_routes.review_router)
    app.dependency_overrides[require_line_identity_reader] = lambda: object()
    with TestClient(app) as client:
        result = client.get('/api/v1/line/identity/reviews/numbered?search=ORD-001')
    assert result.status_code == 200
    view = result.json()['data']['items'][0]
    assert view['display_name'] == '已綁客戶' and view['subject_display_reference'] == 'ORD-001'
    assert view['current_line_user_id'] == 'U-shared'
    assert queries[0].search == 'ORD-001'
    assert 'phone' not in view and 'proof_fingerprint' not in view
