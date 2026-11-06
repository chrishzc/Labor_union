"""
File: test_controlled_file_workflow.py
Description: 驗證受控檔案 Preview/Apply 的 fresh-read、outer UoW、重播與 public projection 契約。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

import pytest

from shared_kernel.clock import FixedBusinessClock
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.controlled_files.contracts import (
    ControlledFileStorageError,
    ControlledFileStagingContent,
    ControlledFileStagingRegistrationStatus,
    ControlledFileStagingResult,
)
from subsystems.controlled_files.workflow import (
    ApplyControlledFile,
    ControlledFileApplyOutcome,
    ControlledFileCommandClaim,
    ControlledFileCandidate,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
    ControlledFileStagingFacts,
    ControlledFileWorkflow,
    ControlledFileWorkflowError,
    ControlledFileDownloadReference,
    StageControlledFile,
    StoredControlledFileApplyReceipt,
    FILE_PURPOSE_REGISTRY,
)


NOW = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
STAGING_ID = "cfs_1234567890abcdef1234567890abcdef"
FILE_ID = "cf_1234567890abcdef1234567890abcdef"
CONTENT = b"signed-contract"
DIGEST = hashlib.sha256(CONTENT).hexdigest()


@dataclass
class FakeUnitOfWork:
    commits: int = 0
    rollbacks: int = 0

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None:
            self.rollbacks += 1
        return False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeStorage:
    def __init__(self, content: bytes = CONTENT) -> None:
        self.content = content
        self.reads = 0
        self.finalized: list[tuple[str, str]] = []

    def put_staged(self, *, idempotency_key, filename, mime_type, content):
        digest = hashlib.sha256(content).hexdigest()
        return ControlledFileStagingResult(
            staging_id=STAGING_ID,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(content),
            sha256_digest=digest,
            expires_at=NOW + timedelta(hours=24),
            replayed=False,
        )

    def read_staged(self, staging_id: str, *, expected_sha256: str):
        self.reads += 1
        digest = hashlib.sha256(self.content).hexdigest()
        return ControlledFileStagingContent(
            staging_id=staging_id,
            content=self.content,
            sha256_digest=digest,
            expires_at=NOW + timedelta(hours=24),
        )

    def read_registered_staged(self, staging_id: str, *, expected_sha256: str):
        return self.read_staged(staging_id, expected_sha256=expected_sha256)

    def finalize_staged(self, staging_id: str, *, expected_sha256: str):
        self.finalized.append((staging_id, expected_sha256))
        return self.read_registered_staged(staging_id, expected_sha256=expected_sha256)


class FakeRepository:
    def __init__(self) -> None:
        self.facts = ControlledFileStagingFacts(
            staging=ControlledFileStagingResult(
                staging_id=STAGING_ID,
                filename="contract.pdf",
                mime_type="application/pdf",
                size_bytes=len(CONTENT),
                sha256_digest=DIGEST,
                expires_at=NOW + timedelta(hours=24),
                replayed=False,
            ),
            version=1,
            registration_status=ControlledFileStagingRegistrationStatus.UNREGISTERED,
            stored_intent=_intent(),
        )
        self.owner_exists = True
        self.receipt = None
        self.claim = ControlledFileCommandClaim.CREATED
        self.loads: list[bool] = []
        self.owner_reads: list[bool] = []
        self.registered = 0
        self.marked = 0
        self.saved = 0
        self.finalize_intents = []

    def register_staging(self, command, result, *, command_fingerprint, created_at):
        self.facts = ControlledFileStagingFacts(
            staging=result,
            version=1,
            registration_status=ControlledFileStagingRegistrationStatus.UNREGISTERED,
            stored_intent=_intent(),
        )
        return result

    def load_staging(self, staging_id: str, *, for_update: bool):
        self.loads.append(for_update)
        return self.facts if staging_id == STAGING_ID else None

    def owner_subject_exists(self, intent, *, for_update: bool):
        self.owner_reads.append(for_update)
        return self.owner_exists

    def find_receipt(self, key, *, for_update: bool):
        return self.receipt

    def claim_command(self, key, command_fingerprint, correlation_id):
        return self.claim

    def register_file(self, candidate, *, actor, applied_at):
        self.registered += 1
        return ControlledFileReadback(
            file_id=FILE_ID,
            owner=candidate.owner,
            purpose=candidate.purpose,
            subject_reference=candidate.subject_reference,
            filename=candidate.filename,
            logical_folder=candidate.logical_folder,
            version=1,
            sha256_digest=candidate.sha256_digest,
            mime_type=candidate.mime_type,
            size_bytes=candidate.size_bytes,
            status="registered",
            applied_at=applied_at,
        )

    def mark_staging_registered(self, staging_id, *, expected_version, file_id):
        self.marked += 1

    def save_receipt(self, key, receipt, correlation_id):
        self.saved += 1
        self.receipt = receipt

    def save_post_commit_finalize_intent(self, intent):
        self.finalize_intents.append(intent)

    def get_readback(self, file_id):
        return None

    def list_readbacks(self):
        return ()

    def get_download_reference(self, file_id):
        if file_id != FILE_ID:
            return None
        return ControlledFileDownloadReference(
            readback=self.register_file(
                _workflow_candidate(), actor=ActorContext("admin-001"), applied_at=NOW
            ),
            staging_id=STAGING_ID,
        )

    def get_receipt(self, receipt_id):
        return None if self.receipt is None else self.receipt.receipt


def test_current_purpose_registry_matches_formal_nine_without_legacy_permanent_outputs():
    assert {purpose.value for purpose in FILE_PURPOSE_REGISTRY} == {
        "final_signed_contract", "signed_staff_agreement", "staff_resume", "staff_certificate",
        "staff_health_exam", "baby_log_photo", "meal_photo", "rich_menu_background", "database_backup",
    }
    assert FILE_PURPOSE_REGISTRY[ControlledFilePurpose.DATABASE_BACKUP][0] == "global_migration"


@pytest.mark.parametrize("owner,purpose", [
    (ControlledFileOwner.CONTRACT_SIGNING, ControlledFilePurpose.UNSIGNED_CONTRACT),
    (ControlledFileOwner.SCHEDULING, ControlledFilePurpose.SERVICE_DATE_CONFIRMATION),
    (ControlledFileOwner.ORDERS, ControlledFilePurpose.ORDER_NOTICE),
])
def test_retired_purpose_rejects_new_stage_preview_and_apply_before_bytes_or_writes(monkeypatch, owner, purpose):
    workflow, repository, storage, uow = _workflow()
    intent = replace(_intent(), owner=owner, purpose=purpose)
    monkeypatch.setattr(storage, "put_staged", lambda **_: pytest.fail("retired purpose wrote bytes"))
    command = StageControlledFile(owner, purpose, "CASE-001", "legacy", "legacy", "legacy.pdf",
        "application/pdf", CONTENT, IdempotencyKey("legacy-stage"), ActorContext("admin-001"), CorrelationId("policy"))
    with pytest.raises(ControlledFileWorkflowError, match="停止建立永久檔案"):
        workflow.stage(command)
    with pytest.raises(ControlledFileWorkflowError) as preview:
        workflow.preview(intent)
    with pytest.raises(ControlledFileWorkflowError) as apply:
        workflow.apply_borrowed(ApplyControlledFile(intent, ExpectedVersion(1), PreviewFingerprint("0" * 64),
            IdempotencyKey("legacy-apply"), ActorContext("admin-001"), CorrelationId("policy")))
    assert preview.value.code == apply.value.code == "controlled_file_purpose_retired"
    assert not repository.loads and not repository.registered and not repository.saved
    assert storage.reads == uow.commits == 0


@pytest.mark.parametrize("owner,purpose", [
    (ControlledFileOwner.CONTRACT_SIGNING, ControlledFilePurpose.UNSIGNED_CONTRACT),
    (ControlledFileOwner.SCHEDULING, ControlledFilePurpose.SERVICE_DATE_CONFIRMATION),
    (ControlledFileOwner.ORDERS, ControlledFilePurpose.ORDER_NOTICE),
])
def test_public_preview_explains_retired_purpose_without_a_stale_retry_or_effect(owner, purpose):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import controlled_files as routes
    from api.dependencies.admin_auth import require_persisted_admin
    workflow, repository, storage, uow = _workflow()
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_persisted_admin] = lambda: object()
    app.dependency_overrides[routes.get_controlled_file_route_workflow] = lambda: workflow
    with TestClient(app) as client:
        response = client.post("/api/v1/storage/files/preview", json={
            "staging_id": STAGING_ID, "owner": owner.value, "purpose": purpose.value,
            "subject_reference": "CASE-001", "object_key": "legacy", "logical_folder": "legacy",
        })
    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "controlled_file_purpose_retired" and error["category"] == "domain_blocked"
    assert "停止建立永久檔案" in error["message"]
    assert not repository.loads and storage.reads == repository.registered == uow.commits == 0


def test_retired_committed_receipt_still_replays_and_original_file_can_be_read(monkeypatch):
    from subsystems.controlled_files.workflow import _command_fingerprint
    workflow, repository, storage, _ = _workflow()
    receipt = workflow.apply(_command(workflow.preview(_intent())))
    legacy_intent = replace(_intent(), purpose=ControlledFilePurpose.UNSIGNED_CONTRACT)
    legacy_command = ApplyControlledFile(legacy_intent, ExpectedVersion(1), PreviewFingerprint("1" * 64),
        IdempotencyKey("legacy-committed"), ActorContext("admin-001"), CorrelationId("policy"))
    legacy_receipt = replace(receipt, readback=replace(receipt.readback, purpose=legacy_intent.purpose))
    repository.receipt = StoredControlledFileApplyReceipt(_command_fingerprint(legacy_command), legacy_receipt)
    monkeypatch.setattr(repository, "load_staging", lambda *_args, **_kw: pytest.fail("replay revalidated retired staging"))
    monkeypatch.setattr(repository, "get_download_reference", lambda _: ControlledFileDownloadReference(legacy_receipt.readback, STAGING_ID))
    before = (repository.registered, repository.marked, repository.saved)
    assert workflow.apply_borrowed(legacy_command).outcome is ControlledFileApplyOutcome.REPLAYED
    assert workflow.read_receipt(legacy_receipt.receipt_id).readback.purpose is legacy_intent.purpose
    assert workflow.download(FILE_ID).content == CONTENT
    assert (repository.registered, repository.marked, repository.saved) == before


@pytest.mark.parametrize("owner,purpose,mime", [
    (ControlledFileOwner.STAFF, ControlledFilePurpose.STAFF_RESUME, "image/jpeg"),
    (ControlledFileOwner.LINE_INTEGRATION, ControlledFilePurpose.RICH_MENU_BACKGROUND, "image/jpeg"),
    (ControlledFileOwner.SCHEDULING, ControlledFilePurpose.BABY_LOG_PHOTO, "application/pdf"),
])
def test_current_purpose_format_is_enforced_before_stage_bytes(monkeypatch, owner, purpose, mime):
    workflow, repository, storage, _ = _workflow()
    monkeypatch.setattr(storage, "put_staged", lambda **_: pytest.fail("invalid format wrote bytes"))
    command = StageControlledFile(owner, purpose, "CASE-001", "source", "files", "source",
        mime, CONTENT, IdempotencyKey("format-stage"), ActorContext("admin-001"), CorrelationId("policy"))
    with pytest.raises(ControlledFileWorkflowError) as error:
        workflow.stage(command)
    assert error.value.code == "controlled_file_purpose_format_invalid"
    assert not repository.loads and not repository.registered


def test_apply_fresh_reads_purpose_mime_before_using_bytes_or_writing():
    workflow, repository, storage, _ = _workflow()
    command = _command(workflow.preview(_intent()))
    reads_before = storage.reads
    repository.facts = replace(repository.facts, staging=replace(repository.facts.staging, mime_type="image/jpeg"))
    with pytest.raises(ControlledFileWorkflowError) as error:
        workflow.apply_borrowed(command)
    assert error.value.code == "controlled_file_purpose_format_invalid"
    assert storage.reads == reads_before and repository.registered == repository.saved == 0


@pytest.mark.parametrize("owner", list(ControlledFileOwner))
def test_database_backup_cannot_enter_generic_business_file_stage(owner):
    with pytest.raises(ValueError, match="owner/purpose pairing"):
        StageControlledFile(owner, ControlledFilePurpose.DATABASE_BACKUP, "backup", "backup", "backup", "backup.sql.gz",
            "application/gzip", CONTENT, IdempotencyKey("backup-stage"), ActorContext("admin-001"), CorrelationId("policy"))


def _intent() -> ControlledFileIntent:
    return ControlledFileIntent(
        staging_id=STAGING_ID,
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
        subject_reference="CASE-001",
        object_key="final-contract",
        logical_folder="contracts",
    )


def _workflow_candidate():
    return ControlledFileCandidate(
        staging_id=STAGING_ID,
        staging_version=1,
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
        subject_reference="CASE-001",
        object_key="final-contract",
        logical_folder="contracts",
        filename="contract.pdf",
        mime_type="application/pdf",
        size_bytes=len(CONTENT),
        sha256_digest=DIGEST,
        expires_at=NOW + timedelta(hours=24),
    )


def _workflow(repository=None, storage=None, unit_of_work=None):
    repository = repository or FakeRepository()
    storage = storage or FakeStorage()
    unit_of_work = unit_of_work or FakeUnitOfWork()
    return (
        ControlledFileWorkflow(
            repository,
            storage,
            lambda: unit_of_work,
            FixedBusinessClock(NOW),
        ),
        repository,
        storage,
        unit_of_work,
    )


def _command(preview, *, key="controlled-file:test-001") -> ApplyControlledFile:
    return ApplyControlledFile(
        intent=_intent(),
        expected_staging_version=preview.expected_staging_version,
        preview_fingerprint=preview.preview_fingerprint,
        idempotency_key=IdempotencyKey(key),
        actor=ActorContext("admin-001"),
        correlation_id=CorrelationId("corr-001"),
    )


def test_preview_is_read_only_deterministic_and_fresh_reads_bytes() -> None:
    workflow, repository, storage, unit_of_work = _workflow()

    first = workflow.preview(_intent())
    second = workflow.preview(_intent())

    assert first == second
    assert first.blockers == ()
    assert first.expected_staging_version == ExpectedVersion(1)
    assert storage.reads == 2
    assert repository.loads == [False, False]
    assert repository.owner_reads == [False, False]
    assert unit_of_work.commits == 0


def test_preview_rejects_intent_that_differs_from_stored_staging_metadata() -> None:
    workflow, repository, storage, unit_of_work = _workflow()
    mismatched = ControlledFileIntent(
        staging_id=STAGING_ID,
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
        subject_reference="CASE-002",
        object_key="final-contract",
        logical_folder="contracts",
    )

    with pytest.raises(ControlledFileWorkflowError) as captured:
        workflow.preview(mismatched)

    assert captured.value.code == "controlled_file_staging_intent_mismatch"
    assert repository.owner_reads == []
    assert storage.reads == 0
    assert unit_of_work.commits == 0


def test_invalid_owner_purpose_pairing_fails_before_repository_access() -> None:
    workflow, repository, _, _ = _workflow()

    with pytest.raises(ValueError, match="pairing"):
        ControlledFileIntent(
            staging_id=STAGING_ID,
            owner=ControlledFileOwner.ORDERS,
            purpose=ControlledFilePurpose.STAFF_RESUME,
            subject_reference="CASE-001",
            object_key="notice",
            logical_folder="orders",
        )

    assert repository.loads == []
    assert workflow is not None


def test_preview_reports_owner_blocker_without_writes() -> None:
    repository = FakeRepository()
    repository.owner_exists = False
    workflow, repository, _, unit_of_work = _workflow(repository=repository)

    preview = workflow.preview(_intent())

    assert preview.blockers == ("owner_subject_not_found",)
    assert repository.registered == repository.marked == repository.saved == 0
    assert unit_of_work.commits == 0


def test_apply_fresh_locks_and_commits_once_without_locator_projection() -> None:
    workflow, repository, _, unit_of_work = _workflow()
    preview = workflow.preview(_intent())

    receipt = workflow.apply(_command(preview))

    assert receipt.outcome is ControlledFileApplyOutcome.CREATED
    assert receipt.receipt_type == "controlled_file_apply"
    assert receipt.schema_version == "controlled-file-apply-receipt.v1"
    assert receipt.readback.file_id == FILE_ID
    assert repository.loads == [False, True]
    assert repository.owner_reads == [False, True]
    assert (repository.registered, repository.marked, repository.saved) == (1, 1, 1)
    assert unit_of_work.commits == 1
    assert repository.finalize_intents[0].staging_id == STAGING_ID
    assert repository.finalize_intents[0].file_id == FILE_ID
    projection = repr(receipt).casefold()
    assert "storage_locator" not in projection
    assert "file:" not in projection
    assert "://" not in projection


def test_apply_registers_idempotent_integrity_finalize_after_commit_when_supported() -> None:
    class HookedUnitOfWork(FakeUnitOfWork):
        def __init__(self):
            super().__init__()
            self._committed = False
            self.hooks = []

        def add_after_completion(self, hook):
            self.hooks.append(hook)

        def commit(self):
            super().commit()
            self._committed = True
            for hook in self.hooks:
                hook()

    storage = FakeStorage()
    unit_of_work = HookedUnitOfWork()
    workflow, _, _, _ = _workflow(storage=storage, unit_of_work=unit_of_work)
    preview = workflow.preview(_intent())

    workflow.apply(_command(preview))

    assert unit_of_work.commits == 1
    assert storage.finalized == [(STAGING_ID, DIGEST)]


def test_metadata_commit_failure_retains_staging_bytes_for_reconciliation() -> None:
    class FailingUnitOfWork(FakeUnitOfWork):
        def __init__(self):
            super().__init__()
            self._committed = False
            self.hooks = []

        def add_after_completion(self, hook):
            self.hooks.append(hook)

        def commit(self):
            for hook in self.hooks:
                hook()
            raise RuntimeError("db_commit_failed")

    storage = FakeStorage()
    unit_of_work = FailingUnitOfWork()
    workflow, _, _, _ = _workflow(storage=storage, unit_of_work=unit_of_work)
    preview = workflow.preview(_intent())

    with pytest.raises(RuntimeError, match="db_commit_failed"):
        workflow.apply(_command(preview))

    assert storage.content == CONTENT
    assert storage.finalized == []
    assert unit_of_work.rollbacks == 1


def test_post_commit_finalize_failure_is_a_typed_reconciliation_blocker() -> None:
    class FailingFinalizeStorage(FakeStorage):
        def finalize_staged(self, staging_id: str, *, expected_sha256: str):
            raise ControlledFileStorageError(
                "controlled_file_staging_not_found", "missing", retryable=False
            )

    storage = FailingFinalizeStorage()

    class HookedUnitOfWork(FakeUnitOfWork):
        def __init__(self):
            super().__init__()
            self._committed = False
            self.hooks = []

        def add_after_completion(self, hook):
            self.hooks.append(hook)

        def commit(self):
            super().commit()
            self._committed = True
            for hook in self.hooks:
                hook()

    unit_of_work = HookedUnitOfWork()
    workflow, _, _, _ = _workflow(storage=storage, unit_of_work=unit_of_work)
    preview = workflow.preview(_intent())

    with pytest.raises(ControlledFileWorkflowError) as captured:
        workflow.apply(_command(preview))

    assert captured.value.code == "controlled_file_post_commit_reconciliation_required"
    assert unit_of_work.commits == 1


def test_apply_borrowed_leaves_commit_to_outer_owner() -> None:
    workflow, repository, _, unit_of_work = _workflow()
    preview = workflow.preview(_intent())

    receipt = workflow.apply_borrowed(_command(preview))

    assert receipt.outcome is ControlledFileApplyOutcome.CREATED
    assert (repository.registered, repository.marked, repository.saved) == (1, 1, 1)
    assert unit_of_work.commits == 0
    assert unit_of_work.rollbacks == 0


def test_apply_replay_returns_same_identity_without_second_registration() -> None:
    workflow, repository, _, unit_of_work = _workflow()
    preview = workflow.preview(_intent())
    command = _command(preview)
    created = workflow.apply(command)

    replayed = workflow.apply(command)

    assert replayed.receipt_id == created.receipt_id
    assert replayed.readback.file_id == created.readback.file_id
    assert replayed.outcome is ControlledFileApplyOutcome.REPLAYED
    assert repository.registered == 1
    assert unit_of_work.commits == 2


def test_apply_rejects_idempotency_mismatch_without_new_writes() -> None:
    workflow, repository, _, unit_of_work = _workflow()
    preview = workflow.preview(_intent())
    created = workflow.apply(_command(preview))
    repository.receipt = StoredControlledFileApplyReceipt(
        PreviewFingerprint("f" * 64), created
    )

    with pytest.raises(ControlledFileWorkflowError) as captured:
        workflow.apply(_command(preview))

    assert captured.value.code == "idempotency_mismatch"
    assert repository.registered == 1
    assert unit_of_work.commits == 1
    assert unit_of_work.rollbacks == 1


def test_apply_detects_byte_drift_and_rolls_back_before_persistence() -> None:
    workflow, repository, storage, unit_of_work = _workflow()
    preview = workflow.preview(_intent())
    storage.content = b"changed"

    with pytest.raises(ControlledFileWorkflowError) as captured:
        workflow.apply(_command(preview))

    assert captured.value.code == "controlled_file_staging_drift"
    assert repository.registered == repository.marked == repository.saved == 0
    assert unit_of_work.commits == 0
    assert unit_of_work.rollbacks == 1


def test_apply_rejects_stale_expected_version_before_persistence() -> None:
    workflow, repository, _, unit_of_work = _workflow()
    preview = workflow.preview(_intent())
    command = ApplyControlledFile(
        intent=_intent(),
        expected_staging_version=ExpectedVersion(2),
        preview_fingerprint=preview.preview_fingerprint,
        idempotency_key=IdempotencyKey("controlled-file:test-002"),
        actor=ActorContext("admin-001"),
        correlation_id=CorrelationId("corr-002"),
    )

    with pytest.raises(ControlledFileWorkflowError) as captured:
        workflow.apply(command)

    assert captured.value.code == "stale_staging_version"
    assert repository.registered == repository.marked == repository.saved == 0
    assert unit_of_work.commits == 0
    assert unit_of_work.rollbacks == 1


@pytest.mark.parametrize("key", ["Uppercase", "bad/key", " leading", "a" * 192])
def test_apply_command_rejects_noncanonical_idempotency_key(key: str) -> None:
    workflow, _, _, _ = _workflow()
    preview = workflow.preview(_intent())

    with pytest.raises(ValueError, match="idempotency"):
        _command(preview, key=key)


def test_stage_persists_metadata_in_one_outer_uow_and_download_hides_locator() -> None:
    workflow, repository, _, unit_of_work = _workflow()
    staged = workflow.stage(
        StageControlledFile(
            owner=ControlledFileOwner.CONTRACT_SIGNING,
            purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
            subject_reference="CASE-001",
            object_key="final-contract",
            logical_folder="contracts",
            filename="contract.pdf",
            mime_type="application/pdf",
            content=CONTENT,
            idempotency_key=IdempotencyKey("controlled-file:stage-001"),
            actor=ActorContext("admin-001"),
            correlation_id=CorrelationId("corr-stage-001"),
        )
    )
    downloaded = workflow.download(FILE_ID)

    assert staged.staging_id == STAGING_ID
    assert unit_of_work.commits == 1
    assert downloaded.object_reference == FILE_ID
    assert downloaded.content == CONTENT
    assert "storage_locator" not in repr(downloaded)
