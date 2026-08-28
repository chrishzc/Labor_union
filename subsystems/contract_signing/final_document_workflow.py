"""
File: final_document_workflow.py
Description: 以單一 outer UoW 編排最終 PDF、Orders completion、receipt 與安全 readback。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Protocol

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    final_signed_contract_blockers,
)
from domains.orders.contract_completion import ContractCompletionIntent
from shared_kernel.clock import BusinessClock
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.contract_signing.final_document_preview_token import (
    FinalDocumentPreviewTokenError,
    HmacFinalDocumentPreviewTokenCodec,
)
from subsystems.controlled_files.workflow import (
    ApplyControlledFile,
    ControlledFileApplyReceipt,
    ControlledFileIntent,
    ControlledFilePreview,
)
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionApplyRequest,
    ContractCompletionPreview,
    ContractCompletionReceipt,
)


@dataclass(frozen=True, slots=True)
class PreviewFinalSignedContractUpload:
    session_id: str
    case_no: str
    expected_status_version: ExpectedVersion
    controlled_file_intent: ControlledFileIntent


@dataclass(frozen=True, slots=True)
class FinalSignedContractPreview:
    preview_token: str
    expected_status_version: int
    expected_staging_version: int
    filename: str
    mime_type: str
    size_bytes: int
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ApplyFinalSignedContractUpload:
    preview: PreviewFinalSignedContractUpload
    expected_staging_version: ExpectedVersion
    preview_token: str
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "final contract completion reason", 500)


@dataclass(frozen=True, slots=True)
class FinalContractDocumentReadback:
    final_document_id: str
    case_no: str
    file_id: str
    version: int
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    applied_at: datetime

    def __post_init__(self) -> None:
        require_canonical_text(self.final_document_id, "final document ID", 64)
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.file_id, "controlled file ID", 64)
        require_positive_integer(self.version, "final document version")
        if self.mime_type != "application/pdf":
            raise ValueError("final contract document must be PDF")
        require_positive_integer(self.size_bytes, "final document size")


@dataclass(frozen=True, slots=True)
class FinalSignedContractApplyReceipt:
    receipt_id: str
    session_id: str
    resulting_status_version: int
    resulting_state: ExternalSigningState
    document: FinalContractDocumentReadback
    contract_identity: str
    replayed: bool = False
    schema_version: str = "final-signed-contract-apply-receipt.v1"


@dataclass(frozen=True, slots=True)
class StoredFinalSignedContractReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: FinalSignedContractApplyReceipt


class FinalDocumentWorkflowError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        category: str = "conflict",
        retryable: bool = False,
        current_version: int | None = None,
    ) -> None:
        self.code = code
        self.category = category
        self.retryable = retryable
        self.current_version = current_version
        super().__init__(code)


class FinalDocumentRepository(Protocol):
    def load_final_session(
        self, case_no: str, session_id: str, *, for_update: bool
    ) -> ExternalSigningSessionFacts | None: ...

    def find_final_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredFinalSignedContractReceipt | None: ...

    def register_final_document(
        self,
        session: ExternalSigningSessionFacts,
        controlled_file: ControlledFileApplyReceipt,
        *,
        actor: ActorContext,
        contract_identity: str,
        applied_at: datetime,
    ) -> FinalContractDocumentReadback: ...

    def complete_session_and_recovery(
        self,
        session: ExternalSigningSessionFacts,
        document: FinalContractDocumentReadback,
        *,
        resulting_status_version: int,
        applied_at: datetime,
    ) -> None: ...

    def save_final_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredFinalSignedContractReceipt,
        correlation_id: CorrelationId,
        *,
        expected_status_version: int,
        applied_at: datetime,
    ) -> None: ...

    def get_final_document(
        self, case_no: str
    ) -> FinalContractDocumentReadback | None: ...


class BorrowedControlledFileWorkflow(Protocol):
    def preview(self, intent: ControlledFileIntent) -> ControlledFilePreview: ...

    def apply_borrowed(
        self, command: ApplyControlledFile
    ) -> ControlledFileApplyReceipt: ...


class BorrowedContractCompletionWorkflow(Protocol):
    def preview(
        self, case_no: str, intent: ContractCompletionIntent
    ) -> ContractCompletionPreview: ...

    def apply_borrowed(
        self, request: ContractCompletionApplyRequest
    ) -> ContractCompletionReceipt: ...


class FinalSignedContractWorkflow:
    def __init__(
        self,
        repository: FinalDocumentRepository,
        controlled_files: BorrowedControlledFileWorkflow,
        contract_completion: BorrowedContractCompletionWorkflow,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: BusinessClock,
        token_codec: HmacFinalDocumentPreviewTokenCodec,
    ) -> None:
        self._repository = repository
        self._controlled_files = controlled_files
        self._contract_completion = contract_completion
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._token_codec = token_codec

    def preview(
        self, command: PreviewFinalSignedContractUpload
    ) -> FinalSignedContractPreview:
        session, file_preview, completion_preview = self._fresh_preview(
            command, for_update=False
        )
        blockers = _blockers(session, file_preview)
        payload = _preview_payload(session, file_preview, completion_preview)
        candidate = file_preview.candidate
        return FinalSignedContractPreview(
            preview_token=self._token_codec.issue(payload),
            expected_status_version=session.status_version,
            expected_staging_version=file_preview.expected_staging_version.value,
            filename=candidate.filename,
            mime_type=candidate.mime_type,
            size_bytes=candidate.size_bytes,
            blockers=blockers,
        )

    def apply(
        self, command: ApplyFinalSignedContractUpload
    ) -> FinalSignedContractApplyReceipt:
        command_fingerprint = _command_fingerprint(command)
        with self._unit_of_work_factory() as unit_of_work:
            stored = self._repository.find_final_receipt(
                command.idempotency_key, for_update=True
            )
            if stored is not None:
                receipt = _replay(stored, command_fingerprint)
                unit_of_work.commit()
                return receipt

            session, file_preview, completion_preview = self._fresh_preview(
                command.preview, for_update=True
            )
            blockers = _blockers(session, file_preview)
            if blockers:
                raise FinalDocumentWorkflowError(blockers[0], category="domain_blocked")
            if file_preview.expected_staging_version != command.expected_staging_version:
                raise FinalDocumentWorkflowError("final_document_staging_version_stale")
            try:
                self._token_codec.verify(
                    command.preview_token,
                    _preview_payload(session, file_preview, completion_preview),
                )
            except FinalDocumentPreviewTokenError as error:
                raise FinalDocumentWorkflowError(error.code) from error

            orders_receipt = self._contract_completion.apply_borrowed(
                _orders_apply(command, completion_preview)
            )
            controlled_receipt = self._controlled_files.apply_borrowed(
                _controlled_apply(command, file_preview)
            )
            now = _utc(self._clock.now())
            document = self._repository.register_final_document(
                session,
                controlled_receipt,
                actor=command.actor,
                contract_identity=orders_receipt.contract_identity,
                applied_at=now,
            )
            resulting_version = session.status_version + 1
            self._repository.complete_session_and_recovery(
                session,
                document,
                resulting_status_version=resulting_version,
                applied_at=now,
            )
            receipt = FinalSignedContractApplyReceipt(
                receipt_id=_receipt_id(command.idempotency_key),
                session_id=session.session_id,
                resulting_status_version=resulting_version,
                resulting_state=ExternalSigningState.COMPLETED,
                document=document,
                contract_identity=orders_receipt.contract_identity,
            )
            self._repository.save_final_receipt(
                command.idempotency_key,
                StoredFinalSignedContractReceipt(command_fingerprint, receipt),
                command.correlation_id,
                expected_status_version=session.status_version,
                applied_at=now,
            )
            unit_of_work.commit()
            return receipt

    def readback(self, case_no: str) -> FinalContractDocumentReadback:
        require_canonical_text(case_no, "case number", 50)
        result = self._repository.get_final_document(case_no)
        if result is None:
            raise FinalDocumentWorkflowError(
                "final_contract_document_not_found", category="not_found"
            )
        return result

    def read_receipt(
        self, key: IdempotencyKey
    ) -> FinalSignedContractApplyReceipt:
        stored = self._repository.find_final_receipt(key, for_update=False)
        if stored is None:
            raise FinalDocumentWorkflowError(
                "final_contract_receipt_not_found", category="not_found"
            )
        return stored.receipt

    def _fresh_preview(self, command, *, for_update):
        session = self._repository.load_final_session(
            command.case_no, command.session_id, for_update=for_update
        )
        if session is None:
            raise FinalDocumentWorkflowError(
                "external_signing_session_not_found", category="not_found"
            )
        if session.status_version != command.expected_status_version.value:
            raise FinalDocumentWorkflowError(
                "external_signing_status_version_stale",
                current_version=session.status_version,
            )
        completion_preview = self._contract_completion.preview(
            command.case_no, ContractCompletionIntent.CONFIRM_COMPLETED
        )
        file_preview = self._controlled_files.preview(command.controlled_file_intent)
        return session, file_preview, completion_preview


def _blockers(
    session: ExternalSigningSessionFacts,
    file_preview: ControlledFilePreview,
) -> tuple[str, ...]:
    result = [item.value for item in final_signed_contract_blockers(session)]
    result.extend(file_preview.blockers)
    if file_preview.candidate.mime_type != "application/pdf":
        result.append("final_contract_document_mime_invalid")
    return tuple(sorted(set(result)))


def _preview_payload(session, file_preview, completion_preview):
    candidate = file_preview.candidate
    return {
        "case_no": session.case_no,
        "session_id": session.session_id,
        "status_version": session.status_version,
        "document_set_fingerprint": session.document_set_fingerprint,
        "staging_fingerprint": file_preview.preview_fingerprint.value,
        "staging_version": file_preview.expected_staging_version.value,
        "staging_sha256": candidate.sha256_digest,
        "staging_size": candidate.size_bytes,
        "orders_fingerprint": completion_preview.fingerprint.value,
        "orders_version": completion_preview.candidate.expected_order_version,
        "client_finance_version": (
            completion_preview.client_finance_impact.expected_account_version
        ),
    }


def _orders_apply(command, preview):
    key = _derived_key(command.idempotency_key, "orders")
    return ContractCompletionApplyRequest(
        case_no=command.preview.case_no,
        intent=ContractCompletionIntent.CONFIRM_COMPLETED,
        expected_order_version=ExpectedVersion(preview.candidate.expected_order_version),
        expected_client_finance_version=ExpectedVersion(
            preview.client_finance_impact.expected_account_version
        ),
        preview_fingerprint=preview.fingerprint,
        idempotency_key=key,
        actor=command.actor,
        reason=command.reason,
        correlation_id=command.correlation_id,
    )


def _controlled_apply(command, preview):
    return ApplyControlledFile(
        intent=command.preview.controlled_file_intent,
        expected_staging_version=command.expected_staging_version,
        preview_fingerprint=preview.preview_fingerprint,
        idempotency_key=_derived_key(command.idempotency_key, "file"),
        actor=command.actor,
        correlation_id=command.correlation_id,
    )


def _command_fingerprint(command):
    return fingerprint_payload(
        {
            "session_id": command.preview.session_id,
            "case_no": command.preview.case_no,
            "expected_status_version": command.preview.expected_status_version.value,
            "staging_id": command.preview.controlled_file_intent.staging_id,
            "expected_staging_version": command.expected_staging_version.value,
            "preview_token": command.preview_token,
            "actor": command.actor.actor_id,
            "reason": command.reason,
        }
    )


def _derived_key(parent: IdempotencyKey, lane: str) -> IdempotencyKey:
    digest = hashlib.sha256(f"{parent.value}:{lane}".encode("utf-8")).hexdigest()
    return IdempotencyKey(f"contract-final-{lane}:{digest}")


def _receipt_id(key: IdempotencyKey) -> str:
    suffix = key.value.rsplit(":", 1)[-1]
    if len(suffix) == 32 and all(character in "0123456789abcdef" for character in suffix):
        return f"cesr_{suffix}"
    return f"cesr_{hashlib.sha256(key.value.encode('utf-8')).hexdigest()[:32]}"


def _replay(stored, command_fingerprint):
    if stored.command_fingerprint != command_fingerprint:
        raise FinalDocumentWorkflowError(
            "final_contract_idempotency_mismatch", category="idempotency_mismatch"
        )
    return replace(stored.receipt, replayed=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("business clock must return timezone-aware datetime")
    return value.astimezone(timezone.utc)


__all__ = [
    "ApplyFinalSignedContractUpload",
    "FinalContractDocumentReadback",
    "FinalDocumentRepository",
    "FinalDocumentWorkflowError",
    "FinalSignedContractApplyReceipt",
    "FinalSignedContractPreview",
    "FinalSignedContractWorkflow",
    "PreviewFinalSignedContractUpload",
    "StoredFinalSignedContractReceipt",
]
