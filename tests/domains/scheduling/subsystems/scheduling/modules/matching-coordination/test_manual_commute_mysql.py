"""Opt-in real MySQL check using connection-local temporary tables only."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from infrastructure.mysql.commute_query_repository import MySqlCommuteRepository
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection
from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.contracts import DurableJobCommandConflict
from subsystems.scheduling.commute_query import COMMAND_TYPE, RECONCILIATION_TYPE, CommuteApplication, CommuteError, RouteResult

pytestmark = pytest.mark.skipif(os.environ.get('RUN_COMMUTE_MYSQL_TESTS') != '1', reason='explicit local MySQL opt-in required')


@pytest.fixture
def connection():
    assert os.environ.get('APP_ENV', 'development') == 'development'
    assert DB_CONFIG.get('host') in ('localhost', '127.0.0.1')
    assert DB_CONFIG.get('database') == 'union_db' or str(DB_CONFIG.get('database', '')).startswith('lu_test_')
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Shadows the existing canonical table on this connection; all writes
            # below disappear on close and cannot touch existing user rows.
            cursor.execute('SHOW CREATE TABLE background_jobs')
            ddl = cursor.fetchone()['Create Table']
            assert ddl.startswith('CREATE TABLE `background_jobs`')
            cursor.execute(ddl.replace('CREATE TABLE `background_jobs`', 'CREATE TEMPORARY TABLE `background_jobs`', 1))
            cursor.execute('CREATE TEMPORARY TABLE staff (id INT PRIMARY KEY,status VARCHAR(20),city VARCHAR(50),address VARCHAR(255),name VARCHAR(100))')
            cursor.execute('CREATE TEMPORARY TABLE staff_lifecycle_states (staff_id INT PRIMARY KEY,lifecycle_state VARCHAR(20))')
            cursor.execute('CREATE TEMPORARY TABLE clients (id INT PRIMARY KEY,city VARCHAR(50),address VARCHAR(255))')
            cursor.execute('CREATE TEMPORARY TABLE orders (case_no VARCHAR(50) PRIMARY KEY,client_id INT)')
            cursor.execute("INSERT INTO staff VALUES (7,'active','新竹市','測試起點','測試月嫂')")
            cursor.execute("INSERT INTO clients VALUES (9,'新竹市','測試終點')")
            cursor.execute("INSERT INTO orders VALUES ('DEMO',9)")
        conn.commit()
        yield conn
    finally:
        conn.close()


def test_committed_manual_claim_replay_usage_and_account_reconciliation(connection):
    now = datetime.now(timezone.utc)
    calls = []
    class Provider:
        configured = True
        def compute(self, origin, destination):
            with connection.cursor() as cursor:
                cursor.execute("SELECT status,command_payload FROM background_jobs WHERE command_identity='commute:mysql-one'")
                row = cursor.fetchone()
            assert row['status'] == 'running'
            assert '測試' not in str(row['command_payload'])
            calls.append((origin, destination))
            return RouteResult('ready', 'billable', 8600, 1320)
    app = CommuteApplication(MySqlCommuteRepository(connection), connection, Provider())
    def command(job_id):
        return DurableJobCommand(job_id, 'commute:mysql-one', COMMAND_TYPE, 1,
            dict(case_no='DEMO',staff_id=7,event_key='mysql-one'), 'admin_user_id:1', 'test', 1)
    assert app.query(command('first'), now)['distance_meters'] == 8600
    assert app.query(command('second'), now)['status'] == 'already_requested'
    assert len(calls) == 1
    other = DurableJobCommand('other', 'commute:mysql-one', COMMAND_TYPE, 1,
        dict(case_no='OTHER',staff_id=7,event_key='mysql-one'), 'admin_user_id:1', 'test', 1)
    with pytest.raises(DurableJobCommandConflict):
        app.query(other, now)
    assert len(calls) == 1
    usage = app.monthly_usage(now)
    assert usage['local_requests'] == 1 and usage['free_used'] == 1
    through = now + timedelta(microseconds=1)
    reconcile = DurableJobCommand('reconcile', 'commute-billing:mysql-one', RECONCILIATION_TYPE, 1,
        dict(month=usage['billing_month'],count=312,through=through.isoformat()), 'admin_user_id:1', 'test', 1)
    app.reconcile(reconcile, through)
    usage = app.monthly_usage(through)
    assert usage['estimated_billable'] == 312 and usage['free_remaining'] == 688
    with connection.cursor() as cursor:
        cursor.execute('SELECT command_payload,receipt_payload,error_payload FROM background_jobs')
        serialized = str(cursor.fetchall())
    assert 'distance' not in serialized and '測試' not in serialized


def test_missing_address_and_retired_staff_do_not_create_paid_jobs(connection):
    class Provider:
        configured = True
        def compute(self, *args): pytest.fail('must not call Google')
    app = CommuteApplication(MySqlCommuteRepository(connection), connection, Provider())
    def command(key):
        return DurableJobCommand(key, f'commute:{key}', COMMAND_TYPE, 1,
            dict(case_no='DEMO',staff_id=7,event_key=key), 'admin_user_id:1', 'test', 1)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE staff SET address='' WHERE id=7")
    connection.commit()
    with pytest.raises(CommuteError) as failure:
        app.query(command('missing-address'), datetime.now(timezone.utc))
    assert failure.value.code == 'commute_address_missing'
    with connection.cursor() as cursor:
        cursor.execute("UPDATE staff SET address='測試起點' WHERE id=7")
        cursor.execute("INSERT INTO staff_lifecycle_states VALUES (7,'retired')")
    connection.commit()
    with pytest.raises(CommuteError) as failure:
        app.query(command('retired'), datetime.now(timezone.utc))
    assert failure.value.code == 'commute_subject_unavailable'
    assert app.monthly_usage(datetime.now(timezone.utc))['local_requests'] == 0


def test_history_reads_real_outcomes_and_keeps_billing_independent_without_google(connection):
    now = datetime.now(timezone.utc)
    results = iter([RouteResult('ready','billable',8600,1320), RouteResult('no_route','billable'),
        RouteResult('failed','billable',message='測試解析失敗'), RouteResult('failed','not_billable',message='測試拒絕請求'), RouteResult('unknown','unknown',message='測試逾時')])
    class Provider:
        configured = True
        def compute(self, *args): return next(results)
    repository = MySqlCommuteRepository(connection)
    app = CommuteApplication(repository, connection, Provider())
    for index in range(5):
        key = f'history-{index}'
        command = DurableJobCommand(key, f'commute:{key}', COMMAND_TYPE, 1,
            dict(case_no='DEMO',staff_id=7,event_key=key), 'admin_user_id:1', 'test', 1)
        app.query(command, now + timedelta(seconds=index))
    before = app.monthly_usage(now)
    assert [r['status'] for r in app.history('DEMO')['records']] == ['unknown','failed','failed','failed','succeeded']
    assert app.history('OTHER')['records'] == []
    assert app.monthly_usage(now) == before
    assert before['estimated_billable'] == 3 and before['uncertain_requests'] == 1
    records = app.history('DEMO')['records']
    assert all(record['staff_name'] == '測試月嫂' for record in records)
    assert records[0]['queried_at'] == (now + timedelta(seconds=4)).isoformat()
    assert all(set(record) == {'record_id','queried_at','staff_id','staff_name','status','message'} for record in records)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE background_jobs SET result_reference='commute:billable' WHERE job_id='history-0'")
        cursor.execute("UPDATE background_jobs SET status='running',error_payload=NULL WHERE job_id='history-4'")
        cursor.execute('DELETE FROM staff WHERE id=7')
    connection.commit()
    records = app.history('DEMO')['records']
    assert records[-1]['status'] == 'unknown' and '舊紀錄' in records[-1]['message']
    assert records[0]['status'] == 'unknown'
    assert all(record['staff_name'] is None for record in records)
    assert app.monthly_usage(now) == before


def test_history_bounds_latest_fifty_and_does_not_mix_cases(connection):
    now = datetime.now(timezone.utc)
    class Provider:
        configured = True
        def compute(self, *args): return RouteResult('ready','billable',1000,120)
    repository = MySqlCommuteRepository(connection)
    app = CommuteApplication(repository, connection, Provider())
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO orders VALUES ('OTHER',9)")
    connection.commit()
    for index in range(53):
        key = f'bounded-{index}'
        command = DurableJobCommand(key, f'commute:{key}', COMMAND_TYPE, 1,
            dict(case_no='OTHER' if index==52 else 'DEMO',staff_id=7,event_key=key), 'admin_user_id:1', 'test', 1)
        app.query(command, now + timedelta(seconds=index))
    records = app.history('DEMO')['records']
    assert len(records) == 50
    assert records[0]['record_id'] == 'bounded-51' and records[-1]['record_id'] == 'bounded-2'
    assert len(app.history('OTHER')['records']) == 1
