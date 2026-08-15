"""
File: test_finance_source_warning.py
Description: 驗證 Finance 無法正規化來源列的分流、去敏 root 與欄位級 warning。
"""

from __future__ import annotations

from decimal import Decimal

from domains.finance_import.source_warning_review import build_finance_source_review
from domains.finance_import.warning_review import (
    build_finance_source_warning_occurrences,
)
from scripts.imports.finance_statement_normalizer import partition_normalized_rows


def test_mixed_rows_keep_valid_row_and_isolate_invalid_amount() -> None:
    valid = _row(2)
    invalid = _row(
        3,
        debit=None,
        direction="unknown",
        warnings=["debit_invalid", "direction_missing"],
    )

    normalized, reviews = partition_normalized_rows([valid, invalid])

    assert normalized == [valid]
    assert reviews == [
        {
            "format_id": "taishin",
            "sheet_name": "交易明細",
            "source_row": 3,
            "issue_codes": (
                "finance_source_field_invalid:transaction_amount",
            ),
        }
    ]


def test_noninteger_ntd_amount_is_source_review_not_canonical_row() -> None:
    invalid = _row(4, debit=Decimal("10.5"))

    normalized, reviews = partition_normalized_rows([invalid])

    assert normalized == []
    assert reviews[0]["issue_codes"] == (
        "finance_source_field_invalid:transaction_amount",
    )


def test_review_identity_is_deterministic_and_contains_no_raw_bank_data() -> None:
    first = build_finance_source_review(
        source_content_digest="a" * 64,
        format_id="sinopac",
        sheet_name="交易明細報表",
        source_row=8,
        issue_codes=(
            "finance_source_field_invalid:source_bank_account",
        ),
    )
    replay = build_finance_source_review(
        source_content_digest="a" * 64,
        format_id="sinopac",
        sheet_name="交易明細報表",
        source_row=8,
        issue_codes=(
            "finance_source_field_invalid:source_bank_account",
        ),
    )

    assert replay == first
    assert first.masked_source_identity == "finance-sinopac-row-8"
    assert "交易明細報表" not in first.review_identity


def test_source_review_expands_each_field_without_raw_values() -> None:
    review = build_finance_source_review(
        source_content_digest="b" * 64,
        format_id="legacy",
        sheet_name="銀行資料",
        source_row=9,
        issue_codes=(
            "finance_source_field_missing:transaction_date",
            "finance_source_field_invalid:transaction_amount",
        ),
    )

    warnings = build_finance_source_warning_occurrences(review)

    assert {(item.logical_code, item.field_path) for item in warnings} == {
        ("FINANCE-SOURCE-001", "transaction_date"),
        ("FINANCE-SOURCE-001", "transaction_amount"),
    }


def _row(source_row: int, **changes):
    row = {
        "format_id": "taishin",
        "source_file": "C:/sensitive/source.xlsx",
        "source_bank_account": None,
        "sheet_name": "交易明細",
        "source_row": source_row,
        "source_reference": None,
        "transaction_date": "2026-08-15",
        "transaction_time": "09:00:00",
        "posting_date": "2026-08-15",
        "value_date": None,
        "debit": Decimal("100"),
        "credit": None,
        "direction": "outgoing",
        "balance": Decimal("900"),
        "currency": None,
        "summary": "不得進 review",
        "memo": "完整帳號 1234567890123456",
        "counterparty_name": None,
        "counterparty_account": "1234567890123456",
        "cancellation_code": None,
        "bank_references": {},
        "warnings": [],
        "raw_payload": {"備註": "完整帳號 1234567890123456"},
    }
    row.update(changes)
    return row
