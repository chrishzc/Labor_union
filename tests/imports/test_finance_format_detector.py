from pathlib import Path
from shutil import copyfile

import pandas as pd
import pytest

from scripts.imports.finance_formats.detector import (
    StatementFormatDetectionError,
    detect_statement_format,
)


SAMPLES = Path("document") / "資料庫、資料處理"


@pytest.mark.parametrize(
    ("filename", "format_id", "sheet_name", "header_row"),
    [
        ("歷史對帳單.xlsx", "legacy", "永豐3131(虛擬)", 3),
        ("台新範例對帳單.xlsx", "taishin", "交易明細查詢", 16),
        ("永豐範例對帳單.xlsx", "sinopac", "交易明細報表", 3),
    ],
)
def test_detects_real_samples(filename, format_id, sheet_name, header_row):
    result = detect_statement_format(SAMPLES / filename)

    assert result["format_id"] == format_id
    assert result["sheet_name"] == sheet_name
    assert result["header_row"] == header_row


def test_detection_does_not_depend_on_filename(tmp_path):
    renamed = tmp_path / "任意名稱.xlsx"
    copyfile(SAMPLES / "台新範例對帳單.xlsx", renamed)

    assert detect_statement_format(renamed)["format_id"] == "taishin"


def test_rejects_workbook_without_supported_header(tmp_path):
    path = tmp_path / "unknown.xlsx"
    pd.DataFrame([["日期", "金額"], ["2026-01-01", 100]]).to_excel(
        path, index=False, header=False
    )

    with pytest.raises(StatementFormatDetectionError, match="找不到") as error:
        detect_statement_format(path)

    assert isinstance(error.value.diagnostics, list)


def test_rejects_multiple_matching_sheets(tmp_path):
    path = tmp_path / "duplicate.xlsx"
    headers = [[
        "序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額",
        "存入金額", "帳戶餘額", "備註",
    ]]
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(headers).to_excel(writer, sheet_name="one", index=False, header=False)
        pd.DataFrame(headers).to_excel(writer, sheet_name="two", index=False, header=False)

    with pytest.raises(StatementFormatDetectionError, match="多個") as error:
        detect_statement_format(path)

    assert len(error.value.diagnostics) == 2
