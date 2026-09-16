import json
import sqlite3

import pytest
from datetime import date, datetime, timezone
from pathlib import Path

from infrastructure.mysql.order_pre_start_notification_source_repository import (
    MySqlOrderPreStartNotificationSourceRepository,
)
from subsystems.line.message_configuration import render_message_template
from subsystems.line.notification_source_adapters import (
    from_order_pre_start_checkpoint,
    from_order_second_payment_checkpoint,
)
from subsystems.line.order_pre_start_notification_source import (
    OrderPreStartNotificationSourceProjector,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.executed = (sql, params)

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


def test_pre_start_scan_is_keyed_by_service_date_and_preserves_payment_deadline():
    connection = _Connection(
        [
            {
                "case_no": "CASE-310-A",
                "service_start_date": date(2026, 9, 20),
                "first_payment_due_date": date(2026, 9, 18),
                "first_payment_required": 10000,
                "first_payment_received": 4000,
                "client_line_user_id": "U310",
            }
        ]
    )
    repository = MySqlOrderPreStartNotificationSourceRepository(connection)

    candidates = repository.find_due_candidates(date(2026, 9, 20))

    sql, params = connection.cursor_instance.executed
    assert "COALESCE(o.actual_start_date, o.start_date) = %s" in sql
    assert "p.first_payment_due_date = %s" not in sql
    assert params == ("2026-09-20",)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.planned_start_date == "2026-09-20"
    assert candidate.first_payment_due_date == "2026-09-18"
    assert candidate.first_payment_amount == 6000
    assert candidate.payment_state == "partial"
    assert candidate.already_settled is False


def test_second_payment_scan_keeps_missing_and_zero_obligation_states_distinct():
    connection = _Connection(
        [
            {
                "case_no": "CASE-310-MISSING",
                "service_start_date": date(2026, 9, 1),
                "second_payment_due_date": date(2026, 9, 20),
                "second_payment_required": None,
                "second_payment_received": 0,
                "client_line_user_id": None,
            },
            {
                "case_no": "CASE-310-ZERO",
                "service_start_date": date(2026, 9, 2),
                "second_payment_due_date": date(2026, 9, 20),
                "second_payment_required": 0,
                "second_payment_received": 0,
                "client_line_user_id": None,
            },
        ]
    )
    repository = MySqlOrderPreStartNotificationSourceRepository(connection)

    candidates = repository.find_second_payment_due_candidates(date(2026, 9, 20))

    assert len(candidates) == 2
    assert candidates[0].payment_state == "missing"
    assert candidates[0].second_payment_amount == 0
    assert candidates[0].already_settled is False
    assert candidates[0].service_start_date == "2026-09-01"
    assert candidates[1].payment_state == "not_required"
    assert candidates[1].second_payment_amount == 0
    assert candidates[1].already_settled is True
    assert candidates[1].service_start_date == "2026-09-02"


def test_notification_facts_do_not_alias_payment_deadlines_to_service_date():
    occurred_at = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)

    first = from_order_pre_start_checkpoint(
        case_no="CASE-310-FIRST",
        planned_start_date="2026-09-20",
        first_payment_due_date="2026-09-18",
        first_payment_amount=6000,
        payment_state="partial",
        already_settled=False,
        occurred_at=occurred_at,
    )
    assert first.facts["service_date"] == "2026-09-20"
    assert first.facts["first_payment_due_date"] == "2026-09-18"
    assert first.facts["first_payment_status"] == "部分已收，尚有餘額"

    second = from_order_second_payment_checkpoint(
        case_no="CASE-310-SECOND",
        service_start_date="2026-09-20",
        second_payment_due_date="2026-10-01",
        second_payment_amount=0,
        payment_state="missing",
        already_settled=False,
        occurred_at=occurred_at,
    )
    assert second.facts["service_date"] == "2026-09-20"
    assert second.facts["second_payment_due_date"] == "2026-10-01"
    assert second.facts["second_payment_amount"] == "帳務資料尚未確認"
    assert second.facts["second_payment_status"] == "帳務資料尚未確認"


def test_pre_start_template_renders_service_date_and_payment_deadline_separately():
    repository_root = Path(__file__).resolve().parents[6]
    definition = json.loads((repository_root / "config" / "message_templates.json").read_text())

    rendered = render_message_template(
        definition,
        "LU96-ORDER-PRE-START-REMINDER-CARD-V1",
        {
            "case_no": "CASE-310-RENDER",
            "planned_start_date": "2026-09-20",
            "first_payment_due_date": "2026-09-18",
            "first_payment_amount": "NT$ 6,000",
            "first_payment_status": "部分已收，尚有餘額",
        },
    )
    text = json.loads(rendered.payload_json)["text"]

    assert "3 天後（2026-09-20）正式開始" in text
    assert "繳款期限：2026-09-18" in text
    assert "繳款期限：服務開始日（2026-09-20）" not in text


def test_projector_uses_taipei_business_date_for_three_day_window():
    class Scanner:
        def __init__(self):
            self.targets = []

        def find_due_candidates(self, target_date):
            self.targets.append(target_date)
            return ()

        def find_second_payment_due_candidates(self, target_date):
            self.targets.append(target_date)
            return ()

    class Registry:
        def register_and_project(self, event):
            raise AssertionError("no events expected")

    scanner = Scanner()
    projector = OrderPreStartNotificationSourceProjector(scanner, Registry())

    processed = projector.run_once(datetime(2026, 9, 15, 16, 30, tzinfo=timezone.utc))

    assert processed == 0
    assert scanner.targets == [date(2026, 9, 19), date(2026, 9, 19)]


class _SqliteCursor:
    """Execute production SELECTs; only DB-API placeholders are translated."""
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cursor.close()

    def execute(self, sql, params):
        self.cursor.execute(sql.replace("%s", "?"), params)

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]


class _SqliteConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return _SqliteCursor(self.connection)


@pytest.fixture
def reminder_db():
    # Minimal columns used by the SELECT, matching the Orders/Finance schema.
    # No synthetic orders.service_start_date column; SQLite is NOT MySQL proof.
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.create_function("CONCAT", -1, lambda *values: (
        None if any(value is None for value in values) else "".join(map(str, values))
    ))
    connection.executescript("""
        CREATE TABLE orders (case_no TEXT PRIMARY KEY, status TEXT,
            start_date TEXT, actual_start_date TEXT);
        CREATE TABLE client_payment_terms (case_no TEXT PRIMARY KEY,
            first_payment_due_date TEXT, second_payment_due_date TEXT);
        CREATE TABLE client_obligations (obligation_identity TEXT PRIMARY KEY,
            case_no TEXT, obligation_type TEXT, current_event_id INTEGER);
        CREATE TABLE client_obligation_events (id INTEGER PRIMARY KEY, after_amount_ntd INTEGER);
        CREATE TABLE client_ledger_entries (id INTEGER PRIMARY KEY, entry_type TEXT);
        CREATE TABLE client_ledger_obligation_allocations (ledger_entry_id INTEGER,
            obligation_identity TEXT, amount_ntd INTEGER);
        CREATE TABLE line_order_group_participants (id INTEGER PRIMARY KEY,
            case_no TEXT, participant_type TEXT, invitation_status TEXT, line_user_id TEXT);
        CREATE TABLE clients (case_no TEXT PRIMARY KEY, line_user_id TEXT);
        CREATE TABLE line_notification_source_events (source_domain TEXT,
            event_code TEXT, source_event_identity TEXT, facts_snapshot TEXT,
            UNIQUE(source_domain,event_code,source_event_identity));
        INSERT INTO orders VALUES ('CASE-A','訂單成立','2026-09-19',NULL);
        INSERT INTO client_payment_terms VALUES ('CASE-A','2026-09-18','2026-09-19');
        INSERT INTO clients VALUES ('CASE-A','test-client-a');
        INSERT INTO client_obligation_events VALUES (1,10000),(2,20000);
        INSERT INTO client_obligations VALUES
            ('first-a','CASE-A','first',1),('second-a','CASE-A','second',2);
    """)
    try:
        yield connection
    finally:
        connection.close()


class _CheckpointRegistry:
    def __init__(self, connection):
        self.connection = connection

    def register_and_project(self, event):
        # Duplicate registration fails: the production scanner must omit an
        # already materialized occurrence, not rewrite its immutable facts.
        cursor = self.connection.execute(
            "INSERT INTO line_notification_source_events VALUES (?,?,?,?)",
            (event.source_domain, event.event_code, event.identity,
             json.dumps(dict(event.facts), sort_keys=True)),
        )
        return cursor.lastrowid


@pytest.mark.parametrize("change", [
    "none", "first-paid", "first-deadline", "second-partial", "second-service", "recipient",
])
def test_rescan_does_not_recreate_checkpoint_after_facts_change(reminder_db, change):
    repository = MySqlOrderPreStartNotificationSourceRepository(_SqliteConnection(reminder_db))
    projector = OrderPreStartNotificationSourceProjector(repository, _CheckpointRegistry(reminder_db))
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    assert projector.run_once(now) == 2
    original = [tuple(row) for row in reminder_db.execute(
        "SELECT * FROM line_notification_source_events ORDER BY event_code"
    )]
    if change in {"first-paid", "second-partial"}:
        reminder_db.execute("INSERT INTO client_ledger_entries VALUES (1,'receipt')")
        reminder_db.execute("INSERT INTO client_ledger_obligation_allocations VALUES (1,?,?)",
            ("first-a" if change == "first-paid" else "second-a", 10000 if change == "first-paid" else 4000))
    elif change == "first-deadline":
        reminder_db.execute("UPDATE client_payment_terms SET first_payment_due_date='2026-09-20'")
    elif change == "second-service":
        reminder_db.execute("UPDATE orders SET actual_start_date='2026-09-20'")
    elif change == "recipient":
        reminder_db.execute("UPDATE clients SET line_user_id='test-client-new'")
    reminder_db.execute("INSERT INTO orders VALUES ('CASE-B','訂單成立','2026-09-19',NULL)")
    assert projector.run_once(now) == 1  # The other case still progresses.
    assert projector.run_once(now) == 0
    retained = [tuple(row) for row in reminder_db.execute(
        "SELECT * FROM line_notification_source_events WHERE source_event_identity LIKE '%CASE-A:%' ORDER BY event_code"
    )]
    assert retained == original
    assert reminder_db.execute("SELECT COUNT(*) FROM line_notification_source_events").fetchone()[0] == 3


@pytest.mark.parametrize("actual_start,target,count", [
    (None, "2026-09-19", 1), ("2026-09-18", "2026-09-18", 1),
    ("2026-09-20", "2026-09-20", 1), ("2026-09-20", "2026-09-19", 0),
])
def test_sql_uses_confirmed_actual_start_before_planned_start(reminder_db, actual_start, target, count):
    reminder_db.execute("UPDATE orders SET actual_start_date=?", (actual_start,))
    repository = MySqlOrderPreStartNotificationSourceRepository(_SqliteConnection(reminder_db))
    candidates = repository.find_due_candidates(date.fromisoformat(target))
    assert len(candidates) == count
    if count:
        assert candidates[0].planned_start_date == target
        assert candidates[0].first_payment_due_date == "2026-09-18"
    second = repository.find_second_payment_due_candidates(date(2026, 9, 19))
    assert second[0].service_start_date == (actual_start or "2026-09-19")


@pytest.mark.parametrize("domain,event", [
    ("manual_replay", "order.pre_start_reminder"), ("orders", "other.event"),
])
def test_checkpoint_exclusion_uses_the_complete_source_key(reminder_db, domain, event):
    reminder_db.execute("INSERT INTO line_notification_source_events VALUES (?,?,?,?)",
        (domain, event, "order-pre-start-reminder:CASE-A:2026-09-19", "{}"))
    repository = MySqlOrderPreStartNotificationSourceRepository(_SqliteConnection(reminder_db))
    assert len(repository.find_due_candidates(date(2026, 9, 19))) == 1


def test_unregistered_occurrence_reads_current_facts(reminder_db):
    reminder_db.execute("UPDATE client_payment_terms SET first_payment_due_date='2026-09-17'")
    reminder_db.execute("INSERT INTO client_ledger_entries VALUES (1,'receipt')")
    reminder_db.execute("INSERT INTO client_ledger_obligation_allocations VALUES (1,'first-a',4000)")
    repository = MySqlOrderPreStartNotificationSourceRepository(_SqliteConnection(reminder_db))
    candidate = repository.find_due_candidates(date(2026, 9, 19))[0]
    assert candidate.first_payment_due_date == "2026-09-17"
    assert candidate.first_payment_amount == 6000
    assert candidate.payment_state == "partial"


def test_genuinely_new_due_occurrence_is_not_suppressed(reminder_db):
    repository = MySqlOrderPreStartNotificationSourceRepository(_SqliteConnection(reminder_db))
    projector = OrderPreStartNotificationSourceProjector(repository, _CheckpointRegistry(reminder_db))
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    assert projector.run_once(now) == 2
    reminder_db.execute("UPDATE client_payment_terms SET second_payment_due_date='2026-09-20'")
    assert projector.run_once(now, target_date=date(2026, 9, 20)) == 1
    assert projector.run_once(now, target_date=date(2026, 9, 20)) == 0
