"""
File: historical_order_warning_review.py
Description: 將歷史訂單已登錄 issue 展開為警示，未知狀態 fail-closed。
"""

from __future__ import annotations

from domains.anomalies.import_warning_tracking import (
    ImportWarningOccurrence,
    UnknownImportWarningIssueError,
    build_import_warning_occurrence,
)


def build_historical_order_warning_occurrences(
    *,
    source_event_identity: str,
    masked_case_identity: str,
    issue_codes: tuple[str, ...],
) -> tuple[ImportWarningOccurrence, ...]:
    """Expand only registry-approved historical-order review issues."""
    warnings: list[ImportWarningOccurrence] = []
    for issue_code in issue_codes:
        mapped = _warning_type(issue_code)
        if mapped is None:
            raise UnknownImportWarningIssueError(
                owning_lane="historical_order", issue_code=issue_code
            )
        logical_code, field_path = mapped
        warnings.append(
            build_import_warning_occurrence(
                owning_lane="historical_order",
                source_event_identity=source_event_identity,
                logical_code=logical_code,
                field_path=field_path,
                masked_subject=masked_case_identity,
                issue_codes=(issue_code,),
            )
        )
    return tuple(warnings)


def _warning_type(issue_code: str) -> tuple[str, str] | None:
    if issue_code in {"historical_staff_not_found", "staff_missing"}:
        return "ORDER-HIST-STAFF-001", "$staff"
    if issue_code in {"historical_staff_ambiguous", "staff_ambiguous"}:
        return "ORDER-HIST-STAFF-002", "$staff"
    if issue_code in {
        "historical_assignment_conflict",
        "historical_assignment_evidence_insufficient",
    } or issue_code.startswith("historical_caregiver_"):
        return "ORDER-HIST-ASSIGNMENT-001", "$assignment"
    if issue_code == "historical_status_invalid" or issue_code == "historical_current_status_conflict":
        return "ORDER-HIST-FIELD-001", "$status"
    if issue_code == "historical_order_date_range_invalid":
        return "ORDER-HIST-FIELD-001", "$service_period"
    if issue_code == "historical_order_start_date_invalid":
        return "ORDER-HIST-FIELD-001", "actual_start_date"
    if issue_code == "historical_order_end_date_invalid":
        return "ORDER-HIST-FIELD-001", "actual_end_date"
    if issue_code.startswith("historical_nonempty_conflict:"):
        return "ORDER-HIST-FIELD-001", issue_code.removeprefix("historical_nonempty_conflict:")
    return None


__all__ = ["build_historical_order_warning_occurrences"]
