"""
File: test_final_document_workflow.py
Description: 驗證最終 PDF Preview、opaque token、單一交易、重播與 readback 門禁。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    StaffSigningReportTarget,
)
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.contract_signing.final_document_preview_token import (
    HmacFinalDocumentPreviewTokenCodec,
)
from subsystems.contract_signing.final_document_workflow import (
    ApplyFinalSignedContractUpload,
    FinalContractDocumentReadback,
    FinalDocumentWorkflowError,
    FinalSignedContractWorkflow,
    PreviewFinalSignedContractUpload,
)
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileCandidate,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePreview,
    ControlledFilePurpose,
    ControlledFileReadback,
)


NOW = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)


def test_preview_is_zero_write_and_hides_internal_fingerprints() -> None:
    workflow, repository, controlled, orders, _ = _workflow()

    preview = workflow.preview(_preview_command())

    assert preview.preview_token.startswith("cp_")
    assert preview.blockers == ()
    assert preview.mime_type == "application/pdf"
    assert repository.writes == []
    projection = repr(preview)
    assert "a" * 64 not in projection
    assert "b" * 64 not in projection
    assert controlled.applies == []
    assert orders.applies == []


def test_apply_uses_one_outer_uow_and_required_lock_order() -> None:
    workflow, repository, controlled, orders, uows = _workflow()
    preview = workflow.preview(_preview_command())
    repository.events.clear()

    receipt = workflow.apply(_apply_command(preview.preview_token))

    assert receipt.resulting_state is ExternalSigningState.COMPLETED
    assert receipt.document.file_id == "cf_" + "c" * 32
    assert uows.instances[0].commits == 1
    assert repository.events == [
        "session:lock",
        "orders:preview",
        "file:preview",
        "orders:apply",
        "file:apply",
        "final:register",
        "session:complete",
        "receipt:save",
    ]
    assert len(controlled.applies) == 1
    assert len(orders.applies) == 1


def test_stale_token_rolls_back_before_domain_writes() -> None:
    workflow, repository, controlled, orders, uows = _workflow()
    preview = workflow.preview(_preview_command())
    controlled.digest = "d" * 64
    repository.writes.clear()

    with pytest.raises(FinalDocumentWorkflowError) as captured:
        workflow.apply(_apply_command(preview.preview_token))

    assert captured.value.code == "final_document_preview_stale"
    assert repository.writes == []
    assert controlled.applies == []
    assert orders.applies == []
    assert uows.instances[0].commits == 0
    assert uows.instances[0].rollbacks == 1


def test_same_command_replays_without_second_final_write() -> None:
    workflow, repository, controlled, orders, _ = _workflow()
    preview = workflow.preview(_preview_command())
    command = _apply_command(preview.preview_token)
    first = workflow.apply(command)
    repository.writes.clear()
    controlled.applies.clear()
    orders.applies.clear()

    replay = workflow.apply(command)

    assert replay.receipt_id == first.receipt_id
    assert replay.replayed is True
    assert repository.writes == []
    assert controlled.applies == []
    assert orders.applies == []


def test_readback_is_safe_and_missing_is_typed() -> None:
    workflow, repository, _, _, _ = _workflow()

    with pytest.raises(FinalDocumentWorkflowError) as captured:
        workflow.readback("CASE-001")
    repository.document = _document()

    assert captured.value.category == "not_found"
    assert workflow.readback("CASE-001") == _document()
    assert "sha256" not in repr(workflow.readback("CASE-001")).casefold()


class FakeRepository:
    def __init__(self, events) -> None:
        self.events = events
        self.writes = []
        self.receipts = {}
        self.document = None

    def load_final_session(self, case_no, session_id, *, for_update):
        self.events.append("session:lock" if for_update else "session:read")
        facts = _session()
        return facts if (case_no, session_id) == (facts.case_no, facts.session_id) else None

    def find_final_receipt(self, key, *, for_update):
        return self.receipts.get(key.value)

    def register_final_document(self, session, controlled_file, **_):
        self.events.append("final:register")
        self.writes.append("document")
        self.document = _document()
        return self.document

    def complete_session_and_recovery(self, *_args, **_kwargs):
        self.events.append("session:complete")
        self.writes.append("session")

    def save_final_receipt(self, key, stored, *_args, **_kwargs):
        self.events.append("receipt:save")
        self.writes.append("receipt")
        self.receipts[key.value] = stored

    def get_final_document(self, case_no):
        return self.document if case_no == "CASE-001" else None


class FakeControlledFiles:
    def __init__(self, events) -> None:
        self.events = events
        self.applies = []
        self.digest = "b" * 64

    def preview(self, intent):
        self.events.append("file:preview")
        candidate = ControlledFileCandidate(
            staging_id=intent.staging_id,
            staging_version=2,
            owner=intent.owner,
            purpose=intent.purpose,
            subject_reference=intent.subject_reference,
            object_key=intent.object_key,
            logical_folder=intent.logical_folder,
            filename="final-contract.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            sha256_digest=self.digest,
            expires_at=NOW + timedelta(hours=1),
        )
        return ControlledFilePreview(
            candidate,
            PreviewFingerprint(self.digest),
            ExpectedVersion(2),
            (),
        )

    def apply_borrowed(self, command):
        self.events.append("file:apply")
        self.applies.append(command)
        readback = ControlledFileReadback(
            file_id="cf_" + "c" * 32,
            owner=ControlledFileOwner.CONTRACT_SIGNING,
            purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
            subject_reference="CASE-001",
            filename="final-contract.pdf",
            logical_folder="contracts",
            version=1,
            sha256_digest=self.digest,
            mime_type="application/pdf",
            size_bytes=1024,
            status="active",
            applied_at=NOW,
        )
        return ControlledFileApplyReceipt(
            "cfr_" + "d" * 32, ControlledFileApplyOutcome.CREATED, readback
        )


class FakeOrders:
    def __init__(self, events) -> None:
        self.events = events
        self.applies = []

    def preview(self, case_no, _intent):
        self.events.append("orders:preview")
        return SimpleNamespace(
            candidate=SimpleNamespace(expected_order_version=7),
            client_finance_impact=SimpleNamespace(expected_account_version=4),
            fingerprint=PreviewFingerprint("e" * 64),
        )

    def apply_borrowed(self, command):
        self.events.append("orders:apply")
        self.applies.append(command)
        return SimpleNamespace(contract_identity="CONTRACT-001")


class FakeUow:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, error_type, *_):
        if error_type is not None:
            self.rollbacks += 1
        return False

    def commit(self):
        self.commits += 1


class FakeUowFactory:
    def __init__(self) -> None:
        self.instances = []

    def __call__(self):
        unit = FakeUow()
        self.instances.append(unit)
        return unit


def _workflow():
    events = []
    repository = FakeRepository(events)
    controlled = FakeControlledFiles(events)
    orders = FakeOrders(events)
    uows = FakeUowFactory()
    workflow = FinalSignedContractWorkflow(
        repository,
        controlled,
        orders,
        uows,
        FixedBusinessClock(NOW),
        HmacFinalDocumentPreviewTokenCodec("s" * 32),
    )
    return workflow, repository, controlled, orders, uows


def _session():
    return ExternalSigningSessionFacts(
        session_id="ces_" + "1" * 32,
        case_no="CASE-001",
        matching_plan_id=9,
        document_set_fingerprint="a" * 64,
        staff_targets=(StaffSigningReportTarget(11, "501", 101),),
        reported_staff_segment_ids=(11,),
        client_subject_reference="301",
        client_document_version_id=201,
        commitment_id=44,
        client_reported=True,
        state=ExternalSigningState.CLIENT_REPORTED_FINAL_PDF_PENDING,
        status_version=3,
    )


def _intent():
    return ControlledFileIntent(
        staging_id="cfs_" + "2" * 32,
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
        subject_reference="CASE-001",
        object_key="final-contract",
        logical_folder="contracts",
    )


def _preview_command():
    return PreviewFinalSignedContractUpload(
        _session().session_id,
        "CASE-001",
        ExpectedVersion(3),
        _intent(),
    )


def _apply_command(token):
    return ApplyFinalSignedContractUpload(
        preview=_preview_command(),
        expected_staging_version=ExpectedVersion(2),
        preview_token=token,
        idempotency_key=IdempotencyKey("contract-final:case-001"),
        actor=ActorContext("admin:1"),
        reason="verified final signed PDF",
        correlation_id=CorrelationId("corr-final-001"),
    )


def _document():
    return FinalContractDocumentReadback(
        final_document_id="cfd_" + "3" * 32,
        case_no="CASE-001",
        file_id="cf_" + "c" * 32,
        version=1,
        filename="final-contract.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        status="active",
        applied_at=NOW,
    )
