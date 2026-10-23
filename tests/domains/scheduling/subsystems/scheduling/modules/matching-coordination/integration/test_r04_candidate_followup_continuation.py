"""Real SQL on an in-memory store; no workspace database or LINE provider is used."""
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from domains.line.identities import LineUserId
from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.scheduling.candidate_contact_response import parse_candidate_response
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.line import candidate_contact_response_application as intake
from subsystems.line.candidate_contact_coordination_worker import (
    CandidateContactCoordinationWorker, query_manual_followups, query_manual_followup_operation,
)
from subsystems.scheduling.candidate_adjustment_review import CandidateAdjustmentReviewApplication

NOW = datetime(2026, 10, 22, 4, tzinfo=timezone.utc)
CASE = 'R04-SYNTHETIC'


class _Cursor:
    def __init__(self, store):
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
        sql = sql.replace(' FOR UPDATE', '').replace('%s', '?')
        sql = sql.replace('UPDATE line_delivery_tasks task SET', 'UPDATE line_delivery_tasks AS task SET')
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
        self.db.create_function('JSON_LENGTH', 1, lambda value: len(json.loads(value)))
        self.db.create_function('SHA2', 2, lambda value, _: hashlib.sha256(value.encode()).hexdigest())
        self.db.executescript("""
            CREATE TABLE orders(case_no TEXT PRIMARY KEY,status TEXT,lifecycle_version INTEGER,client_id INTEGER,
              start_date TEXT,service_days INTEGER,service_hours_per_day REAL,requires_cooking INTEGER,floor_fee INTEGER);
            CREATE TABLE scheduling_aggregates(case_no TEXT,effective_generation_id INTEGER);
            CREATE TABLE scheduling_service_before_replacement_events(id INTEGER,case_no TEXT,replacement_generation_id INTEGER,scenario TEXT);
            CREATE TABLE scheduling_service_before_replacement_receipts(replacement_event_id INTEGER);
            CREATE TABLE case_staff_assignments(case_no TEXT,generation_id INTEGER);
            CREATE TABLE caregiver_candidate_contact_pools(id INTEGER PRIMARY KEY,case_no TEXT);
            CREATE TABLE staff(id INTEGER PRIMARY KEY,name TEXT,line_user_id TEXT);
            CREATE TABLE line_identity_role_bindings(subject_type TEXT,subject_reference TEXT,binding_status TEXT,line_user_id TEXT);
            CREATE TABLE caregiver_candidate_contact_entries(id INTEGER PRIMARY KEY,pool_id INTEGER,staff_id INTEGER,active_marker INTEGER,status TEXT);
            CREATE TABLE caregiver_candidate_contact_events(id INTEGER PRIMARY KEY,pool_id INTEGER,candidate_id INTEGER,event_type TEXT,event_key TEXT UNIQUE,actor TEXT,payload TEXT,occurred_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE line_delivery_tasks(id INTEGER PRIMARY KEY,source_aggregate_type TEXT,source_aggregate_identity TEXT,idempotency_key TEXT UNIQUE,processing_status TEXT,sent_at_utc TEXT,error_code TEXT,error_message TEXT,lease_owner TEXT,lease_acquired_at_utc TEXT,lease_expires_at_utc TEXT,payload_json TEXT);
        """)
        self.db.execute("INSERT INTO orders VALUES (?,'訂單成立',1,3,'2026-11-01',14,8,0,0)", (CASE,))
        self.db.execute('INSERT INTO scheduling_aggregates VALUES (?,2)', (CASE,))
        self.db.execute("INSERT INTO scheduling_service_before_replacement_events VALUES (9,?,2,'R-04')", (CASE,))
        self.db.execute('INSERT INTO scheduling_service_before_replacement_receipts VALUES (9)')
        self.db.execute('INSERT INTO caregiver_candidate_contact_pools VALUES (100,?)', (CASE,))
        for staff_id in (7, 8):
            self.db.execute('INSERT INTO staff VALUES (?,?,?)', (staff_id, f'Synthetic {staff_id}', f'U-{staff_id}'))
            self.db.execute("INSERT INTO line_identity_role_bindings VALUES ('staff',?,'bound',?)", (str(staff_id), f'U-{staff_id}'))
            self.db.execute("INSERT INTO caregiver_candidate_contact_entries VALUES (?,100,?,1,'active')", (staff_id, staff_id))
        self.db.execute("INSERT INTO line_identity_role_bindings VALUES ('customer','3','bound','U-customer')")
        self.db.execute("INSERT INTO line_delivery_tasks(id,source_aggregate_type,source_aggregate_identity,processing_status,sent_at_utc) VALUES (70,'candidate_matching_willingness_card','initial','sent',?)", ((NOW - timedelta(hours=25)).isoformat(),))
        self.event(10, 'info_1_sent', {'line_task_id': 70}, NOW - timedelta(hours=25))
        self.db.commit()
    def event(self, event_id, kind, payload, occurred_at=NOW):
        self.db.execute('INSERT INTO caregiver_candidate_contact_events VALUES (?,100,7,?,?,?,?,?)',
                        (event_id, kind, f'synthetic:{event_id}', 'synthetic', json.dumps(payload), occurred_at.isoformat()))
    def cursor(self):
        return _Cursor(self)
    def begin(self):
        self.db.execute('BEGIN')
    def commit(self):
        self.db.commit()
    def rollback(self):
        self.db.rollback()
    def close(self):
        pass


@pytest.fixture
def store(monkeypatch):
    store = _Store()
    class DeliveryPort:
        def __init__(self, connection):
            assert connection is store
        def enqueue(self, request):
            store.db.execute("INSERT OR IGNORE INTO line_delivery_tasks(source_aggregate_type,source_aggregate_identity,idempotency_key,processing_status,payload_json) VALUES (?,?,?,'pending',?)",
                             (request.source_aggregate_type, request.source_aggregate_identity, request.idempotency_key.value, request.payload_json))
            row = store.db.execute('SELECT id FROM line_delivery_tasks WHERE idempotency_key=?', (request.idempotency_key.value,)).fetchone()
            return SimpleNamespace(task_id=SimpleNamespace(value=row['id']))
    monkeypatch.setattr(intake, 'MySqlLineDeliveryTaskRepository', DeliveryPort)
    monkeypatch.setenv('LINE_LIFF_ID', 'synthetic-liff')
    yield store
    store.db.close()


def app(store):
    return intake.CandidateContactResponseApplication(lambda: store, lambda: NOW)


def test_question_pagination_counts_distinct_work_on_same_case_and_removes_answered_items(store):
    first_id = adjustment(store)
    payload = store.db.execute('SELECT payload FROM caregiver_candidate_contact_events WHERE id=?', (first_id,)).fetchone()[0]
    for index in range(100):
        candidate = 1000 + index
        store.db.execute('INSERT INTO staff VALUES (?,?,NULL)', (candidate, f'Public staff {index}'))
        store.db.execute("INSERT INTO caregiver_candidate_contact_entries VALUES (?,100,?,1,'active')", (candidate, candidate))
        store.db.execute("INSERT INTO caregiver_candidate_contact_events VALUES (?,100,?,'willingness_changed',?,'synthetic',?,?)",
                         (2000 + index, candidate, f'public-question-{index}', payload, NOW.isoformat()))
    store.db.commit()
    seen = []
    for page in range(1, 6):
        result = app(store).query_staff_questions(page=page, page_size=25)
        assert result['total'] == 101
        assert all(item['case_no'] == CASE for item in result['items'])
        seen.extend(item['question_id'] for item in result['items'])
    assert len(seen) == len(set(seen)) == 101
    store.event(5000, 'willingness_changed', {'response_kind': 'information_answered'})
    result = app(store).query_staff_questions(page=1, page_size=25)
    assert result['total'] == 100 and first_id not in [item['question_id'] for item in result['items']]


def test_reminder_pagination_exposes_every_pool_and_keeps_full_total(store):
    for index in range(100):
        case = f'PUBLIC-REMINDER-{index:03d}'
        pool, candidate, task = 1000 + index, 2000 + index, 3000 + index
        store.db.execute("INSERT INTO orders(case_no,status) VALUES (?,'洽談中')", (case,))
        store.db.execute('INSERT INTO caregiver_candidate_contact_pools VALUES (?,?)', (pool, case))
        store.db.execute("INSERT INTO caregiver_candidate_contact_entries VALUES (?,?,7,1,'active')", (candidate, pool))
        store.db.execute("INSERT INTO line_delivery_tasks(id,processing_status,sent_at_utc) VALUES (?,'sent',?)", (task, (NOW - timedelta(hours=25)).isoformat()))
        store.db.execute("INSERT INTO caregiver_candidate_contact_events VALUES (?, ?, ?, 'info_1_sent', ?, 'synthetic', ?, ?)",
                         (4000 + index, pool, candidate, f'public-reminder-{index}', json.dumps({'line_task_id': task}), NOW.isoformat()))
    seen = []
    for page in range(1, 6):
        result = query_manual_followups(lambda: store, NOW, limit=25, page=page)
        assert result.total == 101
        seen.extend(item.pool_id for item in result.items)
    assert len(seen) == len(set(seen)) == 101


def adjustment(store):
    response = parse_candidate_response(no_interest=False, issues=[{
        'category': 'daily_service_hours', 'mode': 'condition_adjustment', 'detail': '想改為六小時'
    }])
    return app(store).submit(hashlib.sha256(b'synthetic:10').hexdigest(), LineUserId('U-7'), response, IdempotencyKey('adjustment-intake'))['event_id']


def ask(store, question_id, key='round-one'):
    return app(store).send_staff_information(question_id, 'customer', '請提供目前可配合的時數與時段。', 'admin:1', IdempotencyKey(key))


def answer(store, key='round-one', text='更新為每天六小時，09:00 到 15:00。'):
    return app(store).submit_customer_answer(hashlib.sha256(key.encode()).hexdigest(), LineUserId('U-customer'), text, IdempotencyKey('answer-' + key))


class TermsOwnerPort:
    """A transaction-aware Orders port double; all coordination SQL remains production code."""
    fail = False
    def __init__(self, store):
        self.store = store
        self.calls = []
    def preview(self, case_no, proposed):
        row = self.store.db.execute('SELECT * FROM orders WHERE case_no=?', (case_no,)).fetchone()
        before = OrderTerms(date.fromisoformat(row['start_date']), row['service_days'], row['service_hours_per_day'], MoneyNTD(row['floor_fee']), ServiceTimeTerms(time(9), time(17), 0), bool(row['requires_cooking']))
        return SimpleNamespace(before=before, after=proposed, order_version=row['lifecycle_version'], scheduling_version=0,
            client_finance_version=None, payroll_version=None, fingerprint=PreviewFingerprint('f'*64), requires_formal_apply=False)
    def apply_in_current_uow(self, request):
        assert self.store.db.in_transaction
        self.calls.append(request)
        self.store.db.execute('UPDATE orders SET service_hours_per_day=?,lifecycle_version=lifecycle_version+1 WHERE case_no=?', (request.proposed_terms.service_hours_per_day, request.case_no))
        if self.fail:
            raise RuntimeError('owner apply failed')
        return SimpleNamespace(order_version=request.expected_order_version.value+1)


def proposed():
    return OrderTerms(date(2026, 11, 1), 14, 6, MoneyNTD(0), ServiceTimeTerms(time(9), time(15), 0), False)


def test_24_hour_reminder_is_read_only_and_does_not_block_or_send(store):
    reminders = query_manual_followups(lambda: store, NOW)
    assert reminders.total == 1 and reminders.items[0].reminder_count == 1
    assert store.db.execute("SELECT COUNT(*) FROM caregiver_candidate_contact_events").fetchone()[0] == 1
    assert app(store).query(hashlib.sha256(b'synthetic:10').hexdigest(), LineUserId('U-7'))['status'] == 'open'
    question_id = adjustment(store)
    assert question_id > 10
    assert query_manual_followups(lambda: store, NOW).total == 0
    assert store.db.execute('SELECT COUNT(*) FROM line_delivery_tasks').fetchone()[0] == 1


def test_customer_conditions_can_be_negotiated_again_and_old_round_cannot_answer(store):
    question_id = adjustment(store)
    ask(store, question_id)
    first = answer(store)
    item = app(store).query_staff_questions()['items'][0]
    assert item['customer_answer_event_id'] == first['event_id'] and item['customer_answer'].startswith('更新為')
    ask(store, question_id, 'round-two')
    old_reference = hashlib.sha256(b'round-one').hexdigest()
    assert app(store).query_customer(old_reference, LineUserId('U-customer'))['status'] == 'closed'
    with pytest.raises(ValueError, match='question_closed'):
        app(store).submit_customer_answer(old_reference, LineUserId('U-customer'), '舊連結不能修改本輪條件', IdempotencyKey('stale-answer'))
    second = answer(store, 'round-two', '新條件：每天六小時。')
    port = TermsOwnerPort(store)
    reviewer = CandidateAdjustmentReviewApplication(store, port)
    with pytest.raises(ValueError, match='round_stale'):
        reviewer.approve(CASE, 100, first['event_id'], proposed(), 1, ActorContext('union:1'), IdempotencyKey('old-approval'))
    assert second['event_id'] > first['event_id'] and port.calls == []
    assert store.db.execute('SELECT lifecycle_version FROM orders').fetchone()[0] == 1


def test_approval_atomically_updates_orders_then_allows_selected_caregiver_recontact(store):
    question_id = adjustment(store)
    ask(store, question_id)
    reply = answer(store)
    before = query_manual_followup_operation(lambda: store, 100, CASE, reply['event_id'])
    assert not before.recontact_allowed
    port = TermsOwnerPort(store)
    reviewer = CandidateAdjustmentReviewApplication(store, port)
    result = reviewer.approve(CASE, 100, reply['event_id'], proposed(), 1, ActorContext('union:1'), IdempotencyKey('approve-current'))
    assert result['status'] == 'approved'
    row = store.db.execute('SELECT service_hours_per_day,lifecycle_version FROM orders').fetchone()
    assert tuple(row) == (6, 2)
    operation = query_manual_followup_operation(lambda: store, 100, CASE, reply['event_id'])
    assert operation.recontact_allowed and operation.customer_new_conditions.startswith('更新為')
    assert [item.candidate_id for item in operation.candidates] == [7, 8]
    assert len(port.calls) == 1 and port.calls[0].requires_formal_apply is False
    replay = reviewer.approve(CASE, 100, reply['event_id'], proposed(), 1, ActorContext('union:1'), IdempotencyKey('approve-current'))
    assert replay['status'] == 'idempotent_replay' and len(port.calls) == 1
    with pytest.raises(ValueError, match='idempotency_conflict'):
        reviewer.approve(CASE, 100, reply['event_id'], proposed(), 2, ActorContext('union:1'), IdempotencyKey('approve-current'))


def test_failed_order_apply_rolls_back_both_new_conditions_and_approval(store):
    question_id = adjustment(store)
    ask(store, question_id)
    reply = answer(store)
    port = TermsOwnerPort(store)
    port.fail = True
    with pytest.raises(RuntimeError, match='owner apply failed'):
        CandidateAdjustmentReviewApplication(store, port).approve(CASE, 100, reply['event_id'], proposed(), 1, ActorContext('union:1'), IdempotencyKey('failed-approval'))
    assert tuple(store.db.execute('SELECT service_hours_per_day,lifecycle_version FROM orders').fetchone()) == (8, 1)
    assert not app(store).query_staff_questions()['items'][0]['review_completed']
    assert not query_manual_followup_operation(lambda: store, 100, CASE, reply['event_id']).recontact_allowed


def test_wrong_customer_cannot_answer_and_new_order_version_blocks_old_review(store):
    question_id = adjustment(store)
    ask(store, question_id)
    with pytest.raises(ValueError, match='recipient_mismatch'):
        app(store).query_customer(hashlib.sha256(b'round-one').hexdigest(), LineUserId('U-other'))
    reply = answer(store)
    store.db.execute('UPDATE orders SET lifecycle_version=2')
    store.db.commit()
    port = TermsOwnerPort(store)
    with pytest.raises(ValueError, match='order_conflict'):
        CandidateAdjustmentReviewApplication(store, port).approve(CASE, 100, reply['event_id'], proposed(), 1, ActorContext('union:1'), IdempotencyKey('stale-order'))
    assert port.calls == []


def test_late_approval_event_failure_also_rolls_back_the_orders_update(store, monkeypatch):
    question_id = adjustment(store)
    ask(store, question_id)
    reply = answer(store)
    original = _Cursor.execute
    def fail_approval(cursor, sql, args=()):
        if sql.startswith('INSERT INTO caregiver_candidate_contact_events') and 'adjustment_approved' in str(args[-1]):
            raise RuntimeError('approval storage failed')
        return original(cursor, sql, args)
    monkeypatch.setattr(_Cursor, 'execute', fail_approval)
    port = TermsOwnerPort(store)
    with pytest.raises(RuntimeError, match='approval storage failed'):
        CandidateAdjustmentReviewApplication(store, port).approve(CASE, 100, reply['event_id'], proposed(), 1, ActorContext('union:1'), IdempotencyKey('late-failure'))
    assert len(port.calls) == 1
    assert tuple(store.db.execute('SELECT service_hours_per_day,lifecycle_version FROM orders').fetchone()) == (8, 1)
    assert not query_manual_followup_operation(lambda: store, 100, CASE, reply['event_id']).recontact_allowed


def test_old_caregiver_card_cannot_answer_a_refreshed_service_period(store):
    store.event(20, 'willingness_changed', {'response_kind': 'candidate_period_refreshed'})
    store.db.commit()
    with pytest.raises(ValueError, match='period_changed'):
        app(store).query(hashlib.sha256(b'synthetic:10').hexdigest(), LineUserId('U-7'))
