from decimal import Decimal
import json
from pathlib import Path

import pytest

from subsystems.finance_import import staging


class FakeCursor:
    def __init__(self, fail_on_execute=None, existing_rows=None, *, staff_cases=None, client_cases=None):
        self.executed = []
        self.lastrowid = None
        self._next_id = 100
        self.fail_on_execute = fail_on_execute
        self.rows_by_fingerprint = dict(existing_rows or {})
        self._fetchone = None
        self._fetchall = ()
        self.staff_cases = staff_cases or {}
        self.client_cases = client_cases or {}

    def execute(self, sql, params):
        statement = " ".join(sql.split())
        self.executed.append((statement, params))
        if self.fail_on_execute == len(self.executed):
            raise RuntimeError("database write failed")
        self._fetchone = None
        self._fetchall = ()
        if statement.startswith("SELECT DISTINCT case_no FROM orders WHERE "):
            owners = self.staff_cases if "staff_id=%s" in statement else self.client_cases
            self._fetchall = tuple({"case_no": case} for case in owners.get(params[0], ()))
            return
        if statement.startswith(("SELECT case_no,staff_id AS person_id FROM orders", "SELECT case_no,client_id AS person_id FROM orders")):
            owners = self.staff_cases if "staff_id AS person_id" in statement else self.client_cases
            self._fetchall = tuple({"case_no": case, "person_id": owner} for owner in dict.fromkeys(params)
                                   for case in owners.get(owner, ()))
            return
        if statement.startswith("SELECT DISTINCT case_no FROM case_staff_assignments"):
            return
        if statement.startswith("SELECT client_id FROM orders WHERE case_no=%s"):
            self._fetchone = next(
                ({"client_id": owner} for owner, cases in self.client_cases.items() if params[0] in cases),
                None,
            )
            return
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

    def fetchall(self):
        return self._fetchall


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


@pytest.mark.parametrize("reconciliation_status", ["pending", "reconciled"])
@pytest.mark.parametrize("repeat_count", [1, 2])
def test_existing_fingerprint_keeps_existing_state_without_another_occurrence(
    monkeypatch, reconciliation_status, repeat_count,
):
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
                "reconciliation_status": reconciliation_status,
            }
        }
    )
    monkeypatch.setattr(
        staging,
        "classify_finance_transaction",
        lambda *args: pytest.fail("existing canonical row must not be reclassified"),
    )

    original = dict(cursor.rows_by_fingerprint[fingerprint])
    result = staging.stage_finance_rows(
        cursor,
        _normalized([
            {**_row(17 + index), "source_file": "另一檔案.xlsx"}
            for index in range(repeat_count)
        ]),
        {"client_refund_accounts": {}, "staff_accounts": {}},
    )

    assert result["staged_rows"] == [{
        "row_id": 77,
        "dedup_fingerprint": fingerprint,
        "classification_type": "manually_adjusted",
        "matched_identity_ids": [8],
        "resolved_counterparty_account": "0012345678901234",
        "reconciliation_status": reconciliation_status,
        "result": "skipped_existing",
    }] * repeat_count
    assert cursor.rows_by_fingerprint[fingerprint] == original
    assert sum(sql.startswith("INSERT INTO finance_import_rows") for sql, _ in cursor.executed) == 0
    assert sum(sql.startswith("INSERT INTO finance_import_occurrences") for sql, _ in cursor.executed) == 0
    assert sum(sql.startswith("UPDATE finance_import_rows") for sql, _ in cursor.executed) == 0


@pytest.mark.parametrize("business_only", [False, True])
def test_duplicate_fingerprint_in_same_batch_preserves_both_source_positions(monkeypatch, business_only):
    cursor = FakeCursor()
    classifier_calls = []
    monkeypatch.setattr(
        staging,
        "classify_finance_transaction",
        lambda row, *_, **__: classifier_calls.append(row) or {
            "classification_type": "government_subsidy",
            "matched_identity_ids": [],
            "reason": "manual review",
        },
    )

    rows = [
        {**_row(position), "direction": "incoming", "debit": None,
         "credit": Decimal("1200"), "memo": "新竹市政府補助款"}
        for position in (17, 18)
    ]
    rows[1]["warnings"] = ["second_source_warning"]
    assert staging.build_dedup_fingerprint(rows[0]) == staging.build_dedup_fingerprint(rows[1])
    result = staging.stage_finance_rows(
        cursor,
        _normalized(rows),
        {"client_refund_accounts": {}, "staff_accounts": {}},
        business_only=business_only,
    )

    assert [item["result"] for item in result["staged_rows"]] == ["inserted", "skipped_existing"]
    assert len(classifier_calls) == 1
    occurrences = [params for sql, params in cursor.executed if sql.startswith("INSERT INTO finance_import_occurrences")]
    row_id = result["staged_rows"][0]["row_id"]
    assert {item["row_id"] for item in result["staged_rows"]} == {row_id}
    assert sum(sql.startswith("INSERT INTO finance_import_rows") for sql, _ in cursor.executed) == 1
    assert len(occurrences) == 2
    for occurrence, row in zip(occurrences, rows, strict=True):
        assert occurrence[:5] == (
            result["batch_id"], row_id, row["source_file"], row["sheet_name"], row["source_row"],
        )
        assert json.loads(occurrence[-1]) == row["warnings"]


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


@pytest.mark.parametrize(("primary_staff", "retained"), [((), False), ((12,), True)])
def test_business_only_staging_retains_staff_return_with_verified_primary_account(primary_staff, retained):
    class ReturnCursor(FakeCursor):
        def execute(self, sql, params):
            super().execute(sql, params)
            if "FROM staff_bank_accounts WHERE account_no=" in sql:
                self._fetchall = tuple({"staff_id": staff_id} for staff_id in primary_staff)

    account = "000000000024"
    row = _normalized_row(format_id="sinopac", bank_references={"交易參考編號": account})
    result = staging.stage_finance_rows(
        ReturnCursor(), {**_normalized([row]), "format_id": "sinopac"},
        {"staff_accounts": {account: [12]}}, business_only=True,
    )
    assert bool(result["staged_rows"]) is retained
    if retained:
        assert result["staged_rows"][0]["classification_type"] == "non_business_review"


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


@pytest.mark.parametrize("other_case_amount", [12000, 20000])
def test_workbook_staging_skips_without_verified_memo_identity_when_multiple_cases(other_case_amount):
    row = _normalized_row(direction="outgoing", debit=Decimal(12000), credit=None,
                          memo="Synthetic Staff", counterparty_name="Synthetic Staff", bank_references={})
    first = {"staff_id": 12, "name": "Synthetic Staff", "case_no": "115000001",
             "due_date": "2026-10-20", "amount_due_ntd": 12000}
    cursor = FakeCursor()
    result = staging.stage_finance_rows(cursor, _normalized([row]), {
        "staff_payout_candidates": (first, {**first, "case_no": "115000002", "amount_due_ntd": other_case_amount}),
    }, business_only=True)

    assert result["staged_rows"] == []
    assert not any("INSERT INTO finance_import_rows" in statement for statement, _ in cursor.executed)


@pytest.mark.parametrize("staff_ids", [[12], [12, 13]])
def test_workbook_staging_retains_name_only_taishin_staff_without_formal_accounting(staff_ids):
    name = "合成缺應付款月嫂"
    row = _normalized_row(direction="outgoing", debit=Decimal(12000), credit=None,
                          memo=name + " 　GB,轉入0000000000000003", bank_references={})
    result = staging.stage_finance_rows(
        FakeCursor(staff_cases={12: ("115000001", "115000002")}), _normalized([row]),
        {"all_staff_names": (name,), "staff_name_identities": {name: staff_ids}}, business_only=True,
    )
    assert result["staged_rows"][0]["classification_type"] == "non_business_review"


@pytest.mark.parametrize("resolved", [True, False])
@pytest.mark.parametrize("memo", ["HC115001", "115001月嫂薪資", "ＨＣ１１５００１服務人員薪資", "ＨＣ１１５００１雇主補助款", "合成台新月嫂ＨＣ１１５００１薪資"])
def test_workbook_staging_keeps_taishin_case_for_manual_scheme_only_if_unique(monkeypatch, resolved, memo):
    row = _normalized_row(direction="outgoing", debit=Decimal(12000), credit=None,
                          memo=memo, bank_references={})
    monkeypatch.setattr(staging, "resolve_client_virtual_account_suffix", lambda _cursor, suffix: {
        "result": "resolved" if resolved and suffix == "115001" else "pending",
        "case_no": "115000001" if resolved else None,
    })
    cursor = FakeCursor(staff_cases={7: ("115000001",)})
    result = staging.stage_finance_rows(cursor, _normalized([row]), {
        "known_case_suffixes": frozenset({"115001"}),
        "all_staff_names": ("合成台新月嫂",),
        "staff_name_identities": {"合成台新月嫂": (7,)},
    }, business_only=True)

    assert len(result["staged_rows"]) == int(resolved)
    if resolved:
        item = result["staged_rows"][0]
        if memo.startswith("合成台新月嫂"):
            assert item["classification_type"] == "staff_legacy_subsidy"
            assert item["matched_identity_ids"] == [7]
        else:
            assert item["classification_type"] == "non_business_review"
            assert item["matched_identity_ids"] == []
            updates = [params for sql, params in cursor.executed if sql.startswith('UPDATE finance_import_rows')]
            assert updates[0][3] == 'taishin_memo_case_requires_manual_scheme'
    else:
        assert not any("INSERT INTO finance_import_rows" in statement for statement, _ in cursor.executed)


def test_taishin_normalization_preserves_original_note_spacing_and_fullwidth(tmp_path):
    import pandas as pd
    from scripts.imports.finance_formats.taishin import TAISHIN_HEADERS
    from scripts.imports.finance_statement_normalizer import normalize_workbook
    memo = '  ＨＣ１１５０３２服務人員薪資\n'
    target = tmp_path / 'synthetic.xlsx'
    pd.DataFrame([list(TAISHIN_HEADERS),[1,'2026/11/09','10:00:00','2026/11/09','轉帳',1000,None,0,memo]]).to_excel(target,header=False,index=False)
    assert normalize_workbook(target)['normalized_rows'][0]['memo'] == memo


def test_taishin_staff_name_cannot_override_an_unrelated_memo_case(monkeypatch):
    row = _normalized_row(direction="outgoing", debit=Decimal(12000), credit=None,
                          memo="Synthetic Staff HC115002", counterparty_account=None, bank_references={})
    monkeypatch.setattr(staging, 'resolve_client_virtual_account_suffix',
                        lambda *_: {"result": "resolved", "case_no": "115000002"})
    result = staging.stage_finance_rows(FakeCursor(), _normalized([row]), {
        'all_staff_names': ('Synthetic Staff',),
        'staff_payout_candidates': ({'staff_id': 12, 'name': 'Synthetic Staff', 'case_no': '115000001',
            'due_date': '2026-10-20', 'amount_due_ntd': 12000},),
    }, business_only=True)
    assert result["staged_rows"] == []


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


@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
@pytest.mark.parametrize("has_name", [True, False])
def test_unknown_memo_suffix_requires_a_known_name_to_keep_source(monkeypatch, bank, has_name):
    name = "合成客戶"
    purpose_text = "雇主退款" if bank == "sinopac" else "雇主補助款"
    row = _normalized_row(format_id=bank, direction="outgoing", debit=Decimal("5985"), credit=None,
                          memo=f"HC115999{name if has_name else ''}{purpose_text}", bank_references={})
    maps = {"known_case_suffixes": frozenset(), "client_name_identities": {name: (7, 8)}}
    monkeypatch.setattr(staging, "resolve_client_virtual_account_suffix",
                        lambda *_: {"result": "pending", "case_no": None, "reason": "case_not_found"})
    cursor = FakeCursor(client_cases={7: ("115000001",), 8: ("115000002",)})
    result = staging.stage_finance_rows(cursor, {**_normalized([row]), "format_id": bank}, maps, business_only=True)
    assert len(result["staged_rows"]) == int(has_name)
    if has_name:
        assert result["staged_rows"][0]["classification_type"] == "non_business_review"
        candidates = staging.bank_case_candidates(cursor, row, maps)
        assert [item["case_no"] for item in candidates] == ["115000001", "115000002"]
        assert {item["purpose"] for item in candidates} == {
            "client_refund" if bank == "sinopac" else "client_subsidy_return"
        }


@pytest.mark.parametrize("memo", ["HC115001退訂金", "HC115001雇主退款合成客戶"])
def test_taishin_does_not_admit_ordinary_refunds_even_with_known_case_or_name(memo):
    row = _normalized_row(format_id="taishin", direction="outgoing", debit=Decimal(5985), credit=None, memo=memo)
    maps = {"known_case_suffixes": frozenset({"115001"}), "client_name_identities": {"合成客戶": (7,)}}
    cursor = FakeCursor(client_cases={7: ("115000001",)})
    result = staging.stage_finance_rows(cursor, {**_normalized([row]), "format_id": "taishin"}, maps, business_only=True)
    assert result["staged_rows"] == []
    assert staging.bank_case_candidates(cursor, row, maps) == ()


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
    cursor = FakeCursor(existing_rows={fingerprint: {"id": 77, "reconciliation_status": "excluded"}})
    monkeypatch.setattr(staging, "classify_row_with_identity_maps",
                        lambda *_args: pytest.fail("an existing row must bypass admission"))

    result = staging.stage_finance_rows(
        cursor, {**_normalized([row]), "format_id": bank}, {}, business_only=True,
    )

    assert result["staged_rows"] == [{
        "row_id": 77, "dedup_fingerprint": fingerprint, "result": "skipped_existing",
    }]
    assert len(cursor.executed) == 2


@pytest.mark.parametrize("kind", ["staff_salary", "client_refund"])
@pytest.mark.parametrize(
    "proof,staff_admitted,refund_admitted",
    [("account", False, False), ("case", True, True), ("both", True, True), ("none", False, False),
     ("conflict", True, True), ("other_person", False, False), ("ambiguous_account", False, False),
     ("cross_type", False, False)],
)
def test_sinopac_shared_names_use_only_consistent_original_evidence_before_admission(
    monkeypatch, kind, proof, staff_admitted, refund_admitted,
):
    name, account = "合成同名對象", "0000007001"
    is_staff = kind == "staff_salary"
    admitted = staff_admitted if is_staff else refund_admitted
    person_key = "staff_id" if is_staff else "client_id"
    candidates = tuple(
        {person_key: person, "name": name, "case_no": f"11500000{person - 6}",
         "due_date": "2026-10-15", "amount_due_ntd": 12000, "obligation_type": "refund"}
        for person in (7, 8)
    )
    has_case = proof in {"case", "both", "conflict"}
    has_account = proof not in {"case", "none"}
    owners = [8] if proof == "conflict" else [9] if proof == "other_person" else [7, 8] if proof == "ambiguous_account" else [7]
    accounts = {account: owners} if has_account else {}
    other_accounts = {account: [9]} if proof == "cross_type" else {}
    maps = {
        "staff_accounts": accounts if is_staff else other_accounts,
        "client_refund_accounts": other_accounts if is_staff else accounts,
        "client_subsidy_return_accounts": {},
        "all_staff_names" if is_staff else "all_client_names": (name, name),
        "staff_payout_candidates" if is_staff else "taishin_client_refund_candidates": candidates,
        "staff_case_suffixes" if is_staff else "client_refund_case_suffixes": {"115001": [7]} if has_case else {},
    }
    row = _normalized_row(
        format_id="sinopac", direction="outgoing", debit=Decimal("11970"), credit=None,
        memo=f"{name} HC115001" if has_case else name,
        bank_references={"交易參考編號": account} if has_account else {},
    )
    unrelated = _normalized_row(
        format_id="sinopac", source_row=3, direction="outgoing", debit=Decimal("500"), credit=None,
        memo="無關交易", bank_references={},
    )
    resolved_suffixes = []

    def resolve_case(_cursor, suffix):
        resolved_suffixes.append(suffix)
        assert suffix == "115001"
        return {"result": "resolved", "case_no": "115000001"}

    monkeypatch.setattr(staging, "resolve_client_virtual_account_suffix", resolve_case)
    cursor = FakeCursor(client_cases={7: ("115000001",), 8: ("115000002",)})
    result = staging.stage_finance_rows(
        cursor, {**_normalized([row, unrelated]), "format_id": "sinopac"}, maps, business_only=True,
    )

    assert len(result["staged_rows"]) == int(admitted)
    inserts = [params for sql, params in cursor.executed if sql.startswith("INSERT INTO finance_import_rows")]
    occurrences = [params for sql, params in cursor.executed if sql.startswith("INSERT INTO finance_import_occurrences")]
    assert len(inserts) == len(occurrences) == int(admitted)
    assert resolved_suffixes == (["115001"] if admitted and has_case else [])
    if admitted:
        saved = result["staged_rows"][0]
        assert saved["classification_type"] == kind
        assert saved["matched_identity_ids"] == [7]
        assert saved["reconciliation_status"] == "pending"
        assert occurrences[0][2:5] == (row["source_file"], row["sheet_name"], row["source_row"])
        assert json.loads(inserts[0][22]) == row["bank_references"]
        assert json.loads(inserts[0][24]) == row["raw_payload"]


@pytest.mark.parametrize("kind", ["staff_salary", "client_refund"])
@pytest.mark.parametrize("unrelated_field", ["存摺備註", "summary"])
def test_sinopac_unrelated_names_cannot_override_original_recipient(monkeypatch, kind, unrelated_field):
    staff = kind == "staff_salary"
    key = "staff_id" if staff else "client_id"
    candidates = tuple({key: person, "name": name, "case_no": f"11500000{person - 6}",
                        "due_date": "2026-10-15", "amount_due_ntd": 12000, "obligation_type": "refund"}
                       for person, name in ((7, "合成甲"), (8, "合成乙乙")))
    maps = {"client_subsidy_return_accounts": {},
            "staff_accounts" if staff else "client_refund_accounts": {"0000007001": [7]},
            "staff_case_suffixes" if staff else "client_refund_case_suffixes": {"115001": [7]},
            "all_staff_names" if staff else "all_client_names": ("合成甲", "合成乙乙"),
            "staff_name_identities" if staff else "client_name_identities": {"合成甲": (7,), "合成乙乙": (8,)},
            "staff_payout_candidates" if staff else "taishin_client_refund_candidates": candidates}
    references = {"交易參考編號": "0000007001合成甲"}
    if unrelated_field == "存摺備註":
        references[unrelated_field] = "合成乙乙其他案件"
    row = _normalized_row(format_id="sinopac", direction="outgoing", debit=Decimal(12000), credit=None,
                          transaction_date="2026-10-20", memo="HC115001", bank_references=references,
                          summary="合成乙乙" if unrelated_field == "summary" else "轉帳")
    monkeypatch.setattr(staging, "resolve_client_virtual_account_suffix",
                        lambda *_: {"result": "resolved", "case_no": "115000001"})
    cursor = FakeCursor(client_cases={7: ("115000001",), 8: ("115000002",)})
    result = staging.stage_finance_rows(cursor, {**_normalized([row]), "format_id": "sinopac"}, maps, business_only=True)
    assert len(result["staged_rows"]) == 1
    assert result["staged_rows"][0]["classification_type"] == kind
    assert result["staged_rows"][0]["matched_identity_ids"] == [7]
    inserted = [params for sql, params in cursor.executed if sql.startswith("INSERT INTO finance_import_rows")]
    assert json.loads(inserted[0][22]) == references


@pytest.mark.parametrize("kind", ["staff_salary", "client_refund"])
@pytest.mark.parametrize("proof", ["account", "case", "both", "none", "conflict"])
def test_sinopac_paid_namesake_remains_identifiable_before_open_payment_matching(monkeypatch, kind, proof):
    staff = kind == "staff_salary"
    name = "合成同名對象"
    key = "staff_id" if staff else "client_id"
    has_case = proof in {"case", "both", "conflict"}
    has_account = proof in {"account", "both", "conflict"}
    maps = {"client_subsidy_return_accounts": {},
            "staff_accounts" if staff else "client_refund_accounts": {"0000007001": [7]} if has_account else {},
            "staff_case_suffixes" if staff else "client_refund_case_suffixes": {"115001": [8 if proof == "conflict" else 7]} if has_case else {},
            "all_staff_names" if staff else "all_client_names": (name, name),
            "staff_name_identities" if staff else "client_name_identities": {name: (7, 8)},
            "staff_payout_candidates" if staff else "taishin_client_refund_candidates": (
                {key: 8, "name": name, "case_no": "115000002", "due_date": "2026-10-15",
                 "amount_due_ntd": 12000, "obligation_type": "refund"},)}
    row = _normalized_row(format_id="sinopac", direction="outgoing", debit=Decimal(12000), credit=None,
                          transaction_date="2026-10-20", memo=f"HC115001{name}" if has_case else name,
                          bank_references={"交易參考編號": f"0000007001{name}"} if has_account else {})
    monkeypatch.setattr(staging, "resolve_client_virtual_account_suffix",
                        lambda *_: {"result": "resolved", "case_no": "115000001"})
    case_owner = 8 if proof == "conflict" else 7
    cases_by_owner = {case_owner: ("115000001",)}
    cursor = FakeCursor(staff_cases=cases_by_owner, client_cases=cases_by_owner)
    result = staging.stage_finance_rows(cursor, {**_normalized([row]), "format_id": "sinopac"}, maps, business_only=True)
    admitted = proof in {"case", "both", "conflict"}
    manual = proof in {"account", "none"} and not admitted
    assert len(result["staged_rows"]) == int(admitted or manual)
    if manual:
        assert result["staged_rows"][0]["classification_type"] == "non_business_review"
    if admitted:
        assert result["staged_rows"][0]["classification_type"] == kind
        assert result["staged_rows"][0]["matched_identity_ids"] == [case_owner]


@pytest.mark.parametrize("case_count", [0, 1, 2])
def test_taishin_memo_staff_with_explicit_subsidy_purpose_keeps_source_for_matching(case_count):
    class CaseCursor(FakeCursor):
        def fetchall(self):
            return tuple({"case_no": f"11500000{index + 1}", "person_id": 7} for index in range(case_count))

    name = "合成台新月嫂"
    row = _normalized_row(direction="outgoing", debit=Decimal("11970"), credit=None,
                          memo=name + "補助款", bank_references={})
    cursor = CaseCursor()
    result = staging.stage_finance_rows(cursor, _normalized([row]), {
        "all_staff_names": (name,), "staff_name_identities": {name: (7,)},
    }, business_only=True)

    assert len(result["staged_rows"]) == 1
    assert result["staged_rows"][0]["classification_type"] == ("non_business_review" if case_count > 1 else "staff_legacy_subsidy")
    assert result["staged_rows"][0]["matched_identity_ids"] == ([] if case_count > 1 else [7])
    assert result["staged_rows"][0]["reconciliation_status"] == "pending"
