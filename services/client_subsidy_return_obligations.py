"""Activate the canonical subsidy-return obligation after full client receipt."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


def _is_sqlite_cursor(cursor: Any) -> bool:
    return type(cursor).__module__.split(".", 1)[0] == "sqlite3"


def _placeholder(cursor: Any) -> str:
    return "?" if _is_sqlite_cursor(cursor) else "%s"


def _locking_clause(cursor: Any) -> str:
    # SQLite does not support SELECT ... FOR UPDATE.  Production MySQL does,
    # and the caller owns the transaction that keeps this row lock alive.
    return "" if _is_sqlite_cursor(cursor) else " FOR UPDATE"


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def _due_date_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError("due_date must be an explicit date value or None")


def _row_mapping(row: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return {column: row[column] for column in columns}
    return dict(zip(columns, row, strict=True))


def _output_number(number: Decimal) -> int | Decimal:
    return int(number) if number == number.to_integral_value() else number


def _obligation(receivable: Any, refunded: Any, due_date: Any) -> dict[str, Any]:
    receivable_number = _decimal(receivable, "subsidy_return_receivable")
    refunded_number = _decimal(refunded, "subsidy_return_refunded")
    return {
        "subsidy_return_receivable": receivable,
        "subsidy_return_refunded": refunded,
        "due_date": due_date,
        "remaining": _output_number(receivable_number - refunded_number),
    }


def activate_subsidy_return_obligation(
    cursor: Any,
    client_payment_id: int,
    calculated_return_amount: Any,
    due_date: Any,
) -> dict[str, Any]:
    """Activate an immutable canonical obligation only after exact full receipt.

    ``due_date`` is persisted exactly as an explicit input (normalized only for
    Python date objects), or as SQL ``NULL`` when the caller passes ``None``.
    No date is inferred here.
    """
    if isinstance(client_payment_id, bool) or not isinstance(client_payment_id, int):
        raise ValueError("client_payment_id must be an integer")
    if client_payment_id <= 0:
        raise ValueError("client_payment_id must be positive")

    return_amount = _decimal(calculated_return_amount, "calculated_return_amount")
    explicit_due_date = _due_date_value(due_date)
    placeholder = _placeholder(cursor)
    columns = (
        "amount_receivable",
        "amount_received",
        "subsidy_return_receivable",
        "subsidy_return_refunded",
        "subsidy_return_due_date",
    )
    cursor.execute(
        f"SELECT {', '.join(columns)} FROM client_payments "
        f"WHERE id = {placeholder}{_locking_clause(cursor)}",
        (client_payment_id,),
    )
    row = cursor.fetchone()
    if row is None:
        result = "review_required"
        assert result == "review_required"
        return {"obligation": None, "result": result}

    payment = _row_mapping(row, columns)
    amount_receivable = _decimal(payment["amount_receivable"], "amount_receivable")
    amount_received = _decimal(payment["amount_received"], "amount_received")
    current_receivable = payment["subsidy_return_receivable"]
    current_refunded = payment["subsidy_return_refunded"]
    current_due_date = payment["subsidy_return_due_date"]

    active = current_receivable is not None and _decimal(
        current_receivable, "subsidy_return_receivable"
    ) > 0
    if active:
        obligation = _obligation(current_receivable, current_refunded, current_due_date)
        matches = (
            _decimal(current_receivable, "subsidy_return_receivable") == return_amount
            and current_due_date == explicit_due_date
            and _decimal(current_refunded, "subsidy_return_refunded") <= return_amount
        )
        result = "existing" if matches else "review_required"
        assert result in {"existing", "review_required"}
        return {"obligation": obligation, "result": result}

    fully_received = (
        amount_receivable > 0 and amount_received == amount_receivable
    )
    inactive_clean = (
        current_receivable is None or _decimal(current_receivable, "subsidy_return_receivable") == 0
    ) and (
        current_refunded is None or _decimal(current_refunded, "subsidy_return_refunded") == 0
    ) and current_due_date is None

    if not fully_received or return_amount <= 0 or not inactive_clean:
        result = "review_required"
        assert result == "review_required"
        existing_obligation = None
        if current_receivable is not None and current_refunded is not None:
            existing_obligation = _obligation(
                current_receivable, current_refunded, current_due_date
            )
        return {"obligation": existing_obligation, "result": result}

    cursor.execute(
        "UPDATE client_payments SET "
        f"subsidy_return_receivable = {placeholder}, "
        f"subsidy_return_refunded = {placeholder}, "
        f"subsidy_return_due_date = {placeholder} "
        f"WHERE id = {placeholder}",
        (calculated_return_amount, 0, explicit_due_date, client_payment_id),
    )
    obligation = _obligation(calculated_return_amount, 0, explicit_due_date)
    result = "activated"
    assert result == "activated"
    return {"obligation": obligation, "result": result}
