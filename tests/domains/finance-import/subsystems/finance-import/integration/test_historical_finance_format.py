from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    _bank_row_is_eligible,
    _cancellation_code,
)
from scripts.imports.finance_statement_normalizer import normalize_workbook

from scripts.imports.finance_formats.historical_multisheet import (
    normalize_historical_multisheet_rows,
)


SAMPLE = Path("document") / "資料庫、資料處理" / "歷史對帳單.xlsx"


@pytest.mark.parametrize(("suffix", "eligible"), [
    ("", True), ("測試甲", True), (" 測試甲", True),
    ("0", False), ("測試甲 009876543210", False),
])
@pytest.mark.parametrize("direction", ["incoming", "outgoing"])
def test_historical_direction_account_columns_feed_classification(tmp_path, suffix, eligible, direction):
    headers = [
        "帳號", "交易日", "計息日", "入帳日", "摘要", "幣別", "支出",
        "存入", "餘額", "銷帳編號", "交易參考編號", "", "更正註記", "存摺備註",
        "姓名-貼值",
    ]
    account = "99781699114033" if direction == "incoming" else "001234567890"
    reference = account + suffix
    values = [
        "000012345678", "2026/07/15", "2026/07/15", "2026/07/15", "轉帳",
        "TWD", 12000 if direction == "outgoing" else None,
        12000 if direction == "incoming" else None, 50000,
        reference if direction == "incoming" else "99781699114044",
        reference if direction == "outgoing" else "009876543210",
        "009876543210其他人", "Y", "009876543210其他人", "其他人",
    ]
    path = tmp_path / "historical.xlsx"
    pd.DataFrame([headers, values]).to_excel(path, index=False, header=False)

    result = normalize_workbook(path)
    assert result["format_id"] == "legacy"
    row = result["normalized_rows"][0]
    decision = classify_finance_transaction(row, {}, {account: [7], "009876543210": [8]})
    if not eligible:
        assert decision["classification_type"] == "non_business_review"
        if direction == "incoming":
            assert _cancellation_code(row) is None
    elif direction == "incoming":
        assert decision["classification_type"] == "client_receipt"
        assert row["cancellation_code"] == reference
        assert _cancellation_code(row) == account
        bank = {**row, "classification_type": "client_receipt",
                "reconciliation_status": "pending", "ledger_entry_id": None}
        assert _bank_row_is_eligible(bank, "114000033")
    else:
        assert decision["classification_type"] == "staff_salary"
        assert decision["matched_identity_ids"] == [7]
        assert decision["resolved_counterparty_account"] == account
        assert row["bank_references"]["transaction_reference"] == reference
    assert row["raw_payload"]["銷帳編號" if direction == "incoming" else "交易參考編號"] == reference


def test_normalizes_real_historical_statement_and_excludes_footer():
    rows = normalize_historical_multisheet_rows(SAMPLE, "永豐3131(虛擬)", 3)

    assert len(rows) == 1
    row = rows[0]
    assert row["format_id"] == "legacy"
    assert row["source_row"] == 4
    assert row["source_bank_account"] == "03201800231313"
    assert row["transaction_date"] == "2024-08-26"
    assert row["transaction_time"] == "10:53:00"
    assert row["debit"] == Decimal("9025")
    assert row["credit"] is None
    assert row["direction"] == "outgoing"
    assert "direction_ambiguous" not in row["warnings"]
    assert row["cancellation_code"] is None
    assert row["memo"] == "新竹市月子工會課程退費游嘉玲 張淑婷"
    assert (
        row["bank_references"]["comparison_field"]
        == "新竹市月子工會課程退費游嘉玲 張淑婷"
    )
    assert row["bank_references"]["存摺備註"] == "張淑婷"
    assert len(row["raw_payload"]) == 14


def test_uses_detected_sheet_and_header_row_not_filename(tmp_path):
    path = tmp_path / "任意名稱.xlsx"
    headers = [
        "帳號", "交易日 ", "計息日 ", "入帳日 ", "摘要", "幣別", "支出",
        "存入", "餘額", "銷帳編號", "交易參考編號", "", "更正註記", "存摺備註",
    ]
    rows = [
        ["說明"],
        ["更多說明"],
        ["前置列"],
        headers,
        [
            "000012345678", "2026/07/15 08:09:10", "2026/07/15", "2026/07/15",
            "轉帳", "TWD", None, "1,200", "5,000", "000099", "000077", "比對 001234567890",
            None, "備註",
        ],
        ["總計", None, None, None, None, "TWD", None, "1,200"],
    ]
    pd.DataFrame(rows).to_excel(path, sheet_name="任意分頁", index=False, header=False)

    result = normalize_historical_multisheet_rows(path, "任意分頁", 4)

    assert len(result) == 1
    assert result[0]["source_bank_account"] == "000012345678"
    assert result[0]["cancellation_code"] == "000099"
    assert result[0]["bank_references"]["transaction_reference"] == "000077"
    assert result[0]["memo"] == "比對 001234567890"
    assert result[0]["bank_references"]["comparison_field"] == "比對 001234567890"
    assert result[0]["bank_references"]["存摺備註"] == "備註"
    assert result[0]["direction"] == "incoming"


def test_rejects_missing_twelfth_comparison_column(tmp_path):
    path = tmp_path / "missing-comparison.xlsx"
    headers = [
        "帳號", "交易日", "計息日", "入帳日", "摘要", "幣別", "支出",
        "存入", "餘額", "銷帳編號", "交易參考編號", "錯誤欄位", "更正註記", "存摺備註",
    ]
    pd.DataFrame([headers]).to_excel(path, index=False, header=False)

    try:
        normalize_historical_multisheet_rows(path, "Sheet1", 1)
    except ValueError as error:
        assert "第 12 欄" in str(error)
    else:
        raise AssertionError("missing comparison column must fail")


def test_missing_required_header_fails(tmp_path):
    path = tmp_path / "missing.xlsx"
    pd.DataFrame([["帳號", "交易日"]]).to_excel(path, index=False, header=False)

    try:
        normalize_historical_multisheet_rows(path, "Sheet1", 1)
    except ValueError as error:
        assert "缺少必要欄位" in str(error)
    else:
        raise AssertionError("missing headers must fail")


def test_reads_optional_name_and_ignores_columns_after_fifteen(tmp_path):
    path = tmp_path / "extra-columns.xlsx"
    headers = [
        "帳號", "交易日", "計息日", "入帳日", "摘要", "幣別", "支出",
        "存入", "餘額", "銷帳編號", "交易參考編號", "", "更正註記", "存摺備註",
        "姓名-貼值", "存摺備註", "姓名-貼值",
    ]
    values = [
        "000012345678", "2026/07/15", "2026/07/15", "2026/07/15", "轉帳",
        "TWD", None, "1200", "5000", "000099", "000077", "001234567890",
        None, "核心備註", "王小明", "應忽略的重複備註", "應忽略的重複姓名",
    ]
    pd.DataFrame([headers, values]).to_excel(path, index=False, header=False)

    result = normalize_historical_multisheet_rows(path, "Sheet1", 1)

    assert len(result) == 1
    assert result[0]["counterparty_name"] == "王小明"
    assert result[0]["memo"] == "001234567890"
    assert result[0]["bank_references"]["存摺備註"] == "核心備註"
    assert result[0]["raw_payload"]["姓名-貼值"] == "王小明"
    assert "應忽略的重複備註" not in result[0]["raw_payload"].values()
    assert "應忽略的重複姓名" not in result[0]["raw_payload"].values()


def test_rejects_unknown_fifteenth_column(tmp_path):
    path = tmp_path / "unknown-fifteenth.xlsx"
    headers = [
        "帳號", "交易日", "計息日", "入帳日", "摘要", "幣別", "支出",
        "存入", "餘額", "銷帳編號", "交易參考編號", "", "更正註記", "存摺備註",
        "未知欄位",
    ]
    pd.DataFrame([headers]).to_excel(path, index=False, header=False)

    try:
        normalize_historical_multisheet_rows(path, "Sheet1", 1)
    except ValueError as error:
        assert "第 15 欄" in str(error)
    else:
        raise AssertionError("unknown fifteenth column must fail")
