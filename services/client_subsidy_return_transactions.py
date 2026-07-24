"""Reconcile an exact Taishin subsidy-return debit with a client obligation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping


_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


def _decimal(value: Any, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal amount") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    return amount


def _bank_date(value: Any, field: str = "transaction_date") -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date") from exc
    raise ValueError(f"{field} is required")


def _identity_ids(value: Any) -> list[int] | None:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return None
    if not isinstance(value, list):
        return None
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        return None
    return value


def _obligation(receivable: Decimal, refunded: Decimal, return_at: str | None) -> dict[str, Any]:
    return {
        "subsidy_return_receivable": receivable,
        "subsidy_return_refunded": refunded,
        "subsidy_return_remaining": max(receivable - refunded, Decimal("0")),
        "subsidy_return_at": return_at,
    }


def _pending(obligation: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "transaction_id": None,
        "obligation": dict(obligation),
        "result": "pending",
        "reason": reason,
    }


def _net_refunded(transactions: list[Mapping[str, Any]], receivable: Decimal) -> tuple[Decimal, str | None]:
    refund_amounts: dict[int, Decimal] = {}
    reversed_amounts: dict[int, Decimal] = {}
    refunded = Decimal("0")
    return_at = None

    for transaction in transactions:
        if transaction.get("transaction_status") != "succeeded":
            continue
        amount = _decimal(transaction.get("amount"), "transaction amount")
        if amount <= 0:
            raise ValueError("succeeded subsidy-return transaction amount must be positive")
        transaction_type = transaction.get("transaction_type")
        transaction_id = transaction.get("id")
        if isinstance(transaction_id, bool) or not isinstance(transaction_id, int):
            raise ValueError("subsidy-return transaction id must be an integer")

        if transaction_type == "refund":
            if transaction.get("reversal_of_transaction_id") is not None:
                raise ValueError("refund must not reference a reversed transaction")
            refund_amounts[transaction_id] = amount
            refunded += amount
        elif transaction_type == "reversal":
            original_id = transaction.get("reversal_of_transaction_id")
            if original_id not in refund_amounts:
                raise ValueError("reversal must reference an earlier succeeded subsidy-return refund")
            reversed_amounts[original_id] = reversed_amounts.get(original_id, Decimal("0")) + amount
            if reversed_amounts[original_id] > refund_amounts[original_id]:
                raise ValueError("subsidy-return reversal exceeds its original refund")
            refunded -= amount
        else:
            raise ValueError("unsupported succeeded subsidy-return transaction type")

        if refunded < 0 or refunded > receivable:
            raise ValueError("subsidy-return transaction net is outside the obligation")
        return_at = _bank_date(transaction.get("occurred_at"), "occurred_at") if refunded == receivable and receivable > 0 else None

    return refunded, return_at


def _same_existing(
    existing: Mapping[str, Any],
    *,
    client_payment_id: int,
    case_no: str,
    finance_import_row_id: int,
    debit: Decimal,
    bank_date: str,
    external_reference: str,
) -> bool:
    try:
        existing_amount = _decimal(existing.get("amount"), "existing amount")
        existing_date = _bank_date(existing.get("occurred_at"), "existing occurred_at")
    except ValueError:
        return False
    return (
        existing.get("client_payment_id") == client_payment_id
        and existing.get("case_no") == case_no
        and existing.get("finance_import_row_id") == finance_import_row_id
        and existing.get("stage") == "subsidy_return"
        and existing.get("transaction_type") == "refund"
        and existing.get("transaction_status") == "succeeded"
        and existing.get("reversal_of_transaction_id") is None
        and existing_amount == debit
        and existing_date == bank_date
        and existing.get("external_reference") == external_reference
    )


def record_client_subsidy_return(
    cursor: Any,
    client_payment_id: int,
    finance_import_row_id: int,
) -> dict[str, Any]:
    """Record one exact Taishin subsidy-return debit in the caller transaction."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    if not isinstance(client_payment_id, int) or isinstance(client_payment_id, bool) or client_payment_id < 1:
        raise ValueError("client_payment_id must be a positive integer")
    if not isinstance(finance_import_row_id, int) or isinstance(finance_import_row_id, bool) or finance_import_row_id < 1:
        raise ValueError("finance_import_row_id must be a positive integer")

    cursor.execute(
        """SELECT fir.id AS finance_import_row_id, fir.format_id,
                  fir.dedup_fingerprint, fir.transaction_date,
                  fir.transaction_time, fir.direction, fir.debit,
                  fir.classification_type, fir.reconciliation_status,
                  fir.reconciliation_reference, fir.matched_identity_ids,
                  cp.id AS client_payment_id, cp.case_no,
                  cp.subsidy_return_receivable, cp.subsidy_return_refunded,
                  cp.subsidy_return_at, cp.subsidy_return_review_status
           FROM finance_import_rows fir
           JOIN client_payments cp ON cp.id=%s
           WHERE fir.id=%s
           FOR UPDATE""",
        (client_payment_id, finance_import_row_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("finance import row or client payment was not found")
    if not isinstance(row, Mapping):
        raise TypeError("cursor must return mapping rows")

    receivable = _decimal(row.get("subsidy_return_receivable", 0), "subsidy_return_receivable")
    stored_refunded = _decimal(row.get("subsidy_return_refunded", 0), "subsidy_return_refunded")
    obligation = _obligation(receivable, stored_refunded, row.get("subsidy_return_at"))

    if row.get("subsidy_return_review_status") == "review_required":
        return _pending(obligation, "subsidy_return_review_required")

    fingerprint = row.get("dedup_fingerprint")
    if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
        return _pending(obligation, "fingerprint_missing_or_invalid")
    if (
        row.get("format_id") != "taishin"
        or row.get("direction") != "outgoing"
        or row.get("classification_type") != "client_subsidy_return"
    ):
        return _pending(obligation, "staging_row_not_eligible")
    if _identity_ids(row.get("matched_identity_ids")) != [client_payment_id]:
        return _pending(obligation, "matched_identity_not_unique")
    try:
        bank_date = _bank_date(row.get("transaction_date"))
    except ValueError:
        return _pending(obligation, "transaction_date_missing_or_invalid")
    try:
        debit = _decimal(row.get("debit"), "debit")
    except ValueError:
        return _pending(obligation, "amount_mismatch")
    external_reference = f"fp:{fingerprint}"

    cursor.execute(
        """SELECT id, client_payment_id, case_no, finance_import_row_id, stage,
                  transaction_type, transaction_status, amount, occurred_at,
                  external_reference, reversal_of_transaction_id
           FROM client_payment_transactions
           WHERE external_reference=%s OR finance_import_row_id=%s
           FOR UPDATE""",
        (external_reference, finance_import_row_id),
    )
    conflicts = cursor.fetchall()
    if len(conflicts) > 1:
        raise ValueError("fingerprint or staging row is linked to multiple transactions")
    existing = conflicts[0] if conflicts else None

    cursor.execute(
        """SELECT id, transaction_type, transaction_status, amount, occurred_at,
                  external_reference, reversal_of_transaction_id,
                  finance_import_row_id
           FROM client_payment_transactions
           WHERE client_payment_id=%s AND stage='subsidy_return'
           ORDER BY occurred_at, id
           FOR UPDATE""",
        (client_payment_id,),
    )
    transactions = cursor.fetchall()
    refunded, return_at = _net_refunded(transactions, receivable)
    obligation = _obligation(receivable, refunded, return_at)

    if existing is not None:
        if not isinstance(existing, Mapping) or not _same_existing(
            existing,
            client_payment_id=client_payment_id,
            case_no=row.get("case_no"),
            finance_import_row_id=finance_import_row_id,
            debit=debit,
            bank_date=bank_date,
            external_reference=external_reference,
        ):
            raise ValueError("fingerprint or staging row is linked to a different transaction")
        if not any(transaction.get("id") == existing.get("id") for transaction in transactions):
            raise ValueError("existing transaction is missing from the locked subsidy-return ledger")
        if (
            row.get("reconciliation_status") != "reconciled"
            or row.get("reconciliation_reference") != external_reference
        ):
            raise ValueError("existing transaction has inconsistent staging reconciliation")
        return {
            "transaction_id": existing["id"],
            "obligation": obligation,
            "result": "existing",
        }

    if row.get("reconciliation_status") != "pending":
        raise ValueError("non-pending staging row has no matching transaction")
    remaining = obligation["subsidy_return_remaining"]
    if debit <= 0 or debit != remaining:
        return _pending(obligation, "amount_mismatch")

    cursor.execute(
        """INSERT INTO client_payment_transactions (
                  client_payment_id, case_no, stage, transaction_type,
                  transaction_status, amount, occurred_at, external_reference,
                  finance_import_row_id
              ) VALUES (%s,%s,'subsidy_return','refund','succeeded',%s,%s,%s,%s)""",
        (
            client_payment_id,
            row.get("case_no"),
            debit,
            bank_date,
            external_reference,
            finance_import_row_id,
        ),
    )
    transaction_id = cursor.lastrowid
    if not transaction_id:
        raise RuntimeError("client subsidy-return transaction id was not generated")

    transactions.append(
        {
            "id": transaction_id,
            "transaction_type": "refund",
            "transaction_status": "succeeded",
            "amount": debit,
            "occurred_at": bank_date,
            "external_reference": external_reference,
            "reversal_of_transaction_id": None,
            "finance_import_row_id": finance_import_row_id,
        }
    )
    refunded, return_at = _net_refunded(transactions, receivable)
    if refunded != receivable or return_at != bank_date:
        raise RuntimeError("exact subsidy-return reconciliation did not settle the obligation")

    cursor.execute(
        """UPDATE client_payments
           SET subsidy_return_refunded=%s, subsidy_return_at=%s
           WHERE id=%s""",
        (refunded, return_at, client_payment_id),
    )
    cursor.execute(
        """UPDATE finance_import_rows
           SET reconciliation_status='reconciled', reconciliation_reference=%s,
               reconciled_at=CURRENT_TIMESTAMP
           WHERE id=%s AND reconciliation_status='pending'""",
        (external_reference, finance_import_row_id),
    )
    if getattr(cursor, "rowcount", 1) != 1:
        raise RuntimeError("staging row reconciliation update failed")

    obligation = _obligation(receivable, refunded, return_at)
    return {
        "transaction_id": transaction_id,
        "obligation": obligation,
        "result": "reconciled",
    }
