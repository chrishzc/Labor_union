from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.imports.finance_formats.legacy import normalize_legacy_rows


SAMPLE = Path("document") / "資料庫、資料處理" / "歷史對帳單.xlsx"


def test_normalizes_real_historical_statement_and_excludes_footer():
    rows = normalize_legacy_rows(SAMPLE, "永豐3131(虛擬)", 3)

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
            "轉帳", "TWD", None, "1,200", "5,000", "000099", "000077", None,
            None, "備註",
        ],
        ["總計", None, None, None, None, "TWD", None, "1,200"],
    ]
    pd.DataFrame(rows).to_excel(path, sheet_name="任意分頁", index=False, header=False)

    result = normalize_legacy_rows(path, "任意分頁", 4)

    assert len(result) == 1
    assert result[0]["source_bank_account"] == "000012345678"
    assert result[0]["cancellation_code"] == "000099"
    assert result[0]["bank_references"]["transaction_reference"] == "000077"
    assert result[0]["direction"] == "incoming"


def test_missing_required_header_fails(tmp_path):
    path = tmp_path / "missing.xlsx"
    pd.DataFrame([["帳號", "交易日"]]).to_excel(path, index=False, header=False)

    try:
        normalize_legacy_rows(path, "Sheet1", 1)
    except ValueError as error:
        assert "缺少必要欄位" in str(error)
    else:
        raise AssertionError("missing headers must fail")
