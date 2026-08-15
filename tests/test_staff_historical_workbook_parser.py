"""
File: test_staff_historical_workbook_parser.py
Description: 驗證 Staff 歷史 workbook 選表、identity 正規化與 IP 空值契約。
"""

from __future__ import annotations

import pandas as pd
import pytest

from subsystems.case_import.staff_historical_workbook import load_staff_historical_workbook


def test_parser_selects_arbitrary_sheet_and_normalizes_blank_ip(tmp_path):
    path = tmp_path / "staff.xlsx"
    row = _row()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([row]).to_excel(writer, sheet_name="任意名稱", index=False)

    workbook = load_staff_historical_workbook(path)

    assert workbook.rows[0].record["identity_card"] == "A123456789"
    assert workbook.rows[0].record["ip_address"] is None
    assert "IP位址" not in workbook.rows[0].errors


def test_parser_rejects_multiple_matching_sheets(tmp_path):
    path = tmp_path / "staff.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([_row()]).to_excel(writer, sheet_name="甲", index=False)
        pd.DataFrame([_row()]).to_excel(writer, sheet_name="乙", index=False)

    with pytest.raises(ValueError, match="staff_historical_sheet_contract_not_unique"):
        load_staff_historical_workbook(path)


def _row() -> dict[str, object]:
    return {"查詢序號": "1", "報名時間": "2026-08-13", "IP位址": "", "姓名": "測試月嫂", "銀行帳號": "", "銀行代3碼+分行代號4碼": "", "身分證字號": "a123456789", "行動電話": "0912345678", "EMAIL": "staff@example.test", "出生年": 1990, "月": 1, "日": 2}
