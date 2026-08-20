"""
File: finance_statement_normalizer.py
Description: 偵測銀行格式並將合格列與去敏來源 review 分流，不做業務分類。
"""

from __future__ import annotations

from pathlib import Path
from decimal import Decimal
from typing import Any, Callable

from scripts.imports.finance_formats.detector import detect_statement_format
from scripts.imports.finance_formats.historical_multisheet import (
    normalize_historical_multisheet_rows,
)
from scripts.imports.finance_formats.sinopac import normalize_sinopac_rows
from scripts.imports.finance_formats.taishin import normalize_taishin_rows
from scripts.imports.finance_normalized_row import validate_normalized_row


Adapter = Callable[[str | Path, str, int], list[dict[str, Any]]]

FORMAT_ADAPTERS: dict[str, Adapter] = {
    "legacy": normalize_historical_multisheet_rows,
    "taishin": normalize_taishin_rows,
    "sinopac": normalize_sinopac_rows,
}


def normalize_workbook(excel_path: str | Path) -> dict[str, Any]:
    """Return detector metadata and validator-approved normalized rows."""
    assert set(FORMAT_ADAPTERS) == {"legacy", "taishin", "sinopac"}
    detected = detect_statement_format(excel_path)
    format_id = detected["format_id"]
    try:
        adapter = FORMAT_ADAPTERS[format_id]
    except KeyError as exc:
        raise ValueError(f"unsupported detected finance format: {format_id}") from exc

    sheet_name = detected["sheet_name"]
    header_row = detected["header_row"]
    rows = adapter(excel_path, sheet_name, header_row)
    normalized_rows, source_reviews = partition_normalized_rows(rows)
    return {
        "format_id": format_id,
        "sheet_name": sheet_name,
        "header_row": header_row,
        "normalized_rows": normalized_rows,
        "source_reviews": source_reviews,
        "source_row_count": len(normalized_rows) + len(source_reviews),
    }


def partition_normalized_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_rows: list[dict[str, Any]] = []
    source_reviews: list[dict[str, Any]] = []
    for row in rows:
        validate_normalized_row(row)
        issue_codes = _source_review_issue_codes(row)
        if not issue_codes:
            normalized_rows.append(row)
            continue
        source_reviews.append(
            {
                "format_id": str(row["format_id"]),
                "sheet_name": str(row["sheet_name"]),
                "source_row": int(row["source_row"]),
                "issue_codes": issue_codes,
            }
        )
    return normalized_rows, source_reviews


def _source_review_issue_codes(row: dict[str, Any]) -> tuple[str, ...]:
    warnings = set(row["warnings"])
    issues: set[str] = set()
    _date_issue(issues, warnings, row, "transaction_date", required=True)
    _date_issue(issues, warnings, row, "posting_date", required=False)
    _date_issue(issues, warnings, row, "value_date", required=False)
    if row["format_id"] in {"legacy", "sinopac"} and row["source_bank_account"] is None:
        account_state = (
            "invalid"
            if "source_bank_account_invalid" in warnings
            else "missing"
        )
        issues.add(f"finance_source_field_{account_state}:source_bank_account")
    amount = _single_positive_amount(row["debit"], row["credit"])
    if warnings & {"debit_invalid", "credit_invalid", "invalid_debit", "invalid_credit"}:
        issues.add("finance_source_field_invalid:transaction_amount")
    elif amount is None:
        prefix = "invalid" if warnings & {"direction_ambiguous"} else "missing"
        issues.add(f"finance_source_field_{prefix}:transaction_amount")
    elif amount != amount.to_integral_value():
        issues.add("finance_source_field_invalid:transaction_amount")
    return tuple(sorted(issues))


def _date_issue(issues, warnings, row, field: str, *, required: bool) -> None:
    invalid_codes = {f"{field}_invalid", f"invalid_{field}"}
    if warnings & invalid_codes:
        issues.add(f"finance_source_field_invalid:{field}")
    elif required and row[field] is None:
        issues.add(f"finance_source_field_missing:{field}")


def _single_positive_amount(debit: object, credit: object) -> Decimal | None:
    debit_positive = isinstance(debit, Decimal) and debit > 0
    credit_positive = isinstance(credit, Decimal) and credit > 0
    if debit_positive == credit_positive:
        return None
    return debit if debit_positive else credit


__all__ = ["normalize_workbook", "partition_normalized_rows"]
