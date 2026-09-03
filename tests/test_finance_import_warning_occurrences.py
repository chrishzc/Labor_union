"""
File: test_finance_import_warning_occurrences.py
Description: 驗證 Finance review warning 使用 row identity 而非銀行來源內容。
"""

from domains.finance_import.warning_review import build_finance_row_warning_occurrence


def test_finance_row_warning_uses_stable_row_identity_and_no_bank_values():
    warning = build_finance_row_warning_occurrence(
        finance_import_row_id=17,
    )

    assert (warning.owning_lane, warning.logical_code, warning.field_path) == (
        "finance_import",
        "FINANCE-ROW-001",
        "$classification",
    )
    assert warning.subject == "finance-row-17"
    assert "bank" not in warning.occurrence_identity
