"""Real SQL on an in-memory store; no workspace database or LINE provider is used."""
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from subsystems.line.candidate_contact_coordination_worker import (
    CandidateContactCoordinationWorker, query_manual_followups,
)

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
