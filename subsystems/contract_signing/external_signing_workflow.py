"""
File: external_signing_workflow.py
Description: 編排外部簽約回報的唯讀查詢、fresh-lock Apply、重播與 borrowed outer UoW。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    ExternalSigningTransition,
    final_signed_contract_blockers,
    reduce_client_completion_report,
    reduce_staff_completion_report,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_positive_integer
from subsystems.contract_signing.external_signing_contracts import (
    ApplyLegacyManualRecoveryReport,
    ExternalCompletionReportScope,
    ExternalReportCommandType,
    ExternalSigningReportCommand,
    ExternalSigningReportReceipt,
    ExternalSigningTypedError,
    LegacyManualRecoverySnapshot,
    LegacyManualSigningEvidence,
    ManualAttestationEvidence,
    PreviewLegacyManualRecoveryReport,
    RecordExternalClientSigningReport,
    RecordExternalStaffSigningReport,
    RecordManualExternalClientSigningReport,
    RecordManualExternalStaffSigningReport,
    StoredExternalSigningReportReceipt,
    VerifiedReporterBindingSnapshot,
    external_report_command_fingerprint,
    reconcile_external_report_replay,
)
from shared_kernel.fingerprints import fingerprint_payload


@dataclass(frozen=True, slots=True)
class StaffCompletionPrerequisites:
    commitment_id: int
    client_reminder_task_id: int

    def __post_init__(self) -> None:
        require_positive_integer(self.commitment_id, "commitment ID")
        require_positive_integer(self.client_reminder_task_id, "client reminder task ID")


@dataclass(frozen=True, slots=True)
class PersistedExternalReport:
    report_id: str
    database_id: int

    def __post_init__(self) -> None:
        require_positive_integer(self.database_id, "completion report database ID")


@dataclass(frozen=True, slots=True)
class ExternalSigningSessionQuery:
    session_id: str
    case_no: str
    state: ExternalSigningState
    status_version: int
    required_staff_report_count: int
    recorded_staff_report_count: int
    client_reported: bool
    persisted: bool = True


@dataclass(frozen=True, slots=True)
class FinalPdfReadinessPreview:
    session_id: str
    state: ExternalSigningState
    status_version: int
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LegacyManualRecoveryTargetQuery:
    scope: ExternalCompletionReportScope
    matching_segment_id: int | None
    target_subject_reference: str
    current_document_version_id: int
    reported: bool
    legacy_document_version_id: int | None
    signing_event_id: int | None
    command_receipt_id: int | None
    legacy_media_sha256: str | None


@dataclass(frozen=True, slots=True)
class LegacyManualRecoveryQuery:
    case_no: str
    session_id: str
    matching_plan_id: int
    current_document_set_sha256: str
    commitment_id: int | None
    state: ExternalSigningState
    status_version: int
    targets: tuple[LegacyManualRecoveryTargetQuery, ...]


@dataclass(frozen=True, slots=True)
class LegacyManualRecoveryPreview:
    preview_fingerprint: PreviewFingerprint
    session_id: str
    expected_status_version: int
    scope: ExternalCompletionReportScope
    matching_segment_id: int | None
    current_document_version_id: int
    current_document_set_sha256: str
    current_commitment_id: int | None
    legacy_media_sha256: str
    blockers: tuple[str, ...]

    @property
    def can_apply(self) -> bool:
        return not self.blockers


class ExternalStaffCompletionPort(Protocol):
    """Runs inside the caller-owned transaction; never commits or opens a UoW."""

    def establish_prerequisites(
        self,
        command: RecordExternalStaffSigningReport,
        facts: ExternalSigningSessionFacts,
        resulting_status_version: int,
    ) -> StaffCompletionPrerequisites: ...


class ExternalSigningWorkflowRepository(Protocol):
    def load_session(
        self, session_id: str, *, for_update: bool
    ) -> ExternalSigningSessionFacts | None: ...

    def load_active_session_by_case(
        self, case_no: str, *, for_update: bool
    ) -> ExternalSigningSessionFacts | None: ...

    def derive_current_session(
        self, case_no: str, *, for_update: bool
    ) -> ExternalSigningSessionFacts | None: ...

    def load_legacy_manual_signing_evidence(
        self, case_no: str, *, for_update: bool
    ) -> tuple[LegacyManualSigningEvidence, ...]: ...

    def activate_session(
        self, facts: ExternalSigningSessionFacts, *, actor_id: str
    ) -> None: ...

    def find_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredExternalSigningReportReceipt | None: ...

    def find_source_receipt(
        self, source_event_identity: str, *, for_update: bool
    ) -> StoredExternalSigningReportReceipt | None: ...

    def reporter_binding_is_current(
        self, snapshot: VerifiedReporterBindingSnapshot, *, for_update: bool
    ) -> bool: ...

    def append_report(
        self,
        command: ExternalSigningReportCommand,
        transition: ExternalSigningTransition,
        command_fingerprint: PreviewFingerprint,
        commitment_id: int | None,
    ) -> PersistedExternalReport: ...

    def create_final_pdf_recovery(
        self,
        command: RecordExternalClientSigningReport,
        report: PersistedExternalReport,
        command_fingerprint: PreviewFingerprint,
    ) -> None: ...

    def advance_session(
        self,
        command: ExternalSigningReportCommand,
        transition: ExternalSigningTransition,
        prerequisites: StaffCompletionPrerequisites | None,
    ) -> None: ...

    def save_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredExternalSigningReportReceipt,
        command: ExternalSigningReportCommand,
        report: PersistedExternalReport,
    ) -> None: ...


class ExternalSigningWorkflow:
    def __init__(
        self,
        repository: ExternalSigningWorkflowRepository,
        staff_completion_port: ExternalStaffCompletionPort,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._staff_completion_port = staff_completion_port
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, session_id: str) -> ExternalSigningSessionQuery:
        facts = self._require_session(session_id, for_update=False)
        return _session_query(facts, persisted=True)

    def query_case(self, case_no: str) -> ExternalSigningSessionQuery:
        facts = self._repository.load_active_session_by_case(
            case_no, for_update=False
        )
        if facts is not None:
            return _session_query(facts, persisted=True)
        facts = self._repository.derive_current_session(case_no, for_update=False)
        if facts is None:
            raise _typed_error(
                "external_signing_session_facts_unavailable",
                "目前案件尚未具備可啟動的簽約 facts。",
            )
        return _session_query(facts, persisted=False)

    def preview_final_pdf_readiness(self, session_id: str) -> FinalPdfReadinessPreview:
        facts = self._require_session(session_id, for_update=False)
        return FinalPdfReadinessPreview(
            facts.session_id,
            facts.state,
            facts.status_version,
            tuple(blocker.value for blocker in final_signed_contract_blockers(facts)),
        )

    def query_legacy_manual_recovery(self, case_no: str) -> LegacyManualRecoveryQuery:
        facts = self._load_case_facts(case_no, for_update=False)
        evidence = self._repository.load_legacy_manual_signing_evidence(
            case_no, for_update=False
        )
        return _legacy_recovery_query(facts, evidence)

    def preview_legacy_manual_recovery(
        self, request: PreviewLegacyManualRecoveryReport
    ) -> LegacyManualRecoveryPreview:
        facts = self._load_case_facts(request.case_no, for_update=False)
        evidence = self._repository.load_legacy_manual_signing_evidence(
            request.case_no, for_update=False
        )
        snapshot = _build_recovery_snapshot(request, facts, evidence)
        return _legacy_recovery_preview(snapshot, facts)

    def apply_legacy_manual_recovery(
        self, command: ApplyLegacyManualRecoveryReport
    ) -> ExternalSigningReportReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            stored = self._repository.find_receipt(
                command.idempotency_key, for_update=True
            )
            if stored is None:
                stored = self._repository.find_source_receipt(
                    f"legacy-contract-signing-event:{command.preview.signing_event_id}",
                    for_update=True,
                )
            if stored is not None:
                if stored.recovery is None:
                    raise _typed_error(
                        "contract_legacy_manual_recovery_replay_kind_mismatch",
                        "相同命令識別已被其他簽約命令使用。",
                    )
                _require_recovery_replay_request_matches(command, stored.recovery)
                report_command = _recovery_report_command(command, stored.recovery)
                replay = reconcile_external_report_replay(stored, report_command)
                unit_of_work.commit()
                return replay

            facts = self._load_case_facts(command.preview.case_no, for_update=True)
            evidence = self._repository.load_legacy_manual_signing_evidence(
                command.preview.case_no, for_update=True
            )
            snapshot = _build_recovery_snapshot(command.preview, facts, evidence)
            if snapshot.preview_fingerprint != command.preview_fingerprint:
                raise _typed_error(
                    "contract_legacy_manual_recovery_preview_stale",
                    "歷史簽回或目前簽約 facts 已變更，請重新 Preview。",
                )
            report_command = _recovery_report_command(command, snapshot)
            return self._apply_report_in_uow(report_command, facts, unit_of_work)

    def apply_staff_report(
        self, command: RecordExternalStaffSigningReport
    ) -> ExternalSigningReportReceipt:
        return self._apply_report(command)

    def apply_client_report(
        self, command: RecordExternalClientSigningReport
    ) -> ExternalSigningReportReceipt:
        return self._apply_report(command)

    def apply_manual_staff_report(
        self, command: RecordManualExternalStaffSigningReport
    ) -> ExternalSigningReportReceipt:
        return self._apply_report(command)

    def apply_manual_client_report(
        self, command: RecordManualExternalClientSigningReport
    ) -> ExternalSigningReportReceipt:
        return self._apply_report(command)

    def _apply_report(
        self, command: ExternalSigningReportCommand
    ) -> ExternalSigningReportReceipt:
        fingerprint = external_report_command_fingerprint(command)
        with self._unit_of_work_factory() as unit_of_work:
            facts = self._repository.load_session(command.session_id, for_update=True)
            activate = facts is None
            if activate:
                if _is_client(command):
                    raise _typed_error(
                        "external_signing_session_not_activated",
                        "client report 不可先啟動 external signing session。",
                    )
                facts = self._repository.derive_current_session(
                    command.case_no, for_update=True
                )
                if facts is None or facts.session_id != command.session_id:
                    raise _typed_error(
                        "external_signing_session_identity_stale",
                        "virtual session facts 已變更。",
                    )
            return self._apply_report_in_uow(command, facts, unit_of_work, activate=activate)

    def _apply_report_in_uow(
        self,
        command: ExternalSigningReportCommand,
        facts: ExternalSigningSessionFacts,
        unit_of_work: UnitOfWork,
        *,
        activate: bool | None = None,
    ) -> ExternalSigningReportReceipt:
        fingerprint = external_report_command_fingerprint(command)
        if activate is None:
            persisted = self._repository.load_session(
                command.session_id, for_update=True
            )
            activate = persisted is None
            if not activate:
                facts = persisted
        replay = self._find_replay(command)
        if replay is not None:
            unit_of_work.commit()
            return replay
        _require_command_session(command, facts)
        if _is_verified(command) and not self._repository.reporter_binding_is_current(
            command.reporter_binding, for_update=True
        ):
            raise _typed_error("external_signing_reporter_binding_stale", "回報者綁定已變更。")
        transition = _reduce(command, facts)
        if activate:
            self._repository.activate_session(
                facts, actor_id=command.actor.actor_id
            )
        prerequisites = self._staff_prerequisites(command, facts, transition)
        commitment_id = (
            prerequisites.commitment_id
            if prerequisites is not None
            else facts.commitment_id
        )
        report = self._repository.append_report(
            command, transition, fingerprint, commitment_id
        )
        if _is_client(command):
            self._repository.create_final_pdf_recovery(command, report, fingerprint)
        self._repository.advance_session(command, transition, prerequisites)
        receipt = _receipt(command, transition, report)
        self._repository.save_receipt(
            command.idempotency_key,
            StoredExternalSigningReportReceipt(
                fingerprint,
                receipt,
                command.recovery
                if isinstance(
                    command,
                    (
                        RecordManualExternalStaffSigningReport,
                        RecordManualExternalClientSigningReport,
                    ),
                )
                else None,
            ),
            command,
            report,
        )
        unit_of_work.commit()
        return receipt

    def _find_replay(
        self, command: ExternalSigningReportCommand
    ) -> ExternalSigningReportReceipt | None:
        stored = self._repository.find_receipt(command.idempotency_key, for_update=True)
        if stored is None:
            stored = self._repository.find_source_receipt(
                command.source_event_identity, for_update=True
            )
        return None if stored is None else reconcile_external_report_replay(stored, command)

    def _staff_prerequisites(self, command, facts, transition):
        if not _is_staff(command):
            return None
        if not transition.requires_commitment:
            return None
        return self._staff_completion_port.establish_prerequisites(
            command, facts, transition.resulting_status_version
        )

    def _require_session(self, session_id: str, *, for_update: bool):
        facts = self._repository.load_session(session_id, for_update=for_update)
        if facts is None:
            raise _typed_error("external_signing_session_not_found", "找不到外部簽約 session。")
        return facts

    def _load_case_facts(self, case_no: str, *, for_update: bool):
        facts = self._repository.load_active_session_by_case(
            case_no, for_update=for_update
        )
        if facts is None:
            facts = self._repository.derive_current_session(
                case_no, for_update=for_update
            )
        if facts is None:
            raise _typed_error(
                "external_signing_session_facts_unavailable",
                "目前案件尚未具備可啟動的簽約 facts。",
            )
        return facts


def _reduce(command, facts):
    if _is_staff(command):
        return reduce_staff_completion_report(
            facts,
            matching_segment_id=command.matching_segment_id,
            expected_document_version_id=command.expected_document_version_id,
            expected_status_version=command.expected_status_version.value,
        )
    return reduce_client_completion_report(
        facts,
        expected_document_version_id=command.expected_document_version_id,
        expected_commitment_id=command.expected_commitment_id,
        expected_status_version=command.expected_status_version.value,
    )


def _require_command_session(command, facts):
    if command.case_no != facts.case_no or command.matching_plan_id != facts.matching_plan_id:
        raise _typed_error("external_signing_session_identity_stale", "回報目標已變更。")
    expected_subject = (
        facts.staff_target(command.matching_segment_id).staff_subject_reference
        if _is_staff(command)
        and facts.staff_target(command.matching_segment_id) is not None
        else facts.client_subject_reference
    )
    actual_subject = (
        command.reporter_binding.subject_reference
        if _is_verified(command)
        else command.attested_subject_reference
    )
    if actual_subject != expected_subject:
        raise _typed_error("external_signing_reporter_target_mismatch", "回報者不屬於此簽署目標。")


def _receipt(command, transition, report):
    staff = _is_staff(command)
    return ExternalSigningReportReceipt(
        command_type=(
            ExternalReportCommandType.RECORD_STAFF_REPORT
            if staff
            else ExternalReportCommandType.RECORD_CLIENT_REPORT
        ),
        report_id=report.report_id,
        session_id=command.session_id,
        scope=(ExternalCompletionReportScope.STAFF if staff else ExternalCompletionReportScope.CLIENT),
        matching_segment_id=command.matching_segment_id if staff else None,
        resulting_status_version=transition.resulting_status_version,
        resulting_state=transition.after_state,
        client_reminder_intent_created=transition.create_client_reminder_intent,
        final_pdf_recovery_task_created=transition.create_final_pdf_recovery_task,
    )


def _typed_error(code: str, message: str) -> ExternalSigningTypedError:
    return ExternalSigningTypedError(
        category="conflict", code=code, message=message, retryable=False
    )


def _is_staff(command) -> bool:
    return isinstance(
        command,
        (RecordExternalStaffSigningReport, RecordManualExternalStaffSigningReport),
    )


def _is_client(command) -> bool:
    return isinstance(
        command,
        (RecordExternalClientSigningReport, RecordManualExternalClientSigningReport),
    )


def _is_verified(command) -> bool:
    return isinstance(
        command, (RecordExternalStaffSigningReport, RecordExternalClientSigningReport)
    )


def _session_query(facts, *, persisted):
    return ExternalSigningSessionQuery(
        facts.session_id,
        facts.case_no,
        facts.state,
        facts.status_version,
        len(facts.staff_targets),
        len(facts.reported_staff_segment_ids),
        facts.client_reported,
        persisted,
    )


def _legacy_recovery_query(facts, evidence):
    targets = []
    reported = frozenset(facts.reported_staff_segment_ids)
    for target in facts.staff_targets:
        legacy = _find_legacy_evidence(
            evidence,
            ExternalCompletionReportScope.STAFF,
            target.matching_segment_id,
            required=False,
        )
        targets.append(
            LegacyManualRecoveryTargetQuery(
                ExternalCompletionReportScope.STAFF,
                target.matching_segment_id,
                target.staff_subject_reference,
                target.document_version_id,
                target.matching_segment_id in reported,
                None if legacy is None else legacy.legacy_document_version_id,
                None if legacy is None else legacy.signing_event_id,
                None if legacy is None else legacy.command_receipt_id,
                None if legacy is None else legacy.media_sha256,
            )
        )
    legacy_client = _find_legacy_evidence(
        evidence, ExternalCompletionReportScope.CLIENT, None, required=False
    )
    targets.append(
        LegacyManualRecoveryTargetQuery(
            ExternalCompletionReportScope.CLIENT,
            None,
            facts.client_subject_reference,
            facts.client_document_version_id,
            facts.client_reported,
            None if legacy_client is None else legacy_client.legacy_document_version_id,
            None if legacy_client is None else legacy_client.signing_event_id,
            None if legacy_client is None else legacy_client.command_receipt_id,
            None if legacy_client is None else legacy_client.media_sha256,
        )
    )
    return LegacyManualRecoveryQuery(
        facts.case_no,
        facts.session_id,
        facts.matching_plan_id,
        facts.document_set_fingerprint,
        facts.commitment_id,
        facts.state,
        facts.status_version,
        tuple(targets),
    )


def _build_recovery_snapshot(request, facts, evidence):
    legacy = _find_legacy_evidence(
        evidence, request.scope, request.matching_segment_id, required=True
    )
    if (
        legacy.legacy_document_version_id != request.legacy_document_version_id
        or legacy.signing_event_id != request.signing_event_id
        or legacy.command_receipt_id != request.command_receipt_id
        or legacy.matching_plan_id != facts.matching_plan_id
    ):
        raise _typed_error(
            "contract_legacy_manual_recovery_lineage_stale",
            "歷史簽回 identity 或目前配對方案已變更。",
        )
    if request.scope is ExternalCompletionReportScope.STAFF:
        target = facts.staff_target(request.matching_segment_id)
        if target is None:
            raise _typed_error(
                "contract_legacy_manual_recovery_target_not_found",
                "目前方案找不到指定月嫂簽署目標。",
            )
        if request.matching_segment_id in facts.reported_staff_segment_ids:
            raise _typed_error(
                "contract_legacy_manual_recovery_target_already_reported",
                "指定月嫂簽署目標已完成回報。",
            )
        subject = target.staff_subject_reference
        current_document_id = target.document_version_id
    else:
        if facts.client_reported:
            raise _typed_error(
                "contract_legacy_manual_recovery_target_already_reported",
                "客戶簽署目標已完成回報。",
            )
        if set(facts.reported_staff_segment_ids) != {
            item.matching_segment_id for item in facts.staff_targets
        } or facts.commitment_id is None:
            raise _typed_error(
                "contract_legacy_manual_recovery_client_out_of_order",
                "所有月嫂回報與 commitment 完成後才能修復客戶簽回。",
            )
        subject = facts.client_subject_reference
        current_document_id = facts.client_document_version_id
    payload = {
        "case_no": facts.case_no,
        "confirmation_method": request.confirmation_method.value,
        "current_commitment_id": facts.commitment_id,
        "current_document_set_sha256": facts.document_set_fingerprint,
        "current_document_version_id": current_document_id,
        "current_matching_plan_id": facts.matching_plan_id,
        "expected_status_version": facts.status_version,
        "kind": "contract_legacy_manual_recovery.v1",
        "legacy": legacy.canonical_payload,
        "matching_segment_id": request.matching_segment_id,
        "reason": request.reason,
        "scope": request.scope.value,
        "session_id": facts.session_id,
        "target_subject_reference": subject,
    }
    return LegacyManualRecoverySnapshot(
        fingerprint_payload(payload),
        facts.case_no,
        facts.session_id,
        request.scope,
        request.matching_segment_id,
        subject,
        facts.matching_plan_id,
        current_document_id,
        facts.document_set_fingerprint,
        facts.commitment_id,
        legacy,
        request.confirmation_method,
        request.reason,
    )


def _legacy_recovery_preview(snapshot, facts):
    return LegacyManualRecoveryPreview(
        snapshot.preview_fingerprint,
        snapshot.session_id,
        facts.status_version,
        snapshot.scope,
        snapshot.matching_segment_id,
        snapshot.current_document_version_id,
        snapshot.current_document_set_sha256,
        snapshot.current_commitment_id,
        snapshot.legacy.media_sha256,
        (),
    )


def _find_legacy_evidence(evidence, scope, segment_id, *, required):
    matches = tuple(
        item
        for item in evidence
        if item.scope is scope and item.matching_segment_id == segment_id
    )
    if len(matches) > 1:
        raise _typed_error(
            "contract_legacy_manual_recovery_evidence_ambiguous",
            "歷史簽回證據不唯一。",
        )
    if not matches:
        if required:
            raise _typed_error(
                "contract_legacy_manual_recovery_evidence_missing",
                "找不到完整歷史簽回證據。",
            )
        return None
    return matches[0]


def _recovery_report_command(command, snapshot):
    attestation = ManualAttestationEvidence(
        snapshot.confirmation_method,
        snapshot.reason,
        f"legacy-contract-media:{snapshot.legacy.legacy_document_version_id}",
        snapshot.legacy.media_sha256,
    )
    common = {
        "session_id": snapshot.session_id,
        "case_no": snapshot.case_no,
        "matching_plan_id": snapshot.current_matching_plan_id,
        "expected_document_version_id": snapshot.current_document_version_id,
        "attested_subject_reference": snapshot.target_subject_reference,
        "attestation": attestation,
        "source_event_identity": snapshot.legacy.source_event_identity,
        "source_payload_sha256": snapshot.legacy.canonical_tuple_sha256,
        "occurred_at": command.occurred_at,
        "expected_status_version": command.expected_status_version,
        "actor": command.actor,
        "idempotency_key": command.idempotency_key,
        "correlation_id": command.correlation_id,
        "recovery": snapshot,
    }
    if snapshot.scope is ExternalCompletionReportScope.STAFF:
        return RecordManualExternalStaffSigningReport(
            matching_segment_id=snapshot.matching_segment_id,
            **common,
        )
    if snapshot.current_commitment_id is None:
        raise _typed_error(
            "contract_legacy_manual_recovery_commitment_missing",
            "客戶 recovery 缺少 current commitment。",
        )
    return RecordManualExternalClientSigningReport(
        expected_commitment_id=snapshot.current_commitment_id,
        **common,
    )


def _require_recovery_replay_request_matches(command, snapshot):
    request = command.preview
    matches = (
        command.preview_fingerprint == snapshot.preview_fingerprint
        and request.case_no == snapshot.case_no
        and request.scope is snapshot.scope
        and request.matching_segment_id == snapshot.matching_segment_id
        and request.legacy_document_version_id
        == snapshot.legacy.legacy_document_version_id
        and request.signing_event_id == snapshot.legacy.signing_event_id
        and request.command_receipt_id == snapshot.legacy.command_receipt_id
        and request.confirmation_method is snapshot.confirmation_method
        and request.reason == snapshot.reason
    )
    if not matches:
        raise ExternalSigningTypedError(
            category="idempotency_mismatch",
            code="contract_legacy_manual_recovery_replay_conflict",
            message="相同 recovery 命令識別對應不同內容。",
            retryable=False,
            current_version=None,
        )


__all__ = [
    "ExternalSigningSessionQuery",
    "ExternalSigningWorkflow",
    "ExternalSigningWorkflowRepository",
    "ExternalStaffCompletionPort",
    "FinalPdfReadinessPreview",
    "LegacyManualRecoveryPreview",
    "LegacyManualRecoveryQuery",
    "LegacyManualRecoveryTargetQuery",
    "PersistedExternalReport",
    "StaffCompletionPrerequisites",
]
