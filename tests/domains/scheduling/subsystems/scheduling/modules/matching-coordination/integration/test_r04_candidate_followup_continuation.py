"""Execute R-04 scan predicates and the real timeout/followup/LIFF orchestration.

An in-memory SQL store adapts MySQL cursor syntax; delivery is a local port double.
No provider or workspace database is contacted.
"""

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from infrastructure.mysql.replacement_matching_query import candidate_contact_open
from subsystems.line import candidate_contact_coordination_worker as worker_module
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
CASE = 'R04-SYNTHETIC'


class _Cursor:
    def __init__(self, store):
        self.store = store
        self.cursor = store.db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cursor.close()

    @property
    def rowcount(self):
        return self.cursor.rowcount

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    def execute(self, sql, args=()):
        self.store.queries.append(sql)
        if sql.startswith('UPDATE line_delivery_tasks task JOIN'):
            # SQLite's UPDATE FROM spelling; preserve the production WHERE predicate verbatim.
            _, _, tail = sql.partition('SET ')
            assignments, _, predicate = tail.partition(' WHERE ')
            sql = ('UPDATE line_delivery_tasks AS task SET ' + assignments.replace('task.', '')
                   + ' FROM caregiver_candidate_contact_pools pool JOIN orders ON orders.case_no=pool.case_no '
                   + "WHERE CAST(SUBSTRING_INDEX(task.source_aggregate_identity,':',1) AS UNSIGNED)=pool.id AND " + predicate)
        sql = sql.replace(' FOR UPDATE', '').replace('INSERT IGNORE', 'INSERT OR IGNORE').replace('%s', '?')
        sql = re.sub(r'CAST\(([^)]+) AS CHAR CHARACTER SET utf8mb4\) COLLATE utf8mb4_unicode_ci', r'CAST(\1 AS TEXT)', sql)
        self.cursor.execute(sql, tuple(value.isoformat() if isinstance(value, datetime) else value for value in args))

    def _row(self, row):
        if row is None:
            return None
        result = dict(row)
        for key in ('occurred_at', 'sent_at_utc', 'created_at'):
            if result.get(key) is not None:
                result[key] = datetime.fromisoformat(result[key])
        return result

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return tuple(self._row(row) for row in self.cursor.fetchall())


class _Store:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.create_function('JSON_UNQUOTE', 1, lambda value: value)
        self.db.create_function('SUBSTRING_INDEX', 3, lambda value, separator, count: separator.join(value.split(separator)[:count]))
        self.queries = []
        self.commits = 0
        self.db.executescript('''
            CREATE TABLE orders(case_no TEXT PRIMARY KEY,status TEXT);
            CREATE TABLE scheduling_aggregates(case_no TEXT,effective_generation_id INTEGER);
            CREATE TABLE scheduling_service_before_replacement_events(id INTEGER,case_no TEXT,replacement_generation_id INTEGER,scenario TEXT);
            CREATE TABLE scheduling_service_before_replacement_receipts(replacement_event_id INTEGER);
            CREATE TABLE case_staff_assignments(case_no TEXT,generation_id INTEGER);
            CREATE TABLE caregiver_candidate_contact_pools(id INTEGER PRIMARY KEY,case_no TEXT);
            CREATE TABLE staff(id INTEGER PRIMARY KEY,name TEXT,line_user_id TEXT);
            CREATE TABLE line_identity_role_bindings(subject_type TEXT,subject_reference TEXT,binding_status TEXT,line_user_id TEXT);
            CREATE TABLE caregiver_candidate_contact_entries(id INTEGER PRIMARY KEY,pool_id INTEGER,staff_id INTEGER,active_marker INTEGER,status TEXT);
            CREATE TABLE caregiver_candidate_contact_events(id INTEGER PRIMARY KEY,pool_id INTEGER,candidate_id INTEGER,event_type TEXT,event_key TEXT UNIQUE,actor TEXT,payload TEXT,occurred_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE line_alert_notification_targets(id INTEGER,group_id TEXT,target_type TEXT,enabled INTEGER);
            CREATE TABLE line_delivery_tasks(id INTEGER PRIMARY KEY,source_aggregate_type TEXT,source_aggregate_identity TEXT,idempotency_key TEXT UNIQUE,processing_status TEXT,sent_at_utc TEXT,error_code TEXT,error_message TEXT,lease_owner TEXT,lease_acquired_at_utc TEXT,lease_expires_at_utc TEXT);
            CREATE TABLE order_terms_apply_receipts(id INTEGER PRIMARY KEY,case_no TEXT,correlation_id TEXT,created_at TEXT);
        ''')
        self.db.execute('INSERT INTO orders VALUES (?,?)', (CASE, '訂單成立'))
        self.db.execute('INSERT INTO scheduling_aggregates VALUES (?,2)', (CASE,))
        self.db.execute("INSERT INTO scheduling_service_before_replacement_events VALUES (9,?,2,'R-04')", (CASE,))
        self.db.execute('INSERT INTO scheduling_service_before_replacement_receipts VALUES (9)')
        self.db.execute('INSERT INTO caregiver_candidate_contact_pools VALUES (100,?)', (CASE,))
        self.db.execute("INSERT INTO staff VALUES (7,'Synthetic caregiver','U-synthetic')")
        self.db.execute("INSERT INTO line_identity_role_bindings VALUES ('staff','7','bound','U-synthetic')")
        self.db.execute("INSERT INTO caregiver_candidate_contact_entries VALUES (7,100,7,1,'active')")
        self.db.execute("INSERT INTO line_alert_notification_targets VALUES (1,'C-synthetic-group','group',1)")
        self.db.execute("INSERT INTO line_delivery_tasks(id,source_aggregate_type,source_aggregate_identity,processing_status,sent_at_utc) VALUES (70,'candidate_matching_willingness_card','initial','sent',?)", ((NOW - timedelta(hours=25)).isoformat(),))
        self.event(10, 'info_1_sent', {'line_task_id': 70}, NOW - timedelta(hours=25))
        self.db.commit()

    def event(self, event_id, kind, payload, occurred_at):
        self.db.execute('INSERT INTO caregiver_candidate_contact_events VALUES (?,100,7,?,?,?, ?,?)',
                        (event_id, kind, f'synthetic:{event_id}', 'synthetic', json.dumps(payload), occurred_at.isoformat()))

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def close(self):
        pass  # Request-scoped handles share this fixture's in-memory database.

    def notification(self):
        return self.db.execute("SELECT * FROM line_delivery_tasks WHERE source_aggregate_type='candidate_contact_manual_followup'").fetchone()


@pytest.fixture
def store(monkeypatch):
    store = _Store()

    class DeliveryPort:
        def __init__(self, connection):
            assert connection is store

        def enqueue(self, request):
            cursor = store.db.execute(
                "INSERT OR IGNORE INTO line_delivery_tasks(source_aggregate_type,source_aggregate_identity,idempotency_key,processing_status) VALUES (?,?,?,'pending')",
                (request.source_aggregate_type, request.source_aggregate_identity, request.idempotency_key.value),
            )
            return SimpleNamespace(outcome='created' if cursor.rowcount else 'existing')

    monkeypatch.setattr(worker_module, 'MySqlLineDeliveryTaskRepository', DeliveryPort)
    monkeypatch.setenv('LINE_LIFF_ID', 'synthetic-liff')
    yield store
    store.db.close()


def _worker(store):
    return worker_module.CandidateContactCoordinationWorker(lambda: store, lambda: NOW, batch_size=1)


def test_r04_timeout_becomes_liff_followup_without_cancelling_or_duplicating_notice(store, monkeypatch):
    # Ineligible earlier pools must not use up the worker's one-row batch.
    for pool_id in range(1, 30):
        store.db.execute('INSERT INTO orders VALUES (?,?)', (f'INELIGIBLE-{pool_id}', '訂單成立'))
        store.db.execute('INSERT INTO caregiver_candidate_contact_pools VALUES (?,?)', (pool_id, f'INELIGIBLE-{pool_id}'))
    assert _worker(store).run_once() == 2  # Timeout event plus one durable group intent.
    notice = dict(store.notification())
    assert notice['processing_status'] == 'pending'
    assert _worker(store).run_once() == 0
    assert dict(store.notification()) == notice
    assert store.db.execute("SELECT COUNT(*) FROM caregiver_candidate_contact_events WHERE actor='system:candidate-contact-timeout'").fetchone()[0] == 1

    from api.routes import line_mobile_admin
    monkeypatch.setattr(line_mobile_admin, 'get_connection', lambda: store)
    monkeypatch.setattr(line_mobile_admin, '_mobile_admin_context', lambda *args: (None, None))
    result = line_mobile_admin.matching_followups(line_mobile_admin._LiffAuthRequest(line_id_token='synthetic-token'))
    assert result.data['total'] == 1
    item = result.data['items'][0]
    assert item['case_no'] == CASE
    assert item['timed_out_count'] == 1
    assert item['notification_status'] == 'pending'


@pytest.mark.parametrize('change', ['assignment', 'generation', 'receipt', 'scenario', 'cancelled', 'in_service'])
def test_invalidated_r04_is_cancelled_before_delivery_and_disappears_from_liff(store, monkeypatch, change):
    assert _worker(store).run_once() == 2
    if change == 'assignment':
        store.db.execute('INSERT INTO case_staff_assignments VALUES (?,2)', (CASE,))
    elif change == 'generation':
        store.db.execute('UPDATE scheduling_aggregates SET effective_generation_id=3')
    elif change == 'receipt':
        store.db.execute('DELETE FROM scheduling_service_before_replacement_receipts')
    elif change == 'scenario':
        store.db.execute("UPDATE scheduling_service_before_replacement_events SET scenario='R-03'")
    else:
        store.db.execute('UPDATE orders SET status=?', ('訂單取消' if change == 'cancelled' else '服務中',))
    sent = []

    def deliver():
        if store.notification()['processing_status'] == 'pending':
            sent.append('provider would have been called')
        return len(sent)

    runtime = CanonicalLineWorkerRuntime(SimpleNamespace(run_once=lambda: 0), SimpleNamespace(run_once=deliver),
        SimpleNamespace(wait=lambda timeout: None), lambda: None, lambda heartbeat: None, 'synthetic-worker',
        additional_workers={'candidate_contact_coordination': _worker(store)})
    counts = runtime.run_once()
    assert counts['candidate_contact_coordination'] == 1
    assert counts['delivery_tasks'] == 0
    assert not sent
    assert store.notification()['processing_status'] == 'cancelled'
    assert worker_module.query_manual_followups(lambda: store, NOW).total == 0

    from api.routes import line_mobile_admin
    monkeypatch.setattr(line_mobile_admin, 'get_connection', lambda: store)
    with pytest.raises(HTTPException) as error:
        line_mobile_admin._matching_operation(100, CASE)
    assert error.value.status_code == 409


def test_r04_liff_adjustment_operation_keeps_post_answer_terms_receipt_gate(store, monkeypatch):
    store.event(20, 'willingness_changed', {'response_kind': 'coordination_requested', 'willingness': 'unwilling',
        'issues': [{'mode': 'condition_adjustment', 'category': 'cooking_requirement', 'detail': 'Synthetic adjustment'}]}, NOW - timedelta(hours=2))
    store.event(30, 'willingness_changed', {'response_kind': 'adjustment_batch_dispatched', 'source_response_event_ids': [20]}, NOW - timedelta(hours=1))
    store.event(31, 'willingness_changed', {'response_kind': 'adjustment_customer_answer', 'decision': 'can_adjust',
        'source_coordination_event_id': 30}, NOW - timedelta(minutes=30))
    assert _worker(store).run_once() == 1
    from api.routes import line_mobile_admin
    monkeypatch.setattr(line_mobile_admin, 'get_connection', lambda: store)
    blocked = line_mobile_admin._matching_operation(100, CASE)
    assert not blocked.recontact_allowed
    store.db.execute('INSERT INTO order_terms_apply_receipts VALUES (1,?,?,?)',
        (CASE, 'mobile-matching-followup:100:synthetic', (NOW - timedelta(minutes=10)).isoformat()))
    ready = line_mobile_admin._matching_operation(100, CASE)
    assert ready.recontact_allowed
    assert ready.candidates[0].candidate_id == 7
    assert worker_module.query_manual_followups(lambda: store, NOW).items[0].action_required == 'modify_then_recontact'


def test_scan_predicate_matches_per_case_r04_eligibility(store):
    with store.cursor() as cursor:
        assert candidate_contact_open(cursor, CASE, '訂單成立')
    store.db.execute('DELETE FROM scheduling_service_before_replacement_receipts')
    with store.cursor() as cursor:
        assert not candidate_contact_open(cursor, CASE, '訂單成立')
    assert _worker(store).run_once() == 0


@pytest.mark.parametrize('status,expected', [
    ('pending', 'cancelled'), ('retryable_failed', 'cancelled'),
    ('sent', 'sent'), ('processing', 'processing'),
])
def test_invalid_r04_cancellation_keeps_existing_delivery_status_boundaries(store, status, expected):
    assert _worker(store).run_once() == 2
    store.db.execute("UPDATE line_delivery_tasks SET processing_status=? WHERE source_aggregate_type='candidate_contact_manual_followup'", (status,))
    store.db.execute('DELETE FROM scheduling_service_before_replacement_receipts')
    _worker(store).run_once()
    assert store.notification()['processing_status'] == expected
    assert store.db.execute('SELECT processing_status FROM line_delivery_tasks WHERE id=70').fetchone()[0] == 'sent'
