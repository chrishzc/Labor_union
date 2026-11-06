"""
File: workflow.py
Description: 編排受控檔案的 closed owner 契約、Preview、Apply、重播與單一 outer UoW。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Callable, Protocol

from shared_kernel.clock import BusinessClock
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text
from subsystems.controlled_files.contracts import (
    ControlledFileContent,
    ControlledFileStoragePort,
    ControlledFileStagingRegistrationStatus,
    ControlledFileStagingResult,
)


class ControlledFileOwner(str, Enum):
    CONTRACT_SIGNING = "contract_signing"
    SCHEDULING = "scheduling"
    ORDERS = "orders"
    STAFF = "staff"
    LINE_INTEGRATION = "line_integration"


class ControlledFilePurpose(str, Enum):
    UNSIGNED_CONTRACT = "unsigned_contract"
    FINAL_SIGNED_CONTRACT = "final_signed_contract"
    SIGNED_STAFF_AGREEMENT = "signed_staff_agreement"
    SERVICE_DATE_CONFIRMATION = "service_date_confirmation"
    BABY_LOG_PHOTO = "baby_log_photo"
    MEAL_PHOTO = "meal_photo"
    ORDER_NOTICE = "order_notice"
    STAFF_RESUME = "staff_resume"
    STAFF_CERTIFICATE = "staff_certificate"
    STAFF_HEALTH_EXAM = "staff_health_exam"
    RICH_MENU_BACKGROUND = "rich_menu_background"
    DATABASE_BACKUP = "database_backup"


class ControlledFileApplyOutcome(str, Enum):
    CREATED = "created"
    REPLAYED = "replayed"


class ControlledFileCommandClaim(str, Enum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


class ControlledFileWorkflowError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


_PDF_AND_EXCEL = frozenset({"application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
_PHOTOS = frozenset({"image/jpeg", "image/png"})
@dataclass(frozen=True, slots=True)
class FilePurposePolicy:
    """Spec30 §3 policy, distinct from observed backup/restore readiness.

    The eight business formats are accepted primary MIME alternatives. Backup
    formats describe a required gzip + SHA256 text sidecar pair, consumed only
    by Global migration. No policy value establishes a successful drill.
    A retention boundary states the current operation contract, not a legal age.
    """

    owner_domain: str
    file_format: frozenset[str]
    source_of_truth: tuple[str, ...]
    generation_cadence: str
    db_reference: tuple[str, ...]
    consumers: tuple[str, ...]
    overwrite_policy: str
    retention_policy: str
    backup_required: bool
    restore_owner: str


_ADDITIVE_REVISIONS = "additive_revision_preserve_frozen_lineage"
_BUSINESS_RETENTION = "long_term_no_automatic_purge_of_committed_or_frozen_artifacts"
# Business metadata AND bytes require backup/restore under Global §2.2. This
# does not claim a destination, cadence, copy or readiness. The 2026-11-06
# user decision assigns NAS restore to its administrator and verification to
# each owning business Domain. Existing backup archives need no additional
# replica under the same decision; their spec10 §9.5 restore boundary remains.
FILE_PURPOSE_REGISTRY = MappingProxyType({
    ControlledFilePurpose.FINAL_SIGNED_CONTRACT: FilePurposePolicy(
        owner_domain=ControlledFileOwner.CONTRACT_SIGNING.value,
        file_format=_PDF_AND_EXCEL,
        source_of_truth=("ContractSigning completed final owner receipt", "per-file immutable ControlledFile Apply receipt"),
        generation_cadence="on_owner_signed_return",
        db_reference=("contract_final_document_versions", "contract_external_signing_receipts.result_snapshot.documents", "controlled_file_apply_receipts"),
        consumers=("ContractSigning external-final query", "authenticated final ControlledFile download", "ControlledFile reconciliation"),
        overwrite_policy=_ADDITIVE_REVISIONS, retention_policy=_BUSINESS_RETENTION,
        backup_required=True, restore_owner="nas_administrator",
    ),
    ControlledFilePurpose.SIGNED_STAFF_AGREEMENT: FilePurposePolicy(
        owner_domain=ControlledFileOwner.CONTRACT_SIGNING.value,
        file_format=_PDF_AND_EXCEL,
        source_of_truth=("ContractSigning completed final owner receipt", "per-staff immutable ControlledFile Apply receipt"),
        generation_cadence="on_owner_signed_return",
        db_reference=("contract_final_document_versions", "contract_external_signing_receipts.result_snapshot.documents", "controlled_file_apply_receipts"),
        consumers=("ContractSigning staff external-final query", "authenticated final ControlledFile download", "ControlledFile reconciliation"),
        overwrite_policy=_ADDITIVE_REVISIONS, retention_policy=_BUSINESS_RETENTION,
        backup_required=True, restore_owner="nas_administrator",
    ),
    ControlledFilePurpose.STAFF_RESUME: FilePurposePolicy(
        owner_domain=ControlledFileOwner.STAFF.value,
        file_format=frozenset({"application/pdf"}),
        source_of_truth=("Staff root and current resume logical key", "immutable ControlledFile Apply receipt"),
        generation_cadence="on_authenticated_owner_upload",
        db_reference=("staff", "controlled_file_objects", "controlled_file_apply_receipts"),
        consumers=("Staff current-resume query", "authenticated resume PDF download", "ControlledFile reconciliation"),
        overwrite_policy=_ADDITIVE_REVISIONS, retention_policy=_BUSINESS_RETENTION,
        backup_required=True, restore_owner="nas_administrator",
    ),
    ControlledFilePurpose.STAFF_CERTIFICATE: FilePurposePolicy(
        owner_domain=ControlledFileOwner.STAFF.value,
        file_format=frozenset({"application/pdf", "image/jpeg"}),
        source_of_truth=("Staff saved-document inventory membership; not qualification facts", "immutable ControlledFile Apply receipt"),
        generation_cadence="on_authenticated_owner_upload",
        db_reference=("staff", "controlled_file_objects", "controlled_file_apply_receipts"),
        consumers=("Staff profile saved-document collection", "authenticated ControlledFile download", "ControlledFile reconciliation"),
        overwrite_policy=_ADDITIVE_REVISIONS, retention_policy=_BUSINESS_RETENTION,
        backup_required=True, restore_owner="nas_administrator",
    ),
    ControlledFilePurpose.STAFF_HEALTH_EXAM: FilePurposePolicy(
        owner_domain=ControlledFileOwner.STAFF.value,
        file_format=frozenset({"application/pdf", "image/jpeg"}),
        source_of_truth=("Staff saved-document inventory membership; not medical, police or validity facts", "immutable ControlledFile Apply receipt"),
        generation_cadence="on_authenticated_owner_upload",
        db_reference=("staff", "controlled_file_objects", "controlled_file_apply_receipts"),
        consumers=("Staff profile saved-document collection", "authenticated ControlledFile download", "ControlledFile reconciliation"),
        overwrite_policy=_ADDITIVE_REVISIONS, retention_policy=_BUSINESS_RETENTION,
        backup_required=True, restore_owner="nas_administrator",
    ),
    ControlledFilePurpose.BABY_LOG_PHOTO: FilePurposePolicy(
        owner_domain=ControlledFileOwner.SCHEDULING.value,
        file_format=_PHOTOS,
        source_of_truth=("Scheduling submitted service-day log and attachment", "exact frozen ControlledFile reference"),
        generation_cadence="on_verified_staff_service_day_submission",
        db_reference=("scheduling_service_day_logs", "scheduling_service_day_log_events", "scheduling_service_day_log_attachments", "controlled_file_references"),
        consumers=("Scheduling submitted-log photo list", "authenticated ControlledFile download", "ControlledFile reconciliation"),
        overwrite_policy=_ADDITIVE_REVISIONS, retention_policy=_BUSINESS_RETENTION,
        backup_required=True, restore_owner="nas_administrator",
    ),
    ControlledFilePurpose.MEAL_PHOTO: FilePurposePolicy(
        owner_domain=ControlledFileOwner.SCHEDULING.value,
        file_format=_PHOTOS,
        source_of_truth=("Scheduling submitted service-day log and attachment", "exact frozen ControlledFile reference"),
        generation_cadence="on_verified_staff_service_day_submission",
        db_reference=("scheduling_service_day_logs", "scheduling_service_day_log_events", "scheduling_service_day_log_attachments", "controlled_file_references"),
        consumers=("Scheduling submitted-log photo list", "authenticated ControlledFile download", "ControlledFile reconciliation"),
        overwrite_policy=_ADDITIVE_REVISIONS, retention_policy=_BUSINESS_RETENTION,
        backup_required=True, restore_owner="nas_administrator",
    ),
    ControlledFilePurpose.RICH_MENU_BACKGROUND: FilePurposePolicy(
        owner_domain=ControlledFileOwner.LINE_INTEGRATION.value,
        file_format=frozenset({"image/png"}),
        source_of_truth=("LINE media asset and immutable ControlledFile Apply receipt", "outbound publication evidence only: published task frozen image and immutable upload acknowledgment"),
        generation_cadence="on_owner_upload_or_rich_menu_generation",
        db_reference=("media_assets.controlled_file_object_id", "line_configuration_revisions", "line_rich_menu_publication_tasks"),
        consumers=("LINE Rich Menu preview", "committed Rich Menu publication worker", "ControlledFile reconciliation"),
        overwrite_policy=_ADDITIVE_REVISIONS, retention_policy=_BUSINESS_RETENTION,
        backup_required=True, restore_owner="nas_administrator",
    ),
    ControlledFilePurpose.DATABASE_BACKUP: FilePurposePolicy(
        owner_domain="global_migration", file_format=frozenset({"application/gzip", "text/plain"}),
        source_of_truth=("Global migration verified SQL.GZ and SHA256 pair", "completed backup success receipt"),
        generation_cadence="configured_daily_default_18_00_or_manual",
        db_reference=("no source-DB registration; Global migration backup success receipt",),
        consumers=("Global migration Windows backup/restore maintenance", "Data Center backup readiness"),
        overwrite_policy="new_backup_pair_preserve_existing_and_failed_materials",
        retention_policy="no_automatic_delete_or_overwrite_of_backup_or_failure_materials",
        backup_required=False, restore_owner="global_migration",
    ),
})
# Retain the historical owner/purpose pairing for reads and exact receipt replay.
# This set is deliberately not the active write policy.
_ALLOWED_PURPOSES = {
    ControlledFileOwner.CONTRACT_SIGNING: frozenset(
        {
            ControlledFilePurpose.UNSIGNED_CONTRACT,
            ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
            ControlledFilePurpose.SIGNED_STAFF_AGREEMENT,
        }
    ),
    ControlledFileOwner.SCHEDULING: frozenset(
        {
            ControlledFilePurpose.SERVICE_DATE_CONFIRMATION,
            ControlledFilePurpose.BABY_LOG_PHOTO,
            ControlledFilePurpose.MEAL_PHOTO,
        }
    ),
    ControlledFileOwner.ORDERS: frozenset({ControlledFilePurpose.ORDER_NOTICE}),
    ControlledFileOwner.STAFF: frozenset(
        {
            ControlledFilePurpose.STAFF_RESUME,
            ControlledFilePurpose.STAFF_CERTIFICATE,
            ControlledFilePurpose.STAFF_HEALTH_EXAM,
        }
    ),
    ControlledFileOwner.LINE_INTEGRATION: frozenset(
        {ControlledFilePurpose.RICH_MENU_BACKGROUND}
    ),
}
_STAGING_ID = re.compile(r"^cfs_[0-9a-f]{32}$")
_FILE_ID = re.compile(r"^cf_[0-9a-f]{32}$")
_RECEIPT_ID = re.compile(r"^cfr_[0-9a-f]{32}$")
_IDEMPOTENCY_KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,190}$")


@dataclass(frozen=True, slots=True)
class ControlledFileIntent:
    staging_id: str
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    object_key: str
    logical_folder: str

    def __post_init__(self) -> None:
        _validate_intent(self)


@dataclass(frozen=True, slots=True)
class StageControlledFile:
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    object_key: str
    logical_folder: str
    filename: str
    mime_type: str
    content: bytes
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_owner_fields(
            self.owner,
            self.purpose,
            self.subject_reference,
            self.object_key,
            self.logical_folder,
        )
        if _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key.value) is None:
            raise ValueError("controlled file idempotency key is invalid")


@dataclass(frozen=True, slots=True)
class ControlledFileStagingFacts:
    staging: ControlledFileStagingResult
    version: int
    registration_status: ControlledFileStagingRegistrationStatus
    stored_intent: ControlledFileIntent


@dataclass(frozen=True, slots=True)
class ControlledFileCandidate:
    staging_id: str
    staging_version: int
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    object_key: str
    logical_folder: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256_digest: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ControlledFilePreview:
    candidate: ControlledFileCandidate
    preview_fingerprint: PreviewFingerprint
    expected_staging_version: ExpectedVersion
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ApplyControlledFile:
    intent: ControlledFileIntent
    expected_staging_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        if _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key.value) is None:
            raise ValueError("controlled file idempotency key is invalid")


@dataclass(frozen=True, slots=True)
class ControlledFileReadback:
    file_id: str
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    filename: str
    logical_folder: str
    version: int
    sha256_digest: str
    mime_type: str
    size_bytes: int
    status: str
    applied_at: datetime

    def __post_init__(self) -> None:
        if _FILE_ID.fullmatch(self.file_id) is None:
            raise ValueError("controlled file identity is invalid")


@dataclass(frozen=True, slots=True)
class ControlledFileApplyReceipt:
    receipt_id: str
    outcome: ControlledFileApplyOutcome
    readback: ControlledFileReadback
    receipt_type: str = "controlled_file_apply"
    schema_version: str = "controlled-file-apply-receipt.v1"

    def __post_init__(self) -> None:
        if _RECEIPT_ID.fullmatch(self.receipt_id) is None:
            raise ValueError("controlled file receipt identity is invalid")


@dataclass(frozen=True, slots=True)
class StoredControlledFileApplyReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: ControlledFileApplyReceipt


@dataclass(frozen=True, slots=True)
class ControlledFilePostCommitFinalizeIntent:
    """The immutable facts a worker needs to verify bytes after DB commit.

    The intent is deliberately separate from the apply receipt.  A repository
    that owns a durable intent table may persist it in the same outer UoW; a
    repository without that schema can still use the completion hook as a
    local compatibility path while the missing durable capability remains
    visible to reconciliation.
    """

    staging_id: str
    file_id: str
    expected_sha256: str
    created_at: datetime

    def __post_init__(self) -> None:
        if _STAGING_ID.fullmatch(self.staging_id) is None:
            raise ValueError("controlled file staging identity is invalid")
        if _FILE_ID.fullmatch(self.file_id) is None:
            raise ValueError("controlled file identity is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256):
            raise ValueError("controlled file digest is invalid")
        if self.created_at.tzinfo is None:
            raise ValueError("controlled file finalize intent time must include timezone")


@dataclass(frozen=True, slots=True)
class ControlledFileDownloadReference:
    readback: ControlledFileReadback
    staging_id: str


class ControlledFileWorkflowRepository(Protocol):
    def register_staging(
        self,
        command: StageControlledFile,
        result: ControlledFileStagingResult,
        *,
        command_fingerprint: PreviewFingerprint,
        created_at: datetime,
    ) -> ControlledFileStagingResult: ...

    def load_staging(
        self, staging_id: str, *, for_update: bool
    ) -> ControlledFileStagingFacts | None: ...

    def owner_subject_exists(
        self, intent: ControlledFileIntent, *, for_update: bool
    ) -> bool: ...

    def find_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredControlledFileApplyReceipt | None: ...

    def claim_command(
        self,
        key: IdempotencyKey,
        command_fingerprint: PreviewFingerprint,
        correlation_id: CorrelationId,
    ) -> ControlledFileCommandClaim: ...

    def register_file(
        self,
        candidate: ControlledFileCandidate,
        *,
        actor: ActorContext,
        applied_at: datetime,
    ) -> ControlledFileReadback: ...

    def mark_staging_registered(
        self, staging_id: str, *, expected_version: ExpectedVersion, file_id: str
    ) -> None: ...

    def save_receipt(
        self,
        key: IdempotencyKey,
        receipt: StoredControlledFileApplyReceipt,
        correlation_id: CorrelationId,
    ) -> None: ...

    def save_post_commit_finalize_intent(
        self, intent: ControlledFilePostCommitFinalizeIntent
    ) -> None: ...

    def get_readback(self, file_id: str) -> ControlledFileReadback | None: ...

    def list_readbacks(self) -> tuple[ControlledFileReadback, ...]: ...

    def find_current_readback(
        self, owner: ControlledFileOwner, purpose: ControlledFilePurpose,
        subject_reference: str, object_key: str,
    ) -> ControlledFileReadback | None: ...

    def get_download_reference(
        self, file_id: str
    ) -> ControlledFileDownloadReference | None: ...

    def get_receipt(self, receipt_id: str) -> ControlledFileApplyReceipt | None: ...


class ControlledFileWorkflow:
    def __init__(
        self,
        repository: ControlledFileWorkflowRepository,
        storage: ControlledFileStoragePort,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: BusinessClock,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def stage(self, command: StageControlledFile) -> ControlledFileStagingResult:
        _require_current_purpose(command.owner, command.purpose, command.mime_type)
        result = self._storage.put_staged(
            idempotency_key=command.idempotency_key.value,
            filename=command.filename,
            mime_type=command.mime_type,
            content=command.content,
        )
        command_fingerprint = fingerprint_payload(_staging_command_payload(command, result))
        with self._unit_of_work_factory() as unit_of_work:
            persisted = self._repository.register_staging(
                command,
                result,
                command_fingerprint=command_fingerprint,
                created_at=_utc(self._clock.now()),
            )
            unit_of_work.commit()
        return persisted

    def preview(self, intent: ControlledFileIntent) -> ControlledFilePreview:
        return self._build_preview(intent, for_update=False)

    def apply(self, command: ApplyControlledFile) -> ControlledFileApplyReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self.apply_borrowed(command)
            _register_postcommit_finalize(
                unit_of_work,
                self._storage,
                receipt.readback,
                command.intent.staging_id,
            )
            unit_of_work.commit()
            return receipt

    def apply_borrowed(
        self, command: ApplyControlledFile
    ) -> ControlledFileApplyReceipt:
        """Apply inside a caller-owned transaction without committing it."""
        command_fingerprint = _command_fingerprint(command)
        stored = self._repository.find_receipt(
            command.idempotency_key, for_update=True
        )
        if stored is not None:
            return _replay(stored, command_fingerprint)

        fresh = self._build_preview(command.intent, for_update=True)
        if fresh.expected_staging_version != command.expected_staging_version:
            raise ControlledFileWorkflowError("stale_staging_version", "staging 版本已變更")
        if fresh.blockers:
            raise ControlledFileWorkflowError(fresh.blockers[0], "檔案目前不可 Apply")
        if fresh.preview_fingerprint != command.preview_fingerprint:
            raise ControlledFileWorkflowError("stale_preview", "Preview 已過期")

        claim = self._repository.claim_command(
            command.idempotency_key, command_fingerprint, command.correlation_id
        )
        if claim is ControlledFileCommandClaim.MISMATCH:
            raise ControlledFileWorkflowError(
                "idempotency_mismatch", "相同重播識別對應不同命令"
            )
        if claim is ControlledFileCommandClaim.MATCHED:
            matched = self._repository.find_receipt(
                command.idempotency_key, for_update=True
            )
            if matched is None:
                raise ControlledFileWorkflowError(
                    "idempotency_evidence_incomplete", "命令已存在但 receipt 不完整"
                )
            return _replay(matched, command_fingerprint)

        now = _utc(self._clock.now())
        readback = self._repository.register_file(
            fresh.candidate, actor=command.actor, applied_at=now
        )
        self._repository.mark_staging_registered(
            fresh.candidate.staging_id,
            expected_version=command.expected_staging_version,
            file_id=readback.file_id,
        )
        receipt = ControlledFileApplyReceipt(
            receipt_id=_receipt_id(command.idempotency_key),
            outcome=ControlledFileApplyOutcome.CREATED,
            readback=readback,
        )
        self._repository.save_receipt(
            command.idempotency_key,
            StoredControlledFileApplyReceipt(command_fingerprint, receipt),
            command.correlation_id,
        )
        save_finalize_intent = getattr(
            self._repository, "save_post_commit_finalize_intent", None
        )
        if callable(save_finalize_intent):
            save_finalize_intent(
                ControlledFilePostCommitFinalizeIntent(
                    staging_id=fresh.candidate.staging_id,
                    file_id=readback.file_id,
                    expected_sha256=readback.sha256_digest,
                    created_at=now,
                )
            )
        return receipt

    def readback(self, file_id: str) -> ControlledFileReadback:
        if _FILE_ID.fullmatch(file_id) is None:
            raise ControlledFileWorkflowError("controlled_file_id_invalid", "檔案識別格式無效")
        result = self._repository.get_readback(file_id)
        if result is None:
            raise ControlledFileWorkflowError("controlled_file_not_found", "指定檔案不存在")
        return result

    def list_readbacks(self) -> tuple[ControlledFileReadback, ...]:
        return self._repository.list_readbacks()

    def find_current_readback(
        self, owner: ControlledFileOwner, purpose: ControlledFilePurpose,
        subject_reference: str, object_key: str,
    ) -> ControlledFileReadback | None:
        _validate_owner_fields(owner, purpose, subject_reference, object_key, "current-read")
        return self._repository.find_current_readback(owner, purpose, subject_reference, object_key)

    def download(self, file_id: str) -> ControlledFileContent:
        if _FILE_ID.fullmatch(file_id) is None:
            raise ControlledFileWorkflowError("controlled_file_id_invalid", "檔案識別格式無效")
        reference = self._repository.get_download_reference(file_id)
        if reference is None:
            raise ControlledFileWorkflowError("controlled_file_not_found", "指定檔案不存在")
        staged = self._storage.read_registered_staged(
            reference.staging_id,
            expected_sha256=reference.readback.sha256_digest,
        )
        return ControlledFileContent(
            object_reference=file_id,
            filename=reference.readback.filename,
            content_type=reference.readback.mime_type,
            content=staged.content,
            content_sha256=staged.sha256_digest,
        )

    def read_receipt(self, receipt_id: str) -> ControlledFileApplyReceipt:
        if _RECEIPT_ID.fullmatch(receipt_id) is None:
            raise ControlledFileWorkflowError("controlled_file_receipt_id_invalid", "receipt 識別格式無效")
        receipt = self._repository.get_receipt(receipt_id)
        if receipt is None:
            raise ControlledFileWorkflowError("controlled_file_receipt_not_found", "指定 receipt 不存在")
        return receipt

    def _build_preview(
        self, intent: ControlledFileIntent, *, for_update: bool
    ) -> ControlledFilePreview:
        _require_current_purpose(intent.owner, intent.purpose)
        facts = self._repository.load_staging(intent.staging_id, for_update=for_update)
        if facts is None:
            raise ControlledFileWorkflowError("controlled_file_staging_not_found", "staging 不存在")
        if facts.registration_status is ControlledFileStagingRegistrationStatus.UNKNOWN:
            raise ControlledFileWorkflowError(
                "controlled_file_reconciliation_required", "staging 狀態需要對帳"
            )
        if facts.registration_status is not ControlledFileStagingRegistrationStatus.UNREGISTERED:
            raise ControlledFileWorkflowError("controlled_file_already_registered", "staging 已 Apply")
        if facts.version <= 0:
            raise ControlledFileWorkflowError("controlled_file_staging_version_invalid", "staging 版本無效")
        if facts.stored_intent != intent:
            raise ControlledFileWorkflowError(
                "controlled_file_staging_intent_mismatch",
                "staging owner 與用途已變更",
            )
        _require_current_purpose(intent.owner, intent.purpose, facts.staging.mime_type)

        now = _utc(self._clock.now())
        expires_at = _utc(facts.staging.expires_at)
        if now >= expires_at:
            raise ControlledFileWorkflowError("controlled_file_staging_expired", "staging 已過期")
        content = self._storage.read_staged(
            intent.staging_id, expected_sha256=facts.staging.sha256_digest
        )
        digest = hashlib.sha256(content.content).hexdigest()
        if (
            content.staging_id != intent.staging_id
            or digest != facts.staging.sha256_digest
            or content.sha256_digest != digest
            or len(content.content) != facts.staging.size_bytes
            or _utc(content.expires_at) != expires_at
        ):
            raise ControlledFileWorkflowError(
                "controlled_file_staging_drift", "staging bytes 與 metadata 不一致"
            )

        candidate = ControlledFileCandidate(
            staging_id=intent.staging_id,
            staging_version=facts.version,
            owner=intent.owner,
            purpose=intent.purpose,
            subject_reference=intent.subject_reference,
            object_key=intent.object_key,
            logical_folder=intent.logical_folder,
            filename=facts.staging.filename,
            mime_type=facts.staging.mime_type,
            size_bytes=facts.staging.size_bytes,
            sha256_digest=digest,
            expires_at=expires_at,
        )
        blockers = () if self._repository.owner_subject_exists(intent, for_update=for_update) else (
            "owner_subject_not_found",
        )
        return ControlledFilePreview(
            candidate=candidate,
            preview_fingerprint=fingerprint_payload(_candidate_payload(candidate)),
            expected_staging_version=ExpectedVersion(facts.version),
            blockers=blockers,
        )


def _validate_intent(intent: ControlledFileIntent) -> None:
    if _STAGING_ID.fullmatch(intent.staging_id) is None:
        raise ValueError("controlled file staging identity is invalid")
    _validate_owner_fields(
        intent.owner,
        intent.purpose,
        intent.subject_reference,
        intent.object_key,
        intent.logical_folder,
    )


def _validate_owner_fields(owner, purpose, subject_reference, object_key, logical_folder) -> None:
    if purpose not in _ALLOWED_PURPOSES.get(owner, frozenset()):
        raise ValueError("controlled file owner/purpose pairing is invalid")
    for field_name, raw_value in (
        ("subject_reference", subject_reference),
        ("object_key", object_key),
        ("logical_folder", logical_folder),
    ):
        value = require_canonical_text(raw_value, field_name, 500)
        if "\\" in value or "://" in value or value.casefold().startswith("file:"):
            raise ValueError(f"{field_name} must not contain a storage locator")


def _require_current_purpose(owner, purpose, mime_type=None):
    policy = FILE_PURPOSE_REGISTRY.get(purpose)
    if policy is None:
        raise ControlledFileWorkflowError("controlled_file_purpose_retired", "此用途已停止建立永久檔案，歷史檔案仍可查閱。")
    if owner.value != policy.owner_domain:
        raise ControlledFileWorkflowError("controlled_file_purpose_owner_required", "此檔案用途須由原 owner 處理。")
    if mime_type is not None and (not isinstance(mime_type, str) or mime_type.lower() not in policy.file_format):
        raise ControlledFileWorkflowError("controlled_file_purpose_format_invalid", "檔案格式不符合此用途。")


def _staging_command_payload(
    command: StageControlledFile, result: ControlledFileStagingResult
) -> dict[str, object]:
    return {
        "actor": command.actor.actor_id,
        "filename": result.filename,
        "logical_folder": command.logical_folder,
        "mime_type": result.mime_type,
        "object_key": command.object_key,
        "owner": command.owner.value,
        "purpose": command.purpose.value,
        "sha256_digest": result.sha256_digest,
        "size_bytes": result.size_bytes,
        "subject_reference": command.subject_reference,
        "type": "controlled_file_staging",
    }


def _candidate_payload(candidate: ControlledFileCandidate) -> dict[str, object]:
    return {
        "expires_at": candidate.expires_at.isoformat(),
        "filename": candidate.filename,
        "logical_folder": candidate.logical_folder,
        "mime_type": candidate.mime_type,
        "object_key": candidate.object_key,
        "owner": candidate.owner.value,
        "purpose": candidate.purpose.value,
        "sha256_digest": candidate.sha256_digest,
        "size_bytes": candidate.size_bytes,
        "staging_id": candidate.staging_id,
        "staging_version": candidate.staging_version,
        "subject_reference": candidate.subject_reference,
    }


def _command_fingerprint(command: ApplyControlledFile) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "actor": command.actor.actor_id,
            "expected_staging_version": command.expected_staging_version.value,
            "intent": {
                "logical_folder": command.intent.logical_folder,
                "object_key": command.intent.object_key,
                "owner": command.intent.owner.value,
                "purpose": command.intent.purpose.value,
                "staging_id": command.intent.staging_id,
                "subject_reference": command.intent.subject_reference,
            },
            "preview_fingerprint": command.preview_fingerprint.value,
            "type": "controlled_file_apply",
        }
    )


def _replay(
    stored: StoredControlledFileApplyReceipt,
    command_fingerprint: PreviewFingerprint,
) -> ControlledFileApplyReceipt:
    if stored.command_fingerprint != command_fingerprint:
        raise ControlledFileWorkflowError(
            "idempotency_mismatch", "相同重播識別對應不同命令"
        )
    return replace(stored.receipt, outcome=ControlledFileApplyOutcome.REPLAYED)


def _receipt_id(key: IdempotencyKey) -> str:
    return f"cfr_{hashlib.sha256(key.value.encode('utf-8')).hexdigest()[:32]}"


def _register_postcommit_finalize(
    unit_of_work: UnitOfWork,
    storage: ControlledFileStoragePort,
    readback: ControlledFileReadback,
    staging_id: str,
) -> None:
    """Attach an integrity-only finalizer when the UoW supports completion hooks.

    The DB transaction remains the sole owner of metadata/reference/receipt.  A
    completion hook is intentionally best-effort infrastructure composition: a
    failure happens after commit and must be surfaced as an unknown post-commit
    outcome for reconciliation, never converted into a rollback or object delete.
    The baseline MySQL UoW has no hook and therefore leaves the durable
    reconciliation path as the owner of any later verification.
    """
    add_after_commit = getattr(unit_of_work, "add_after_commit", None)
    add_after_completion = getattr(unit_of_work, "add_after_completion", None)
    finalize = getattr(storage, "finalize_staged", None)
    if not callable(finalize):
        return

    def run_finalize() -> None:
        # Some legacy UoWs expose only an ``after_completion`` hook and invoke
        # it for both commit and rollback.  Never verify (or otherwise touch)
        # bytes after a failed DB commit.  Native UoWs expose this state as a
        # private implementation detail; custom test UoWs without it are
        # treated as commit-only hooks for backwards compatibility.
        if getattr(unit_of_work, "_committed", False) is not True:
            return
        try:
            finalize(staging_id, expected_sha256=readback.sha256_digest)
        except ControlledFileWorkflowError:
            raise
        except Exception as error:  # noqa: BLE001 - convert provider/storage failure to typed blocker
            retryable = bool(getattr(error, "retryable", False))
            raise ControlledFileWorkflowError(
                "controlled_file_post_commit_reconciliation_required",
                "資料庫已提交，但檔案完整性尚待對帳",
                retryable=retryable,
            ) from error

    if callable(add_after_commit):
        add_after_commit(run_finalize)
    elif callable(add_after_completion) and isinstance(
        getattr(unit_of_work, "_committed", None), bool
    ):
        add_after_completion(run_finalize)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ControlledFileWorkflowError("business_time_invalid", "時間必須包含時區")
    return value.astimezone(timezone.utc)


__all__ = [
    "ApplyControlledFile",
    "ControlledFileApplyOutcome",
    "ControlledFileApplyReceipt",
    "ControlledFileCandidate",
    "ControlledFileCommandClaim",
    "ControlledFileDownloadReference",
    "ControlledFileIntent",
    "ControlledFileOwner",
    "ControlledFilePostCommitFinalizeIntent",
    "ControlledFilePreview",
    "ControlledFilePurpose",
    "ControlledFileReadback",
    "ControlledFileStagingFacts",
    "ControlledFileWorkflow",
    "ControlledFileWorkflowError",
    "ControlledFileWorkflowRepository",
    "StageControlledFile",
    "StoredControlledFileApplyReceipt",
]
