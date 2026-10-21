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
    SignedContractDocumentTarget,
    require_complete_signed_contract_documents,
    require_signed_contract_target,
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
    ControlledFileOwner,
    ControlledFilePurpose,
)
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionApplyRequest,
    ContractCompletionPreview,
    ContractCompletionQuery,
    ContractCompletionReceipt,
)


@dataclass(frozen=True, slots=True)
class SignedContractDocumentUpload:
    target: SignedContractDocumentTarget
    controlled_file_intent: ControlledFileIntent
    expected_staging_version: ExpectedVersion


@dataclass(frozen=True, slots=True)
class PreviewFinalSignedContractUpload:
    session_id: str
    case_no: str
    expected_status_version: ExpectedVersion
    documents: tuple[SignedContractDocumentUpload, ...]


@dataclass(frozen=True, slots=True)
class SignedContractDocumentPreview:
    target: SignedContractDocumentTarget
    staging_id: str
    expected_staging_version: int
    filename: str
    mime_type: str
    size_bytes: int
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FinalSignedContractPreview:
    preview_token: str
    expected_status_version: int
    documents: tuple[SignedContractDocumentPreview, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExistingTestingContractCompletion:
    """Recover test documents without repeating an existing Orders completion."""
    order: ContractCompletionQuery
    commitment_id: int


@dataclass(frozen=True, slots=True)
class ApplyFinalSignedContractUpload:
    preview: PreviewFinalSignedContractUpload
    preview_token: str
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    testing_skip_confirmed: bool = False

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "final contract completion reason", 500, allow_empty=True)


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
class SignedContractDocumentReadback:
    target: SignedContractDocumentTarget
    file_id: str
    version: int
    filename: str
    mime_type: str
    size_bytes: int

    def __post_init__(self) -> None:
        require_canonical_text(self.file_id, "signed contract file ID", 64)
        require_canonical_text(self.filename, "signed contract filename", 255)
        require_positive_integer(self.version, "signed contract file version")
        require_positive_integer(self.size_bytes, "signed contract file size")
        if self.mime_type != "application/pdf":
            raise ValueError("signed contract must be PDF")


def signed_contract_object_key(session_id: str, target: SignedContractDocumentTarget) -> str:
    return f"signed-contract:{session_id}:{target.key}:v{target.document_version_id}"


def signed_contract_intent(case_no: str, session_id: str, target: SignedContractDocumentTarget, staging_id: str) -> ControlledFileIntent:
    return ControlledFileIntent(
        staging_id, ControlledFileOwner.CONTRACT_SIGNING,
        ControlledFilePurpose.FINAL_SIGNED_CONTRACT, case_no,
        signed_contract_object_key(session_id, target), f"contract-signing/{case_no}",
    )


@dataclass(frozen=True, slots=True)
class FinalSignedContractApplyReceipt:
    receipt_id: str
    session_id: str
    resulting_status_version: int
    resulting_state: ExternalSigningState
    document: FinalContractDocumentReadback
    contract_identity: str
    documents: tuple[SignedContractDocumentReadback, ...] = ()
    replayed: bool = False
    schema_version: str = "final-signed-contract-apply-receipt.v1"


@dataclass(frozen=True, slots=True)
class StoredFinalSignedContractReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: FinalSignedContractApplyReceipt


@dataclass(frozen=True, slots=True)
class FinalSigningPrerequisiteCommand:
    case_no: str
    matching_plan_id: int
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


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
        commitment_id: int,
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

    def get_final_documents(self, case_no: str) -> tuple[SignedContractDocumentReadback, ...]: ...

    def load_staged_document(self, case_no: str, object_key: str, target: SignedContractDocumentTarget) -> SignedContractDocumentPreview | None: ...

    def get_final_document(
        self, case_no: str
    ) -> FinalContractDocumentReadback | None: ...


class BorrowedControlledFileWorkflow(Protocol):
    def preview(self, intent: ControlledFileIntent) -> ControlledFilePreview: ...

    def apply_borrowed(
        self, command: ApplyControlledFile
    ) -> ControlledFileApplyReceipt: ...


class BorrowedContractCompletionWorkflow(Protocol):
    def query(self, case_no: str, *, for_update: bool = False) -> ContractCompletionQuery: ...

    def preview_with_identity(
        self,
        case_no: str,
        intent: ContractCompletionIntent,
        contract_identity: str,
        *,
        fallback_service_dates: tuple,
    ) -> ContractCompletionPreview: ...

    def apply_borrowed_with_identity(
        self, request: ContractCompletionApplyRequest, contract_identity: str
    ) -> ContractCompletionReceipt: ...


class FinalSigningPrerequisitePort(Protocol):
    def signing_blockers(self, facts: ExternalSigningSessionFacts, *, for_update: bool = False) -> tuple[str, ...]: ...

    def existing_commitment(
        self, facts: ExternalSigningSessionFacts, *, for_update: bool
    ) -> int | None: ...

    def preview_service_dates(
        self, facts: ExternalSigningSessionFacts
    ) -> tuple: ...

    def establish_prerequisites(
        self,
        command: FinalSigningPrerequisiteCommand,
        facts: ExternalSigningSessionFacts,
        resulting_status_version: int,
    ): ...


class FinalSignedContractWorkflow:
    def __init__(
        self,
        repository: FinalDocumentRepository,
        controlled_files: BorrowedControlledFileWorkflow,
        contract_completion: BorrowedContractCompletionWorkflow,
        prerequisites: FinalSigningPrerequisitePort,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: BusinessClock,
        token_codec: HmacFinalDocumentPreviewTokenCodec,
    ) -> None:
        self._repository = repository
        self._controlled_files = controlled_files
        self._contract_completion = contract_completion
        self._prerequisites = prerequisites
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._token_codec = token_codec

    def validate_target(self, case_no: str, session_id: str, expected_status_version: ExpectedVersion, target: SignedContractDocumentTarget) -> ExternalSigningSessionFacts:
        session = self._load_session(case_no, session_id, expected_status_version, for_update=False)
        require_signed_contract_target(session, target)
        blockers = final_signed_contract_blockers(session)
        if blockers:
            raise FinalDocumentWorkflowError(blockers[0].value, category="domain_blocked")
        return session

    def preview_document(self, case_no: str, session_id: str, expected_status_version: ExpectedVersion, document: SignedContractDocumentUpload) -> SignedContractDocumentPreview:
        self.validate_target(case_no, session_id, expected_status_version, document.target)
        self._require_document_intent(case_no, session_id, document)
        preview = self._controlled_files.preview(document.controlled_file_intent)
        if preview.expected_staging_version != document.expected_staging_version:
            raise FinalDocumentWorkflowError("final_document_staging_version_stale")
        return _document_preview(document, preview)

    def staged_documents(self, case_no: str, session_id: str, expected_status_version: ExpectedVersion) -> tuple[SignedContractDocumentPreview, ...]:
        session = self._load_session(case_no, session_id, expected_status_version, for_update=False)
        targets = (SignedContractDocumentTarget("client", None, session.client_document_version_id),) + tuple(
            SignedContractDocumentTarget("staff", row.matching_segment_id, row.document_version_id) for row in session.staff_targets
        )
        return tuple(value for target in targets if (value := self._repository.load_staged_document(
            case_no, signed_contract_object_key(session_id, target), target
        )) is not None)

    def preview(self, command: PreviewFinalSignedContractUpload) -> FinalSignedContractPreview:
        session, file_previews, completion_preview = self._fresh_preview(command, for_update=False)
        return FinalSignedContractPreview(
            preview_token=self._token_codec.issue(_preview_payload(session, file_previews, completion_preview)),
            expected_status_version=session.status_version,
            documents=tuple(_document_preview(upload, preview) for upload, preview in file_previews),
            blockers=_blockers(session, file_previews),
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

            session, file_previews, completion_preview = self._fresh_preview(
                command.preview, for_update=True
            )
            testing_documents = tuple(
                preview.candidate.filename.startswith("TEST-ONLY-")
                for _, preview in file_previews
            )
            if (
                command.testing_skip_confirmed and not all(testing_documents)
                or not command.testing_skip_confirmed and any(testing_documents)
            ):
                raise FinalDocumentWorkflowError("final_contract_testing_confirmation_required")
            blockers = _blockers(session, file_previews)
            if blockers:
                raise FinalDocumentWorkflowError(blockers[0], category="domain_blocked")
            try:
                self._token_codec.verify(
                    command.preview_token,
                    _preview_payload(session, file_previews, completion_preview),
                )
            except FinalDocumentPreviewTokenError as error:
                raise FinalDocumentWorkflowError(error.code) from error

            resulting_version = session.status_version + 1
            if isinstance(completion_preview, ExistingTestingContractCompletion):
                commitment_id = completion_preview.commitment_id
                contract_identity = completion_preview.order.facts.contract_identity
            else:
                prerequisites = self._prerequisites.establish_prerequisites(
                    _prerequisite_command(command, session),
                    session,
                    resulting_version,
                )
                commitment_id = prerequisites.commitment_id
                completion_preview = self._completion_preview(session, file_previews, for_update=True)
                contract_identity = completion_preview.candidate.contract_identity
                orders_receipt = self._contract_completion.apply_borrowed_with_identity(
                    _orders_apply(command, completion_preview), contract_identity
                )
                contract_identity = orders_receipt.contract_identity
            controlled_receipts = tuple(
                self._controlled_files.apply_borrowed(_controlled_apply(command, upload, file_preview))
                for upload, file_preview in file_previews
            )
            now = _utc(self._clock.now())
            document = self._repository.register_final_document(
                session,
                controlled_receipts[0],
                actor=command.actor,
                contract_identity=contract_identity,
                applied_at=now,
            )
            self._repository.complete_session_and_recovery(
                session,
                document,
                commitment_id=commitment_id,
                resulting_status_version=resulting_version,
                applied_at=now,
            )
            receipt = FinalSignedContractApplyReceipt(
                receipt_id=_receipt_id(command.idempotency_key),
                session_id=session.session_id,
                resulting_status_version=resulting_version,
                resulting_state=ExternalSigningState.COMPLETED,
                document=document,
                contract_identity=contract_identity,
                documents=tuple(SignedContractDocumentReadback(
                    upload.target, controlled.readback.file_id,
                    controlled.readback.version, controlled.readback.filename,
                    controlled.readback.mime_type, controlled.readback.size_bytes,
                ) for (upload, _), controlled in zip(file_previews, controlled_receipts, strict=True)),
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

    def readback_documents(self, case_no: str) -> tuple[SignedContractDocumentReadback, ...]:
        self.readback(case_no)
        return self._repository.get_final_documents(case_no)

    def read_receipt(
        self, key: IdempotencyKey
    ) -> FinalSignedContractApplyReceipt:
        stored = self._repository.find_final_receipt(key, for_update=False)
        if stored is None:
            raise FinalDocumentWorkflowError(
                "final_contract_receipt_not_found", category="not_found"
            )
        return stored.receipt

    def _load_session(self, case_no, session_id, expected_status_version, *, for_update):
        session = self._repository.load_final_session(case_no, session_id, for_update=for_update)
        if session is None:
            raise FinalDocumentWorkflowError("external_signing_session_not_found", category="not_found")
        if session.status_version != expected_status_version.value:
            raise FinalDocumentWorkflowError("external_signing_status_version_stale", current_version=session.status_version)
        return session

    def _require_document_intent(self, case_no, session_id, document):
        expected = signed_contract_intent(case_no, session_id, document.target, document.controlled_file_intent.staging_id)
        if expected != document.controlled_file_intent:
            raise FinalDocumentWorkflowError("final_signed_contract_target_mismatch")

    def _fresh_preview(self, command, *, for_update):
        session = self._load_session(command.case_no, command.session_id, command.expected_status_version, for_update=for_update)
        require_complete_signed_contract_documents(session, tuple(row.target for row in command.documents))
        if len({row.controlled_file_intent.staging_id for row in command.documents}) != len(command.documents):
            raise FinalDocumentWorkflowError("final_signed_contract_target_mismatch")
        ordered = sorted(command.documents, key=lambda row: (row.target.scope != "client", row.target.matching_segment_id or 0))
        previews = []
        for row in ordered:
            self._require_document_intent(command.case_no, command.session_id, row)
            preview = self._controlled_files.preview(row.controlled_file_intent)
            if preview.expected_staging_version != row.expected_staging_version:
                raise FinalDocumentWorkflowError("final_document_staging_version_stale")
            previews.append((row, preview))
        file_previews = tuple(previews)
        completion_preview = self._completion_preview(session, file_previews, for_update=for_update)
        return session, file_previews, completion_preview

    def _completion_preview(self, session, file_previews, *, for_update=False):
        identity = _contract_identity(file_previews)
        if all(preview.candidate.filename.startswith("TEST-ONLY-") for _, preview in file_previews):
            current = self._contract_completion.query(session.case_no, for_update=for_update)
            if current.facts.contract_completed:
                if current.facts.contract_identity is None:
                    raise FinalDocumentWorkflowError("contract_identity_missing")
                commitment_id = self._prerequisites.existing_commitment(session, for_update=for_update)
                if commitment_id is None:
                    raise FinalDocumentWorkflowError("contract_testing_completed_commitment_missing")
                return ExistingTestingContractCompletion(current, commitment_id)
            if current.facts.contract_identity is not None:
                identity = current.facts.contract_identity
        blockers = self._prerequisites.signing_blockers(session, for_update=for_update)
        if blockers:
            raise FinalDocumentWorkflowError(blockers[0], category="domain_blocked")
        return self._contract_completion.preview_with_identity(
            session.case_no, ContractCompletionIntent.CONFIRM_COMPLETED,
            identity,
            fallback_service_dates=self._prerequisites.preview_service_dates(session),
        )


def _document_preview(upload, preview):
    return SignedContractDocumentPreview(
        upload.target, preview.candidate.staging_id,
        preview.expected_staging_version.value, preview.candidate.filename,
        preview.candidate.mime_type, preview.candidate.size_bytes, tuple(preview.blockers),
    )


def _blockers(session, file_previews):
    result = [item.value for item in final_signed_contract_blockers(session)]
    for _, preview in file_previews:
        result.extend(preview.blockers)
        if preview.candidate.mime_type != "application/pdf":
            result.append("final_contract_document_mime_invalid")
    return tuple(dict.fromkeys(result))


def _preview_payload(session, file_previews, completion_preview):
    payload = {
        "case_no": session.case_no, "session_id": session.session_id,
        "status_version": session.status_version,
        "document_set_fingerprint": session.document_set_fingerprint,
        "documents": [{
            "target": upload.target.key, "unsigned_version": upload.target.document_version_id,
            "staging_id": preview.candidate.staging_id,
            "staging_fingerprint": preview.preview_fingerprint.value,
            "staging_version": preview.expected_staging_version.value,
            "staging_sha256": preview.candidate.sha256_digest,
            "staging_size": preview.candidate.size_bytes,
        } for upload, preview in file_previews],
    }
    if isinstance(completion_preview, ExistingTestingContractCompletion):
        payload.update({
            "existing_testing_completion": True,
            "contract_identity": completion_preview.order.facts.contract_identity,
            "orders_version": completion_preview.order.facts.aggregate_version,
            "commitment_id": completion_preview.commitment_id,
        })
    else:
        payload.update({
            "orders_fingerprint": completion_preview.fingerprint.value,
            "orders_version": completion_preview.candidate.expected_order_version,
            "client_finance_version": completion_preview.client_finance_impact.expected_account_version,
        })
    return payload


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


def _contract_identity(file_previews) -> str:
    identity = fingerprint_payload({"documents": [
        {"target": upload.target.key, "unsigned_version": upload.target.document_version_id,
         "sha256": preview.candidate.sha256_digest}
        for upload, preview in file_previews
    ]})
    return f"external-final-set:{identity.value}"


def _prerequisite_command(command, session):
    return FinalSigningPrerequisiteCommand(
        case_no=session.case_no,
        matching_plan_id=session.matching_plan_id,
        actor=command.actor,
        idempotency_key=_derived_key(command.idempotency_key, "prerequisites"),
        correlation_id=command.correlation_id,
    )


def _controlled_apply(command, upload, preview):
    return ApplyControlledFile(
        intent=upload.controlled_file_intent,
        expected_staging_version=upload.expected_staging_version,
        preview_fingerprint=preview.preview_fingerprint,
        idempotency_key=_derived_key(command.idempotency_key, "file-" + upload.target.key),
        actor=command.actor, correlation_id=command.correlation_id,
    )


def _command_fingerprint(command):
    return fingerprint_payload({
        "session_id": command.preview.session_id, "case_no": command.preview.case_no,
        "expected_status_version": command.preview.expected_status_version.value,
        "documents": [{"target": row.target.key, "unsigned_version": row.target.document_version_id,
                       "staging_id": row.controlled_file_intent.staging_id,
                       "expected_staging_version": row.expected_staging_version.value}
                      for row in sorted(command.preview.documents, key=lambda row: row.target.key)],
        "preview_token": command.preview_token, "actor": command.actor.actor_id, "reason": command.reason,
        **({"testing_skip_confirmed": True} if command.testing_skip_confirmed else {}),
    })


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
    "FinalSigningPrerequisiteCommand",
    "FinalSigningPrerequisitePort",
    "PreviewFinalSignedContractUpload",
    "StoredFinalSignedContractReceipt",
]
