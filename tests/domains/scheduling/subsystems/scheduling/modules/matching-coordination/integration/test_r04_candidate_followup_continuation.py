"""Real SQL on an in-memory store; no workspace database or LINE provider is used."""
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from domains.scheduling.matching_communication import CandidateMatchingError
from infrastructure.mysql.replacement_matching_query import candidate_matching_blocker
from subsystems.line.candidate_contact_coordination_worker import (
    CandidateContactCoordinationWorker, query_manual_followups,
)
from subsystems.scheduling import candidate_contact_pool_workflow

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
        self.db.executescript("""
            CREATE TABLE orders(case_no TEXT PRIMARY KEY,status TEXT,lifecycle_version INTEGER,client_id INTEGER,
              start_date TEXT,service_days INTEGER,service_hours_per_day REAL,requires_cooking INTEGER,floor_fee INTEGER,
              actual_start_date TEXT,actual_end_date TEXT);
            CREATE TABLE scheduling_aggregates(case_no TEXT,effective_generation_id INTEGER,aggregate_version INTEGER);
            CREATE TABLE scheduling_generations(id INTEGER,case_no TEXT,generation_number INTEGER,
              resulting_aggregate_version INTEGER,status TEXT,effective_marker INTEGER);
            CREATE TABLE scheduling_service_before_replacement_events(id INTEGER,case_no TEXT,replacement_generation_id INTEGER,scenario TEXT);
            CREATE TABLE scheduling_service_before_replacement_receipts(replacement_event_id INTEGER);
            CREATE TABLE case_staff_assignments(case_no TEXT,generation_id INTEGER,status TEXT);
            CREATE TABLE order_lifecycle_control_state(case_no TEXT,control_type TEXT,control_key TEXT,state TEXT,current_event_id INTEGER);
            CREATE TABLE order_lifecycle_control_events(id INTEGER,case_no TEXT,control_type TEXT,control_key TEXT,action TEXT);
            CREATE TABLE order_cancellation_apply_receipts(case_no TEXT,cancellation_event_id INTEGER,cancellation_control_event_id INTEGER,
              scheduling_command_receipt_id INTEGER,scheduling_version INTEGER,scheduling_generation INTEGER,official_service_day_count INTEGER);
            CREATE TABLE order_reopen_apply_receipts(case_no TEXT,cancellation_control_event_id INTEGER,cancellation_event_id INTEGER,lifecycle_status TEXT);
            CREATE TABLE scheduling_command_receipts(id INTEGER,case_no TEXT,resulting_generation_id INTEGER,resulting_scheduling_version INTEGER);
            CREATE TABLE order_service_data_locks(case_no TEXT);
            CREATE TABLE caregiver_candidate_contact_pools(id INTEGER PRIMARY KEY,case_no TEXT);
            CREATE TABLE staff(id INTEGER PRIMARY KEY,name TEXT,line_user_id TEXT,status TEXT DEFAULT 'active');
            CREATE TABLE staff_lifecycle_states(staff_id INTEGER,lifecycle_state TEXT);
            CREATE TABLE line_identity_role_bindings(subject_type TEXT,subject_reference TEXT,binding_status TEXT,line_user_id TEXT);
            CREATE TABLE caregiver_candidate_contact_entries(id INTEGER PRIMARY KEY,pool_id INTEGER,staff_id INTEGER,active_marker INTEGER,
              status TEXT DEFAULT 'active',service_start_date TEXT,service_end_date TEXT,coverage_fingerprint TEXT);
            CREATE TABLE caregiver_candidate_contact_events(id INTEGER PRIMARY KEY,pool_id INTEGER,candidate_id INTEGER,event_type TEXT,event_key TEXT UNIQUE,actor TEXT,payload TEXT,occurred_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE line_delivery_tasks(id INTEGER PRIMARY KEY,source_aggregate_type TEXT,source_aggregate_identity TEXT,idempotency_key TEXT UNIQUE,processing_status TEXT,sent_at_utc TEXT,error_code TEXT,error_message TEXT,lease_owner TEXT,lease_acquired_at_utc TEXT,lease_expires_at_utc TEXT,payload_json TEXT);
        """)
        self.db.execute("INSERT INTO orders VALUES (?,'訂單成立',1,3,'2026-11-01',14,8,0,0,NULL,NULL)", (CASE,))
        self.db.execute('INSERT INTO scheduling_aggregates VALUES (?,2,7)', (CASE,))
        self.db.execute("INSERT INTO scheduling_generations VALUES (2,?,8,7,'effective',1)", (CASE,))
        self.db.execute("INSERT INTO scheduling_service_before_replacement_events VALUES (9,?,2,'R-04')", (CASE,))
        self.db.execute('INSERT INTO scheduling_service_before_replacement_receipts VALUES (9)')
        self.db.execute('INSERT INTO caregiver_candidate_contact_pools VALUES (100,?)', (CASE,))
        for staff_id in (7, 8):
            self.db.execute('INSERT INTO staff(id,name,line_user_id) VALUES (?,?,?)', (staff_id, f'Synthetic {staff_id}', f'U-{staff_id}'))
            self.db.execute("INSERT INTO line_identity_role_bindings VALUES ('staff',?,'bound',?)", (str(staff_id), f'U-{staff_id}'))
            self.db.execute("INSERT INTO caregiver_candidate_contact_entries(id,pool_id,staff_id,active_marker) VALUES (?,100,?,1)", (staff_id, staff_id))
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
def store():
    store = _Store()
    yield store
    store.db.close()


def test_reminder_pagination_exposes_every_pool_and_keeps_full_total(store):
    for index in range(100):
        case = f'PUBLIC-REMINDER-{index:03d}'
        pool, candidate, task = 1000 + index, 2000 + index, 3000 + index
        store.db.execute("INSERT INTO orders(case_no,status) VALUES (?,'洽談中')", (case,))
        store.db.execute('INSERT INTO caregiver_candidate_contact_pools VALUES (?,?)', (pool, case))
        store.db.execute("INSERT INTO caregiver_candidate_contact_entries(id,pool_id,staff_id,active_marker) VALUES (?,?,7,1)", (candidate, pool))
        store.db.execute("INSERT INTO line_delivery_tasks(id,processing_status,sent_at_utc) VALUES (?,'sent',?)", (task, (NOW - timedelta(hours=25)).isoformat()))
        store.db.execute("INSERT INTO caregiver_candidate_contact_events VALUES (?, ?, ?, 'info_1_sent', ?, 'synthetic', ?, ?)",
                         (4000 + index, pool, candidate, f'public-reminder-{index}', json.dumps({'line_task_id': task}), NOW.isoformat()))
    seen = []
    for page in range(1, 6):
        result = query_manual_followups(lambda: store, NOW, limit=25, page=page)
        assert result.total == 101
        seen.extend(item.pool_id for item in result.items)
    assert len(seen) == len(set(seen)) == 101


def test_24_hour_reminder_is_read_only_and_disappears_after_either_intent(store):
    reminders = query_manual_followups(lambda: store, NOW)
    assert reminders.total == 1 and reminders.items[0].reminder_count == 1
    assert store.db.execute("SELECT COUNT(*) FROM caregiver_candidate_contact_events").fetchone()[0] == 1
    store.event(11, "willingness_changed", {"willingness": "unwilling"})
    assert query_manual_followups(lambda: store, NOW).total == 0
    assert store.db.execute("SELECT COUNT(*) FROM line_delivery_tasks").fetchone()[0] == 1


def test_worker_cancels_retired_coordination_and_recontact_without_touching_initial_package(store):
    requests = [
        ("candidate_contact_question", "question", "pending"),
        ("candidate_contact_answer", "answer", "retryable_failed"),
        ("candidate_contact_staff_review", "review", "pending"),
        ("candidate_matching_willingness_card", "mobile-matching-followup:100:11:7:info1", "pending"),
        ("candidate_matching_willingness_card", "candidate-information-7-original", "pending"),
        ("candidate_contact_question", "historical", "sent"),
    ]
    store.db.executemany(
        "INSERT INTO line_delivery_tasks(source_aggregate_type,source_aggregate_identity,processing_status) VALUES (?,?,?)",
        requests,
    )
    store.db.commit()
    assert CandidateContactCoordinationWorker(lambda: store, lambda: NOW).run_once() == 4
    assert [row[0] for row in store.db.execute("SELECT processing_status FROM line_delivery_tasks WHERE id > 70 ORDER BY id")] == [
        "cancelled", "cancelled", "cancelled", "cancelled", "pending", "sent",
    ]


def _seed_reopen(store, *, scheduled=True):
    store.db.execute("UPDATE scheduling_generations SET status='cancelled',effective_marker=NULL WHERE id=2")
    store.db.execute("DELETE FROM scheduling_aggregates")
    if scheduled:
        store.db.execute("INSERT INTO scheduling_generations VALUES (3,?,9,8,'effective',1)", (CASE,))
        store.db.execute("INSERT INTO scheduling_aggregates VALUES (?,3,8)", (CASE,))
        store.db.execute("INSERT INTO scheduling_command_receipts VALUES (30,?,3,8)", (CASE,))
    store.db.execute("INSERT INTO order_lifecycle_control_events VALUES (31,?,'cancellation','order_cancelled','activate')", (CASE,))
    store.db.execute("INSERT INTO order_lifecycle_control_events VALUES (32,?,'cancellation','order_cancelled','clear')", (CASE,))
    store.db.execute("INSERT INTO order_lifecycle_control_state VALUES (?,'cancellation','order_cancelled','cleared',32)", (CASE,))
    store.db.execute(
        "INSERT INTO order_cancellation_apply_receipts VALUES (?,40,31,?,?,?,0)",
        (CASE, *((30, 8, 9) if scheduled else (None, None, None))),
    )
    store.db.execute("INSERT INTO order_reopen_apply_receipts VALUES (?,32,40,'訂單成立')", (CASE,))


@pytest.mark.parametrize(("change", "blocker"), [
    (None, None),
    ("DELETE FROM order_reopen_apply_receipts", "candidate_contact_order_not_negotiating"),
    ("UPDATE order_lifecycle_control_state SET state='active',current_event_id=31", "candidate_contact_order_not_negotiating"),
    ("UPDATE order_lifecycle_control_state SET current_event_id=33", "candidate_contact_order_not_negotiating"),
    ("UPDATE scheduling_aggregates SET aggregate_version=9", "candidate_contact_order_not_negotiating"),
    ("UPDATE scheduling_aggregates SET effective_generation_id=4", "candidate_matching_data_needs_review"),
    ("INSERT INTO case_staff_assignments SELECT case_no,3,'planned' FROM orders", "candidate_matching_assignment_present"),
    ("INSERT INTO case_staff_assignments SELECT case_no,3,'cancelled' FROM orders", "candidate_matching_data_needs_review"),
    ("INSERT INTO case_staff_assignments SELECT case_no,3,'replaced' FROM orders", "candidate_matching_data_needs_review"),
    ("INSERT INTO case_staff_assignments SELECT case_no,3,'unknown' FROM orders", "candidate_matching_data_needs_review"),
    ("INSERT INTO case_staff_assignments SELECT case_no,2,'planned' FROM orders", None),
    ("UPDATE orders SET actual_start_date='2026-11-01'", "candidate_matching_service_started"),
    ("INSERT INTO order_service_data_locks SELECT case_no FROM orders", "candidate_matching_service_started"),
])
def test_current_reopen_receipt_controls_query_and_apply(store, monkeypatch, change, blocker):
    _seed_reopen(store)
    with store.cursor() as cursor:
        assert candidate_matching_blocker(cursor, CASE) is None
    if change:
        store.db.execute(change)
    store.db.commit()

    assert query_manual_followups(lambda: store, NOW).total == (1 if blocker is None else 0)
    with store.cursor() as cursor:
        assert candidate_matching_blocker(cursor, CASE) == blocker
    if blocker is not None:
        before = tuple(store.db.iterdump())
        monkeypatch.setattr(candidate_contact_pool_workflow, "get_connection", lambda: store)
        with pytest.raises(CandidateMatchingError, match=blocker):
            candidate_contact_pool_workflow.add_candidates(
                CASE, [{"staff_id": 7, "start_date": "2026-11-01", "end_date": "2026-11-14"}],
                "operator", "candidate:blocked",
            )
        assert tuple(store.db.iterdump()) == before


def test_reopen_without_scheduling_and_duplicate_add_keep_history(store, monkeypatch):
    _seed_reopen(store, scheduled=False)
    store.db.execute("INSERT INTO staff(id,name) VALUES (9,'new candidate'),(10,'inactive candidate')")
    store.db.execute("INSERT INTO staff_lifecycle_states VALUES (10,'retired')")
    store.db.commit()
    with store.cursor() as cursor:
        assert candidate_matching_blocker(cursor, CASE) is None
    monkeypatch.setattr(candidate_contact_pool_workflow, "get_connection", lambda: store)
    start, end = "2026-11-01", "2026-11-14"
    monkeypatch.setattr(candidate_contact_pool_workflow, "_require_current_candidate",
                        lambda case, staff_id, start, end: {
                            "staff_id": staff_id, "case_period_start": start, "case_period_end": end,
                            "required_service_dates": [start], "supported_service_dates": [start],
                            "source_scheduling_version": 0,
                        })
    data = [{"staff_id": 9, "start_date": start, "end_date": end}]
    first = candidate_contact_pool_workflow.add_candidates(CASE, data, "operator", "candidate:add")
    before = tuple(store.db.iterdump())
    assert candidate_contact_pool_workflow.add_candidates(CASE, data, "operator", "candidate:add") == first
    with pytest.raises(CandidateMatchingError, match="candidate_staff_not_active"):
        candidate_contact_pool_workflow.add_candidates(
            CASE, [{**data[0], "staff_id": 10}], "operator", "candidate:inactive",
        )
    assert tuple(store.db.iterdump()) == before
    assert store.db.execute("SELECT staff_id FROM caregiver_candidate_contact_entries ORDER BY id").fetchall()[-1][0] == 9
