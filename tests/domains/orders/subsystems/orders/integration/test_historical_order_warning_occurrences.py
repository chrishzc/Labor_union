"""
File: test_historical_order_warning_occurrences.py
Description: 驗證歷史訂單 review 映射已登錄 issue，未知狀態 fail-closed。
"""

import pytest

from domains.anomalies.import_warning_tracking import UnknownImportWarningIssueError
from domains.orders.historical_order_warning_review import (
    build_historical_order_warning_occurrences,
)


def test_historical_review_expands_registered_field_and_staff_issues():
    warnings = build_historical_order_warning_occurrences(
        source_event_identity="historical-order:source:7",
        masked_case_identity="order-***-0007",
        issue_codes=("historical_status_invalid", "staff_missing"),
    )

    assert {(item.logical_code, item.field_path) for item in warnings} == {
        ("ORDER-HIST-FIELD-001", "$status"),
        ("ORDER-HIST-STAFF-001", "$staff"),
    }


def test_historical_unknown_issue_fails_closed_without_partial_warnings():
    with pytest.raises(UnknownImportWarningIssueError):
        build_historical_order_warning_occurrences(
            source_event_identity="historical-order:source:9",
            masked_case_identity="order-***-0009",
            issue_codes=("staff_missing", "unregistered_legacy_issue"),
        )


def test_historical_review_maps_assignment_and_nonempty_conflict_to_distinct_fields():
    warnings = build_historical_order_warning_occurrences(
        source_event_identity="historical-order:source:8",
        masked_case_identity="order-***-0008",
        issue_codes=(
            "historical_assignment_conflict",
            "historical_nonempty_conflict:actual_end_date",
        ),
    )

    assert {(item.logical_code, item.field_path) for item in warnings} == {
        ("ORDER-HIST-ASSIGNMENT-001", "$assignment"),
        ("ORDER-HIST-FIELD-001", "actual_end_date"),
    }


def test_historical_review_maps_real_insufficient_assignment_evidence() -> None:
    warning = build_historical_order_warning_occurrences(
        source_event_identity="historical-order:source:assignment",
        masked_case_identity="order-***-0011",
        issue_codes=("historical_assignment_evidence_insufficient",),
    )[0]

    assert (warning.logical_code, warning.field_path) == (
        "ORDER-HIST-ASSIGNMENT-001",
        "$assignment",
    )


def test_historical_review_maps_real_start_and_end_parse_failures() -> None:
    warnings = build_historical_order_warning_occurrences(
        source_event_identity="historical-order:source:10",
        masked_case_identity="order-***-0010",
        issue_codes=(
            "historical_order_start_date_invalid",
            "historical_order_end_date_invalid",
        ),
    )

    assert {(item.logical_code, item.field_path) for item in warnings} == {
        ("ORDER-HIST-FIELD-001", "actual_start_date"),
        ("ORDER-HIST-FIELD-001", "actual_end_date"),
    }
