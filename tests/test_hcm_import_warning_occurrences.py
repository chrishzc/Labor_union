"""
File: test_hcm_import_warning_occurrences.py
Description: 驗證 HCM review 來源依欄位展開 WP88 獨立警示，不混成整列待辦。
"""

from __future__ import annotations

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


def test_hcm_missing_case_number_remains_rootless_case_warning() -> None:
    root = build_hcm_import_review_root(
        source_content_digest="b" * 64,
        source_sheet="HCM",
        source_row=3,
        case_identity=None,
        issue_codes=("hcm_case_import:case_import_case_no_required",),
        evidence_snapshot={"has_case_identity": False},
    )

    warning = build_hcm_warning_occurrences(root)[0]

    assert (warning.logical_code, warning.field_path) == (
        "HCM-CASE-001", "查詢序號(案件編號)"
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
