"""Regression coverage for the display-only historical assignment overlay."""

import sqlite3

from infrastructure.mysql.scheduling_occupancy_facts import load_historical_reservation_rows
from subsystems.scheduling import staff_monthly_calendar_query


class _Cursor:
    def __init__(self):
        self.responses = [{"id": 7}, [], [], [], [], [], []]
        self.current = None
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        self.current = self.responses.pop(0)

    def fetchone(self):
        return self.current[0] if isinstance(self.current, list) and self.current else self.current

    def fetchall(self):
        return self.current


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        return None


def test_precision_restart_suppresses_the_stale_historical_interval(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(staff_monthly_calendar_query, "get_connection", lambda: connection)

    result = staff_monthly_calendar_query.get_staff_monthly_calendar_schedule(
        staff_id=7,
        year=2026,
        month=7,
    )

    assert all(day["status"] != "historical_assignment" for day in result["days"])
    historical_query, _params = connection.cursor_instance.executed[2]
    assert "orders_historical_precision_restart" in historical_query


def test_historical_reservation_survives_restart_until_schedule_commit_or_cancellation():
    class Cursor:
        def __init__(self, connection):
            self.cursor = connection.cursor()

        def execute(self, sql, params):
            self.cursor.execute(sql.replace("%s", "?"), params)

        def fetchall(self):
            return self.cursor.fetchall()

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE orders (case_no, status, start_date, end_date, client_id);
            CREATE TABLE historical_order_adoption_receipts (id, case_no, outcome);
            CREATE TABLE historical_order_pairing_evidence (receipt_id, staff_id, resolution, caregiver_ordinal);
            CREATE TABLE clients (id, name);
            CREATE TABLE staff (id, name);
            CREATE TABLE scheduling_aggregates (case_no, effective_generation_id);
            CREATE TABLE scheduling_generations (id, effective_marker);
            CREATE TABLE scheduling_command_receipts (case_no, resulting_generation_id, command_family, idempotency_key);
            CREATE TABLE order_lifecycle_state_events (case_no, idempotency_key, trigger_event, before_status);
            INSERT INTO orders VALUES ('HIS-1','歷史訂單－未服務','2026-08-03','2026-08-20',1);
            INSERT INTO historical_order_adoption_receipts VALUES (1,'HIS-1','adopted');
            INSERT INTO historical_order_pairing_evidence VALUES (1,7,'evidence_only',1);
            INSERT INTO clients VALUES (1,'客戶甲');
            INSERT INTO staff VALUES (7,'月嫂甲');
        """)
        cursor = Cursor(db)
        assert [row["staff_id"] for row in load_historical_reservation_rows(cursor)] == [7]

        db.executescript("""
            UPDATE orders SET status='訂單成立';
            INSERT INTO scheduling_aggregates VALUES ('HIS-1',1);
            INSERT INTO scheduling_generations VALUES (1,1),(2,NULL);
            INSERT INTO scheduling_command_receipts VALUES ('HIS-1',1,'orders_historical_precision_restart','restart-1');
            INSERT INTO order_lifecycle_state_events VALUES
                ('HIS-1','restart-1','orders_historical_precision_restart','歷史訂單－未服務');
        """)
        assert [row["staff_id"] for row in load_historical_reservation_rows(cursor)] == [7]

        db.execute("UPDATE scheduling_aggregates SET effective_generation_id=2")
        db.rollback()
        assert [row["staff_id"] for row in load_historical_reservation_rows(cursor)] == [7]

        db.execute("UPDATE orders SET status='訂單取消'")
        assert load_historical_reservation_rows(cursor) == ()
        db.rollback()

        with db:
            db.execute("UPDATE scheduling_generations SET effective_marker=NULL WHERE id=1")
            db.execute("UPDATE scheduling_generations SET effective_marker=1 WHERE id=2")
            db.execute("UPDATE scheduling_aggregates SET effective_generation_id=2")
            db.execute(
                "INSERT INTO scheduling_command_receipts VALUES ('HIS-1',2,'orders_historical_restart_arrangement','save-1')"
            )
        assert load_historical_reservation_rows(cursor) == ()
    finally:
        db.close()
