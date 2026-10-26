from __future__ import annotations

import json
import sqlite3
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from domains.line.identities import LineUserId
from infrastructure.mysql.customer_service_repository import MySqlCustomerServiceRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.customer_service.contracts import CustomerServiceListQuery
from subsystems.line.staff_leave_customer_coordination import (
    StaffLeaveCustomerCoordinationApplication,
    _postback_value,
)

from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from subsystems.scheduling.staff_leave_intake_workflow import (
    RecordStaffLeaveCustomerDecision,
    StaffLeaveIntakeWorkflow,
    StaffLeaveIntakeWorkflowError,
)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0
        self._one = None
        self._all = ()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.rowcount = 0
        self._one = None
        self._all = ()
        if "FROM scheduling_staff_leave_request_receipts WHERE idempotency_key" in sql:
            key = params[0]
            self._one = self.connection.receipts.get(key)
            return
        if "FROM scheduling_staff_leave_request_aggregates WHERE id=%s FOR UPDATE" in sql:
            self._one = dict(self.connection.root) if params[0] == self.connection.root["id"] else None
            return
        if sql.startswith("SELECT DISTINCT g.case_no"):
            self._all = tuple(dict(item) for item in self.connection.targets)
            return
        if sql.startswith("INSERT INTO scheduling_staff_leave_request_receipts"):
            key, request_id, fingerprint, result_snapshot = params
            assert request_id == self.connection.root["id"]
            if key in self.connection.receipts:
                raise AssertionError("duplicate receipt insert")
            self.connection.receipts[key] = {
                "request_fingerprint": fingerprint,
                "result_snapshot": result_snapshot,
            }
            self.connection.writes.append((key, result_snapshot))
            self.rowcount = 1
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _Connection:
    def __init__(self):
        self.root = {
            "id": 17,
            "staff_id": 23,
            "line_user_id": "U-staff",
            "leave_start_date": date(2026, 9, 20),
            "leave_end_date": date(2026, 9, 21),
            "request_reason": "family",
            "request_status": "accepted_for_processing",
            "aggregate_version": 4,
            "request_fingerprint": "request-fingerprint",
        }
        self.targets = ({"case_no": "CASE-1", "client_line_user_id": "U-customer"},)
        self.receipts = {}
        self.writes = []

    def cursor(self):
        return _Cursor(self)


def _workflow(connection):
    return StaffLeaveIntakeWorkflow(MySqlStaffLeaveIntakeRepository(connection))


def _command(*, decision="agree_defer", key="leave-decision-1", version=4,
             case_no="CASE-1", line_user_id="U-customer"):
    return RecordStaffLeaveCustomerDecision(
        request_id=17,
        expected_version=version,
        case_no=case_no,
        line_user_id=line_user_id,
        decision=decision,
        idempotency_key=key,
    )


def test_customer_decision_is_immutable_receipt_without_leave_state_transition():
    connection = _Connection()

    receipt = _workflow(connection).record_customer_decision(_command())

    assert receipt.request_id == 17
    assert receipt.request_version == 4
    assert receipt.case_no == "CASE-1"
    assert receipt.line_user_id == "U-customer"
    assert receipt.decision == "agree_defer"
    assert receipt.replayed is False
    assert connection.root["request_status"] == "accepted_for_processing"
    assert connection.root["aggregate_version"] == 4
    assert len(connection.writes) == 1


def test_exact_customer_decision_replay_reads_same_receipt_without_second_write():
    connection = _Connection()
    workflow = _workflow(connection)
    command = _command()
    first = workflow.record_customer_decision(command)

    replay = workflow.record_customer_decision(command)

    assert replay.fingerprint == first.fingerprint
    assert replay.decision == first.decision
    assert replay.replayed is True
    assert len(connection.writes) == 1


def test_same_idempotency_key_cannot_change_terminal_customer_decision():
    connection = _Connection()
    workflow = _workflow(connection)
    workflow.record_customer_decision(_command())

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_decision_idempotency_conflict"):
        workflow.record_customer_decision(
            _command(decision="reject_substitution", key="leave-decision-1")
        )

    assert len(connection.writes) == 1


def test_wrong_recipient_is_rejected_before_receipt_write():
    connection = _Connection()

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_recipient_mismatch"):
        _workflow(connection).record_customer_decision(
            _command(line_user_id="U-someone-else")
        )

    assert connection.writes == []


def test_stale_leave_version_is_rejected_before_target_lookup_or_write():
    connection = _Connection()

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_request_stale"):
        _workflow(connection).record_customer_decision(_command(version=3))

    assert connection.writes == []


def test_unaffected_case_is_rejected_before_receipt_write():
    connection = _Connection()

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_case_not_affected"):
        _workflow(connection).record_customer_decision(_command(case_no="CASE-OTHER"))

    assert connection.writes == []


def test_missing_current_customer_binding_is_not_treated_as_authorized_recipient():
    connection = _Connection()
    connection.targets = ({"case_no": "CASE-1", "client_line_user_id": None},)

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_recipient_unavailable"):
        _workflow(connection).record_customer_decision(_command())

    assert connection.writes == []


def test_unknown_customer_decision_is_rejected_before_repository_access():
    connection = _Connection()

    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_customer_decision_invalid"):
        _workflow(connection).record_customer_decision(_command(decision="maybe"))

    assert connection.writes == []

# These tests execute the actual repositories and MySqlUnitOfWork against a
# temporary SQLite database. Only DB-API dialect and LINE delivery transport are
# doubles; MySQL lock/isolation and the real LINE provider are not exercised.
class _SqlCursor:
    def __init__(self, connection):
        self.cursor = connection.db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.cursor.close()
        return False

    def execute(self, sql, parameters=()):
        sql = re.sub(r'CAST\(([^)]+) AS CHAR CHARACTER SET utf8mb4\)', r'CAST(\1 AS TEXT)', sql)
        self.cursor.execute(sql.replace(' COLLATE utf8mb4_unicode_ci', '').replace("%s", "?").replace(" FOR UPDATE", ""), parameters)

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount


class _SqlConnection:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.create_function("IF", 3, lambda condition, yes, no: yes if condition else no)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _SqlCursor(self)

    def begin(self):
        self.db.execute("BEGIN")

    def commit(self):
        self.db.commit()
        self.commits += 1

    def rollback(self):
        self.db.rollback()
        self.rollbacks += 1

    def close(self):
        self.db.close()


class _TransactionalDelivery:
    def __init__(self, connection):
        self.connection = connection
        self.fail = False

    def enqueue(self, request):
        if self.fail:
            raise RuntimeError("delivery-storage-unavailable")
        values = (request.idempotency_key.value, request.fingerprint.value,
                  request.payload_json, request.recipient.recipient_type.value,
                  request.recipient.identity.value)
        row = self.connection.db.execute(
            "SELECT * FROM test_deliveries WHERE identity=?", (values[0],)
        ).fetchone()
        if row is not None:
            assert tuple(row) == values, "changed request under the same delivery identity"
            return
        self.connection.db.execute("INSERT INTO test_deliveries VALUES (?,?,?,?,?)", values)


class _LineUnitOfWork(MySqlUnitOfWork):
    def __init__(self, connection):
        super().__init__(connection)
        self.customer_service = MySqlCustomerServiceRepository(connection)
        self.delivery_tasks = _TransactionalDelivery(connection)


@pytest.fixture
def transaction_context(tmp_path):
    path = tmp_path / "leave.sqlite"
    connection = _SqlConnection(path)
    connection.db.executescript("""
        CREATE TABLE scheduling_staff_leave_request_aggregates (
            id INTEGER PRIMARY KEY, staff_id INTEGER, line_user_id TEXT,
            leave_start_date TEXT, leave_end_date TEXT, request_reason TEXT,
            request_status TEXT, aggregate_version INTEGER, request_fingerprint TEXT
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
        CREATE TABLE orders (
            case_no TEXT PRIMARY KEY, client_id INTEGER, status TEXT DEFAULT 'active',
            start_date TEXT, end_date TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT, phone TEXT);
        CREATE TABLE line_identity_role_bindings (
            line_user_id TEXT, subject_type TEXT, subject_reference TEXT, binding_status TEXT
        );
        CREATE TABLE customer_service_tickets (
            id INTEGER PRIMARY KEY, line_user_id TEXT, client_id INTEGER, case_no TEXT,
            category TEXT, status TEXT DEFAULT 'waiting', version INTEGER DEFAULT 0,
            resolved_at_utc TEXT, updated_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,
            active_marker INTEGER GENERATED ALWAYS AS (
                CASE WHEN status IN ('waiting','handling') THEN 1 ELSE NULL END
            ) STORED,
            UNIQUE (line_user_id, category, active_marker)
        );
        CREATE TABLE customer_service_ticket_events (
            id INTEGER PRIMARY KEY, ticket_id INTEGER, event_key TEXT UNIQUE,
            event_type TEXT, message_text TEXT, actor_id TEXT,
            created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE test_deliveries (
            identity TEXT PRIMARY KEY, fingerprint TEXT, payload TEXT,
            recipient_type TEXT, recipient TEXT
        );
        INSERT INTO scheduling_staff_leave_request_aggregates VALUES
            (17,23,'U-staff','2026-09-20','2026-09-21','family',
             'accepted_for_processing',4,'request-fingerprint');
        INSERT INTO orders (case_no,client_id) VALUES ('CASE-1',11),('CASE-2',11),('OTHER',22);
        INSERT INTO clients VALUES (11,'test customer',''),(22,'other test customer','');
        INSERT INTO scheduling_aggregates VALUES ('CASE-1',101),('CASE-2',102);
        INSERT INTO case_staff_assignments VALUES
            (201,'CASE-1',23,101,'active'),(202,'CASE-2',23,102,'active');
        INSERT INTO staff_schedule VALUES (201,23,'2026-09-20',1),(202,23,'2026-09-21',1);
        INSERT INTO line_identity_role_bindings VALUES ('U-customer','customer','11','bound');
    """)
    extra_connections = []

    def separate_connection():
        extra_connections.append(True)
        return _SqlConnection(path)

    def unexpected_line_transaction():
        raise AssertionError("postback must use its caller-owned transaction")

    app = StaffLeaveCustomerCoordinationApplication(
        separate_connection, unexpected_line_transaction,
        lambda: datetime(2026, 9, 16, 12, tzinfo=timezone.utc),
    )
    yield connection, app, extra_connections
    connection.close()


def _inbox(decision="reject_substitution", *, case_no="CASE-1", version=4,
           user="U-customer", event_id="leave-event-1", source_type="user"):
    return SimpleNamespace(event=SimpleNamespace(
        source=SimpleNamespace(user_id=LineUserId(user), source_type=SimpleNamespace(value=source_type)),
        event_id=SimpleNamespace(value=event_id),
        payload_json=json.dumps({"postback": {"data": _postback_value(17, version, case_no, decision)}}),
    ))


def _run_postback(connection, application, inbox=None):
    with _LineUnitOfWork(connection) as uow:
        assert application.handle_postback(inbox or _inbox(), uow)
        uow.commit()


def _rows(connection, table):
    return [dict(row) for row in connection.db.execute(f"SELECT * FROM {table}")]


@pytest.mark.parametrize('decision',['agree_defer','reject_substitution'])
@pytest.mark.parametrize('options',[{}, {'user':'U-other'}, {'version':1}, {'source_type':'group'}, {'case_no':'OTHER'}])
def test_retired_customer_card_has_no_sql_effect_for_actor_scope_stale_and_replay(transaction_context,decision,options):
    connection,application,extra_connections=transaction_context
    before={name:_rows(connection,name) for name in ['customer_service_tickets','customer_service_ticket_events','scheduling_staff_leave_request_receipts','test_deliveries']}
    inbox=_inbox(decision,**options)
    _run_postback(connection,application,inbox)
    _run_postback(connection,application,inbox)
    assert {name:_rows(connection,name) for name in before}==before
    assert extra_connections==[]


def test_fixture_preserves_the_production_active_conversation_uniqueness(transaction_context):
    connection, application, _ = transaction_context
    connection.db.execute("INSERT INTO customer_service_tickets (line_user_id,client_id,case_no,category) VALUES ('U-customer',11,'CASE-1','service_progress')")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        connection.db.execute(
            "INSERT INTO customer_service_tickets (line_user_id,client_id,case_no,category) "
            "VALUES ('U-customer',11,'CASE-2','service_progress')"
        )
    assert len(_rows(connection, "customer_service_tickets")) == 1
