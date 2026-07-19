from datetime import date, time
from decimal import Decimal
import json

import pytest

from services.client_subsidy_return_transactions import record_client_subsidy_return


FINGERPRINT = "a" * 64


class Cursor:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.current = None
        self.executed = []
        self.lastrowid = None
        self.rowcount = 1

    def execute(self, sql, params):
        compact = " ".join(sql.split())
        self.executed.append((compact, params))
        if compact.startswith("SELECT"):
            self.current = next(self.responses)
        elif compact.startswith("INSERT"):
            self.lastrowid = 701

    def fetchone(self):
        return self.current

    def fetchall(self):
        return list(self.current or [])


def row(**changes):
    value = {
        "finance_import_row_id": 31,
        "format_id": "taishin",
        "dedup_fingerprint": FINGERPRINT,
        "transaction_date": date(2026, 7, 14),
        "transaction_time": time(9, 8, 7),
        "direction": "outgoing",
        "debit": Decimal("1250.00"),
        "classification_type": "client_subsidy_return",
        "reconciliation_status": "pending",
        "reconciliation_reference": None,
        "matched_identity_ids": [9],
        "client_payment_id": 9,
        "case_no": "CASE-9",
        "subsidy_return_receivable": Decimal("1500.00"),
        "subsidy_return_refunded": Decimal("250.00"),
        "subsidy_return_at": None,
    }
    value.update(changes)
    return value


def refund(transaction_id, amount, occurred_at="2026-07-01", **changes):
    value = {
        "id": transaction_id,
        "transaction_type": "refund",
        "transaction_status": "succeeded",
        "amount": Decimal(str(amount)),
        "occurred_at": occurred_at,
        "external_reference": f"manual:{transaction_id}",
        "reversal_of_transaction_id": None,
        "finance_import_row_id": None,
    }
    value.update(changes)
    return value


def existing_transaction(**changes):
    value = {
        "id": 701,
        "client_payment_id": 9,
        "case_no": "CASE-9",
        "finance_import_row_id": 31,
        "stage": "subsidy_return",
        "transaction_type": "refund",
        "transaction_status": "succeeded",
        "amount": Decimal("1250"),
        "occurred_at": date(2026, 7, 14),
        "external_reference": f"fp:{FINGERPRINT}",
        "reversal_of_transaction_id": None,
    }
    value.update(changes)
    return value


def test_exact_unique_taishin_debit_is_reconciled_with_formal_fields():
    cursor = Cursor([row(), [], [refund(100, 250)]])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result == {
        "transaction_id": 701,
        "obligation": {
            "subsidy_return_receivable": Decimal("1500"),
            "subsidy_return_refunded": Decimal("1500"),
            "subsidy_return_remaining": Decimal("0"),
            "subsidy_return_at": "2026-07-14",
        },
        "result": "reconciled",
    }
    statements = [sql for sql, _ in cursor.executed]
    insert_sql, insert_params = next(
        (sql, params) for sql, params in cursor.executed if sql.startswith("INSERT")
    )
    assert "transaction_status" in insert_sql
    assert "'subsidy_return','refund','succeeded'" in insert_sql
    assert insert_params[-3] == "2026-07-14"
    assert insert_params[-2] == f"fp:{FINGERPRINT}"
    assert any("SET subsidy_return_refunded=%s, subsidy_return_at=%s" in sql for sql in statements)
    staging_sql, staging_params = next(
        (sql, params) for sql, params in cursor.executed
        if sql.startswith("UPDATE finance_import_rows")
    )
    assert "reconciliation_reference=%s" in staging_sql
    assert "reconciled_at=CURRENT_TIMESTAMP" in staging_sql
    assert "reconciled_transaction_id" not in staging_sql
    assert staging_params == (f"fp:{FINGERPRINT}", 31)


def test_succeeded_reversal_is_subtracted_before_exact_remaining_match():
    transactions = [
        refund(100, 500),
        {
            **refund(101, 250, occurred_at="2026-07-05"),
            "transaction_type": "reversal",
            "reversal_of_transaction_id": 100,
        },
    ]
    cursor = Cursor([row(), [], transactions])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "reconciled"
    assert result["obligation"]["subsidy_return_refunded"] == Decimal("1500")


def test_failed_refund_does_not_increase_recomputed_refunded_amount():
    transactions = [refund(100, 250), refund(101, 999, transaction_status="failed")]
    cursor = Cursor([row(), [], transactions])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "reconciled"
    assert result["obligation"]["subsidy_return_refunded"] == Decimal("1500")


@pytest.mark.parametrize("debit", [Decimal("1249.99"), Decimal("1250.01"), None, "invalid"])
def test_amount_difference_remains_pending_without_writes(debit):
    cursor = Cursor([row(debit=debit), [], [refund(100, 250)]])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "pending"
    assert result["reason"] == "amount_mismatch"
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.executed)


@pytest.mark.parametrize("fingerprint", [None, "", "A" * 64, "a" * 63, "g" * 64])
def test_missing_or_invalid_fingerprint_remains_pending(fingerprint):
    cursor = Cursor([row(dedup_fingerprint=fingerprint)])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "pending"
    assert result["reason"] == "fingerprint_missing_or_invalid"
    assert len(cursor.executed) == 1


@pytest.mark.parametrize(
    "matched_ids",
    [[], [10], [9, 10], json.dumps([]), json.dumps([9, 10]), "invalid-json"],
)
def test_identity_must_be_exactly_the_input_client_payment(matched_ids):
    cursor = Cursor([row(matched_identity_ids=matched_ids)])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "pending"
    assert result["reason"] == "matched_identity_not_unique"
    assert len(cursor.executed) == 1


def test_json_identity_with_one_exact_id_is_accepted():
    cursor = Cursor([row(matched_identity_ids=json.dumps([9])), [], [refund(100, 250)]])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "reconciled"


@pytest.mark.parametrize(
    ("change", "value"),
    [("format_id", "sinopac"), ("direction", "incoming"), ("classification_type", "government_subsidy")],
)
def test_ineligible_staging_row_remains_pending(change, value):
    cursor = Cursor([row(**{change: value})])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "pending"
    assert result["reason"] == "staging_row_not_eligible"
    assert len(cursor.executed) == 1


def test_missing_bank_date_stays_pending_without_writes():
    cursor = Cursor([row(transaction_date=None)])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "pending"
    assert result["reason"] == "transaction_date_missing_or_invalid"
    assert len(cursor.executed) == 1


def test_retry_returns_only_completely_identical_existing_transaction():
    staged = row(
        reconciliation_status="reconciled",
        reconciliation_reference=f"fp:{FINGERPRINT}",
        subsidy_return_receivable=Decimal("1250"),
        subsidy_return_refunded=Decimal("1250"),
    )
    existing = existing_transaction()
    cursor = Cursor([staged, [existing], [existing]])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "existing"
    assert result["transaction_id"] == 701
    assert result["obligation"]["subsidy_return_at"] == "2026-07-14"
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.executed)


def test_retry_rejects_existing_transaction_with_different_formal_field():
    staged = row(
        reconciliation_status="reconciled",
        reconciliation_reference=f"fp:{FINGERPRINT}",
    )
    existing = existing_transaction(amount=Decimal("1249.99"))
    cursor = Cursor([staged, [existing], [existing]])

    with pytest.raises(ValueError, match="different transaction"):
        record_client_subsidy_return(cursor, 9, 31)


def test_retry_rejects_existing_transaction_with_different_case_no():
    staged = row(
        reconciliation_status="reconciled",
        reconciliation_reference=f"fp:{FINGERPRINT}",
    )
    existing = existing_transaction(case_no="OTHER-CASE")
    cursor = Cursor([staged, [existing], [existing]])

    with pytest.raises(ValueError, match="different transaction"):
        record_client_subsidy_return(cursor, 9, 31)


def test_source_reference_cannot_override_fingerprint():
    staged = row(source_reference="CALLER-CONTROLLED")
    cursor = Cursor([staged, [], [refund(100, 250)]])

    result = record_client_subsidy_return(cursor, 9, 31)

    assert result["result"] == "reconciled"
    insert_params = next(params for sql, params in cursor.executed if sql.startswith("INSERT"))
    assert insert_params[-2] == f"fp:{FINGERPRINT}"
    assert "CALLER-CONTROLLED" not in insert_params
