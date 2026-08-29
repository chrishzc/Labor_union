"""MySQL adapter for the bounded Staff Payables compatibility query."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Mapping

from subsystems.staff_payables.legacy_payment_query import (
    StaffPaymentSummaryView,
    StaffPaymentTransactionView,
)


_SUMMARY_COLUMNS = (
    "id, assignment_id, case_no, staff_id, service_hours, hourly_rate, "
    "service_salary, floor_fee_amount, adjustment_amount, total_payable, "
    "amount_paid, due_date, paid_at, payment_status, notes, created_at, updated_at"
)
_TRANSACTION_COLUMNS = (
    "id, staff_payment_id, case_no, staff_id, transaction_type, "
    "transaction_status, amount, occurred_at, external_reference, "
    "reversal_of_transaction_id, notes, created_at, updated_at"
)


def _date(value: object) -> date | None:
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value  # type: ignore[return-value]
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value).split(" ", 1)[0])


def _datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value  # type: ignore[return-value]
    return datetime.fromisoformat(str(value))


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _summary(row: Mapping[str, object], transactions=()) -> StaffPaymentSummaryView:
    return StaffPaymentSummaryView(
        id=int(row["id"]),
        assignment_id=int(row["assignment_id"]),
        case_no=str(row["case_no"]),
        staff_id=int(row["staff_id"]),
        service_hours=_decimal(row["service_hours"]),
        hourly_rate=_decimal(row["hourly_rate"]),
        service_salary=_decimal(row["service_salary"]),
        floor_fee_amount=_decimal(row["floor_fee_amount"]),
        adjustment_amount=_decimal(row["adjustment_amount"]),
        total_payable=_decimal(row["total_payable"]),
        amount_paid=_decimal(row["amount_paid"]),
        due_date=_date(row.get("due_date")),
        paid_at=_date(row.get("paid_at")),
        payment_status=str(row["payment_status"]),
        notes=None if row.get("notes") is None else str(row["notes"]),
        created_at=_datetime(row.get("created_at")),
        updated_at=_datetime(row.get("updated_at")),
        transactions=tuple(transactions),
    )


def _transaction(row: Mapping[str, object]) -> StaffPaymentTransactionView:
    return StaffPaymentTransactionView(
        id=int(row["id"]),
        staff_payment_id=int(row["staff_payment_id"]),
        case_no=str(row["case_no"]),
        staff_id=int(row["staff_id"]),
        transaction_type=str(row["transaction_type"]),
        transaction_status=str(row["transaction_status"]),
        amount=_decimal(row["amount"]),
        occurred_at=_date(row.get("occurred_at")),
        external_reference=(
            None
            if row.get("external_reference") is None
            else str(row["external_reference"])
        ),
        reversal_of_transaction_id=(
            None
            if row.get("reversal_of_transaction_id") is None
            else int(row["reversal_of_transaction_id"])
        ),
        notes=None if row.get("notes") is None else str(row["notes"]),
        created_at=_datetime(row.get("created_at")),
        updated_at=_datetime(row.get("updated_at")),
    )


class MySqlStaffPaymentQueryRepository:
    """Read-only adapter; it never commits, rolls back, or closes the connection."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def query_all(self) -> tuple[StaffPaymentSummaryView, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_SUMMARY_COLUMNS} FROM staff_payments ORDER BY id DESC"
            )
            rows = cursor.fetchall()
        return tuple(_summary(row) for row in rows)

    def query_by_case_no(self, case_no: str) -> tuple[StaffPaymentSummaryView, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_SUMMARY_COLUMNS} FROM staff_payments "
                "WHERE case_no = %s ORDER BY id DESC",
                (case_no,),
            )
            payments = tuple(cursor.fetchall())
            if not payments:
                return ()
            payment_ids = tuple(int(row["id"]) for row in payments)
            placeholders = ", ".join("%s" for _ in payment_ids)
            cursor.execute(
                f"SELECT {_TRANSACTION_COLUMNS} FROM staff_payment_transactions "
                f"WHERE staff_payment_id IN ({placeholders}) "
                "ORDER BY occurred_at ASC, id ASC",
                payment_ids,
            )
            transactions_by_payment: dict[int, list[StaffPaymentTransactionView]] = {}
            for row in cursor.fetchall():
                transactions_by_payment.setdefault(int(row["staff_payment_id"]), []).append(
                    _transaction(row)
                )
        return tuple(
            _summary(row, transactions_by_payment.get(int(row["id"]), ()))
            for row in payments
        )


__all__ = ["MySqlStaffPaymentQueryRepository"]
