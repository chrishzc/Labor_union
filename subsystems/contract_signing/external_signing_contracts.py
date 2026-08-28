"""
File: external_signing_contracts.py
Description: 定義外部簽約完成回報的 typed commands、canonical fingerprint 與 closed receipts。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
import re

from domains.contract_signing.external_signing import ExternalSigningState
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
    require_sha256_hex,
)


_SESSION_ID = re.compile(r"^ces_[0-9a-f]{32}$")
_REPORT_ID = re.compile(r"^cer_[0-9a-f]{32}$")
_IDEMPOTENCY_KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,190}$")
_PERSISTED_ADMIN_ACTOR = re.compile(r"^admin:[1-9][0-9]*$")


class ExternalCompletionReportScope(StrEnum):
    STAFF = "staff"
    CLIENT = "client"


class ExternalReporterSubjectType(StrEnum):
    STAFF = "staff"
    CUSTOMER = "customer"


class ExternalReportCommandType(StrEnum):
    RECORD_STAFF_REPORT = "record_external_staff_signing_report"
    RECORD_CLIENT_REPORT = "record_external_client_signing_report"


class ManualAttestationMethod(StrEnum):
    PHONE = "phone"
    PAPER = "paper"
    IN_PERSON = "in_person"
    VERIFIED_OTHER = "verified_other"


class ExternalSigningTypedError(RuntimeError):
    def __init__(
        self,
        *,
        category: str,
        code: str,
        message: str,
        retryable: bool = False,
        current_version: int | None = None,
    ) -> None:
        self.category = category
        self.code = code
        self.retryable = retryable
        self.current_version = current_version
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class VerifiedReporterBindingSnapshot:
    line_user_id: str
    subject_type: ExternalReporterSubjectType
    subject_reference: str
    aggregate_version: ExpectedVersion

    def __post_init__(self) -> None:
        require_canonical_text(self.line_user_id, "LINE user ID", 191)
        if not isinstance(self.subject_type, ExternalReporterSubjectType):
            raise TypeError("reporter subject type is invalid")
        require_canonical_text(
            self.subject_reference,
            "reporter subject reference",
            191,
        )
        if not isinstance(self.aggregate_version, ExpectedVersion):
            raise TypeError("reporter binding version is invalid")


@dataclass(frozen=True, slots=True)
class ManualAttestationEvidence:
    method: ManualAttestationMethod
    reason: str
    evidence_reference: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.method, ManualAttestationMethod):
            raise TypeError("manual attestation method is invalid")
        require_canonical_text(self.reason, "manual attestation reason", 1000)
        require_canonical_text(
            self.evidence_reference, "manual evidence reference", 191
        )
        require_sha256_hex(self.evidence_sha256, "manual evidence digest")


@dataclass(frozen=True, slots=True)
class RecordExternalStaffSigningReport:
    session_id: str
    case_no: str
    matching_plan_id: int
    matching_segment_id: int
    expected_document_version_id: int
    reporter_binding: VerifiedReporterBindingSnapshot
    source_event_identity: str
    source_payload_sha256: str
    occurred_at: datetime
    expected_status_version: ExpectedVersion
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_common_command(self)
        require_positive_integer(self.matching_segment_id, "matching segment ID")
        if self.reporter_binding.subject_type is not ExternalReporterSubjectType.STAFF:
            raise ValueError("staff report requires a staff binding snapshot")


@dataclass(frozen=True, slots=True)
class RecordExternalClientSigningReport:
    session_id: str
    case_no: str
    matching_plan_id: int
    expected_document_version_id: int
    expected_commitment_id: int
    reporter_binding: VerifiedReporterBindingSnapshot
    source_event_identity: str
    source_payload_sha256: str
    occurred_at: datetime
    expected_status_version: ExpectedVersion
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_common_command(self)
        require_positive_integer(self.expected_commitment_id, "expected commitment ID")
        if self.reporter_binding.subject_type is not ExternalReporterSubjectType.CUSTOMER:
            raise ValueError("client report requires a customer binding snapshot")


@dataclass(frozen=True, slots=True)
class RecordManualExternalStaffSigningReport:
    session_id: str
    case_no: str
    matching_plan_id: int
    matching_segment_id: int
    expected_document_version_id: int
    attested_subject_reference: str
    attestation: ManualAttestationEvidence
    source_event_identity: str
    source_payload_sha256: str
    occurred_at: datetime
    expected_status_version: ExpectedVersion
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_common_command(self)
        require_positive_integer(self.matching_segment_id, "matching segment ID")
        require_canonical_text(
            self.attested_subject_reference, "attested staff reference", 191
        )
        if not isinstance(self.attestation, ManualAttestationEvidence):
            raise TypeError("manual attestation evidence is required")
        _require_persisted_admin(self.actor)


@dataclass(frozen=True, slots=True)
class RecordManualExternalClientSigningReport:
    session_id: str
    case_no: str
    matching_plan_id: int
    expected_document_version_id: int
    expected_commitment_id: int
    attested_subject_reference: str
    attestation: ManualAttestationEvidence
    source_event_identity: str
    source_payload_sha256: str
    occurred_at: datetime
    expected_status_version: ExpectedVersion
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_common_command(self)
        require_positive_integer(self.expected_commitment_id, "expected commitment ID")
        require_canonical_text(
            self.attested_subject_reference, "attested client reference", 191
        )
        if not isinstance(self.attestation, ManualAttestationEvidence):
            raise TypeError("manual attestation evidence is required")
        _require_persisted_admin(self.actor)


ExternalSigningReportCommand = (
    RecordExternalStaffSigningReport
    | RecordExternalClientSigningReport
    | RecordManualExternalStaffSigningReport
    | RecordManualExternalClientSigningReport
)


@dataclass(frozen=True, slots=True)
class ExternalSigningReportReceipt:
    command_type: ExternalReportCommandType
    report_id: str
    session_id: str
    scope: ExternalCompletionReportScope
    matching_segment_id: int | None
    resulting_status_version: int
    resulting_state: ExternalSigningState
    client_reminder_intent_created: bool
    final_pdf_recovery_task_created: bool
    replayed: bool = False
    schema_version: str = "external-signing-report-receipt.v1"

    def __post_init__(self) -> None:
        if not isinstance(self.command_type, ExternalReportCommandType):
            raise TypeError("external report command type is invalid")
        _require_pattern(self.report_id, _REPORT_ID, "external signing report ID")
        _require_pattern(self.session_id, _SESSION_ID, "external signing session ID")
        if not isinstance(self.scope, ExternalCompletionReportScope):
            raise TypeError("external report scope is invalid")
        _validate_receipt_scope(self)
        require_nonnegative_integer(
            self.resulting_status_version,
            "resulting status version",
        )
        if not isinstance(self.resulting_state, ExternalSigningState):
            raise TypeError("external signing receipt state is invalid")
        for name, value in (
            ("client reminder intent", self.client_reminder_intent_created),
            ("final PDF recovery task", self.final_pdf_recovery_task_created),
            ("replayed", self.replayed),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} flag must be boolean")
        if self.schema_version != "external-signing-report-receipt.v1":
            raise ValueError("external signing report receipt schema is invalid")


@dataclass(frozen=True, slots=True)
class StoredExternalSigningReportReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: ExternalSigningReportReceipt

    def __post_init__(self) -> None:
        if not isinstance(self.command_fingerprint, PreviewFingerprint):
            raise TypeError("stored external report fingerprint is invalid")
        if not isinstance(self.receipt, ExternalSigningReportReceipt):
            raise TypeError("stored external report receipt is invalid")


def external_report_command_fingerprint(
    command: ExternalSigningReportCommand,
) -> PreviewFingerprint:
    payload = _common_fingerprint_payload(command)
    if isinstance(command, (RecordExternalStaffSigningReport, RecordManualExternalStaffSigningReport)):
        payload.update(
            {
                "command_type": ExternalReportCommandType.RECORD_STAFF_REPORT.value,
                "matching_segment_id": command.matching_segment_id,
            }
        )
    elif isinstance(command, (RecordExternalClientSigningReport, RecordManualExternalClientSigningReport)):
        payload.update(
            {
                "command_type": ExternalReportCommandType.RECORD_CLIENT_REPORT.value,
                "expected_commitment_id": command.expected_commitment_id,
            }
        )
    else:
        raise TypeError("external signing report command is invalid")
    return fingerprint_payload(payload)


def reconcile_external_report_replay(
    stored: StoredExternalSigningReportReceipt,
    command: ExternalSigningReportCommand,
) -> ExternalSigningReportReceipt:
    current = external_report_command_fingerprint(command)
    if current != stored.command_fingerprint:
        raise ExternalSigningTypedError(
            category="idempotency_mismatch",
            code="external_signing_report_replay_conflict",
            message="相同回報識別對應不同內容。",
            retryable=False,
            current_version=stored.receipt.resulting_status_version,
        )
    return replace(stored.receipt, replayed=True)


def _validate_common_command(command: ExternalSigningReportCommand) -> None:
    _require_pattern(command.session_id, _SESSION_ID, "external signing session ID")
    require_canonical_text(command.case_no, "case number", 50)
    require_positive_integer(command.matching_plan_id, "matching plan ID")
    require_positive_integer(
        command.expected_document_version_id,
        "expected document version ID",
    )
    require_canonical_text(command.source_event_identity, "source event identity", 191)
    require_sha256_hex(command.source_payload_sha256, "source payload digest")
    if (
        not isinstance(command.occurred_at, datetime)
        or command.occurred_at.tzinfo is None
        or command.occurred_at.utcoffset() is None
    ):
        raise ValueError("completion report occurred_at must be timezone-aware")
    if not isinstance(command.expected_status_version, ExpectedVersion):
        raise TypeError("expected status version is invalid")
    if not isinstance(command.actor, ActorContext):
        raise TypeError("completion report actor is invalid")
    if not isinstance(command.idempotency_key, IdempotencyKey):
        raise TypeError("completion report idempotency key is invalid")
    if _IDEMPOTENCY_KEY.fullmatch(command.idempotency_key.value) is None:
        raise ValueError("completion report idempotency key is invalid")
    if not isinstance(command.correlation_id, CorrelationId):
        raise TypeError("completion report correlation ID is invalid")


def _common_fingerprint_payload(
    command: ExternalSigningReportCommand,
) -> dict[str, object]:
    payload = {
        "session_id": command.session_id,
        "case_no": command.case_no,
        "matching_plan_id": command.matching_plan_id,
        "expected_document_version_id": command.expected_document_version_id,
        "source_event_identity": command.source_event_identity,
        "source_payload_sha256": command.source_payload_sha256,
        "occurred_at": command.occurred_at.astimezone(timezone.utc).isoformat(),
        "expected_status_version": command.expected_status_version.value,
        "actor": command.actor.actor_id,
    }
    if isinstance(command, (RecordExternalStaffSigningReport, RecordExternalClientSigningReport)):
        binding = command.reporter_binding
        payload["verified_binding"] = {
            "line_user_id": binding.line_user_id,
            "subject_type": binding.subject_type.value,
            "subject_reference": binding.subject_reference,
            "aggregate_version": binding.aggregate_version.value,
        }
    else:
        payload["manual_attestation"] = {
            "subject_reference": command.attested_subject_reference,
            "method": command.attestation.method.value,
            "reason": command.attestation.reason,
            "evidence_reference": command.attestation.evidence_reference,
            "evidence_sha256": command.attestation.evidence_sha256,
        }
    return payload


def _validate_receipt_scope(receipt: ExternalSigningReportReceipt) -> None:
    if receipt.scope is ExternalCompletionReportScope.STAFF:
        require_positive_integer(receipt.matching_segment_id, "matching segment ID")
        if receipt.command_type is not ExternalReportCommandType.RECORD_STAFF_REPORT:
            raise ValueError("staff receipt command type is invalid")
        return
    if receipt.matching_segment_id is not None:
        raise ValueError("client receipt cannot contain matching segment ID")
    if receipt.command_type is not ExternalReportCommandType.RECORD_CLIENT_REPORT:
        raise ValueError("client receipt command type is invalid")


def _require_pattern(value: str, pattern: re.Pattern[str], field_name: str) -> None:
    require_canonical_text(value, field_name, 64)
    if pattern.fullmatch(value) is None:
        raise ValueError(f"{field_name} is invalid")


def _require_persisted_admin(actor: ActorContext) -> None:
    if _PERSISTED_ADMIN_ACTOR.fullmatch(actor.actor_id) is None:
        raise ValueError("manual attestation requires a persisted admin actor")


__all__ = [
    "ExternalCompletionReportScope",
    "ExternalReportCommandType",
    "ExternalReporterSubjectType",
    "ExternalSigningReportCommand",
    "ExternalSigningReportReceipt",
    "ExternalSigningTypedError",
    "ManualAttestationEvidence",
    "ManualAttestationMethod",
    "RecordManualExternalClientSigningReport",
    "RecordManualExternalStaffSigningReport",
    "RecordExternalClientSigningReport",
    "RecordExternalStaffSigningReport",
    "StoredExternalSigningReportReceipt",
    "VerifiedReporterBindingSnapshot",
    "external_report_command_fingerprint",
    "reconcile_external_report_replay",
]
