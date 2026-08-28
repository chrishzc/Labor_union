"""
File: unsigned_contract_pdf_persistence.py
Description: 編排未簽 PDF render、controlled-file staging 與 caller-owned 單一 Apply 交易保存。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import re
from typing import Protocol

from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
    require_sha256_hex,
)
from subsystems.contract_signing.unsigned_contract_pdf import (
    PrepareUnsignedContractPdf,
    PreparedUnsignedContractPdf,
    UnsignedContractPdfError,
)
from subsystems.controlled_files.contracts import ControlledFileStagingResult
from subsystems.controlled_files.workflow import (
    ApplyControlledFile,
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePreview,
    ControlledFilePurpose,
    StageControlledFile,
)


_RENDERER_IDENTITY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")


@dataclass(frozen=True, slots=True)
class PrepareAndPersistUnsignedContractPdf:
    case_no: str
    source_document_version_id: int
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        PrepareUnsignedContractPdf(
            self.case_no,
            self.source_document_version_id,
            self.actor,
        )
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("unsigned PDF persistence idempotency key is invalid")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("unsigned PDF persistence correlation ID is invalid")


@dataclass(frozen=True, slots=True)
class PersistedUnsignedContractPdf:
    case_no: str
    source_document_version_id: int
    document_version_id: int
    filename: str
    mime_type: str
    size_bytes: int
    replayed: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(
            self.source_document_version_id, "source document version ID"
        )
        require_positive_integer(self.document_version_id, "document version ID")
        require_canonical_text(self.filename, "PDF filename", 255)
        require_canonical_text(self.mime_type, "PDF MIME type", 100)
        require_positive_integer(self.size_bytes, "PDF size")
        if not isinstance(self.replayed, bool):
            raise TypeError("unsigned PDF replay flag must be boolean")


@dataclass(frozen=True, slots=True)
class UnsignedContractPdfPersistenceSource:
    case_no: str
    document_version_id: int
    document_scope: str
    matching_plan_id: int
    matching_segment_id: int | None
    document_target_key: str
    template_key: str
    template_sha256: str
    mapping_sha256: str
    facts_snapshot_sha256: str
    version_number: int
    is_current: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.document_version_id, "document version ID")
        require_canonical_text(self.document_scope, "document scope", 50)
        require_positive_integer(self.matching_plan_id, "matching plan ID")
        if self.matching_segment_id is not None:
            require_positive_integer(self.matching_segment_id, "matching segment ID")
        require_canonical_text(self.document_target_key, "document target key", 100)
        require_canonical_text(self.template_key, "template key", 100)
        require_sha256_hex(self.template_sha256, "template SHA-256")
        require_sha256_hex(self.mapping_sha256, "mapping SHA-256")
        require_sha256_hex(self.facts_snapshot_sha256, "facts snapshot SHA-256")
        require_positive_integer(self.version_number, "document version")
        if self.document_scope == "staff_segment":
            if self.matching_segment_id is None:
                raise ValueError("staff PDF source requires matching segment")
        elif self.document_scope == "client_contract":
            if self.matching_segment_id is not None:
                raise ValueError("client PDF source must not have matching segment")
        else:
            raise ValueError("unsigned PDF source scope is invalid")
        if not isinstance(self.is_current, bool):
            raise TypeError("current source flag must be boolean")


class UnsignedContractPdfPreparationPort(Protocol):
    def prepare(
        self, command: PrepareUnsignedContractPdf
    ) -> PreparedUnsignedContractPdf: ...


class UnsignedContractControlledFilePort(Protocol):
    def stage(self, command: StageControlledFile) -> ControlledFileStagingResult: ...

    def preview(self, intent: ControlledFileIntent) -> ControlledFilePreview: ...

    def apply_borrowed(
        self, command: ApplyControlledFile
    ) -> ControlledFileApplyReceipt: ...


class UnsignedContractPdfPersistenceRepository(Protocol):
    def lock_source_for_persistence(
        self, case_no: str, source_document_version_id: int
    ) -> UnsignedContractPdfPersistenceSource: ...

    def register_persisted_pdf(
        self,
        *,
        source: UnsignedContractPdfPersistenceSource,
        controlled_file_receipt: ControlledFileApplyReceipt,
        renderer_identity: str,
        actor: ActorContext,
    ) -> int: ...


class UnsignedContractPdfPersistenceWorkflow:
    def __init__(
        self,
        application: UnsignedContractPdfPreparationPort,
        controlled_files: UnsignedContractControlledFilePort,
        repository: UnsignedContractPdfPersistenceRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._application = application
        self._controlled_files = controlled_files
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def prepare_and_persist(
        self, command: PrepareAndPersistUnsignedContractPdf
    ) -> PersistedUnsignedContractPdf:
        rendered = self._application.prepare(
            PrepareUnsignedContractPdf(
                command.case_no,
                command.source_document_version_id,
                command.actor,
            )
        )
        renderer_identity = _require_renderer_identity(rendered.renderer_identity)
        stage_key = _derived_key("stage", command.idempotency_key)
        apply_key = _derived_key("apply", command.idempotency_key)
        object_key = (
            f"unsigned-contract:{rendered.source_document_version_id}:"
            f"{renderer_identity}"
        )
        try:
            staging = self._controlled_files.stage(
                StageControlledFile(
                    owner=ControlledFileOwner.CONTRACT_SIGNING,
                    purpose=ControlledFilePurpose.UNSIGNED_CONTRACT,
                    subject_reference=rendered.case_no,
                    object_key=object_key,
                    logical_folder="contracts/unsigned",
                    filename=rendered.filename,
                    mime_type=rendered.mime_type,
                    content=rendered.content,
                    idempotency_key=stage_key,
                    actor=command.actor,
                    correlation_id=command.correlation_id,
                )
            )
            intent = ControlledFileIntent(
                staging_id=staging.staging_id,
                owner=ControlledFileOwner.CONTRACT_SIGNING,
                purpose=ControlledFilePurpose.UNSIGNED_CONTRACT,
                subject_reference=rendered.case_no,
                object_key=object_key,
                logical_folder="contracts/unsigned",
            )
            preview = self._controlled_files.preview(intent)
        except UnsignedContractPdfError:
            raise
        except Exception:
            raise _error(
                "contract_pdf_controlled_file_unavailable",
                "未簽契約 PDF staging 目前無法完成。",
                retryable=True,
            ) from None
        if preview.blockers:
            raise _error(
                "contract_pdf_controlled_file_blocked",
                "未簽契約 PDF staging 尚未符合保存條件。",
            )
        try:
            with self._unit_of_work_factory() as unit_of_work:
                source = self._repository.lock_source_for_persistence(
                    rendered.case_no,
                    rendered.source_document_version_id,
                )
                receipt = self._controlled_files.apply_borrowed(
                    ApplyControlledFile(
                        intent=intent,
                        expected_staging_version=preview.expected_staging_version,
                        preview_fingerprint=preview.preview_fingerprint,
                        idempotency_key=apply_key,
                        actor=command.actor,
                        correlation_id=command.correlation_id,
                    )
                )
                document_version_id = self._repository.register_persisted_pdf(
                    source=source,
                    controlled_file_receipt=receipt,
                    renderer_identity=renderer_identity,
                    actor=command.actor,
                )
                unit_of_work.commit()
        except UnsignedContractPdfError:
            raise
        except Exception:
            raise _error(
                "contract_pdf_persistence_failed",
                "未簽契約 PDF 保存失敗。",
                retryable=True,
            ) from None
        return PersistedUnsignedContractPdf(
            case_no=rendered.case_no,
            source_document_version_id=rendered.source_document_version_id,
            document_version_id=document_version_id,
            filename=receipt.readback.filename,
            mime_type=receipt.readback.mime_type,
            size_bytes=receipt.readback.size_bytes,
            replayed=receipt.outcome is ControlledFileApplyOutcome.REPLAYED,
        )


def _derived_key(stage: str, source: IdempotencyKey) -> IdempotencyKey:
    digest = hashlib.sha256(source.value.encode("utf-8")).hexdigest()
    return IdempotencyKey(f"unsigned-pdf-{stage}:{digest}")


def _require_renderer_identity(value: str) -> str:
    identity = value.strip().casefold()
    if _RENDERER_IDENTITY.fullmatch(identity) is None:
        raise _error(
            "contract_pdf_renderer_identity_invalid",
            "未簽契約 PDF renderer 身分無效。",
        )
    return identity


def _error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> UnsignedContractPdfError:
    return UnsignedContractPdfError(
        category="unavailable" if retryable else "domain_blocked",
        code=code,
        message=message,
        retryable=retryable,
    )


__all__ = [
    "PersistedUnsignedContractPdf",
    "PrepareAndPersistUnsignedContractPdf",
    "UnsignedContractPdfPersistenceSource",
    "UnsignedContractPdfPersistenceRepository",
    "UnsignedContractPdfPersistenceWorkflow",
]
