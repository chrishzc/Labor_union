from decimal import Decimal

import pytest

from services.government_subsidy_reconciliation import reconcile_government_subsidy


FINGERPRINT = "a" * 64
EXTERNAL_REFERENCE = f"fp:{FINGERPRINT}"


class FakeCursor:
    def __init__(self, *, row=None, transaction_for_row=None, duplicate_reference=None,
                 batches=None, items_by_batch=None):
        self.row = row
        self.transaction_for_row = transaction_for_row
        self.duplicate_reference = duplicate_reference
        self.batches = batches or []
        self.items_by_batch = items_by_batch or {}
        self.current = None
        self.calls = []
        self.lastrowid = 91

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        if "FROM finance_import_rows WHERE id" in compact:
            self.current = self.row
        elif "FROM government_subsidy_transactions WHERE finance_import_row_id" in compact:
            self.current = self.transaction_for_row
        elif "FROM government_subsidy_transactions WHERE external_reference" in compact:
            self.current = self.duplicate_reference
        elif "FROM subsidy_claim_batches" in compact:
            self.current = self.batches
        elif "FROM subsidy_claim_batch_items" in compact:
            self.current = self.items_by_batch.get(params[0], [])

    def fetchone(self):
        return self.current

    def fetchall(self):
        return list(self.current or [])


def _row(**updates):
    row = {
        "id": 8,
        "dedup_fingerprint": FINGERPRINT,
        "format_id": "taishin",
        "transaction_date": "2026-07-15",
        "debit": None,
        "credit": Decimal("1000"),
        "direction": "incoming",
        "classification_type": "government_subsidy",
        "reconciliation_status": "pending",
        "reconciliation_reference": None,
    }
    row.update(updates)
    return row


def _batch(batch_id=3):
    return {"id": batch_id, "status": "approved", "approved_amount": Decimal("1000"),
            "paid_amount": Decimal("0")}


def _items(batch_id=3):
    return [
        {"id": 31, "batch_id": batch_id, "approved_amount": Decimal("400"), "paid_amount": Decimal("0")},
        {"id": 32, "batch_id": batch_id, "approved_amount": Decimal("600"), "paid_amount": Decimal("0")},
    ]


def test_unique_exact_approved_batch_is_fully_reconciled():
    cursor = FakeCursor(row=_row(), batches=[_batch()], items_by_batch={3: _items()})

    result = reconcile_government_subsidy(cursor, 8)

    assert result == {
        "result": "reconciled", "batch_id": 3, "bank_amount": Decimal("1000"),
        "expected_amount": Decimal("1000"), "transaction_id": 91,
    }
    assert sum(sql.startswith("INSERT INTO government_subsidy_allocations") for sql, _ in cursor.calls) == 2
    assert sum(sql.startswith("UPDATE subsidy_claim_batch_items") for sql, _ in cursor.calls) == 2
    assert any("status = 'paid'" in sql for sql, _ in cursor.calls)
    assert any("reconciliation_status = 'reconciled'" in sql for sql, _ in cursor.calls)
    transaction_insert = next(
        params for sql, params in cursor.calls
        if sql.startswith("INSERT INTO government_subsidy_transactions")
    )
    staging_update = next(
        params for sql, params in cursor.calls
        if sql.startswith("UPDATE finance_import_rows")
    )
    assert transaction_insert[-1] == EXTERNAL_REFERENCE
    assert staging_update == (EXTERNAL_REFERENCE, 8)


@pytest.mark.parametrize(
    ("row_updates", "batches", "items_by_batch"),
    [
        ({"format_id": "sinopac"}, [_batch()], {3: _items()}),
        ({"direction": "outgoing"}, [_batch()], {3: _items()}),
        ({"debit": Decimal("1")}, [_batch()], {3: _items()}),
        ({"credit": Decimal("999")}, [], {}),
        ({}, [_batch(3), _batch(4)], {3: _items(3), 4: _items(4)}),
        ({}, [_batch()], {3: [{**_items()[0], "approved_amount": Decimal("399")}, _items()[1]]}),
        ({}, [_batch()], {3: [{**_items()[0], "paid_amount": Decimal("1")}, _items()[1]]}),
    ],
)
def test_invalid_difference_or_non_unique_candidate_stays_pending(row_updates, batches, items_by_batch):
    cursor = FakeCursor(row=_row(**row_updates), batches=batches, items_by_batch=items_by_batch)

    result = reconcile_government_subsidy(cursor, 8)

    assert result["result"] == "pending"
    assert not any(sql.startswith("INSERT") or sql.startswith("UPDATE") for sql, _ in cursor.calls)


def test_confirmed_batch_only_narrows_candidate_and_cannot_bypass_exact_amount():
    cursor = FakeCursor(
        row=_row(), batches=[{**_batch(), "approved_amount": Decimal("999")}],
        items_by_batch={3: _items()},
    )
    result = reconcile_government_subsidy(cursor, 8, 3)
    assert result["result"] == "pending"
    assert not any(sql.startswith("INSERT") for sql, _ in cursor.calls)


def test_duplicate_derived_external_reference_for_another_row_stays_pending():
    cursor = FakeCursor(
        row=_row(), duplicate_reference={
            "id": 1, "claim_batch_id": 3, "finance_import_row_id": 99,
            "amount": Decimal("1000"), "external_reference": EXTERNAL_REFERENCE,
        },
    )
    result = reconcile_government_subsidy(cursor, 8)
    assert result["result"] == "pending"
    assert not any(sql.startswith("INSERT") for sql, _ in cursor.calls)


@pytest.mark.parametrize("fingerprint", [None, "", "A" * 64, "a" * 63, "g" * 64])
def test_missing_or_invalid_fingerprint_stays_pending_without_writes(fingerprint):
    cursor = FakeCursor(row=_row(dedup_fingerprint=fingerprint))

    result = reconcile_government_subsidy(cursor, 8)

    assert result["result"] == "pending"
    assert "dedup_fingerprint" in result["reason"]
    assert not any(sql.startswith("INSERT") or sql.startswith("UPDATE") for sql, _ in cursor.calls)


def test_reconciled_row_is_idempotent_only_with_matching_transaction():
    transaction = {
        "id": 91, "claim_batch_id": 3, "finance_import_row_id": 8,
        "amount": Decimal("1000"), "external_reference": EXTERNAL_REFERENCE,
    }
    cursor = FakeCursor(
        row=_row(reconciliation_status="reconciled", reconciliation_reference=EXTERNAL_REFERENCE),
        transaction_for_row=transaction,
    )
    result = reconcile_government_subsidy(cursor, 8)
    assert result["result"] == "existing"
    assert result["transaction_id"] == 91
    assert not any(sql.startswith("INSERT") or sql.startswith("UPDATE") for sql, _ in cursor.calls)


def test_reconciled_row_requires_derived_staging_reference_for_idempotency():
    transaction = {
        "id": 91, "claim_batch_id": 3, "finance_import_row_id": 8,
        "amount": Decimal("1000"), "external_reference": EXTERNAL_REFERENCE,
    }
    cursor = FakeCursor(
        row=_row(reconciliation_status="reconciled", reconciliation_reference="BANK-001"),
        transaction_for_row=transaction,
    )

    result = reconcile_government_subsidy(cursor, 8)

    assert result["result"] == "pending"
    assert not any(sql.startswith("INSERT") or sql.startswith("UPDATE") for sql, _ in cursor.calls)
