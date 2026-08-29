from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

from api.routes import staff_payments
from infrastructure.mysql.staff_payment_query_repository import (
    MySqlStaffPaymentQueryRepository,
)
from subsystems.staff_payables.legacy_payment_query import (
    StaffPaymentQueryApplication,
    StaffPaymentSummaryView,
)


def _summary_row(payment_id: int = 7, case_no: str = "CASE-7") -> dict[str, object]:
    return {
        "id": payment_id,
        "assignment_id": 17,
        "case_no": case_no,
        "staff_id": 3,
        "service_hours": Decimal("10.00"),
        "hourly_rate": Decimal("300.00"),
        "service_salary": Decimal("3000.00"),
        "floor_fee_amount": Decimal("0.00"),
        "adjustment_amount": Decimal("0.00"),
        "total_payable": Decimal("3000.00"),
        "amount_paid": Decimal("0.00"),
        "due_date": date(2026, 8, 15),
        "paid_at": None,
        "payment_status": "pending",
        "notes": None,
        "created_at": datetime(2026, 8, 1, 10, 0),
        "updated_at": datetime(2026, 8, 1, 10, 0),
    }


def _transaction_row() -> dict[str, object]:
    return {
        "id": 8,
        "staff_payment_id": 7,
        "case_no": "CASE-7",
        "staff_id": 3,
        "transaction_type": "transfer",
        "transaction_status": "succeeded",
        "amount": Decimal("3000.00"),
        "occurred_at": date(2026, 8, 15),
        "external_reference": "bank-8",
        "reversal_of_transaction_id": None,
        "notes": "paid",
        "created_at": datetime(2026, 8, 15, 10, 0),
        "updated_at": datetime(2026, 8, 15, 10, 0),
    }


class _Cursor:
    def __init__(self, results):
        self.results = iter(results)
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return next(self.results)


class _Connection:
    def __init__(self, results):
        self.cursor_obj = _Cursor(results)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_mysql_query_uses_bounded_columns_and_typed_views():
    connection = _Connection(([_summary_row()],))
    result = MySqlStaffPaymentQueryRepository(connection).query_all()

    assert len(result) == 1
    assert isinstance(result[0], StaffPaymentSummaryView)
    assert result[0].total_payable == Decimal("3000.00")
    sql, params = connection.cursor_obj.executed[0]
    assert "SELECT *" not in sql.upper()
    assert "FROM staff_payments" in sql
    assert params is None


def test_mysql_case_query_returns_typed_transactions_without_connection_ownership():
    connection = _Connection(([_summary_row()], [_transaction_row()]))
    result = MySqlStaffPaymentQueryRepository(connection).query_by_case_no("CASE-7")

    assert result[0].transactions[0].external_reference == "bank-8"
    assert all("SELECT *" not in sql.upper() for sql, _ in connection.cursor_obj.executed)
    assert connection.closed is False
    assert connection.cursor_obj.executed[0][1] == ("CASE-7",)
    assert connection.cursor_obj.executed[1][1] == (7,)


def test_application_rejects_blank_case_number_before_repository_call():
    class Repository:
        def query_all(self):
            return ()

        def query_by_case_no(self, case_no):
            raise AssertionError(f"unexpected repository call: {case_no}")

    with pytest.raises(ValueError):
        StaffPaymentQueryApplication(Repository()).query_by_case_no(" ")


def test_legacy_transaction_endpoint_is_authenticated_and_retired():
    with pytest.raises(HTTPException) as error:
        staff_payments.create_staff_transaction(
            staff_payments.StaffTransactionCreate(
                staff_payment_id=7,
                amount=Decimal("1"),
                occurred_at=date(2026, 8, 15),
                external_reference="x",
                notes="reason",
            ),
            principal=object(),
        )
    assert error.value.status_code == 410
