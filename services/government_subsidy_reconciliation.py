"""Exact-match P0 reconciliation for government subsidy bank receipts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any


EXPECTED_FORMAT = "taishin"
EXPECTED_CLASSIFICATION = "government_subsidy"
FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")

assert EXPECTED_FORMAT == "taishin" and EXPECTED_CLASSIFICATION == "government_subsidy"


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _pending(reason: str, bank_amount: Decimal | None = None,
             expected_amount: Decimal | None = None) -> dict:
    return {
        "result": "pending",
        "batch_id": None,
        "bank_amount": bank_amount,
        "expected_amount": expected_amount,
        "reason": reason,
    }


def _existing_result(transaction: dict) -> dict:
    return {
        "result": "existing",
        "batch_id": transaction["claim_batch_id"],
        "bank_amount": Decimal(str(transaction["amount"])),
        "expected_amount": Decimal(str(transaction["amount"])),
        "transaction_id": transaction["id"],
    }


def reconcile_government_subsidy(
    cursor,
    finance_import_row_id: int,
    confirmed_batch_id: int | None = None,
) -> dict:
    """Reconcile one full Taishin receipt to exactly one approved unpaid batch."""
    if isinstance(finance_import_row_id, bool) or not isinstance(finance_import_row_id, int) or finance_import_row_id < 1:
        raise ValueError("finance_import_row_id must be a positive integer")
    if confirmed_batch_id is not None and (
        isinstance(confirmed_batch_id, bool)
        or not isinstance(confirmed_batch_id, int)
        or confirmed_batch_id < 1
    ):
        raise ValueError("confirmed_batch_id must be a positive integer or None")
    cursor.execute(
        "SELECT id, dedup_fingerprint, format_id, transaction_date, debit, credit, direction, "
        "classification_type, reconciliation_status, reconciliation_reference "
        "FROM finance_import_rows WHERE id = %s FOR UPDATE",
        (finance_import_row_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("finance import row does not exist")
    fingerprint = row.get("dedup_fingerprint")
    if not isinstance(fingerprint, str) or FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        return _pending("staging row has no valid dedup_fingerprint")
    external_reference = f"fp:{fingerprint}"

    cursor.execute(
        "SELECT id, claim_batch_id, finance_import_row_id, amount, external_reference "
        "FROM government_subsidy_transactions WHERE finance_import_row_id = %s FOR UPDATE",
        (finance_import_row_id,),
    )
    transaction_for_row = cursor.fetchone()
    if row["reconciliation_status"] == "reconciled":
        if (
            row.get("reconciliation_reference") == external_reference
            and transaction_for_row
            and transaction_for_row["external_reference"] == external_reference
        ):
            return _existing_result(transaction_for_row)
        return _pending("reconciled staging row has no matching immutable transaction")
    if row["reconciliation_status"] != "pending":
        return _pending("staging row is not pending")
    if transaction_for_row:
        return _pending("staging row already has an immutable transaction but is not reconciled")

    credit = _decimal(row.get("credit"))
    debit = _decimal(row.get("debit"))
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

    cursor.execute(
        "SELECT id, claim_batch_id, finance_import_row_id, amount, external_reference "
        "FROM government_subsidy_transactions WHERE external_reference = %s FOR UPDATE",
        (external_reference,),
    )
    duplicate_reference = cursor.fetchone()
    if duplicate_reference:
        if int(duplicate_reference["finance_import_row_id"]) == finance_import_row_id:
            return _existing_result(duplicate_reference)
        return _pending("external_reference already belongs to another bank row", credit)

    if confirmed_batch_id is None:
        cursor.execute(
            "SELECT * FROM subsidy_claim_batches "
            "WHERE status = 'approved' AND paid_amount = 0 AND approved_amount = %s FOR UPDATE",
            (credit,),
        )
    else:
        cursor.execute(
            "SELECT * FROM subsidy_claim_batches "
            "WHERE id = %s AND status = 'approved' AND paid_amount = 0 "
            "AND approved_amount = %s FOR UPDATE",
            (confirmed_batch_id, credit),
        )
    candidates = cursor.fetchall()

    valid_candidates: list[tuple[dict, list[dict]]] = []
    for batch in candidates:
        cursor.execute(
            "SELECT id, batch_id, approved_amount, paid_amount "
            "FROM subsidy_claim_batch_items WHERE batch_id = %s ORDER BY id FOR UPDATE",
            (batch["id"],),
        )
        items = cursor.fetchall()
        item_approved = [_decimal(item.get("approved_amount")) for item in items]
        item_paid = [_decimal(item.get("paid_amount")) for item in items]
        if (
            items
            and all(amount is not None and amount > 0 for amount in item_approved)
            and all(amount == 0 for amount in item_paid)
            and sum(item_approved, Decimal("0")) == credit
            and _decimal(batch.get("approved_amount")) == credit
        ):
            valid_candidates.append((batch, items))

    if len(valid_candidates) != 1:
        expected = None
        if len(candidates) == 1:
            expected = _decimal(candidates[0].get("approved_amount"))
        return _pending("exact approved batch candidate is not unique", credit, expected)

    batch, items = valid_candidates[0]
    cursor.execute(
        "INSERT INTO government_subsidy_transactions "
        "(claim_batch_id, finance_import_row_id, transaction_type, transaction_status, "
        "amount, occurred_at, external_reference) VALUES (%s,%s,'receipt','succeeded',%s,%s,%s)",
        (batch["id"], finance_import_row_id, credit, row["transaction_date"], external_reference),
    )
    transaction_id = cursor.lastrowid
    for item in items:
        approved_amount = _decimal(item["approved_amount"])
        cursor.execute(
            "INSERT INTO government_subsidy_allocations "
            "(transaction_id, claim_batch_id, claim_item_id, allocation_type, allocated_amount) "
            "VALUES (%s,%s,%s,'receipt',%s)",
            (transaction_id, batch["id"], item["id"], approved_amount),
        )
        cursor.execute(
            "UPDATE subsidy_claim_batch_items SET paid_amount = approved_amount WHERE id = %s",
            (item["id"],),
        )
    cursor.execute(
        "UPDATE subsidy_claim_batches SET paid_amount = approved_amount, status = 'paid' WHERE id = %s",
        (batch["id"],),
    )
    cursor.execute(
        "UPDATE finance_import_rows SET reconciliation_status = 'reconciled', "
        "reconciliation_reference = %s, reconciled_at = CURRENT_TIMESTAMP WHERE id = %s",
        (external_reference, finance_import_row_id),
    )
    return {
        "result": "reconciled",
        "batch_id": batch["id"],
        "bank_amount": credit,
        "expected_amount": credit,
        "transaction_id": transaction_id,
    }
