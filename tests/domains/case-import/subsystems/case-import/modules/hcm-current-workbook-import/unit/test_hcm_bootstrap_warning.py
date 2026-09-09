"""Focused contract for presenting HCM bootstrap failures as system setup work."""

from domains.case_import.hcm_import_review import (
    build_hcm_import_review_root,
    build_hcm_warning_occurrences,
)


def test_hcm_bootstrap_failure_projects_system_setup_guidance() -> None:
    root = build_hcm_import_review_root(
        source_content_digest="a" * 64,
        source_sheet="HCM",
        source_row=6,
        case_identity="HCM-0006",
        issue_codes=("hcm_case_import:case_import_bootstrap_blocked",),
        evidence_snapshot={"has_case_identity": True},
    )

    warning = build_hcm_warning_occurrences(root)[0]

    assert (warning.logical_code, warning.field_path) == (
        "HCM-SYSTEM-001",
        "$case_setup",
    )
