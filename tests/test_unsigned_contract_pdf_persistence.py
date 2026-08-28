"""
File: test_unsigned_contract_pdf_persistence.py
Description: 驗證未簽 PDF render、controlled-file stage/preview/apply 與文件 lineage 的單一 Apply 交易。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.contract_signing.unsigned_contract_pdf import (
    PreparedUnsignedContractPdf,
    UnsignedContractPdfError,
)
from subsystems.contract_signing.unsigned_contract_pdf_persistence import (
    PrepareAndPersistUnsignedContractPdf,
    UnsignedContractPdfPersistenceSource,
    UnsignedContractPdfPersistenceWorkflow,
)
from subsystems.controlled_files.contracts import ControlledFileStagingResult
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileCandidate,
    ControlledFileOwner,
    ControlledFilePreview,
    ControlledFilePurpose,
    ControlledFileReadback,
)


_NOW = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
_PDF = b"%PDF-1.7\nunsigned\n%%EOF\n"


class _Application:
    def __init__(self, events):
        self.events = events

    def prepare(self, command):
        self.events.append("render")
        return PreparedUnsignedContractPdf(
            case_no=command.case_no,
            source_document_version_id=command.document_version_id,
            content=_PDF,
            mime_type="application/pdf",
            filename="unsigned.pdf",
            renderer_identity="libreoffice-headless-v1",
        )


class _ControlledFiles:
    def __init__(self, events):
        self.events = events
        self.stage_commands = []
        self.apply_commands = []

    def stage(self, command):
        self.events.append("stage")
        self.stage_commands.append(command)
        return ControlledFileStagingResult(
            staging_id="cfs_" + "a" * 32,
            filename=command.filename,
            mime_type=command.mime_type,
            size_bytes=len(command.content),
            sha256_digest="b" * 64,
            expires_at=_NOW + timedelta(hours=1),
            replayed=False,
        )

    def preview(self, intent):
        self.events.append("preview")
        candidate = ControlledFileCandidate(
            staging_id=intent.staging_id,
            staging_version=1,
            owner=intent.owner,
            purpose=intent.purpose,
            subject_reference=intent.subject_reference,
            object_key=intent.object_key,
            logical_folder=intent.logical_folder,
            filename="unsigned.pdf",
            mime_type="application/pdf",
            size_bytes=len(_PDF),
            sha256_digest="b" * 64,
            expires_at=_NOW + timedelta(hours=1),
        )
        return ControlledFilePreview(
            candidate,
            PreviewFingerprint("c" * 64),
            ExpectedVersion(1),
            (),
        )

    def apply_borrowed(self, command):
        self.events.append("file:apply")
        self.apply_commands.append(command)
        readback = ControlledFileReadback(
            file_id="cf_" + "d" * 32,
            owner=ControlledFileOwner.CONTRACT_SIGNING,
            purpose=ControlledFilePurpose.UNSIGNED_CONTRACT,
            subject_reference="CASE-1",
            filename="unsigned.pdf",
            logical_folder="contracts/unsigned",
            version=1,
            sha256_digest="b" * 64,
            mime_type="application/pdf",
            size_bytes=len(_PDF),
            status="active",
            applied_at=_NOW,
        )
        return ControlledFileApplyReceipt(
            "cfr_" + "e" * 32,
            ControlledFileApplyOutcome.CREATED,
            readback,
        )


class _Repository:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def lock_source_for_persistence(self, case_no, source_document_version_id):
        self.events.append("source:lock")
        return UnsignedContractPdfPersistenceSource(
            case_no=case_no,
            document_version_id=source_document_version_id,
            document_scope="staff_segment",
            matching_plan_id=9,
            matching_segment_id=12,
            document_target_key="staff-segment:12",
            template_key="staff-contract-v1",
            template_sha256="a" * 64,
            mapping_sha256="b" * 64,
            facts_snapshot_sha256="c" * 64,
            version_number=1,
            is_current=True,
        )

    def register_persisted_pdf(self, **kwargs):
        self.events.append("document:register")
        self.calls.append(kwargs)
        return 52


class _UnitOfWork:
    def __init__(self, events):
        self.events = events
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        self.events.append("uow:enter")
        return self

    def __exit__(self, error_type, *_):
        if error_type is not None:
            self.rollbacks += 1
            self.events.append("uow:rollback")
        return False

    def commit(self):
        self.commits += 1
        self.events.append("uow:commit")

    def rollback(self):
        self.rollbacks += 1


def _command():
    return PrepareAndPersistUnsignedContractPdf(
        case_no="CASE-1",
        source_document_version_id=41,
        actor=ActorContext("admin:7"),
        idempotency_key=IdempotencyKey("unsigned-pdf-case-1-v41"),
        correlation_id=CorrelationId("corr-1"),
    )


def _workflow():
    events = []
    controlled = _ControlledFiles(events)
    repository = _Repository(events)
    uow = _UnitOfWork(events)
    workflow = UnsignedContractPdfPersistenceWorkflow(
        _Application(events), controlled, repository, lambda: uow
    )
    return workflow, controlled, repository, uow, events


def test_render_stage_preview_then_apply_and_document_link_share_outer_uow():
    workflow, controlled, repository, uow, events = _workflow()

    result = workflow.prepare_and_persist(_command())

    assert result.document_version_id == 52
    assert result.source_document_version_id == 41
    assert result.replayed is False
    assert events == [
        "render",
        "stage",
        "preview",
        "uow:enter",
        "source:lock",
        "file:apply",
        "document:register",
        "uow:commit",
    ]
    stage = controlled.stage_commands[0]
    assert stage.owner is ControlledFileOwner.CONTRACT_SIGNING
    assert stage.purpose is ControlledFilePurpose.UNSIGNED_CONTRACT
    assert stage.subject_reference == "CASE-1"
    assert "41" in stage.object_key
    assert "libreoffice-headless-v1" in stage.object_key
    assert repository.calls[0]["source"].document_version_id == 41
    assert uow.commits == 1
    assert uow.rollbacks == 0
    public = repr(result)
    assert "cf_" not in public
    assert "b" * 64 not in public


def test_document_registration_failure_rolls_back_apply_transaction():
    workflow, _, repository, uow, events = _workflow()

    def fail(**_):
        raise RuntimeError("/private/nas/unsigned.pdf")

    repository.register_persisted_pdf = fail

    with pytest.raises(UnsignedContractPdfError) as captured:
        workflow.prepare_and_persist(_command())

    assert captured.value.code == "contract_pdf_persistence_failed"
    assert "/private/" not in str(captured.value)
    assert uow.commits == 0
    assert uow.rollbacks == 1
    assert events[-1] == "uow:rollback"


def test_controlled_preview_blocker_stops_before_outer_uow():
    workflow, controlled, repository, uow, _ = _workflow()
    original = controlled.preview

    def blocked(intent):
        preview = original(intent)
        return ControlledFilePreview(
            preview.candidate,
            preview.preview_fingerprint,
            preview.expected_staging_version,
            ("owner_subject_not_found",),
        )

    controlled.preview = blocked

    with pytest.raises(UnsignedContractPdfError) as captured:
        workflow.prepare_and_persist(_command())

    assert captured.value.code == "contract_pdf_controlled_file_blocked"
    assert repository.calls == []
    assert uow.commits == 0
