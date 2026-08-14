"""Preview and atomically apply one negotiated Case Import command."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

from domains.case_import.case_import import (
    CaseImportCandidate,
    CaseImportDomainError,
    CaseImportFacts,
    CaseImportIntent,
    CaseImportIssue,
    build_case_import_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text

_REASON_MAXIMUM_LENGTH = 500


class CaseImportClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class CaseImportPreview:
    candidate: CaseImportCandidate
    import_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyCaseImport:
    intent: CaseImportIntent
    expected_import_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(
            self.reason,
            "case import reason",
            _REASON_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class CaseImportReceipt:
    case_no: str
    client_id: int
    order_version: int
    client_finance_version: int
    payroll_version: int
    scheduling_version: int
    scheduling_generation: int
    import_event_id: int
    bootstrap_event_id: int | None
    source_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint
    provisional_registration_id: int | None = None
    provisional_case_issue_event_id: int | None = None


@dataclass(frozen=True, slots=True)
class StoredCaseImportReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: CaseImportReceipt


class CaseImportRepository(Protocol):
    def case_exists(self, case_no: str) -> bool: ...

    def load(
        self,
        intent: CaseImportIntent,
        *,
        for_update: bool,
    ) -> CaseImportFacts: ...

    def claim_command(
        self,
        command: ApplyCaseImport,
        command_fingerprint: PreviewFingerprint,
    ) -> CaseImportClaimState: ...

    def find_receipt(
        self,
        key: IdempotencyKey,
    ) -> StoredCaseImportReceipt | None: ...

    def insert_case_roots(self, candidate: CaseImportCandidate) -> int: ...

    def create_architecture_bootstrap(
        self,
        command: ApplyCaseImport,
        candidate: CaseImportCandidate,
    ) -> int: ...

    def append_import_event(
        self,
        command: ApplyCaseImport,
        candidate: CaseImportCandidate,
        client_id: int,
        bootstrap_event_id: int | None,
    ) -> int: ...

    def consume_provisional_registration(
        self, command: ApplyCaseImport, candidate: CaseImportCandidate, client_id: int, import_event_id: int
    ) -> int: ...

    def save_receipt(
        self,
        key: IdempotencyKey,
        receipt: StoredCaseImportReceipt,
    ) -> None: ...


class CaseImportWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class CaseImportStorageError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class CaseImportWorkflow:
    def __init__(
        self,
        repository: CaseImportRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(
        self,
        intent: CaseImportIntent,
        correlation_id: CorrelationId,
    ) -> CaseImportPreview:
        try:
            facts = self._repository.load(intent, for_update=False)
            return _preview(build_case_import_candidate(facts, intent))
        except CaseImportDomainError as error:
            raise _domain_error(correlation_id, error) from error

    def apply(self, command: ApplyCaseImport) -> CaseImportReceipt:
        fingerprint = _command_fingerprint(command)
        try:
            return self._apply_transaction(command, fingerprint)
        except CaseImportWorkflowError:
            raise
        except CaseImportDomainError as error:
            raise _domain_error(command.correlation_id, error) from error
        except CaseImportStorageError as error:
            raise _transaction_error(command, error.retryable) from error
        except Exception as error:
            raise _transaction_error(command, retryable=False) from error

    def _apply_transaction(self, command, command_fingerprint):
        with self._unit_of_work_factory() as unit_of_work:
            claim = self._repository.claim_command(command, command_fingerprint)
            _raise_if_claim_mismatched(command, claim)
            replay = self._find_replay(command, command_fingerprint)
            if replay is not None:
                return replay
            _raise_if_claim_incomplete(command, claim)
            receipt = self._apply_fresh(command, command_fingerprint)
            unit_of_work.commit()
            return receipt

    def _find_replay(self, command, command_fingerprint):
        stored = self._repository.find_receipt(command.idempotency_key)
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _idempotency_error(command)

    def _apply_fresh(self, command, command_fingerprint):
        facts = self._repository.load(command.intent, for_update=True)
        _validate_import_version(command, facts)
        candidate = build_case_import_candidate(facts, command.intent)
        _validate_preview(command, candidate)
        client_id = self._repository.insert_case_roots(candidate)
        bootstrap_event_id = _create_bootstrap_if_complete(
            self._repository, command, candidate
        )
        import_event_id = self._repository.append_import_event(
            command,
            candidate,
            client_id,
            bootstrap_event_id,
        )
        provisional_event_id = _consume_provisional_registration(
            self._repository, command, candidate, client_id, import_event_id
        )
        receipt = _receipt(candidate, client_id, import_event_id, bootstrap_event_id, provisional_event_id)
        self._repository.save_receipt(
            command.idempotency_key,
            StoredCaseImportReceipt(command_fingerprint, receipt),
        )
        return receipt


def _preview(candidate) -> CaseImportPreview:
    fingerprint = fingerprint_payload(
        {
            "import_version": 0,
            "candidate_fingerprint": candidate.fingerprint.value,
        }
    )
    return CaseImportPreview(candidate, 0, fingerprint)


def _validate_import_version(command, facts) -> None:
    if command.expected_import_version.value != 0 or facts.case_exists:
        current_version = ExpectedVersion(1 if facts.case_exists else 0)
        raise _workflow_error(
            command.correlation_id,
            ErrorCategory.CONFLICT,
            "case_import_candidate_stale",
            "Case existence changed after Preview.",
            current_version=current_version,
        )


def _validate_preview(command, candidate) -> None:
    if _preview(candidate).fingerprint == command.preview_fingerprint:
        return
    raise _workflow_error(
        command.correlation_id,
        ErrorCategory.CONFLICT,
        "case_import_candidate_stale",
        "Case import root facts changed after Preview.",
        current_version=ExpectedVersion(0),
    )


def _consume_provisional_registration(repository, command, candidate, client_id, import_event_id):
    if getattr(candidate, "provisional_registration", None) is None:
        return None
    return repository.consume_provisional_registration(command, candidate, client_id, import_event_id)


def _create_bootstrap_if_complete(repository, command, candidate):
    if getattr(candidate, "bootstrap", object()) is None:
        return None
    return repository.create_architecture_bootstrap(command, candidate)


def _receipt(candidate, client_id, import_event_id, bootstrap_event_id, provisional_event_id):
    return CaseImportReceipt(
        candidate.case_no,
        client_id,
        0,
        0,
        0,
        0,
        0,
        import_event_id,
        bootstrap_event_id,
        candidate.source_fingerprint,
        _preview(candidate).fingerprint,
        None if getattr(candidate, "provisional_registration", None) is None else candidate.provisional_registration.registration_id,
        provisional_event_id,
    )


def _command_fingerprint(command) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "case_no": command.intent.case_no,
            "expected_import_version": command.expected_import_version.value,
            "preview_fingerprint": command.preview_fingerprint.value,
            "actor": command.actor.actor_id,
            "reason": command.reason,
            "provisional_registration_id": command.intent.provisional_registration_id,
        }
    )


def _raise_if_claim_mismatched(command, claim) -> None:
    if claim is CaseImportClaimState.MISMATCH:
        raise _idempotency_error(command)


def _raise_if_claim_incomplete(command, claim) -> None:
    if claim is not CaseImportClaimState.MATCHED:
        return
    raise _workflow_error(
        command.correlation_id,
        ErrorCategory.INTERNAL,
        "idempotency_evidence_incomplete",
        "Case import command claim exists without a receipt.",
    )


def _idempotency_error(command):
    return _workflow_error(
        command.correlation_id,
        ErrorCategory.IDEMPOTENCY_MISMATCH,
        "idempotency_mismatch",
        "Idempotency key belongs to another case import payload.",
    )


def _domain_error(correlation_id, error):
    category = (
        ErrorCategory.CONFLICT
        if error.issue is CaseImportIssue.DUPLICATE_CASE
        else ErrorCategory.DOMAIN_BLOCKED
    )
    return _workflow_error(
        correlation_id,
        category,
        error.issue.value,
        str(error),
        blockers=(error.issue.value,),
    )


def _transaction_error(command, retryable):
    category = ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL
    return _workflow_error(
        command.correlation_id,
        category,
        "transaction_failed",
        "Case import transaction was rolled back.",
        retryable=retryable,
    )


def _workflow_error(
    correlation_id,
    category,
    code,
    message,
    *,
    blockers=(),
    retryable=False,
    current_version=None,
):
    return CaseImportWorkflowError(
        TypedError(
            category,
            code,
            message,
            correlation_id,
            domain_blockers=tuple(sorted(set(blockers))),
            retryable=retryable,
            current_version=current_version,
        )
    )


__all__ = [
    "ApplyCaseImport",
    "CaseImportClaimState",
    "CaseImportPreview",
    "CaseImportReceipt",
    "CaseImportStorageError",
    "CaseImportWorkflow",
    "CaseImportWorkflowError",
    "StoredCaseImportReceipt",
]
