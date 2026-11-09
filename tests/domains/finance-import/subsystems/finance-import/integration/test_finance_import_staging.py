from decimal import Decimal
import json
from pathlib import Path

import pytest

from subsystems.finance_import import staging


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
        if statement.startswith(("SELECT id, classification_type, matched_identity_ids", "SELECT id FROM finance_import_rows")):
            self._fetchone = self.rows_by_fingerprint.get(params[0])
            return
        if statement.startswith("INSERT INTO"):
            self.lastrowid = self._next_id
            self._next_id += 1
        if statement.startswith("INSERT INTO finance_import_rows"):
            self.rows_by_fingerprint[params[0]] = {
                "id": self.lastrowid,
                "classification_type": "pending",
                "matched_identity_ids": [],
                "resolved_counterparty_account": None,
                "reconciliation_status": "pending",
                "source_reference": params[7], "posting_date": params[10],
                "value_date": params[11], "currency": params[16],
                "counterparty_name": params[19], "counterparty_account": params[20],
                "bank_references": params[22], "has_formal_reference": False,
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

    def classifier(row, client_accounts, staff_accounts, subsidy_return_accounts, receipt_candidates):
        assert any(sql.startswith("INSERT INTO finance_import_rows") for sql, _ in cursor.executed)
        calls.append(
            (
                row,
                client_accounts,
                staff_accounts,
                subsidy_return_accounts,
                receipt_candidates,
            )
        )
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
                "matched_identity_ids": [8],
                "resolved_counterparty_account": "0012345678901234",
                "reconciliation_status": "pending",
                "result": "inserted",
            }
        ],
    }
    assert len(calls) == 1
    assert cursor.executed[0][0].startswith("INSERT INTO finance_import_batches")
    assert cursor.executed[1][0].startswith("SELECT id, classification_type, matched_identity_ids")
    assert cursor.executed[2][0].startswith("INSERT INTO finance_import_rows")
    assert "'pending'" in cursor.executed[2][0]
    assert cursor.executed[3][0].startswith("INSERT INTO finance_import_occurrences")
    assert cursor.executed[4][0].startswith("UPDATE finance_import_rows")
    assert "reconciliation_status" not in cursor.executed[4][0]
    assert "resolved_counterparty_account=%s" in cursor.executed[4][0]
    assert "classified_at=CURRENT_TIMESTAMP" in cursor.executed[4][0]
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


def test_canonical_staging_does_not_import_or_write_formal_accounting_modules():
    source = Path("subsystems/finance_import/staging.py").read_text(encoding="utf-8")

    assert "get_connection" not in source
    assert "client_payment" not in source
    assert "staff_payment" not in source
    assert "government_subsidy_transactions" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source


def test_existing_fingerprint_keeps_existing_state_without_another_occurrence(monkeypatch):
    fingerprint = staging.build_dedup_fingerprint(_row())
    cursor = FakeCursor(
        existing_rows={
            fingerprint: {
                **_row(),
                "has_formal_reference": True,
                "id": 77,
                "classification_type": "manually_adjusted",
                "matched_identity_ids": "[8]",
                "resolved_counterparty_account": "0012345678901234",
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
        "matched_identity_ids": [8],
        "resolved_counterparty_account": "0012345678901234",
        "reconciliation_status": "reconciled",
        "result": "skipped_existing",
    }]
    assert sum(sql.startswith("INSERT INTO finance_import_rows") for sql, _ in cursor.executed) == 0
    assert sum(sql.startswith("INSERT INTO finance_import_occurrences") for sql, _ in cursor.executed) == 0
    assert sum(sql.startswith("UPDATE finance_import_rows") for sql, _ in cursor.executed) == 0


def test_duplicate_fingerprint_in_same_batch_saves_only_one_occurrence(monkeypatch):
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
    assert len(occurrences) == 1
    assert json.loads(occurrences[0][-1]) == _row()["warnings"]


@pytest.mark.parametrize("formally_dispatched", [False, True])
def test_same_fingerprint_ignores_changed_non_identity_fields(formally_dispatched):
    original = _row()
    fingerprint = staging.build_dedup_fingerprint(original)
    stored = {
        **original, "id": 77, "classification_type": "non_business_review",
        "matched_identity_ids": [], "resolved_counterparty_account": None,
        "reconciliation_status": "pending", "has_formal_reference": formally_dispatched,
    }
    incoming = {**original, "posting_date": "2026-07-16"}
    assert staging.build_dedup_fingerprint(incoming) == fingerprint
    cursor = FakeCursor(existing_rows={fingerprint: stored})
    staging.stage_finance_rows(cursor, _normalized([incoming]), {})
    assert not any(
        sql.startswith(("INSERT INTO finance_import_integrity_events", "INSERT INTO finance_import_occurrences"))
        for sql, _ in cursor.executed
    )


def test_taishin_outgoing_unknown_recipient_is_preserved_for_review():
    cursor = FakeCursor()
    row_known = _row(17)
    row_known["memo"] = "林小美退款"
    row_unknown = _row(18)
    row_unknown["memo"] = "私人轉帳未知對象"

    result = staging.stage_finance_rows(
        cursor,
        _normalized([row_known, row_unknown]),
        {
            "client_refund_accounts": {},
            "staff_accounts": {},
            "all_client_names": ("林小美",),
        },
    )

    assert len(result["staged_rows"]) == 2
    assert result["staged_rows"][1]["classification_type"] == "non_business_review"
    insert_calls = [sql for sql, _ in cursor.executed if sql.startswith("INSERT INTO finance_import_rows")]
    assert len(insert_calls) == 2


def test_sinopac_unmatched_rows_remain_separate_bank_facts():
    cursor = FakeCursor()
    row_valid_incoming = {
        "format_id": "sinopac",
        "source_file": "永豐明細.xlsx",
        "source_bank_account": None,
        "sheet_name": "明細",
        "source_row": 2,
        "source_reference": None,
        "transaction_date": "2026-08-10",
        "transaction_time": "10:00:00",
        "posting_date": "2026-08-10",
        "value_date": None,
        "debit": None,
        "credit": Decimal("30000.00"),
        "direction": "incoming",
        "balance": Decimal("30000.00"),
        "currency": "TWD",
        "summary": "客戶繳款",
        "memo": "99781699115001",
        "counterparty_name": None,
        "counterparty_account": None,
        "cancellation_code": "99781699115001",
        "bank_references": {"銷帳編號": "99781699115001"},
        "warnings": [],
        "raw_payload": {},
    }
    row_junk_incoming = {
        "format_id": "sinopac",
        "source_file": "永豐明細.xlsx",
        "source_bank_account": None,
        "sheet_name": "明細",
        "source_row": 3,
        "source_reference": None,
        "transaction_date": "2026-08-10",
        "transaction_time": "10:05:00",
        "posting_date": "2026-08-10",
        "value_date": None,
        "debit": None,
        "credit": Decimal("15.00"),
        "direction": "incoming",
        "balance": Decimal("30015.00"),
        "currency": "TWD",
        "summary": "存款息",
        "memo": "銀行利息",
        "counterparty_name": None,
        "counterparty_account": None,
        "cancellation_code": None,
        "bank_references": {},
        "warnings": [],
        "raw_payload": {},
    }
    row_junk_outgoing = {
        "format_id": "sinopac",
        "source_file": "永豐明細.xlsx",
        "source_bank_account": None,
        "sheet_name": "明細",
        "source_row": 4,
        "source_reference": None,
        "transaction_date": "2026-08-10",
        "transaction_time": "11:00:00",
        "posting_date": "2026-08-10",
        "value_date": None,
        "debit": Decimal("500.00"),
        "credit": None,
        "direction": "outgoing",
        "balance": Decimal("29515.00"),
        "currency": "TWD",
        "summary": "水電費",
        "memo": "水費自動扣繳",
        "counterparty_name": None,
        "counterparty_account": None,
        "cancellation_code": None,
        "bank_references": {},
        "warnings": [],
        "raw_payload": {},
    }

    result = staging.stage_finance_rows(
        cursor,
        {
            "format_id": "sinopac",
            "sheet_name": "明細",
            "header_row": 1,
            "normalized_rows": [row_valid_incoming, row_junk_incoming, row_junk_outgoing],
        },
        {
            "client_refund_accounts": {},
            "staff_accounts": {},
            "client_receipt_candidates": (),
            "staff_case_suffixes": {},
            "client_refund_case_suffixes": {},
        },
    )

    assert [row["classification_type"] for row in result["staged_rows"]] == [
        "client_receipt", "non_business_review", "non_business_review",
    ]
    insert_calls = [sql for sql, _ in cursor.executed if sql.startswith("INSERT INTO finance_import_rows")]
    assert len(insert_calls) == 3


def _normalized_row(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "format_id": "taishin",
        "source_file": "taishin.xlsx",
        "source_bank_account": "000000000001",
        "sheet_name": "交易明細查詢",
        "source_row": 2,
        "source_reference": None,
        "transaction_date": "2026-10-15",
        "transaction_time": "09:00:00",
        "posting_date": "2026-10-15",
        "value_date": None,
        "debit": None,
        "credit": Decimal("10000"),
        "direction": "incoming",
        "balance": Decimal("80000"),
        "currency": "TWD",
        "summary": "轉帳",
        "memo": "借款",
        "counterparty_name": None,
        "counterparty_account": None,
        "cancellation_code": None,
        "bank_references": {"sequence": "0001"},
        "warnings": [],
        "raw_payload": {"memo": "借款"},
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(("bank", "expected", "unrelated"), [
    ("taishin", "新竹市政府補助入款", "借款"),
    ("sinopac", "虛擬帳號入帳", "無關轉帳"),
])
def test_business_only_staging_keeps_only_matched_new_transactions(bank, expected, unrelated):
    matched = _normalized_row(format_id=bank, source_row=3, memo=expected, cancellation_code="99781699115001",
                              bank_references={"銷帳編號": "99781699115001"})
    unmatched = _normalized_row(format_id=bank, source_row=2, memo=unrelated)
    cursor = FakeCursor()
    result = staging.stage_finance_rows(
        cursor, {**_normalized([unmatched, matched]), "format_id": bank},
        {"known_virtual_accounts": frozenset({"99781699115001"})}, business_only=True,
    )
    assert len(result["staged_rows"]) == 1
    assert result["staged_rows"][0]["dedup_fingerprint"] == staging.build_dedup_fingerprint(matched)


@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
@pytest.mark.parametrize("amount", [11899, 12001])
def test_business_only_staging_preserves_known_same_month_payout_differences(bank, amount):
    row = _normalized_row(format_id=bank, direction="outgoing", debit=Decimal(amount), credit=None,
                          memo="Synthetic Staff", counterparty_name="Synthetic Staff", bank_references={})
    identity_maps = {"staff_payout_candidates": ({
        "staff_id": 12, "name": "Synthetic Staff", "case_no": "115000001", "due_date": "2026-10-20", "amount_due_ntd": 12000,
    },)}
    result = staging.stage_finance_rows(
        FakeCursor(), {**_normalized([row]), "format_id": bank}, identity_maps, business_only=True,
    )
    assert result["staged_rows"][0]["matched_identity_ids"] == [12]


def test_workbook_staging_skips_recognized_staff_with_multiple_same_month_cases():
    row = _normalized_row(direction="outgoing", debit=Decimal(12000), credit=None,
                          memo="Synthetic Staff", counterparty_name="Synthetic Staff", bank_references={})
    first = {"staff_id": 12, "name": "Synthetic Staff", "case_no": "115000001",
             "due_date": "2026-10-20", "amount_due_ntd": 12000}
    cursor = FakeCursor()
    result = staging.stage_finance_rows(cursor, _normalized([row]), {
        "staff_payout_candidates": (first, {**first, "case_no": "115000002"}),
    }, business_only=True)

    assert result["staged_rows"] == []
    assert not any("INSERT INTO finance_import_rows" in statement for statement, _ in cursor.executed)


@pytest.mark.parametrize("resolved", [True, False])
@pytest.mark.parametrize("memo", ["HC115001", "115001月嫂薪資"])
def test_workbook_staging_keeps_taishin_client_subsidy_only_if_memo_case_is_unique(monkeypatch, resolved, memo):
    row = _normalized_row(direction="outgoing", debit=Decimal(12000), credit=None,
                          memo=memo, bank_references={})
    monkeypatch.setattr(staging, "resolve_client_virtual_account_suffix", lambda _cursor, suffix: {
        "result": "resolved" if resolved and suffix == "115001" else "pending",
    })
    cursor = FakeCursor()
    result = staging.stage_finance_rows(cursor, _normalized([row]), {
        "known_case_suffixes": frozenset({"115001"}),
    }, business_only=True)

    assert len(result["staged_rows"]) == int(resolved)
    if resolved:
        assert result["staged_rows"][0]["classification_type"] == "client_subsidy_return"
        assert result["staged_rows"][0]["matched_identity_ids"] == []
    else:
        assert not any("INSERT INTO finance_import_rows" in statement for statement, _ in cursor.executed)


def test_taishin_staff_name_precedes_an_unrelated_six_digit_memo_without_an_account(monkeypatch):
    row = _normalized_row(direction="outgoing", debit=Decimal(12000), credit=None,
                          memo="Synthetic Staff HC115002", counterparty_account=None, bank_references={})
    monkeypatch.setattr(staging, 'resolve_client_virtual_account_suffix',
                        lambda *_: pytest.fail('Staff name must take priority over the six-digit memo'))
    result = staging.stage_finance_rows(FakeCursor(), _normalized([row]), {
        'all_staff_names': ('Synthetic Staff',),
        'staff_payout_candidates': ({'staff_id': 12, 'name': 'Synthetic Staff', 'case_no': '115000001',
            'due_date': '2026-10-20', 'amount_due_ntd': 12000},),
    }, business_only=True)
    assert result['staged_rows'][0]['classification_type'] == 'staff_salary'
    assert result['staged_rows'][0]['matched_identity_ids'] == [12]


def test_incoming_name_account_and_amount_without_a_virtual_account_is_not_persisted():
    row = _normalized_row(format_id='sinopac', direction='incoming', debit=None, credit=Decimal(12000),
                          cancellation_code=None, memo='Synthetic Client', counterparty_name='Synthetic Client',
                          counterparty_account='synthetic-account', bank_references={})
    cursor = FakeCursor()
    result = staging.stage_finance_rows(cursor, {**_normalized([row]), 'format_id': 'sinopac'}, {
        'client_receipt_candidates': ({'client_id': 7, 'name': 'Synthetic Client',
            'account': 'synthetic-account', 'open_amounts': (12000,)},),
    }, business_only=True)
    assert result['staged_rows'] == []
    assert not any('INSERT INTO finance_import_rows' in sql for sql, _ in cursor.executed)


def test_business_only_staging_preserves_batch_name_when_all_rows_are_filtered():
    row = _normalized_row(source_file="only-loan.xlsx")
    cursor = FakeCursor()
    result = staging.stage_finance_rows(cursor, _normalized([row]), {}, business_only=True)
    assert result["staged_rows"] == []
    assert cursor.executed[0][1][1] == "only-loan.xlsx"
    assert cursor.executed[-1][1][0] == 0


@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
def test_business_only_repeat_checks_identity_before_classification(bank, monkeypatch):
    row = _normalized_row(format_id=bank)
    fingerprint = staging.build_dedup_fingerprint(row)
    cursor = FakeCursor(existing_rows={fingerprint: {"id": 77}})
    monkeypatch.setattr(staging, "classify_row_with_identity_maps",
                        lambda *_args: pytest.fail("an existing row must bypass admission"))

    result = staging.stage_finance_rows(
        cursor, {**_normalized([row]), "format_id": bank}, {}, business_only=True,
    )

    assert result["staged_rows"] == [{
        "row_id": 77, "dedup_fingerprint": fingerprint, "result": "skipped_existing",
    }]
    assert len(cursor.executed) == 2
