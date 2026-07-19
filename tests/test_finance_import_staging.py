from decimal import Decimal
import json
from pathlib import Path

import pytest

from services import finance_import_staging as staging


class FakeCursor:
    def __init__(self, fail_on_execute=None, existing_rows=None):
        self.executed = []
        self.lastrowid = None
        self._next_id = 100
        self.fail_on_execute = fail_on_execute
        self.rows_by_fingerprint = dict(existing_rows or {})
        self._fetchone = None

    def execute(self, sql, params):
        statement = " ".join(sql.split())
        self.executed.append((statement, params))
        if self.fail_on_execute == len(self.executed):
            raise RuntimeError("database write failed")
        if statement.startswith("SELECT id, classification_type, reconciliation_status"):
            self._fetchone = self.rows_by_fingerprint.get(params[0])
            return
        if statement.startswith("INSERT INTO"):
            self.lastrowid = self._next_id
            self._next_id += 1
        if statement.startswith("INSERT INTO finance_import_rows"):
            self.rows_by_fingerprint[params[0]] = {
                "id": self.lastrowid,
                "classification_type": "pending",
                "reconciliation_status": "pending",
            }
        elif statement.startswith("UPDATE finance_import_rows"):
            row_id = params[-1]
            for row in self.rows_by_fingerprint.values():
                if row["id"] == row_id:
                    row["classification_type"] = params[0]
                    break

    def fetchone(self):
        return self._fetchone


def _row(source_row=17):
    return {
        "format_id": "taishin",
        "source_file": "任意檔名.xlsx",
        "source_bank_account": None,
        "sheet_name": "交易明細查詢",
        "source_row": source_row,
        "source_reference": None,
        "transaction_date": "2026-07-15",
        "transaction_time": "09:08:07",
        "posting_date": "2026-07-15",
        "value_date": None,
        "debit": Decimal("1200.00"),
        "credit": None,
        "direction": "outgoing",
        "balance": Decimal("8000.00"),
        "currency": None,
        "summary": "轉帳",
        "memo": "對象,0012345678901234",
        "counterparty_name": None,
        "counterparty_account": "0012345678901234",
        "cancellation_code": None,
        "bank_references": {"sequence": "0001", "amount": "1200.00"},
        "warnings": ["review_required"],
        "raw_payload": {"支出金額": "1200.00", "備註": "原始備註"},
    }


def _normalized(rows):
    return {
        "format_id": "taishin",
        "sheet_name": "交易明細查詢",
        "header_row": 16,
        "normalized_rows": rows,
    }


def test_stages_raw_row_before_classification_and_keeps_reconciliation_pending(monkeypatch):
    cursor = FakeCursor()
    calls = []

    def classifier(row, client_accounts, staff_accounts):
        assert any(sql.startswith("INSERT INTO finance_import_rows") for sql, _ in cursor.executed)
        calls.append((row, client_accounts, staff_accounts))
        return {
            "classification_type": "client_subsidy_return",
            "matched_identity_ids": [8],
            "resolved_counterparty_account": "0012345678901234",
            "reason": "unique exact account",
        }

    monkeypatch.setattr(staging, "classify_finance_transaction", classifier)

    result = staging.stage_finance_rows(
        cursor,
        _normalized([_row()]),
        {
            "client_refund_accounts": {"0012345678901234": [8]},
            "staff_accounts": {},
        },
    )

    assert result == {
        "batch_id": 100,
        "staged_rows": [
            {
                "row_id": 101,
                "dedup_fingerprint": staging.build_dedup_fingerprint(_row()),
                "classification_type": "client_subsidy_return",
                "resolved_counterparty_account": "0012345678901234",
                "reconciliation_status": "pending",
                "result": "inserted",
            }
        ],
    }
    assert len(calls) == 1
    assert cursor.executed[0][0].startswith("INSERT INTO finance_import_batches")
    assert cursor.executed[1][0].startswith("SELECT id, classification_type, reconciliation_status")
    assert cursor.executed[2][0].startswith("INSERT INTO finance_import_rows")
    assert "'pending'" in cursor.executed[2][0]
    assert cursor.executed[3][0].startswith("INSERT INTO finance_import_occurrences")
    assert cursor.executed[4][0].startswith("UPDATE finance_import_rows")
    assert "reconciliation_status" not in cursor.executed[4][0]
    assert "resolved_counterparty_account=%s" in cursor.executed[4][0]
    assert "SET counterparty_account=%s" not in cursor.executed[4][0]
    assert cursor.executed[2][1][20] == "0012345678901234"
    assert cursor.executed[4][1] == (
        "client_subsidy_return",
        "[8]",
        "0012345678901234",
        "unique exact account",
        101,
    )


def test_decimal_safe_json_preserves_all_structured_source_fields(monkeypatch):
    cursor = FakeCursor()
    row = _row()
    row["bank_references"]["amount"] = Decimal("1200.00")
    row["raw_payload"]["支出金額"] = Decimal("1200.00")
    monkeypatch.setattr(staging, "build_dedup_fingerprint", lambda _: "a" * 64)
    monkeypatch.setattr(
        staging,
        "classify_finance_transaction",
        lambda *args: {
            "classification_type": "non_business_review",
            "matched_identity_ids": [],
            "reason": "manual review",
        },
    )

    staging.stage_finance_rows(cursor, _normalized([row]), {"client_refund_accounts": {}, "staff_accounts": {}})

    row_params = cursor.executed[2][1]
    assert json.loads(row_params[22]) == {"amount": "1200.00", "sequence": "0001"}
    assert json.loads(row_params[23]) == ["review_required"]
    assert json.loads(row_params[24]) == {"備註": "原始備註", "支出金額": "1200.00"}
    classification_params = cursor.executed[4][1]
    assert json.loads(classification_params[1]) == []


def test_every_row_is_staged_and_classified_without_partial_return(monkeypatch):
    cursor = FakeCursor()
    second_row = _row(18)
    second_row["balance"] = Decimal("6800.00")
    monkeypatch.setattr(
        staging,
        "classify_finance_transaction",
        lambda row, *_: {
            "classification_type": "non_business_review",
            "matched_identity_ids": [],
            "reason": f"row {row['source_row']}",
        },
    )

    result = staging.stage_finance_rows(
        cursor,
        _normalized([_row(17), second_row]),
        {"client_refund_accounts": {}, "staff_accounts": {}},
    )

    assert [item["row_id"] for item in result["staged_rows"]] == [101, 103]
    assert all(item["result"] == "inserted" for item in result["staged_rows"])
    assert all(item["reconciliation_status"] == "pending" for item in result["staged_rows"])
    assert sum(sql.startswith("INSERT INTO finance_import_rows") for sql, _ in cursor.executed) == 2
    assert sum(sql.startswith("INSERT INTO finance_import_occurrences") for sql, _ in cursor.executed) == 2
    assert sum(sql.startswith("UPDATE finance_import_rows") for sql, _ in cursor.executed) == 2


def test_write_error_propagates_for_caller_rollback(monkeypatch):
    cursor = FakeCursor(fail_on_execute=3)
    monkeypatch.setattr(
        staging,
        "classify_finance_transaction",
        lambda *args: pytest.fail("classification must not run before raw row insert succeeds"),
    )

    with pytest.raises(RuntimeError, match="database write failed"):
        staging.stage_finance_rows(
            cursor,
            _normalized([_row()]),
            {"client_refund_accounts": {}, "staff_accounts": {}},
        )


def test_classifier_error_occurs_after_raw_row_was_saved_and_propagates(monkeypatch):
    cursor = FakeCursor()

    def classifier(*args):
        raise ValueError("classification failed")

    monkeypatch.setattr(staging, "classify_finance_transaction", classifier)

    with pytest.raises(ValueError, match="classification failed"):
        staging.stage_finance_rows(
            cursor,
            _normalized([_row()]),
            {"client_refund_accounts": {}, "staff_accounts": {}},
        )

    assert cursor.executed[-2][0].startswith("INSERT INTO finance_import_rows")
    assert cursor.executed[-1][0].startswith("INSERT INTO finance_import_occurrences")


def test_empty_normalized_result_still_creates_batch(monkeypatch):
    cursor = FakeCursor()
    monkeypatch.setattr(
        staging,
        "classify_finance_transaction",
        lambda *args: pytest.fail("empty batch must not classify"),
    )

    result = staging.stage_finance_rows(
        cursor,
        _normalized([]),
        {"client_refund_accounts": {}, "staff_accounts": {}},
    )

    assert result == {"batch_id": 100, "staged_rows": []}
    assert len(cursor.executed) == 1


def test_service_does_not_import_or_write_formal_accounting_modules():
    source = Path("services/finance_import_staging.py").read_text(encoding="utf-8")

    assert "get_connection" not in source
    assert "client_payment" not in source
    assert "staff_payment" not in source
    assert "government_subsidy_transactions" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source


def test_existing_fingerprint_only_adds_occurrence_and_keeps_existing_state(monkeypatch):
    fingerprint = staging.build_dedup_fingerprint(_row())
    cursor = FakeCursor(
        existing_rows={
            fingerprint: {
                "id": 77,
                "classification_type": "manually_adjusted",
                "reconciliation_status": "reconciled",
            }
        }
    )
    monkeypatch.setattr(
        staging,
        "classify_finance_transaction",
        lambda *args: pytest.fail("existing canonical row must not be reclassified"),
    )

    result = staging.stage_finance_rows(
        cursor,
        _normalized([_row()]),
        {"client_refund_accounts": {}, "staff_accounts": {}},
    )

    assert result["staged_rows"] == [{
        "row_id": 77,
        "dedup_fingerprint": fingerprint,
        "classification_type": "manually_adjusted",
        "reconciliation_status": "reconciled",
        "result": "skipped_existing",
    }]
    assert sum(sql.startswith("INSERT INTO finance_import_rows") for sql, _ in cursor.executed) == 0
    assert sum(sql.startswith("INSERT INTO finance_import_occurrences") for sql, _ in cursor.executed) == 1
    assert sum(sql.startswith("UPDATE finance_import_rows") for sql, _ in cursor.executed) == 0


def test_duplicate_fingerprint_in_same_batch_keeps_both_occurrences_and_warns(monkeypatch):
    cursor = FakeCursor()
    classifier_calls = []
    monkeypatch.setattr(
        staging,
        "classify_finance_transaction",
        lambda row, *_: classifier_calls.append(row) or {
            "classification_type": "non_business_review",
            "matched_identity_ids": [],
            "reason": "manual review",
        },
    )

    result = staging.stage_finance_rows(
        cursor,
        _normalized([_row(17), _row(18)]),
        {"client_refund_accounts": {}, "staff_accounts": {}},
    )

    assert [item["result"] for item in result["staged_rows"]] == ["inserted", "skipped_existing"]
    assert len(classifier_calls) == 1
    occurrences = [params for sql, params in cursor.executed if sql.startswith("INSERT INTO finance_import_occurrences")]
    assert len(occurrences) == 2
    assert "duplicate_fingerprint_in_same_batch" not in json.loads(occurrences[0][-1])
    assert "duplicate_fingerprint_in_same_batch" in json.loads(occurrences[1][-1])
