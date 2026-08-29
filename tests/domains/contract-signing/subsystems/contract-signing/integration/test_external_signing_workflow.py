"""
File: test_external_signing_workflow.py
Description: 驗證外部簽約回報 Query、Preview、Apply、重播與 borrowed-UoW 編排。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    StaffSigningReportTarget,
    derive_external_signing_session_id,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.contract_signing.external_signing_contracts import (
    ExternalReporterSubjectType,
    ExternalSigningTypedError,
    RecordExternalClientSigningReport,
    RecordExternalStaffSigningReport,
    ManualAttestationEvidence,
    ManualAttestationMethod,
    RecordManualExternalStaffSigningReport,
    RecordManualExternalClientSigningReport,
    VerifiedReporterBindingSnapshot,
)
from subsystems.contract_signing.external_signing_workflow import (
    ExternalSigningWorkflow,
    StaffCompletionPrerequisites,
)


def test_query_and_final_preview_are_zero_write_and_public_safe() -> None:
    repository = FakeRepository(_facts())
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())

    query = workflow.query(_facts().session_id)
    preview = workflow.preview_final_pdf_readiness(_facts().session_id)

    assert query.required_staff_report_count == 2
    assert preview.blockers
    assert repository.writes == []
    assert repository.loads == [False, False]
    assert not hasattr(query, "document_set_fingerprint")
    assert not hasattr(preview, "preview_fingerprint")


def test_staff_apply_locks_fresh_facts_and_commits_once() -> None:
    repository = FakeRepository(_facts())
    uows = FakeUowFactory()
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), uows)

    receipt = workflow.apply_staff_report(_staff_command())

    assert receipt.resulting_state is ExternalSigningState.STAFF_REPORTING
    assert repository.loads == [True]
    assert repository.binding_locks == [True]
    assert repository.writes == ["report", "session", "receipt"]
    assert uows.instances[0].commits == 1


def test_last_staff_report_uses_borrowed_completion_port_in_same_uow() -> None:
    facts = replace(_facts(), reported_staff_segment_ids=(11,), status_version=1)
    repository = FakeRepository(facts)
    completion = FakeCompletionPort()
    uows = FakeUowFactory()
    workflow = ExternalSigningWorkflow(repository, completion, uows)

    receipt = workflow.apply_staff_report(
        _staff_command(segment_id=12, document_id=102, version=1)
    )

    assert receipt.resulting_state is ExternalSigningState.STAFF_REPORTS_COMPLETE
    assert receipt.client_reminder_intent_created is True
    assert completion.calls == [(facts.session_id, 2)]
    assert repository.session_prerequisites == StaffCompletionPrerequisites(44, 77)
    assert uows.instances[0].commits == 1


def test_client_report_before_all_staff_is_rejected_without_partial_write() -> None:
    repository = FakeRepository(_facts())
    uows = FakeUowFactory()
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), uows)

    with pytest.raises(Exception) as captured:
        workflow.apply_client_report(_client_command(version=0))

    assert "out_of_order" in str(captured.value)
    assert repository.writes == []
    assert uows.instances[0].commits == 0


def test_client_report_only_enters_final_pdf_pending_and_creates_recovery() -> None:
    facts = replace(
        _facts(),
        reported_staff_segment_ids=(11, 12),
        commitment_id=44,
        state=ExternalSigningState.STAFF_REPORTS_COMPLETE,
        status_version=2,
    )
    repository = FakeRepository(facts)
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())

    receipt = workflow.apply_client_report(_client_command(version=2))

    assert receipt.resulting_state is ExternalSigningState.CLIENT_REPORTED_FINAL_PDF_PENDING
    assert receipt.final_pdf_recovery_task_created is True
    assert repository.writes == ["report", "recovery", "session", "receipt"]
    assert "contract_completion" not in repository.writes


def test_same_key_same_payload_replays_without_domain_writes() -> None:
    repository = FakeRepository(_facts())
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())
    command = _staff_command()
    original = workflow.apply_staff_report(command)
    repository.writes.clear()

    replay = workflow.apply_staff_report(command)

    assert replay.report_id == original.report_id
    assert replay.replayed is True
    assert repository.writes == []


def test_same_key_different_payload_is_typed_conflict() -> None:
    repository = FakeRepository(_facts())
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())
    workflow.apply_staff_report(_staff_command())

    with pytest.raises(ExternalSigningTypedError) as captured:
        workflow.apply_staff_report(_staff_command(payload="f" * 64))

    assert captured.value.category == "idempotency_mismatch"


def test_query_case_derives_zero_write_virtual_session() -> None:
    virtual = _virtual_facts()
    repository = FakeRepository(None, virtual=virtual)
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())

    result = workflow.query_case("CASE-001")

    assert result.session_id == virtual.session_id
    assert result.persisted is False
    assert repository.writes == []


def test_first_staff_report_lazy_activates_in_outer_uow() -> None:
    virtual = _virtual_facts()
    repository = FakeRepository(None, virtual=virtual)
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())
    command = replace(_staff_command(), session_id=virtual.session_id)

    workflow.apply_staff_report(command)

    assert repository.writes == ["activate", "report", "session", "receipt"]


def test_client_report_cannot_lazy_activate_session() -> None:
    repository = FakeRepository(None, virtual=_virtual_facts())
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())

    with pytest.raises(ExternalSigningTypedError) as captured:
        workflow.apply_client_report(
            replace(_client_command(version=0), session_id=_virtual_facts().session_id)
        )

    assert captured.value.code == "external_signing_session_not_activated"
    assert repository.writes == []


def test_manual_staff_attestation_skips_line_binding_and_lazy_activates() -> None:
    virtual = _virtual_facts()
    repository = FakeRepository(None, virtual=virtual)
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())

    workflow.apply_manual_staff_report(_manual_staff_command(virtual.session_id))

    assert repository.binding_locks == []
    assert repository.writes == ["activate", "report", "session", "receipt"]


def test_manual_client_attestation_uses_existing_staff_complete_session() -> None:
    facts = replace(
        _facts(), reported_staff_segment_ids=(11, 12), commitment_id=44,
        state=ExternalSigningState.STAFF_REPORTS_COMPLETE, status_version=2,
    )
    repository = FakeRepository(facts)
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())

    receipt = workflow.apply_manual_client_report(_manual_client_command(facts.session_id))

    assert receipt.resulting_state is ExternalSigningState.CLIENT_REPORTED_FINAL_PDF_PENDING
    assert repository.binding_locks == []
    assert repository.writes == ["report", "recovery", "session", "receipt"]


class FakeRepository:
    def __init__(self, facts: ExternalSigningSessionFacts | None, *, virtual=None) -> None:
        self.facts = facts
        self.virtual = virtual
        self.loads: list[bool] = []
        self.binding_locks: list[bool] = []
        self.writes: list[str] = []
        self.receipts = {}
        self.session_prerequisites = None
        self._report_number = 0

    def load_session(self, session_id, *, for_update):
        self.loads.append(for_update)
        return self.facts if self.facts is not None and session_id == self.facts.session_id else None

    def load_active_session_by_case(self, case_no, *, for_update):
        return self.facts if self.facts is not None and self.facts.case_no == case_no else None

    def derive_current_session(self, case_no, *, for_update):
        return self.virtual if self.virtual is not None and self.virtual.case_no == case_no else None

    def activate_session(self, facts, *, actor_id):
        self.writes.append("activate")
        self.facts = facts

    def find_receipt(self, key, *, for_update):
        return self.receipts.get(key.value)

    def find_source_receipt(self, source_event_identity, *, for_update):
        return None

    def reporter_binding_is_current(self, snapshot, *, for_update):
        self.binding_locks.append(for_update)
        return True

    def append_report(self, command, transition, fingerprint, commitment_id):
        from subsystems.contract_signing.external_signing_workflow import PersistedExternalReport

        self.writes.append("report")
        self._report_number += 1
        return PersistedExternalReport(
            f"cer_{self._report_number:032x}", self._report_number
        )

    def create_final_pdf_recovery(self, command, report, fingerprint):
        self.writes.append("recovery")

    def advance_session(self, command, transition, prerequisites):
        self.writes.append("session")
        self.session_prerequisites = prerequisites

    def save_receipt(self, key, stored, command, report):
        self.writes.append("receipt")
        self.receipts[key.value] = stored


class FakeCompletionPort:
    def __init__(self) -> None:
        self.calls = []

    def establish_prerequisites(self, command, facts, resulting_status_version):
        self.calls.append((facts.session_id, resulting_status_version))
        return StaffCompletionPrerequisites(44, 77)


class FakeUow:
    def __init__(self) -> None:
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class FakeUowFactory:
    def __init__(self) -> None:
        self.instances = []

    def __call__(self):
        instance = FakeUow()
        self.instances.append(instance)
        return instance


def _facts() -> ExternalSigningSessionFacts:
    return ExternalSigningSessionFacts(
        session_id="ces_1234567890abcdef1234567890abcdef",
        case_no="CASE-001",
        matching_plan_id=9,
        document_set_fingerprint="a" * 64,
        staff_targets=(
            StaffSigningReportTarget(11, "501", 101),
            StaffSigningReportTarget(12, "502", 102),
        ),
        reported_staff_segment_ids=(),
        client_subject_reference="301",
        client_document_version_id=201,
        commitment_id=None,
        client_reported=False,
        state=ExternalSigningState.STAFF_REPORTING,
        status_version=0,
    )


def _virtual_facts() -> ExternalSigningSessionFacts:
    facts = _facts()
    return replace(
        facts,
        session_id=derive_external_signing_session_id(
            facts.case_no, facts.matching_plan_id, facts.document_set_fingerprint
        ),
    )


def _binding(subject_type, reference, user):
    return VerifiedReporterBindingSnapshot(user, subject_type, reference, ExpectedVersion(3))


def _staff_command(*, segment_id=11, document_id=101, version=0, payload="b" * 64):
    return RecordExternalStaffSigningReport(
        _facts().session_id, "CASE-001", 9, segment_id, document_id,
        _binding(ExternalReporterSubjectType.STAFF, "501" if segment_id == 11 else "502", "U-staff"),
        "line-event-staff-001", payload, datetime(2026, 8, 26, 10, tzinfo=timezone.utc),
        ExpectedVersion(version), ActorContext("line_user_id:U-staff"),
        IdempotencyKey("external-report:staff:001"), CorrelationId("corr-staff-001"),
    )


def _client_command(*, version=2):
    return RecordExternalClientSigningReport(
        _facts().session_id, "CASE-001", 9, 201, 44,
        _binding(ExternalReporterSubjectType.CUSTOMER, "301", "U-client"),
        "line-event-client-001", "c" * 64, datetime(2026, 8, 26, 11, tzinfo=timezone.utc),
        ExpectedVersion(version), ActorContext("line_user_id:U-client"),
        IdempotencyKey("external-report:client:001"), CorrelationId("corr-client-001"),
    )


def _manual_staff_command(session_id):
    return RecordManualExternalStaffSigningReport(
        session_id, "CASE-001", 9, 11, 101, "501",
        ManualAttestationEvidence(
            ManualAttestationMethod.PHONE,
            "administrator confirmed by phone",
            "evidence:manual:001",
            "e" * 64,
        ),
        "manual-event-staff-001", "d" * 64,
        datetime(2026, 8, 26, 10, tzinfo=timezone.utc), ExpectedVersion(0),
        ActorContext("admin:17"), IdempotencyKey("external-report:manual:staff:001"),
        CorrelationId("corr-manual-staff-001"),
    )


def _manual_client_command(session_id):
    return RecordManualExternalClientSigningReport(
        session_id, "CASE-001", 9, 201, 44, "301",
        ManualAttestationEvidence(
            ManualAttestationMethod.IN_PERSON, "administrator witnessed signing",
            "evidence:manual:client:001", "f" * 64,
        ),
        "manual-event-client-001", "c" * 64,
        datetime(2026, 8, 26, 11, tzinfo=timezone.utc), ExpectedVersion(2),
        ActorContext("admin:17"), IdempotencyKey("external-report:manual:client:001"),
        CorrelationId("corr-manual-client-001"),
    )
