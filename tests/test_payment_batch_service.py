from datetime import date
from decimal import Decimal

import pytest

from services import payment_batch_service


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def _row(
    settlement_id,
    staff_id,
    staff_payment_id,
    case_no,
    due_date=date(2026, 7, 15),
    total_payable=Decimal("36000.00"),
    total_paid=Decimal("6000.00"),
):
    return {
        "settlement_id": settlement_id,
        "staff_id": staff_id,
        "total_payable": total_payable,
        "total_paid": total_paid,
        "staff_payment_id": staff_payment_id,
        "case_no": case_no,
        "due_date": due_date,
    }


def test_prepares_one_row_per_monthly_settlement(monkeypatch):
    connection = FakeConnection(
        [
            _row(101, 10, 1, "115000001"),
            _row(101, 10, 2, "115000002"),
            _row(
                102,
                11,
                3,
                "115000003",
                due_date=date(2026, 7, 20),
                total_payable=Decimal("20000.00"),
                total_paid=Decimal("0.00"),
            ),
        ]
    )
    monkeypatch.setattr(payment_batch_service, "get_connection", lambda: connection)

    results = payment_batch_service.prepare_monthly_payments("2026-07")

    assert results == [
        {
            "settlement_id": 101,
            "staff_id": 10,
            "total_payable": Decimal("36000.00"),
            "total_paid": Decimal("6000.00"),
            "case_nos": ["115000001", "115000002"],
            "staff_payment_ids": [1, 2],
            "transfer_date": date(2026, 7, 15),
            "remaining_amount": Decimal("30000.00"),
        },
        {
            "settlement_id": 102,
            "staff_id": 11,
            "total_payable": Decimal("20000.00"),
            "total_paid": Decimal("0.00"),
            "case_nos": ["115000003"],
            "staff_payment_ids": [3],
            "transfer_date": date(2026, 7, 20),
            "remaining_amount": Decimal("20000.00"),
        },
    ]
    assert connection.closed is True

    sql, params = connection.cursor_instance.executed[0]
    assert params == (date(2026, 7, 1),)
    assert "FROM staff_monthly_settlements" in sql
    assert "staff_monthly_settlement_details" in sql
    assert "sms.status IN ('finalized', 'partially_paid')" in sql
    assert "sms.settlement_month = %s" in sql
    assert "INSERT " not in sql.upper()
    assert "UPDATE " not in sql.upper()
    assert "DELETE " not in sql.upper()


@pytest.mark.parametrize(
    "rows",
    [
        [
            _row(101, 10, 1, "115000001", date(2026, 7, 15)),
            _row(101, 10, 2, "115000002", date(2026, 7, 20)),
        ],
        [_row(101, 10, 1, "115000001", None)],
    ],
)
def test_missing_or_inconsistent_source_due_dates_are_not_payable(monkeypatch, rows):
    connection = FakeConnection(rows)
    monkeypatch.setattr(payment_batch_service, "get_connection", lambda: connection)

    assert payment_batch_service.prepare_monthly_payments("2026-07") == []


@pytest.mark.parametrize("target_month", ["2026-7", "2026-13", "bad", None])
def test_invalid_target_month_is_rejected_before_database_access(monkeypatch, target_month):
    monkeypatch.setattr(
        payment_batch_service,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("database must not be opened")),
    )

    with pytest.raises(ValueError, match="YYYY-MM"):
        payment_batch_service.prepare_monthly_payments(target_month)
