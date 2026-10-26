"""Contract tests for the canonical Staff Payables self-service query."""

from datetime import date
from contextlib import closing, contextmanager
from decimal import Decimal
import sqlite3
from types import SimpleNamespace

import pytest

from infrastructure.mysql.staff_payout_self_service_query_repository import (
    MySqlStaffPayoutSelfServiceRepository,
)


def test_mysql_query_reads_canonical_obligations_and_ledger() -> None:
    summary = {
        "assignment_id": 17,
        "case_no": "CASE-7",
        "staff_id": 3,
        "due_date": date(2026, 8, 15),
        "total_payable_ntd": 3000,
        "net_paid_ntd": 3000,
        "balance_ntd": 0,
        "payment_status": "completed",
    }
    transaction = {
        "assignment_id": 17,
        "case_no": "CASE-7",
        "due_date": date(2026, 8, 15),
        "event_type": "payout",
        "allocated_amount_ntd": 3000,
        "occurred_on": date(2026, 8, 14),
    }

    class Cursor:
        def __init__(self):
            self.results = iter(([summary], [transaction]))
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, params):
            self.executed.append((sql, params))

        def fetchall(self):
            return next(self.results)

    cursor = Cursor()
    connection = SimpleNamespace(cursor=lambda: cursor)

    items = MySqlStaffPayoutSelfServiceRepository(
        connection
    ).query_by_staff_and_payment_month(3, 2026, 8)

    assert items[0].paid_at == date(2026, 8, 14)
    assert items[0].amount_remaining == Decimal("0")
    assert items[0].transactions[0].amount == Decimal("3000")
    assert "FROM staff_obligations obligations" in cursor.executed[0][0]
    assert "staff_payable_projections" in cursor.executed[0][0]
    assert "staff_payout_events" in cursor.executed[1][0]
    assert cursor.executed[0][1] == (3, date(2026, 8, 1), date(2026, 8, 31))


@pytest.mark.parametrize(
    ("payouts", "reopened", "projection_status", "expected_status", "remaining"),
    [
        ((), 0, None, "payable", 3000),
        ((1200,), 0, "partially_paid", "partially_paid", 1800),
        ((1200, 1800), 0, "completed", "completed", 0),
        ((1200, 1800), 500, "partially_paid", "partially_paid", 500),
        ((1200,), 1200, "payable", "payable", 3000),
        ((1200,), 0, "anomaly", "anomaly", 1800),
    ],
    ids=["unpaid", "partial", "paid-by-top-up", "partial-after-return", "unpaid-after-return", "anomaly"],
)
def test_query_preserves_payment_status_and_canonical_remaining(
    payouts, reopened, projection_status, expected_status, remaining
) -> None:
    # Execute the production aggregate SQL so a collapsed partial-payment CASE fails.
    with closing(sqlite3.connect(":memory:")) as database:
        database.row_factory = sqlite3.Row
        database.executescript("""
            CREATE TABLE staff_obligations (
                assignment_id INTEGER, case_no TEXT, staff_id INTEGER, due_date TEXT,
                obligation_identity TEXT, amount_due_ntd INTEGER, direction TEXT, status TEXT
            );
            CREATE TABLE staff_payable_projections (
                obligation_identity TEXT, obligation_amount_ntd INTEGER,
                net_paid_ntd INTEGER, balance_ntd INTEGER, status TEXT
            );
            CREATE TABLE staff_payout_events (id INTEGER, event_type TEXT, occurred_on TEXT);
            CREATE TABLE staff_payout_obligation_links (
                obligation_identity TEXT, payout_event_id INTEGER, allocated_amount_ntd INTEGER
            );
            INSERT INTO staff_obligations VALUES
                (17, 'CASE-7', 3, '2026-08-15', 'obligation:17', 3000, 'payable_to_staff', 'open'),
                (18, 'OTHER-STAFF', 4, '2026-08-15', 'obligation:18', 9000, 'payable_to_staff', 'open'),
                (19, 'OTHER-MONTH', 3, '2026-09-15', 'obligation:19', 9000, 'payable_to_staff', 'open');
        """)
        if projection_status is not None:
            database.execute(
                "INSERT INTO staff_payable_projections VALUES (?, ?, ?, ?, ?)",
                ("obligation:17", 3000, sum(payouts) - reopened, remaining, projection_status),
            )
        events = [("payout", amount) for amount in payouts]
        if reopened:
            events.append(("return", reopened))
        for event_id, (event_type, amount) in enumerate(events, 1):
            database.execute(
                "INSERT INTO staff_payout_events VALUES (?, ?, ?)",
                (event_id, event_type, "2026-08-14"),
            )
            database.execute(
                "INSERT INTO staff_payout_obligation_links VALUES (?, ?, ?)",
                ("obligation:17", event_id, amount),
            )

        @contextmanager
        def cursor():
            with closing(database.cursor()) as current:
                yield SimpleNamespace(
                    execute=lambda sql, params: current.execute(sql.replace("%s", "?"), params),
                    fetchall=current.fetchall,
                )

        changes_before = database.total_changes
        items = MySqlStaffPayoutSelfServiceRepository(
            SimpleNamespace(cursor=cursor)
        ).query_by_staff_and_payment_month(3, 2026, 8)

        assert len(items) == 1
        assert items[0].case_no == "CASE-7"
        assert items[0].payment_status == expected_status
        assert items[0].total_payable == Decimal("3000")
        assert items[0].amount_paid == Decimal(sum(payouts) - reopened)
        assert items[0].amount_remaining == Decimal(remaining)
        assert sum((event.amount for event in items[0].transactions), Decimal(0)) == items[0].amount_paid
        assert database.total_changes == changes_before
