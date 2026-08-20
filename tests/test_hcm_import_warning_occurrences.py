"""
File: test_hcm_import_warning_occurrences.py
Description: 驗證 HCM 匯入門檻、通用欄位警示與未知 issue fail-closed。
"""

from __future__ import annotations

import pytest

from domains.anomalies.import_warning_tracking import UnknownImportWarningIssueError
from domains.case_import.hcm_import_review import (
    build_hcm_import_review_root,
    build_hcm_warning_occurrences,
)


def test_hcm_review_expands_missing_and_invalid_fields_independently() -> None:
    root = build_hcm_import_review_root(
        source_content_digest="a" * 64,
        source_sheet="HCM",
        source_row=7,
        case_identity="HCM-0007",
        issue_codes=(
            "hcm_field_invalid:服務時間",
            "hcm_field_missing:行動電話",
        ),
        evidence_snapshot={"invalid_field_count": 2},
    )

    warnings = build_hcm_warning_occurrences(root)

    assert {(item.logical_code, item.field_path) for item in warnings} == {
        ("HCM-FIELD-001", "行動電話"),
        ("HCM-FIELD-002", "服務時間"),
    }
    assert len({item.occurrence_identity for item in warnings}) == 2


def test_hcm_row_below_import_threshold_does_not_create_anomaly_warning() -> None:
    root = build_hcm_import_review_root(
        source_content_digest="b" * 64,
        source_sheet="HCM",
        source_row=3,
        case_identity=None,
        issue_codes=("hcm_case_import:case_import_case_no_required",),
        evidence_snapshot={"has_case_identity": False},
    )

    assert build_hcm_warning_occurrences(root) == ()


def test_existing_hcm_case_with_different_source_creates_case_conflict_warning() -> None:
    root = build_hcm_import_review_root(
        source_content_digest="f" * 64,
        source_sheet="HCM",
        source_row=4,
        case_identity="HCM-0004",
        issue_codes=("hcm_case_import:case_import_existing_source_conflict",),
        evidence_snapshot={"has_case_identity": True},
    )

    warning = build_hcm_warning_occurrences(root)[0]

    assert (warning.logical_code, warning.field_path) == (
        "HCM-CASE-002",
        "$source_row",
    )


def test_hcm_unique_existing_client_candidate_has_a_distinct_link_warning() -> None:
    root = build_hcm_import_review_root(
        source_content_digest="c" * 64,
        source_sheet="HCM",
        source_row=5,
        case_identity="HCM-0005",
        issue_codes=("hcm_identity:hcm_unique_candidate",),
        evidence_snapshot={"has_case_identity": True},
    )

    warning = build_hcm_warning_occurrences(root)[0]

    assert (warning.logical_code, warning.field_path) == ("HCM-LINK-001", "$client_link")


def test_hcm_unknown_issue_fails_closed_without_exposing_raw_issue() -> None:
    raw_issue = "future_hcm_state:完整姓名不得寫入錯誤"
    root = build_hcm_import_review_root(
        source_content_digest="d" * 64,
        source_sheet="HCM",
        source_row=9,
        case_identity="HCM-0009",
        issue_codes=(raw_issue,),
        evidence_snapshot={"has_case_identity": True},
    )

    with pytest.raises(UnknownImportWarningIssueError) as raised:
        build_hcm_warning_occurrences(root)

    assert str(raised.value).startswith("import_warning_projection_unknown_issue:hcm:")
    assert raw_issue not in str(raised.value)


def test_future_hcm_identity_state_does_not_hide_inside_link_ambiguity() -> None:
    root = build_hcm_import_review_root(
        source_content_digest="e" * 64,
        source_sheet="HCM",
        source_row=12,
        case_identity="HCM-0012",
        issue_codes=("hcm_identity:future_identity_state",),
        evidence_snapshot={"has_case_identity": True},
    )

    with pytest.raises(UnknownImportWarningIssueError):
        build_hcm_warning_occurrences(root)
