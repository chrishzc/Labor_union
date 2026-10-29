"""Retained historical review owner -> SQL transaction without customer delivery.

SQLite translates MySQL placeholders, locking and text casts. These tests call
the retained application directly; the retired HTTP route remains unavailable.
They do not establish MySQL isolation, HTTP authentication or mobile delivery.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3
import re
from domains.line.canonical_payload import canonical_line_payload_json
from types import SimpleNamespace
from domains.line.configuration import LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision

import pytest

from api.dependencies import staff_leave_intake as composition
from api.routes import staff_leave_management as route
from infrastructure.mysql import line_unit_of_work as line_composition
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.line.staff_leave_customer_coordination import (
    StaffLeaveCustomerCoordinationApplication,
    parse_staff_leave_customer_postback,
)
from subsystems.scheduling.staff_leave_intake_workflow import (
    ReviewStaffLeaveRequest,
    StaffLeaveIntakeWorkflowError,
)


class Cursor:
    def __init__(self, connection):
        self.raw = connection.db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.raw.close()

    def execute(self, sql, parameters=()):
        sql = re.sub(r'CAST\(([^)]+) AS CHAR CHARACTER SET utf8mb4\)', r'CAST(\1 AS TEXT)', sql)
        sql = sql.replace(' COLLATE utf8mb4_unicode_ci', '')
        self.raw.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""), parameters)

    def fetchone(self):
        row = self.raw.fetchone()
        return None if row is None else dict(row)

    def fetchall(self):
        return [dict(row) for row in self.raw.fetchall()]

    @property
    def rowcount(self):
        return self.raw.rowcount


class Connection:
    def __init__(self, state):
        self.state = state
        self.db = sqlite3.connect(state.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        state.connections += 1

    def cursor(self):
        return Cursor(self)

    def begin(self):
        self.db.execute("BEGIN")

    def commit(self):
        if self.state.fail_commit:
            raise RuntimeError("synthetic-commit-failure")
        self.db.commit()
        self.state.commits += 1

    def rollback(self):
        self.db.rollback()
        self.state.rollbacks += 1

    def close(self):
        self.db.close()


class Delivery:
    def __init__(self, connection):
        self.connection = connection

    def enqueue(self, request):
        state = self.connection.state
        state.enqueue_calls += 1
        if state.enqueue_calls == state.fail_enqueue:
            raise RuntimeError("synthetic-enqueue-failure")
        key = request.idempotency_key.value
        fingerprint = request.fingerprint.value
        row = self.connection.db.execute(
            "SELECT fingerprint FROM test_delivery WHERE identity=?", (key,)
        ).fetchone()
        if row is not None:
            if row[0] != fingerprint:
                raise RuntimeError("line_delivery_idempotency_conflict")
            return
        self.connection.db.execute(
            "INSERT INTO test_delivery VALUES (?,?,?,?,?,'pending')",
            (key, fingerprint, request.payload_json,
             request.recipient.identity.value, request.source_aggregate_identity),
        )


class LineUow(MySqlUnitOfWork):
    def __init__(self, state):
        super().__init__(Connection(state))
        self.delivery_tasks = Delivery(self._connection)
        self.configurations = SimpleNamespace(get=lambda kind: LineConfigurationSnapshot(
            kind, LineConfigurationRevision(1 if getattr(state, 'description', None) else 0),
            canonical_line_payload_json({'templates': [{'id': 'LU96-M1-LEAVE-EXTENSION-CARD-V1', 'message_type': 'text',
                                      'content': state.description, 'variables': []}]})
            if getattr(state, 'description', None) else '{}',
        ))

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self._connection.close()


@pytest.fixture
def inquiry(tmp_path, monkeypatch):
    state = SimpleNamespace(
        path=tmp_path / "inquiry.sqlite", connections=0, commits=0, rollbacks=0,
        enqueue_calls=0, fail_enqueue=0, fail_commit=False,
        now=datetime(2026, 9, 16, 12, tzinfo=timezone.utc),
    )
    db = sqlite3.connect(state.path, isolation_level=None)
    db.executescript("""
        CREATE TABLE scheduling_staff_leave_request_aggregates (
            id INTEGER PRIMARY KEY, staff_id INTEGER, line_user_id TEXT,
            leave_start_date TEXT, leave_end_date TEXT, request_reason TEXT,
            request_status TEXT, aggregate_version INTEGER, request_fingerprint TEXT
        );
        CREATE TABLE scheduling_staff_leave_request_events (
            request_id INTEGER, aggregate_version INTEGER, event_type TEXT,
            actor_id TEXT, reason TEXT, UNIQUE(request_id, aggregate_version)
        );
        CREATE TABLE scheduling_staff_leave_request_receipts (
            idempotency_key TEXT PRIMARY KEY, request_id INTEGER,
            request_fingerprint TEXT, result_snapshot TEXT
        );
        CREATE TABLE scheduling_aggregates (case_no TEXT, effective_generation_id INTEGER);
        CREATE TABLE case_staff_assignments (
            id INTEGER PRIMARY KEY, case_no TEXT, staff_id INTEGER,
            generation_id INTEGER, status TEXT
        );
        CREATE TABLE staff_schedule (
            assignment_id INTEGER, staff_id INTEGER, work_date TEXT, is_work_day INTEGER
        );
        CREATE TABLE orders (case_no TEXT PRIMARY KEY, client_id INTEGER);
        CREATE TABLE line_identity_role_bindings (
            line_user_id TEXT, subject_type TEXT, subject_reference TEXT, binding_status TEXT
        );
        CREATE TABLE test_delivery (
            identity TEXT PRIMARY KEY, fingerprint TEXT, payload TEXT,
            recipient TEXT, source_identity TEXT, status TEXT
        );
        INSERT INTO scheduling_staff_leave_request_aggregates VALUES
            (17,23,'U-staff','2026-09-20','2026-09-21','synthetic leave','pending',1,'source');
        INSERT INTO orders VALUES ('CASE-1',11),('CASE-2',12);
        INSERT INTO scheduling_aggregates VALUES ('CASE-1',101),('CASE-2',102);
        INSERT INTO case_staff_assignments VALUES
            (201,'CASE-1',23,101,'active'),(202,'CASE-2',23,102,'active');
        INSERT INTO staff_schedule VALUES (201,23,'2026-09-20',1),(202,23,'2026-09-21',1);
        INSERT INTO line_identity_role_bindings VALUES
            ('U-customer-1','customer','11','bound'),('U-customer-2','customer','12','bound');
    """)
    state.db = db
    monkeypatch.setattr(composition, "get_connection", lambda: Connection(state))
    monkeypatch.setattr(route, "get_connection", lambda: Connection(state))
    monkeypatch.setattr(line_composition, "open_line_unit_of_work", lambda: LineUow(state))
    original_init = StaffLeaveCustomerCoordinationApplication.__init__

    def init_with_clock(self, connection_factory, line_unit_of_work_factory, now):
        original_init(self, connection_factory, line_unit_of_work_factory, lambda: state.now)

    monkeypatch.setattr(StaffLeaveCustomerCoordinationApplication, "__init__", init_with_clock)
    yield state
    db.close()


def review(*, action="accept", version=1, key="review-17", reason="reviewed", request_id=17):
    application = composition.get_staff_leave_customer_coordination_application()
    return application.review(ReviewStaffLeaveRequest(
        request_id, version, action, reason, False, "synthetic-admin", key,
    ))


def rows(state, table):
    return state.db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()


def assert_pending_without_inquiries(state):
    assert state.db.execute(
        "SELECT request_status,aggregate_version FROM scheduling_staff_leave_request_aggregates"
    ).fetchone() == ("pending", 1)
    for table in ("scheduling_staff_leave_request_events", "scheduling_staff_leave_request_receipts", "test_delivery"):
        assert rows(state, table) == []


def test_historical_review_receipt_commits_without_customer_inquiry(inquiry):
    result = review()
    assert (result.request_id, result.status.value, result.version) == (17, "accepted_for_processing", 2)
    assert rows(inquiry, "scheduling_staff_leave_request_events")[0][3] == "synthetic-admin"
    assert inquiry.commits == 1
    assert len(rows(inquiry,"scheduling_staff_leave_request_events")) == 1
    assert len(rows(inquiry,"scheduling_staff_leave_request_receipts")) == 1
    assert rows(inquiry,"test_delivery") == []


@pytest.mark.parametrize("failure", [1, 2])
def test_retired_delivery_failure_cannot_block_historical_review(inquiry, failure):
    # Retired customer delivery cannot block a historical review.
    inquiry.fail_enqueue = failure
    assert review().status.value == 'accepted_for_processing'
    assert rows(inquiry,'test_delivery') == []
    assert inquiry.enqueue_calls == 0


def test_commit_failure_rolls_back_the_complete_review(inquiry):
    inquiry.fail_commit = True
    with pytest.raises(RuntimeError, match="synthetic-commit-failure"):
        review()
    assert_pending_without_inquiries(inquiry)
    inquiry.fail_commit = False
    review()
    assert rows(inquiry, "test_delivery") == []


@pytest.mark.parametrize("status", ["pending", "sent", "failed", "cancelled"])
def test_review_replay_does_not_reenqueue_or_reset_delivery_result(inquiry, status):
    first = review()
    inquiry.db.execute("UPDATE test_delivery SET status=?", (status,))
    before = rows(inquiry, "test_delivery")
    calls = inquiry.enqueue_calls
    inquiry.now += timedelta(days=1)
    replay = review()
    assert (replay.request_id, replay.status, replay.version) == (first.request_id, first.status, first.version)
    assert rows(inquiry, "test_delivery") == before
    assert inquiry.enqueue_calls == calls
    assert len(rows(inquiry, "scheduling_staff_leave_request_events")) == 1


def test_replay_does_not_send_a_second_inquiry_after_rebinding(inquiry):
    review()
    before = rows(inquiry, "test_delivery")
    inquiry.db.execute("UPDATE line_identity_role_bindings SET line_user_id='U-rebound'")
    inquiry.now += timedelta(days=1)
    review()
    assert rows(inquiry, "test_delivery") == before
    assert inquiry.enqueue_calls == 0


@pytest.mark.parametrize("action,status", [("reject", "rejected"), ("cancel", "cancelled")])
def test_nonaccept_review_never_enqueues_customer_inquiries(inquiry, action, status):
    assert review(action=action).status.value == status
    assert rows(inquiry, "test_delivery") == []
    assert inquiry.commits == 1


@pytest.mark.parametrize("options,code", [({"version": 2}, "leave_request_stale"), ({"request_id": 999}, "leave_request_not_found")])
def test_invalid_review_has_no_persisted_effect(inquiry, options, code):
    with pytest.raises(StaffLeaveIntakeWorkflowError, match=code):
        review(**options)
    assert_pending_without_inquiries(inquiry)


def test_missing_recipient_stays_visible_without_inventing_delivery(inquiry):
    inquiry.db.execute("DELETE FROM line_identity_role_bindings")
    assert review().status.value == "accepted_for_processing"
    assert rows(inquiry, "test_delivery") == []
    assert inquiry.connections == 1
    assert inquiry.commits == 1


def test_old_copy_cannot_reactivate_customer_inquiry(inquiry):
    inquiry.description = '過期客戶確認卡片'
    review()
    assert rows(inquiry,'test_delivery') == []
    assert inquiry.enqueue_calls == 0


def test_no_official_work_days_does_not_create_inquiries(inquiry):
    inquiry.db.execute("UPDATE staff_schedule SET is_work_day=0")
    assert review().status.value == "accepted_for_processing"
    assert rows(inquiry, "test_delivery") == []
    assert inquiry.commits == 1
