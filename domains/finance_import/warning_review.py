"""
File: warning_review.py
Description: 將 Finance canonical row 與無法正規化 source review 展開為去敏警示。
"""

from __future__ import annotations

from domains.anomalies.import_warning_tracking import (
    ImportWarningOccurrence,
    build_import_warning_occurrence,
)
from domains.finance_import.source_warning_review import (
    FinanceSourceReview,
    finance_source_issue_field,
)


def build_finance_row_warning_occurrence(
    *, finance_import_row_id: int
) -> ImportWarningOccurrence:
    if isinstance(finance_import_row_id, bool) or not isinstance(finance_import_row_id, int) or finance_import_row_id <= 0:
        raise ValueError("finance import row id must be positive")
    return build_import_warning_occurrence(
        owning_lane="finance_import",
        source_event_identity=f"finance-import-row:{finance_import_row_id}",
        logical_code="FINANCE-ROW-001",
        field_path="$classification",
        masked_subject=f"finance-row-***-{finance_import_row_id}",
        issue_codes=("finance_manual_review",),
    )


def build_finance_source_warning_occurrences(
    review: FinanceSourceReview,
) -> tuple[ImportWarningOccurrence, ...]:
    return tuple(
        build_import_warning_occurrence(
            owning_lane="finance_import",
            source_event_identity=review.review_identity,
            logical_code="FINANCE-SOURCE-001",
            field_path=finance_source_issue_field(issue_code),
            masked_subject=review.masked_source_identity,
            issue_codes=(issue_code,),
        )
        for issue_code in review.issue_codes
    )


__all__ = [
    "build_finance_row_warning_occurrence",
    "build_finance_source_warning_occurrences",
]
