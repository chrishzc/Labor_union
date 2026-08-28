"""
File: test_contract_legacy_manual_recovery.py
Description: 驗證歷史人工簽回 recovery 的 fresh Q/P/A、單一 UoW、重播與 stale 防線。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    StaffSigningReportTarget,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.contract_signing.external_signing_contracts import (
    ApplyLegacyManualRecoveryReport,
    ExternalCompletionReportScope,
    ExternalSigningTypedError,
    LegacyManualSigningEvidence,
    ManualAttestationMethod,
    PreviewLegacyManualRecoveryReport,
)
from subsystems.contract_signing.external_signing_workflow import (
    ExternalSigningWorkflow,
    PersistedExternalReport,
    StaffCompletionPrerequisites,
)


def test_recovery_query_and_preview_are_fresh_zero_write() -> None:
    repository = FakeRepository(_facts(), (_legacy_staff(), _legacy_client()))
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())

    query = workflow.query_legacy_manual_recovery("CASE-001")
    preview = workflow.preview_legacy_manual_recovery(_preview_staff())

    assert query.session_id == _facts().session_id
    assert [target.reported for target in query.targets] == [False, False, False]
    assert preview.can_apply is True
    assert preview.legacy_media_sha256 == "e" * 64
    assert preview.current_document_set_sha256 == "a" * 64
    assert repository.writes == []
    assert repository.legacy_locks == [False, False]


def test_first_staff_recovery_apply_activates_and_commits_once_with_recovery_snapshot() -> None:
    virtual = replace(_facts(), session_id="ces_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    repository = FakeRepository(None, (_legacy_staff(), _legacy_client()), virtual=virtual)
    uows = FakeUowFactory()
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), uows)
    preview = workflow.preview_legacy_manual_recovery(_preview_staff())

    receipt = workflow.apply_legacy_manual_recovery(_apply_staff(preview.preview_fingerprint.value))

    assert receipt.resulting_state is ExternalSigningState.STAFF_REPORTING
    assert repository.writes == ["activate", "report", "session", "receipt"]
    assert repository.saved_recovery is not None
    assert repository.saved_recovery.kind == "contract_legacy_manual_recovery.v1"
    assert repository.saved_recovery.preview_fingerprint == preview.preview_fingerprint
    assert repository.saved_recovery.legacy_media_sha256 == "e" * 64
    assert uows.instances[-1].commits == 1


def test_recovery_apply_rejects_stale_preview_without_writes() -> None:
    repository = FakeRepository(_facts(), (_legacy_staff(),))
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())
    preview = workflow.preview_legacy_manual_recovery(_preview_staff())
    repository.facts = replace(repository.facts, document_set_fingerprint="f" * 64)

    with pytest.raises(ExternalSigningTypedError) as captured:
        workflow.apply_legacy_manual_recovery(_apply_staff(preview.preview_fingerprint.value))

    assert captured.value.code == "contract_legacy_manual_recovery_preview_stale"
    assert repository.writes == []


def test_recovery_same_key_exact_replay_and_mismatch() -> None:
    repository = FakeRepository(_facts(), (_legacy_staff(),))
    workflow = ExternalSigningWorkflow(repository, FakeCompletionPort(), FakeUowFactory())
    preview = workflow.preview_legacy_manual_recovery(_preview_staff())
    command = _apply_staff(preview.preview_fingerprint.value)
    first = workflow.apply_legacy_manual_recovery(command)
    repository.writes.clear()

    replay = workflow.apply_legacy_manual_recovery(
        replace(command, occurred_at=command.occurred_at + timedelta(seconds=5))
    )
    assert replay.report_id == first.report_id
    assert replay.replayed is True
    assert repository.writes == []

    with pytest.raises(ExternalSigningTypedError) as captured:
        workflow.apply_legacy_manual_recovery(
            replace(command, preview=replace(command.preview, reason="不同理由"))
        )
    assert captured.value.category == "idempotency_mismatch"


class FakeRepository:
    def __init__(self, facts, legacy, *, virtual=None):
        self.facts = facts
        self.virtual = virtual
        self.legacy = tuple(legacy)
        self.writes = []
        self.legacy_locks = []
        self.receipts = {}
        self.saved_recovery = None
        self._report_number = 0

    def load_session(self, session_id, *, for_update):
        return self.facts if self.facts is not None and self.facts.session_id == session_id else None

    def load_active_session_by_case(self, case_no, *, for_update):
        return self.facts if self.facts is not None and self.facts.case_no == case_no else None

    def derive_current_session(self, case_no, *, for_update):
        candidate = self.virtual or self.facts
        return candidate if candidate is not None and candidate.case_no == case_no else None

    def load_legacy_manual_signing_evidence(self, case_no, *, for_update):
        self.legacy_locks.append(for_update)
        return tuple(item for item in self.legacy if item.case_no == case_no)

    def activate_session(self, facts, *, actor_id):
        self.writes.append("activate")
        self.facts = facts

    def find_receipt(self, key, *, for_update):
        return self.receipts.get(key.value)

    def find_source_receipt(self, source_event_identity, *, for_update):
        expected = f"legacy-contract-signing-event:{_legacy_staff().signing_event_id}"
        return next(iter(self.receipts.values()), None) if source_event_identity == expected else None

    def reporter_binding_is_current(self, snapshot, *, for_update):
        return True

    def append_report(self, command, transition, fingerprint, commitment_id):
        self.writes.append("report")
        self._report_number += 1
        return PersistedExternalReport(f"cer_{self._report_number:032x}", self._report_number)

    def create_final_pdf_recovery(self, command, report, fingerprint):
        self.writes.append("recovery")

    def advance_session(self, command, transition, prerequisites):
        self.writes.append("session")
        self.facts = replace(
            self.facts,
            reported_staff_segment_ids=(11,),
            status_version=transition.resulting_status_version,
            state=transition.after_state,
        )

    def save_receipt(self, key, stored, command, report):
        self.writes.append("receipt")
        self.receipts[key.value] = stored
        self.saved_recovery = command.recovery


class FakeCompletionPort:
    def establish_prerequisites(self, command, facts, resulting_status_version):
        return StaffCompletionPrerequisites(44, 77)


class FakeUow:
    def __init__(self):
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class FakeUowFactory:
    def __init__(self):
        self.instances = []

    def __call__(self):
        instance = FakeUow()
        self.instances.append(instance)
        return instance


def _facts():
    return ExternalSigningSessionFacts(
        "ces_1234567890abcdef1234567890abcdef",
        "CASE-001",
        9,
        "a" * 64,
        (StaffSigningReportTarget(11, "501", 101), StaffSigningReportTarget(12, "502", 102)),
        (),
        "301",
        201,
        None,
        False,
        ExternalSigningState.STAFF_REPORTING,
        0,
    )


def _legacy_staff():
    return LegacyManualSigningEvidence(
        case_no="CASE-001",
        scope=ExternalCompletionReportScope.STAFF,
        matching_plan_id=9,
        matching_segment_id=11,
        legacy_document_version_id=81,
        source_document_version_id=80,
        signing_event_id=82,
        command_receipt_id=83,
        event_key="manual-key-1",
        command_kind="record_manual_staff_contract_attestation",
        media_sha256="e" * 64,
        actor_ref="operator-1",
        correlation_id="legacy-corr-1",
    )


def _legacy_client():
    return replace(
        _legacy_staff(),
        scope=ExternalCompletionReportScope.CLIENT,
        matching_segment_id=None,
        legacy_document_version_id=91,
        source_document_version_id=90,
        signing_event_id=92,
        command_receipt_id=93,
        event_key="manual-key-2",
        command_kind="record_manual_client_contract_attestation",
    )


def _preview_staff():
    evidence = _legacy_staff()
    return PreviewLegacyManualRecoveryReport(
        case_no="CASE-001",
        scope=ExternalCompletionReportScope.STAFF,
        matching_segment_id=11,
        legacy_document_version_id=evidence.legacy_document_version_id,
        signing_event_id=evidence.signing_event_id,
        command_receipt_id=evidence.command_receipt_id,
        confirmation_method=ManualAttestationMethod.PAPER,
        reason="依受控歷史紙本建立修復血緣",
    )


def _apply_staff(preview_fingerprint):
    request = _preview_staff()
    return ApplyLegacyManualRecoveryReport(
        preview=request,
        preview_fingerprint=PreviewFingerprint(preview_fingerprint),
        expected_status_version=ExpectedVersion(0),
        occurred_at=datetime(2026, 8, 28, 10, tzinfo=timezone.utc),
        actor=ActorContext("admin:17"),
        idempotency_key=IdempotencyKey("contract-legacy-recovery:staff:001"),
        correlation_id=CorrelationId("corr-recovery-staff-001"),
    )
