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
    ExternalCompletionReportScope,
    ExternalReportCommandType,
    ExternalSigningReportCommand,
    ExternalSigningReportReceipt,
    ExternalSigningTypedError,
    RecordExternalClientSigningReport,
    RecordExternalStaffSigningReport,
    RecordManualExternalClientSigningReport,
    RecordManualExternalStaffSigningReport,
    StoredExternalSigningReportReceipt,
    VerifiedReporterBindingSnapshot,
    external_report_command_fingerprint,
    reconcile_external_report_replay,
)


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
                StoredExternalSigningReportReceipt(fingerprint, receipt),
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


__all__ = [
    "ExternalSigningSessionQuery",
    "ExternalSigningWorkflow",
    "ExternalSigningWorkflowRepository",
    "ExternalStaffCompletionPort",
    "FinalPdfReadinessPreview",
    "PersistedExternalReport",
    "StaffCompletionPrerequisites",
]
