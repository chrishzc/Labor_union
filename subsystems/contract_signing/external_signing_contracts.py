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
_MANUAL_ATTESTATION_ACTOR = re.compile(r"^(?:admin:[1-9][0-9]*|system:local_bypass)$")


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


_LEGACY_RECOVERY_KIND = "contract_legacy_manual_recovery.v1"


@dataclass(frozen=True, slots=True)
class LegacyManualSigningEvidence:
    """Immutable legacy signed-return tuple loaded from its owning tables."""

    case_no: str
    scope: ExternalCompletionReportScope
    matching_plan_id: int
    matching_segment_id: int | None
    legacy_document_version_id: int
    source_document_version_id: int
    signing_event_id: int
    command_receipt_id: int
    event_key: str
    command_kind: str
    media_sha256: str
    actor_ref: str
    correlation_id: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if not isinstance(self.scope, ExternalCompletionReportScope):
            raise TypeError("legacy manual signing scope is invalid")
        require_positive_integer(self.matching_plan_id, "matching plan ID")
        if self.scope is ExternalCompletionReportScope.STAFF:
            require_positive_integer(self.matching_segment_id, "matching segment ID")
        elif self.matching_segment_id is not None:
            raise ValueError("client legacy evidence cannot contain a segment ID")
        for value, name in (
            (self.legacy_document_version_id, "legacy document version ID"),
            (self.source_document_version_id, "source document version ID"),
            (self.signing_event_id, "legacy signing event ID"),
            (self.command_receipt_id, "legacy command receipt ID"),
        ):
            require_positive_integer(value, name)
        require_canonical_text(self.event_key, "legacy event key", 191)
        require_canonical_text(self.command_kind, "legacy command kind", 64)
        expected = (
            "record_manual_staff_contract_attestation"
            if self.scope is ExternalCompletionReportScope.STAFF
            else "record_manual_client_contract_attestation"
        )
        if self.command_kind != expected:
            raise ValueError("legacy manual signing command kind is invalid")
        require_sha256_hex(self.media_sha256, "legacy media digest")
        require_canonical_text(self.actor_ref, "legacy actor", 191)
        require_canonical_text(self.correlation_id, "legacy correlation ID", 191)

    @property
    def source_event_identity(self) -> str:
        return f"legacy-contract-signing-event:{self.signing_event_id}"

    @property
    def canonical_tuple_sha256(self) -> str:
        return fingerprint_payload(self.canonical_payload).value

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "actor_ref": self.actor_ref,
            "case_no": self.case_no,
            "command_kind": self.command_kind,
            "command_receipt_id": self.command_receipt_id,
            "correlation_id": self.correlation_id,
            "event_key": self.event_key,
            "legacy_document_version_id": self.legacy_document_version_id,
            "matching_plan_id": self.matching_plan_id,
            "matching_segment_id": self.matching_segment_id,
            "media_sha256": self.media_sha256,
            "scope": self.scope.value,
            "signing_event_id": self.signing_event_id,
            "source_document_version_id": self.source_document_version_id,
        }


@dataclass(frozen=True, slots=True)
class PreviewLegacyManualRecoveryReport:
    case_no: str
    scope: ExternalCompletionReportScope
    matching_segment_id: int | None
    legacy_document_version_id: int
    signing_event_id: int
    command_receipt_id: int
    confirmation_method: ManualAttestationMethod
    reason: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if not isinstance(self.scope, ExternalCompletionReportScope):
            raise TypeError("legacy recovery scope is invalid")
        if self.scope is ExternalCompletionReportScope.STAFF:
            require_positive_integer(self.matching_segment_id, "matching segment ID")
        elif self.matching_segment_id is not None:
            raise ValueError("client legacy recovery cannot contain a segment ID")
        require_positive_integer(
            self.legacy_document_version_id, "legacy document version ID"
        )
        require_positive_integer(self.signing_event_id, "legacy signing event ID")
        require_positive_integer(self.command_receipt_id, "legacy command receipt ID")
        if not isinstance(self.confirmation_method, ManualAttestationMethod):
            raise TypeError("legacy recovery confirmation method is invalid")
        require_canonical_text(self.reason, "legacy recovery reason", 1000)


@dataclass(frozen=True, slots=True)
class LegacyManualRecoverySnapshot:
    preview_fingerprint: PreviewFingerprint
    case_no: str
    session_id: str
    scope: ExternalCompletionReportScope
    matching_segment_id: int | None
    target_subject_reference: str
    current_matching_plan_id: int
    current_document_version_id: int
    current_document_set_sha256: str
    current_commitment_id: int | None
    legacy: LegacyManualSigningEvidence
    confirmation_method: ManualAttestationMethod
    reason: str
    kind: str = _LEGACY_RECOVERY_KIND

    def __post_init__(self) -> None:
        if not isinstance(self.preview_fingerprint, PreviewFingerprint):
            raise TypeError("legacy recovery Preview fingerprint is invalid")
        require_canonical_text(self.case_no, "case number", 50)
        _require_pattern(self.session_id, _SESSION_ID, "external signing session ID")
        if not isinstance(self.scope, ExternalCompletionReportScope):
            raise TypeError("legacy recovery scope is invalid")
        if self.scope is ExternalCompletionReportScope.STAFF:
            require_positive_integer(self.matching_segment_id, "matching segment ID")
        elif self.matching_segment_id is not None:
            raise ValueError("client legacy recovery cannot contain a segment ID")
        require_canonical_text(
            self.target_subject_reference, "legacy recovery target", 191
        )
        require_positive_integer(self.current_matching_plan_id, "matching plan ID")
        require_positive_integer(
            self.current_document_version_id, "current document version ID"
        )
        require_sha256_hex(
            self.current_document_set_sha256, "current document set digest"
        )
        if self.current_commitment_id is not None:
            require_positive_integer(self.current_commitment_id, "commitment ID")
        if not isinstance(self.legacy, LegacyManualSigningEvidence):
            raise TypeError("legacy signing evidence is invalid")
        if (
            self.legacy.case_no != self.case_no
            or self.legacy.scope is not self.scope
            or self.legacy.matching_segment_id != self.matching_segment_id
            or self.legacy.matching_plan_id != self.current_matching_plan_id
        ):
            raise ValueError("legacy recovery evidence target is inconsistent")
        if (
            self.scope is ExternalCompletionReportScope.CLIENT
            and self.current_commitment_id is None
        ):
            raise ValueError("client legacy recovery requires a commitment ID")
        if not isinstance(self.confirmation_method, ManualAttestationMethod):
            raise TypeError("legacy recovery confirmation method is invalid")
        require_canonical_text(self.reason, "legacy recovery reason", 1000)
        if self.kind != _LEGACY_RECOVERY_KIND:
            raise ValueError("legacy recovery snapshot kind is invalid")

    def persisted_payload(self) -> dict[str, object]:
        return {
            "confirmation_method": self.confirmation_method.value,
            "current": {
                "commitment_id": self.current_commitment_id,
                "document_set_sha256": self.current_document_set_sha256,
                "document_version_id": self.current_document_version_id,
                "matching_plan_id": self.current_matching_plan_id,
                "session_id": self.session_id,
                "target_subject_reference": self.target_subject_reference,
            },
            "kind": self.kind,
            "legacy": self.legacy.canonical_payload,
            "preview_fingerprint": self.preview_fingerprint.value,
            "reason": self.reason,
            "scope": self.scope.value,
            "matching_segment_id": self.matching_segment_id,
        }

    @property
    def legacy_media_sha256(self) -> str:
        return self.legacy.media_sha256


@dataclass(frozen=True, slots=True)
class ApplyLegacyManualRecoveryReport:
    preview: PreviewLegacyManualRecoveryReport
    preview_fingerprint: PreviewFingerprint
    expected_status_version: ExpectedVersion
    occurred_at: datetime
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        if not isinstance(self.preview, PreviewLegacyManualRecoveryReport):
            raise TypeError("legacy recovery Preview request is invalid")
        if not isinstance(self.preview_fingerprint, PreviewFingerprint):
            raise TypeError("legacy recovery Preview fingerprint is invalid")
        if not isinstance(self.expected_status_version, ExpectedVersion):
            raise TypeError("expected status version is invalid")
        if (
            not isinstance(self.occurred_at, datetime)
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
        ):
            raise ValueError("legacy recovery occurred_at must be timezone-aware")
        if not isinstance(self.actor, ActorContext):
            raise TypeError("legacy recovery actor is invalid")
        _require_persisted_admin(self.actor)
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("legacy recovery idempotency key is invalid")
        if _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key.value) is None:
            raise ValueError("legacy recovery idempotency key is invalid")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("legacy recovery correlation ID is invalid")


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
    recovery: LegacyManualRecoverySnapshot | None = None

    def __post_init__(self) -> None:
        _validate_common_command(self)
        require_positive_integer(self.matching_segment_id, "matching segment ID")
        require_canonical_text(
            self.attested_subject_reference, "attested staff reference", 191
        )
        if not isinstance(self.attestation, ManualAttestationEvidence):
            raise TypeError("manual attestation evidence is required")
        if self.recovery is not None and (
            not isinstance(self.recovery, LegacyManualRecoverySnapshot)
            or self.recovery.scope is not ExternalCompletionReportScope.STAFF
            or self.recovery.matching_segment_id != self.matching_segment_id
        ):
            raise ValueError("staff legacy recovery snapshot is invalid")
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
    recovery: LegacyManualRecoverySnapshot | None = None

    def __post_init__(self) -> None:
        _validate_common_command(self)
        require_positive_integer(self.expected_commitment_id, "expected commitment ID")
        require_canonical_text(
            self.attested_subject_reference, "attested client reference", 191
        )
        if not isinstance(self.attestation, ManualAttestationEvidence):
            raise TypeError("manual attestation evidence is required")
        if self.recovery is not None and (
            not isinstance(self.recovery, LegacyManualRecoverySnapshot)
            or self.recovery.scope is not ExternalCompletionReportScope.CLIENT
            or self.recovery.matching_segment_id is not None
        ):
            raise ValueError("client legacy recovery snapshot is invalid")
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
    recovery: LegacyManualRecoverySnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command_fingerprint, PreviewFingerprint):
            raise TypeError("stored external report fingerprint is invalid")
        if not isinstance(self.receipt, ExternalSigningReportReceipt):
            raise TypeError("stored external report receipt is invalid")
        if self.recovery is not None and not isinstance(
            self.recovery, LegacyManualRecoverySnapshot
        ):
            raise TypeError("stored legacy recovery snapshot is invalid")
        if self.recovery is not None:
            expected_command = (
                ExternalReportCommandType.RECORD_STAFF_REPORT
                if self.recovery.scope is ExternalCompletionReportScope.STAFF
                else ExternalReportCommandType.RECORD_CLIENT_REPORT
            )
            if (
                self.receipt.command_type is not expected_command
                or self.receipt.session_id != self.recovery.session_id
                or self.receipt.scope is not self.recovery.scope
                or self.receipt.matching_segment_id
                != self.recovery.matching_segment_id
            ):
                raise ValueError("stored legacy recovery receipt lineage is inconsistent")


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
        if command.recovery is not None:
            payload["legacy_recovery"] = command.recovery.persisted_payload()
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
    if _MANUAL_ATTESTATION_ACTOR.fullmatch(actor.actor_id) is None:
        raise ValueError("manual attestation requires a persisted admin actor")


__all__ = [
    "ApplyLegacyManualRecoveryReport",
    "ExternalCompletionReportScope",
    "ExternalReportCommandType",
    "ExternalReporterSubjectType",
    "ExternalSigningReportCommand",
    "ExternalSigningReportReceipt",
    "ExternalSigningTypedError",
    "LegacyManualRecoverySnapshot",
    "LegacyManualSigningEvidence",
    "ManualAttestationEvidence",
    "ManualAttestationMethod",
    "PreviewLegacyManualRecoveryReport",
    "RecordManualExternalClientSigningReport",
    "RecordManualExternalStaffSigningReport",
    "RecordExternalClientSigningReport",
    "RecordExternalStaffSigningReport",
    "StoredExternalSigningReportReceipt",
    "VerifiedReporterBindingSnapshot",
    "external_report_command_fingerprint",
    "reconcile_external_report_replay",
]
