"""Focused contract for presenting HCM bootstrap failures as system setup work."""

from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from domains.case_import.hcm_import_review import (
    build_hcm_import_review_root,
    build_hcm_warning_occurrences,
)
from scripts.imports.import_client_hcm import _case_import_reason_codes, _row_outcome
from subsystems.case_import.case_import_workflow import CaseImportWorkflowError


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


def test_hcm_bootstrap_failure_preserves_safe_actionable_reason() -> None:
    error = CaseImportWorkflowError(TypedError(
        ErrorCategory.DOMAIN_BLOCKED,
        "case_import_bootstrap_blocked",
        "deposit due date cannot follow service start",
        CorrelationId("hcm-bootstrap-reason"),
    ))

    reason_codes = _case_import_reason_codes(error)
    outcome = _row_outcome(
        "review_required",
        6,
        "HCM-0006",
        {"case_import": "case_import_bootstrap_blocked"},
        "hcm-review:test",
        True,
        reason_codes=reason_codes,
    )

    assert reason_codes == (
        "hcm_bootstrap_deposit_due_after_service_start",
    )
    assert outcome["reason_codes"] == [
        "hcm_bootstrap_deposit_due_after_service_start",
    ]
