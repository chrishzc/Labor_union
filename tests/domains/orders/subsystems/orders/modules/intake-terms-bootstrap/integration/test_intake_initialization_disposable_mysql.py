"""Isolated HTTP/real-writer proof for initialization after completing intake."""

from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_persisted_admin
from api.routes.order_intake_terms_bootstrap import router
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.case_architecture_bootstrap_repository import MySqlCaseArchitectureBootstrapRepository
from infrastructure.mysql.order_intake_architecture_initializer import MySqlOrderIntakeArchitectureInitializer
from infrastructure.mysql.order_intake_terms_bootstrap_repository import MySqlOrderIntakeTermsBootstrapRepository
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from subsystems.access.authentication_session import AdminPrincipal

DATABASE = os.getenv('LABOR_UNION_TEST_MYSQL_DATABASE')
pytestmark = pytest.mark.skipif(not DATABASE, reason='requires an isolated localhost lu_test_* database')
ROOTS = ('client_finance_accounts', 'client_payment_terms', 'payroll_case_accounts',
         'case_payroll_rate_policy_snapshots', 'scheduling_aggregates', 'case_architecture_bootstrap_events')


@pytest.fixture(scope='module', autouse=True)
def isolated_database():
    assert DATABASE and DATABASE.startswith('lu_test_')
    assert os.environ['APP_ENV'] == 'development'
    host = os.environ['LABOR_UNION_TEST_MYSQL_HOST']
    assert host in {'localhost', '127.0.0.1'}
    target = DATABASE + '_intake_init'
    bootstrap(Namespace(host=host, port=int(os.environ['LABOR_UNION_TEST_MYSQL_PORT']),
        user=os.environ['LABOR_UNION_TEST_MYSQL_USER'], password=os.environ['LABOR_UNION_TEST_MYSQL_PASSWORD'],
        database=target, confirm_database=target))
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(mysql_adapter.DB_CONFIG, 'database', target)
        yield target


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_persisted_admin] = lambda: AdminPrincipal(
        id=None, username='intake-test', display_name='Synthetic test', role='line_agent')
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def seed(case, *, status='待補件', missing_time=False, twins=False):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name,identity_status,created_at) VALUES (%s,'Synthetic','一般市民','2026-09-01')", (case,))
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,%s,0,'2026-11-01',30,8,0,%s,%s,%s)",
                (case, client_id, status, None if missing_time else '08:00:00', None if missing_time else '17:00:00', None if missing_time else 0))
            if twins:
                cursor.execute("INSERT INTO beclass_records(bound_case_no,record_origin,survey_details) VALUES (%s,'admin_manual',%s)", (case, '{"特殊計費:胎數":"雙胞胎"}'))
        connection.commit()
    finally:
        connection.close()


def snapshot(case):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            result = {}
            for table in ('orders', *ROOTS, 'client_payment_terms_events', 'case_staff_assignments', 'client_obligations', 'staff_obligations'):
                cursor.execute(f'SELECT * FROM {table} WHERE case_no=%s', (case,))
                result[table] = cursor.fetchall()
            cursor.execute("SELECT * FROM admin_command_receipts WHERE JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.case_no'))=%s", (case,))
            result['receipts'] = cursor.fetchall()
            return result
    finally:
        connection.close()


def command(client, case, *, terms=False):
    path = f'/api/v1/orders/{case}/' + ('intake-terms-bootstrap' if terms else 'intake-completion')
    proposal = {'proposed_start_date': '2026-11-01', 'proposed_service_days': 30,
        'proposed_service_time': {'service_hours_per_day': 8, 'start_time': '08:00:00', 'end_time': '17:00:00', 'end_day_offset': 0}} if terms else {}
    before = snapshot(case)
    preview = client.post(path + '/preview', json=proposal)
    assert preview.status_code == 200, preview.text
    preview = preview.json()['data']
    assert preview['apply_allowed'], preview
    assert snapshot(case) == before  # Every Preview is zero-write.
    return path + '/apply', {**proposal, 'expected_lifecycle_version': preview['lifecycle_version'],
        'preview_fingerprint': preview['preview_fingerprint'], 'reason': 'Synthetic intake initialization verification'}


def apply(client, path, body, key):
    return client.post(path, json=body, headers={'Idempotency-Key': key, 'X-Correlation-ID': key})


@pytest.mark.parametrize('terms,twins', [(False, False), (True, False), (True, True)])
def test_completion_initializes_approved_terms_once_and_preserves_existing_rows(client, terms, twins):
    case = f'INIT-{int(terms)}-{int(twins)}'
    seed(case, status='洽談中' if terms else '待補件', missing_time=terms, twins=twins)
    path, body = command(client, case, terms=terms)
    response = apply(client, path, body, case)
    assert response.status_code == 200, response.text
    saved = snapshot(case)
    assert all(len(saved[table]) == 1 for table in ROOTS)
    payment = saved['client_payment_terms'][0]
    assert payment['policy_version'] == 'client-approved-v1'
    assert payment['client_hourly_rate_ntd'] == 300
    assert payment['deposit_service_days'] == 5
    assert payment['deposit_due_date'] == date(2026, 9, 4)
    assert payment['first_payment_due_date'] == date(2026, 11, 1)
    assert payment['second_payment_due_date'] == date(2026, 11, 16)
    payroll = saved['case_payroll_rate_policy_snapshots'][0]
    assert payroll['policy_kind'] == ('twins' if twins else 'citizen')
    assert payroll['hourly_rate_ntd'] == (450 if twins else 300)
    assert len(saved['client_payment_terms_events']) == 1
    assert all(not saved[table] for table in ('case_staff_assignments', 'client_obligations', 'staff_obligations'))
    replay = apply(client, path, body, case)
    assert replay.status_code == 200 and replay.json()['data']['replayed']
    assert snapshot(case) == saved
    rejected = apply(client, path, body, case + '-new-key')
    assert rejected.status_code == 409, rejected.text
    assert snapshot(case) == saved  # New-key/stale commands cannot overwrite policy or amounts.


def test_concurrent_same_command_has_one_initialization(client):
    case = 'INIT-CONCURRENT'
    seed(case)
    path, body = command(client, case)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: apply(client, path, body, case), range(2)))
    assert [response.status_code for response in responses] == [200, 200], [r.text for r in responses]
    assert sorted(r.json()['data']['replayed'] for r in responses) == [False, True]
    saved = snapshot(case)
    assert all(len(saved[table]) == 1 for table in ROOTS)
    assert len(saved['client_payment_terms_events']) == 1


def test_initialization_failure_rolls_back_completion_and_all_roots(client, monkeypatch):
    case = 'INIT-ROLLBACK'
    seed(case)
    path, body = command(client, case)
    before = snapshot(case)
    create = MySqlCaseArchitectureBootstrapRepository.create_bootstrap
    def fail_after_writing(self, *args):
        create(self, *args)
        raise RuntimeError('synthetic failure after all initialization inserts')
    with monkeypatch.context() as patch:
        patch.setattr(MySqlCaseArchitectureBootstrapRepository, 'create_bootstrap', fail_after_writing)
        assert apply(client, path, body, case).status_code == 500
    assert snapshot(case) == before
    assert apply(client, path, body, case).status_code == 200  # The rolled-back key remains reusable.


def test_existing_partial_finance_is_not_filled_or_overwritten(client):
    case = 'INIT-PARTIAL'
    seed(case)
    path, body = command(client, case)
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,7)', (case,))
        connection.commit()
    finally:
        connection.close()
    before = snapshot(case)
    assert apply(client, path, body, case).status_code == 409
    assert snapshot(case) == before


def test_reentering_initializer_keeps_existing_policy_and_versions(client):
    case = 'INIT-EXISTING'
    seed(case)
    path, body = command(client, case)
    assert apply(client, path, body, case).status_code == 200
    connection = mysql_adapter.get_connection()
    try:
        before = snapshot(case)
        repository = MySqlOrderIntakeTermsBootstrapRepository(connection)
        connection.begin()
        facts = repository.load_case(case, for_update=True)
        MySqlOrderIntakeArchitectureInitializer(connection).ensure(facts, 'intake-test', 'Synthetic repeat', 'another-key')
        connection.commit()
        assert snapshot(case) == before
    finally:
        connection.close()
