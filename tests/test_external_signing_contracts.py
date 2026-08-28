"""
File: test_external_signing_contracts.py
Description: 驗證外部完成回報命令的 canonical fingerprint、typed receipt 與重播衝突。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from domains.contract_signing.external_signing import ExternalSigningState
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.contract_signing.external_signing_contracts import (
    ExternalCompletionReportScope,
    ExternalReportCommandType,
    ExternalReporterSubjectType,
    ExternalSigningReportReceipt,
    ExternalSigningTypedError,
    ManualAttestationEvidence,
    ManualAttestationMethod,
    RecordManualExternalStaffSigningReport,
    RecordExternalClientSigningReport,
    RecordExternalStaffSigningReport,
    StoredExternalSigningReportReceipt,
    VerifiedReporterBindingSnapshot,
    external_report_command_fingerprint,
    reconcile_external_report_replay,
)


def test_staff_command_fingerprint_is_canonical_and_excludes_correlation() -> None:
    first = _staff_command(correlation="corr-001")
    second = _staff_command(correlation="corr-999")

    assert external_report_command_fingerprint(first) == external_report_command_fingerprint(second)


def test_same_command_replays_the_typed_receipt() -> None:
    command = _staff_command()
    receipt = ExternalSigningReportReceipt(
        command_type=ExternalReportCommandType.RECORD_STAFF_REPORT,
        report_id="cer_1234567890abcdef1234567890abcdef",
        session_id=command.session_id,
        scope=ExternalCompletionReportScope.STAFF,
        matching_segment_id=11,
        resulting_status_version=4,
        resulting_state=ExternalSigningState.STAFF_REPORTING,
        client_reminder_intent_created=False,
        final_pdf_recovery_task_created=False,
    )
    stored = StoredExternalSigningReportReceipt(
        external_report_command_fingerprint(command), receipt
    )

    replay = reconcile_external_report_replay(stored, command)

    assert replay.replayed is True
    assert replay.report_id == receipt.report_id
    assert replay.schema_version == "external-signing-report-receipt.v1"


def test_same_key_with_different_payload_is_a_typed_replay_conflict() -> None:
    original = _staff_command()
    changed = _staff_command(payload_sha256="b" * 64)
    receipt = ExternalSigningReportReceipt(
        command_type=ExternalReportCommandType.RECORD_STAFF_REPORT,
        report_id="cer_1234567890abcdef1234567890abcdef",
        session_id=original.session_id,
        scope=ExternalCompletionReportScope.STAFF,
        matching_segment_id=11,
        resulting_status_version=4,
        resulting_state=ExternalSigningState.STAFF_REPORTING,
        client_reminder_intent_created=False,
        final_pdf_recovery_task_created=False,
    )
    stored = StoredExternalSigningReportReceipt(
        external_report_command_fingerprint(original), receipt
    )

    with pytest.raises(ExternalSigningTypedError) as captured:
        reconcile_external_report_replay(stored, changed)

    assert captured.value.code == "external_signing_report_replay_conflict"
    assert captured.value.category == "idempotency_mismatch"
    assert captured.value.retryable is False


def test_client_command_requires_a_customer_binding_snapshot() -> None:
    with pytest.raises(ValueError, match="customer"):
        RecordExternalClientSigningReport(
            session_id="ces_1234567890abcdef1234567890abcdef",
            case_no="CASE-001",
            matching_plan_id=9,
            expected_document_version_id=303,
            expected_commitment_id=44,
            reporter_binding=VerifiedReporterBindingSnapshot(
                line_user_id="U-staff",
                subject_type=ExternalReporterSubjectType.STAFF,
                subject_reference="501",
                aggregate_version=ExpectedVersion(2),
            ),
            source_event_identity="line-event-client-001",
            source_payload_sha256="c" * 64,
            occurred_at=datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
            expected_status_version=ExpectedVersion(5),
            actor=ActorContext("line_user_id:U-client"),
            idempotency_key=IdempotencyKey("external-report:client:event-001"),
            correlation_id=CorrelationId("corr-client-001"),
        )


def test_manual_attestation_is_explicit_and_part_of_fingerprint() -> None:
    command = RecordManualExternalStaffSigningReport(
        "ces_1234567890abcdef1234567890abcdef", "CASE-001", 9, 11, 101, "501",
        ManualAttestationEvidence(
            ManualAttestationMethod.PAPER, "signed paper reviewed", "evidence:paper:1", "e" * 64
        ),
        "manual-event-001", "d" * 64,
        datetime(2026, 8, 26, 12, tzinfo=timezone.utc), ExpectedVersion(0),
        ActorContext("admin:17"), IdempotencyKey("external-report:manual:001"),
        CorrelationId("corr-manual-001"),
    )
    changed = replace(
        command,
        attestation=replace(command.attestation, reason="different review reason"),
    )

    assert external_report_command_fingerprint(command) != external_report_command_fingerprint(changed)


def test_manual_attestation_rejects_non_closed_method() -> None:
    with pytest.raises(TypeError, match="method"):
        ManualAttestationEvidence("email", "reason", "evidence:1", "e" * 64)


def test_manual_report_requires_persisted_admin_actor() -> None:
    with pytest.raises(ValueError, match="persisted admin"):
        RecordManualExternalStaffSigningReport(
            "ces_1234567890abcdef1234567890abcdef", "CASE-001", 9, 11, 101, "501",
            ManualAttestationEvidence(
                ManualAttestationMethod.PHONE, "confirmed", "evidence:1", "e" * 64
            ),
            "manual-event-002", "d" * 64,
            datetime(2026, 8, 26, 12, tzinfo=timezone.utc), ExpectedVersion(0),
            ActorContext("operator:17"), IdempotencyKey("external-report:manual:002"),
            CorrelationId("corr-manual-002"),
        )


def _staff_command(
    *,
    payload_sha256: str = "a" * 64,
    correlation: str = "corr-001",
) -> RecordExternalStaffSigningReport:
    return RecordExternalStaffSigningReport(
        session_id="ces_1234567890abcdef1234567890abcdef",
        case_no="CASE-001",
        matching_plan_id=9,
        matching_segment_id=11,
        expected_document_version_id=101,
        reporter_binding=VerifiedReporterBindingSnapshot(
            line_user_id="U-staff",
            subject_type=ExternalReporterSubjectType.STAFF,
            subject_reference="501",
            aggregate_version=ExpectedVersion(2),
        ),
        source_event_identity="line-event-staff-001",
        source_payload_sha256=payload_sha256,
        occurred_at=datetime(2026, 8, 26, 11, 0, tzinfo=timezone.utc),
        expected_status_version=ExpectedVersion(3),
        actor=ActorContext("line_user_id:U-staff"),
        idempotency_key=IdempotencyKey("external-report:staff:event-001"),
        correlation_id=CorrelationId(correlation),
    )
