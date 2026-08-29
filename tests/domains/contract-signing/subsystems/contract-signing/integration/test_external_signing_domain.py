"""
File: test_external_signing_domain.py
Description: 驗證外部簽約完成回報的順序、狀態版本與最終 PDF 門禁。
"""

from __future__ import annotations

import pytest

from domains.contract_signing.external_signing import (
    ExternalSigningErrorCode,
    ExternalSigningRuleError,
    ExternalSigningSessionFacts,
    ExternalSigningState,
    StaffSigningReportTarget,
    derive_external_signing_session_id,
    final_signed_contract_blockers,
    reduce_client_completion_report,
    reduce_staff_completion_report,
)


def test_virtual_session_identity_is_deterministic_and_fact_bound() -> None:
    first = derive_external_signing_session_id("CASE-001", 9, "a" * 64)
    assert first == derive_external_signing_session_id("CASE-001", 9, "a" * 64)
    assert first.startswith("ces_")
    assert first != derive_external_signing_session_id("CASE-001", 9, "b" * 64)


def test_staff_reports_accept_any_target_order_but_each_target_only_once() -> None:
    facts = _facts()

    second = reduce_staff_completion_report(
        facts,
        matching_segment_id=22,
        expected_document_version_id=202,
        expected_status_version=3,
    )

    assert second.after_state is ExternalSigningState.STAFF_REPORTING
    assert second.reported_staff_segment_ids == (22,)
    assert second.resulting_status_version == 4
    assert second.requires_commitment is False
    assert second.create_client_reminder_intent is False

    replay_facts = _facts(reported_staff_segment_ids=(22,), status_version=4)
    with pytest.raises(ExternalSigningRuleError) as captured:
        reduce_staff_completion_report(
            replay_facts,
            matching_segment_id=22,
            expected_document_version_id=202,
            expected_status_version=4,
        )

    assert captured.value.code is ExternalSigningErrorCode.STAFF_REPORT_ALREADY_RECORDED


def test_last_staff_report_requires_commitment_and_client_reminder() -> None:
    facts = _facts(reported_staff_segment_ids=(22,), status_version=4)

    transition = reduce_staff_completion_report(
        facts,
        matching_segment_id=11,
        expected_document_version_id=101,
        expected_status_version=4,
    )

    assert transition.after_state is ExternalSigningState.STAFF_REPORTS_COMPLETE
    assert transition.reported_staff_segment_ids == (11, 22)
    assert transition.requires_commitment is True
    assert transition.create_client_reminder_intent is True


def test_client_report_is_rejected_until_all_staff_reports_are_complete() -> None:
    with pytest.raises(ExternalSigningRuleError) as captured:
        reduce_client_completion_report(
            _facts(),
            expected_document_version_id=303,
            expected_commitment_id=44,
            expected_status_version=3,
        )

    assert captured.value.code is ExternalSigningErrorCode.CLIENT_REPORT_OUT_OF_ORDER


def test_client_report_only_enters_final_pdf_pending() -> None:
    facts = _facts(
        state=ExternalSigningState.STAFF_REPORTS_COMPLETE,
        reported_staff_segment_ids=(11, 22),
        commitment_id=44,
        status_version=5,
    )

    transition = reduce_client_completion_report(
        facts,
        expected_document_version_id=303,
        expected_commitment_id=44,
        expected_status_version=5,
    )

    assert transition.after_state is ExternalSigningState.CLIENT_REPORTED_FINAL_PDF_PENDING
    assert transition.resulting_status_version == 6
    assert transition.client_reported is True
    assert transition.create_final_pdf_recovery_task is True
    assert transition.contract_completed is False


def test_staff_report_rejects_stale_session() -> None:
    with pytest.raises(ExternalSigningRuleError) as captured:
        reduce_staff_completion_report(
            _facts(status_version=4),
            matching_segment_id=11,
            expected_document_version_id=101,
            expected_status_version=3,
        )

    assert captured.value.code is ExternalSigningErrorCode.STATUS_VERSION_STALE


def test_staff_report_rejects_superseded_session() -> None:
    with pytest.raises(ExternalSigningRuleError) as captured:
        reduce_staff_completion_report(
            _facts(state=ExternalSigningState.SUPERSEDED),
            matching_segment_id=11,
            expected_document_version_id=101,
            expected_status_version=3,
        )

    assert captured.value.code is ExternalSigningErrorCode.SESSION_SUPERSEDED


def test_final_pdf_blockers_are_closed_and_deterministic() -> None:
    assert final_signed_contract_blockers(_facts()) == (
        ExternalSigningErrorCode.STAFF_REPORTS_INCOMPLETE,
        ExternalSigningErrorCode.CLIENT_REPORT_OUT_OF_ORDER,
        ExternalSigningErrorCode.COMMITMENT_MISSING,
        ExternalSigningErrorCode.FINAL_PDF_NOT_PENDING,
    )
    assert final_signed_contract_blockers(
        _facts(state=ExternalSigningState.SUPERSEDED)
    ) == (ExternalSigningErrorCode.SESSION_SUPERSEDED,)
    assert final_signed_contract_blockers(
        _facts(
            state=ExternalSigningState.CLIENT_REPORTED_FINAL_PDF_PENDING,
            reported_staff_segment_ids=(11, 22),
            commitment_id=44,
            client_reported=True,
            status_version=6,
        )
    ) == ()


def _facts(
    *,
    state: ExternalSigningState = ExternalSigningState.STAFF_REPORTING,
    reported_staff_segment_ids: tuple[int, ...] = (),
    commitment_id: int | None = None,
    client_reported: bool = False,
    status_version: int = 3,
) -> ExternalSigningSessionFacts:
    return ExternalSigningSessionFacts(
        session_id="ces_1234567890abcdef1234567890abcdef",
        case_no="CASE-001",
        matching_plan_id=9,
        document_set_fingerprint="a" * 64,
        staff_targets=(
            StaffSigningReportTarget(11, "501", 101),
            StaffSigningReportTarget(22, "502", 202),
        ),
        reported_staff_segment_ids=reported_staff_segment_ids,
        client_subject_reference="701",
        client_document_version_id=303,
        commitment_id=commitment_id,
        client_reported=client_reported,
        state=state,
        status_version=status_version,
    )
