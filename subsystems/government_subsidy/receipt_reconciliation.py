"""Reconcile one exact government-subsidy bank receipt in the caller UoW."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping


FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_FORMAT = "taishin"
EXPECTED_CLASSIFICATION = "government_subsidy"


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return value if value.is_finite() else None


def _pending(reason: str, bank_amount: Decimal | None = None, expected_amount: Decimal | None = None) -> dict[str, Any]:
    return {"result": "pending", "reason": reason, "bank_amount": bank_amount, "expected_amount": expected_amount}


def _existing_result(transaction: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": "existing", "batch_id": transaction["claim_batch_id"], "bank_amount": transaction["amount"], "expected_amount": transaction["amount"], "transaction_id": transaction["id"]}


def reconcile_government_subsidy(cursor: Any, finance_import_row_id: int, confirmed_batch_id: int | None = None) -> dict[str, Any]:
    _validate_ids(finance_import_row_id, confirmed_batch_id)
    row = _load_row(cursor, finance_import_row_id)
    fingerprint = row.get("dedup_fingerprint")
    if not isinstance(fingerprint, str) or FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        return _pending("staging row has no valid dedup_fingerprint")
    reference = f"fp:{fingerprint}"
    transaction = _transaction_for_row(cursor, finance_import_row_id)
    existing = _existing_or_inconsistent(row, transaction, reference)
    if existing is not None:
        return existing
    credit = _decimal(row.get("credit"))
    debit = _decimal(row.get("debit"))
    invalid = _validate_bank_row(row, credit, debit)
    if invalid is not None:
        return invalid
    duplicate = _duplicate_reference(cursor, reference)
    if duplicate is not None:
        return _existing_result(duplicate) if int(duplicate["finance_import_row_id"]) == finance_import_row_id else _pending("external_reference already belongs to another bank row", credit)
    candidates = _candidate_batches(cursor, confirmed_batch_id, credit)
    valid = _valid_candidates(cursor, candidates, credit)
    if len(valid) != 1:
        expected = _decimal(candidates[0].get("approved_amount")) if len(candidates) == 1 else None
        return _pending("exact approved batch candidate is not unique", credit, expected)
    batch, items = valid[0]
    return _record_receipt(cursor, batch, items, finance_import_row_id, credit, row["transaction_date"], reference)


def _validate_ids(row_id: Any, batch_id: Any) -> None:
    if isinstance(row_id, bool) or not isinstance(row_id, int) or row_id < 1:
        raise ValueError("finance_import_row_id must be a positive integer")
    if batch_id is not None and (isinstance(batch_id, bool) or not isinstance(batch_id, int) or batch_id < 1):
        raise ValueError("confirmed_batch_id must be a positive integer or None")


def _load_row(cursor: Any, row_id: int) -> Mapping[str, Any]:
    cursor.execute("SELECT id, dedup_fingerprint, format_id, transaction_date, debit, credit, direction, classification_type, reconciliation_status, reconciliation_reference FROM finance_import_rows WHERE id = %s FOR UPDATE", (row_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("finance import row does not exist")
    return row


def _transaction_for_row(cursor: Any, row_id: int):
    cursor.execute("SELECT id, claim_batch_id, finance_import_row_id, amount, external_reference FROM government_subsidy_transactions WHERE finance_import_row_id = %s FOR UPDATE", (row_id,))
    return cursor.fetchone()


def _existing_or_inconsistent(row: Mapping[str, Any], transaction: Any, reference: str):
    if row["reconciliation_status"] == "reconciled":
        if row.get("reconciliation_reference") == reference and transaction and transaction["external_reference"] == reference:
            return _existing_result(transaction)
        return _pending("reconciled staging row has no matching immutable transaction")
    if row["reconciliation_status"] != "pending":
        return _pending("staging row is not pending")
    if transaction:
        return _pending("staging row already has an immutable transaction but is not reconciled")
    return None


def _validate_bank_row(row: Mapping[str, Any], credit: Decimal | None, debit: Decimal | None):
    if row.get("format_id") != EXPECTED_FORMAT:
        return _pending("staging row is not a Taishin statement row", credit)
    if row.get("classification_type") != EXPECTED_CLASSIFICATION:
        return _pending("staging row is not classified as government_subsidy", credit)
    if row.get("direction") != "incoming" or credit is None or credit <= 0:
        return _pending("staging row is not a positive incoming credit", credit)
    if debit is not None and debit != 0:
        return _pending("incoming government subsidy row must not contain a debit", credit)
    if row.get("transaction_date") is None:
        return _pending("successful receipt requires transaction_date", credit)
    return None


def _duplicate_reference(cursor: Any, reference: str):
    cursor.execute("SELECT id, claim_batch_id, finance_import_row_id, amount, external_reference FROM government_subsidy_transactions WHERE external_reference = %s FOR UPDATE", (reference,))
    return cursor.fetchone()


def _candidate_batches(cursor: Any, batch_id: int | None, credit: Decimal):
    if batch_id is None:
        cursor.execute("SELECT * FROM subsidy_claim_batches WHERE status = 'approved' AND paid_amount = 0 AND approved_amount = %s FOR UPDATE", (credit,))
    else:
        cursor.execute("SELECT * FROM subsidy_claim_batches WHERE id = %s AND status = 'approved' AND paid_amount = 0 AND approved_amount = %s FOR UPDATE", (batch_id, credit))
    return cursor.fetchall()


def _valid_candidates(cursor: Any, candidates, credit: Decimal):
    valid = []
    for batch in candidates:
        cursor.execute("SELECT id, batch_id, approved_amount, paid_amount FROM subsidy_claim_batch_items WHERE batch_id = %s ORDER BY id FOR UPDATE", (batch["id"],))
        items = cursor.fetchall()
        approved = [_decimal(item.get("approved_amount")) for item in items]
        paid = [_decimal(item.get("paid_amount")) for item in items]
        if items and all(value is not None and value > 0 for value in approved) and all(value == 0 for value in paid) and sum(approved, Decimal("0")) == credit and _decimal(batch.get("approved_amount")) == credit:
            valid.append((batch, items))
    return valid


def _record_receipt(cursor: Any, batch: Mapping[str, Any], items, row_id: int, credit: Decimal, occurred_at: Any, reference: str) -> dict[str, Any]:
    cursor.execute("INSERT INTO government_subsidy_transactions (claim_batch_id, finance_import_row_id, transaction_type, transaction_status, amount, occurred_at, external_reference) VALUES (%s,%s,'receipt','succeeded',%s,%s,%s)", (batch["id"], row_id, credit, occurred_at, reference))
    transaction_id = cursor.lastrowid
    for item in items:
        amount = _decimal(item["approved_amount"])
        cursor.execute("INSERT INTO government_subsidy_allocations (transaction_id, claim_batch_id, claim_item_id, allocation_type, allocated_amount) VALUES (%s,%s,%s,'receipt',%s)", (transaction_id, batch["id"], item["id"], amount))
        cursor.execute("UPDATE subsidy_claim_batch_items SET paid_amount = approved_amount WHERE id = %s", (item["id"],))
    cursor.execute("UPDATE subsidy_claim_batches SET paid_amount = approved_amount, status = 'paid' WHERE id = %s", (batch["id"],))
    cursor.execute("UPDATE finance_import_rows SET reconciliation_status='reconciled', reconciliation_reference = %s, reconciled_at = CURRENT_TIMESTAMP WHERE id = %s", (reference, row_id))
    return {"result": "reconciled", "batch_id": batch["id"], "bank_amount": credit, "expected_amount": credit, "transaction_id": transaction_id}
