"""Detect supported bank statement layouts from workbook content."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


MAX_HEADER_ROWS = 40


def _header(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return "".join(text.split())


FORMAT_SIGNATURES = {
    "taishin": {
        "required": {
            "序號",
            "交易日期",
            "交易時間",
            "帳務日期",
            "摘要",
            "支出金額",
            "存入金額",
            "帳戶餘額",
            "備註",
        },
        "forbidden": set(),
        "sheet_hints": {"交易明細查詢"},
    },
    "sinopac": {
        "required": {
            "帳號",
            "交易日",
            "計息日",
            "入帳日",
            "摘要",
            "幣別",
            "支出",
            "存入",
            "餘額",
            "票據號碼",
            "銷帳編號",
            "交易參考編號",
            "備註",
            "更正註記",
            "存摺備註",
        },
        "forbidden": set(),
        "sheet_hints": {"交易明細報表"},
    },
    "legacy": {
        "required": {
            "帳號",
            "交易日",
            "計息日",
            "入帳日",
            "摘要",
            "幣別",
            "支出",
            "存入",
            "餘額",
            "銷帳編號",
            "交易參考編號",
            "更正註記",
            "存摺備註",
        },
        "forbidden": {"票據號碼"},
        "sheet_hints": set(),
    },
}


class StatementFormatDetectionError(ValueError):
    """Raised when workbook content does not identify one unique layout."""

    def __init__(self, message: str, diagnostics: list[dict[str, Any]]):
        super().__init__(message)
        self.diagnostics = diagnostics


def detect_statement_format(excel_path: str | Path) -> dict[str, Any]:
    """Return the unique statement format and its 1-based header position.

    The workbook is opened read-only by pandas and every worksheet's first
    forty rows are checked.  File names are deliberately ignored.
    """

    assert set(FORMAT_SIGNATURES) == {"legacy", "taishin", "sinopac"}
    path = Path(excel_path)
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    with pd.ExcelFile(path) as workbook:
        for sheet_name in workbook.sheet_names:
            frame = workbook.parse(
                sheet_name=sheet_name,
                header=None,
                nrows=MAX_HEADER_ROWS,
                dtype=object,
            )
            for row_index, row in frame.iterrows():
                headers = {_header(value) for value in row.tolist()} - {""}
                if not headers:
                    continue
                for format_id, signature in FORMAT_SIGNATURES.items():
                    required = signature["required"]
                    forbidden = signature["forbidden"]
                    missing = sorted(required - headers)
                    blocked = sorted(forbidden & headers)
                    if not missing and not blocked:
                        candidate = {
                            "format_id": format_id,
                            "sheet_name": sheet_name,
                            "header_row": int(row_index) + 1,
                            "sheet_hint_matched": _header(sheet_name)
                            in {_header(item) for item in signature["sheet_hints"]},
                        }
                        candidates.append(candidate)
                    elif len(missing) <= 2:
                        diagnostics.append(
                            {
                                "format_id": format_id,
                                "sheet_name": sheet_name,
                                "header_row": int(row_index) + 1,
                                "missing_headers": missing,
                                "forbidden_headers": blocked,
                            }
                        )

    if len(candidates) != 1:
        summary = "找不到支援的唯一銀行對帳單格式" if not candidates else "同時找到多個銀行對帳單格式"
        raise StatementFormatDetectionError(summary, candidates or diagnostics)

    result = candidates[0]
    result["diagnostics"] = diagnostics
    return result
