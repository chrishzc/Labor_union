"""Contract tests for the canonical Staff Payables self-service query."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

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
    assert items[0].transactions[0].amount == Decimal("3000")
    assert "FROM staff_obligations obligations" in cursor.executed[0][0]
    assert "staff_payable_projections" in cursor.executed[0][0]
    assert "staff_payout_events" in cursor.executed[1][0]
    assert cursor.executed[0][1] == (3, date(2026, 8, 1), date(2026, 8, 31))
