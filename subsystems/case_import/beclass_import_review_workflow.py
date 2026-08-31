"""Query, preview, and atomically resolve invalid BeClass import rows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

from domains.case_import.beclass_import_review import (
    BeClassImportReviewCandidate,
    BeClassImportReviewDomainError,
    BeClassImportReviewFacts,
    BeClassImportReviewIntent,
    BeClassImportReviewIssue,
    build_beclass_import_review_candidate,
    review_outbox_snapshot,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text

_REASON_MAXIMUM_LENGTH = 500


class BeClassImportReviewClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class BeClassImportReviewQuery:
    facts: BeClassImportReviewFacts


@dataclass(frozen=True, slots=True)
class BeClassImportReviewPreview:
    candidate: BeClassImportReviewCandidate
    expected_version: ExpectedVersion
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyBeClassImportReview:
    intent: BeClassImportReviewIntent
    expected_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(
            self.reason,
            "BeClass import review reason",
            _REASON_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class BeClassImportReviewReceipt:
    review_identity: str
    owning_record_identity: str
    resulting_version: int
    review_event_id: int
    outbox_id: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredBeClassImportReviewReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: BeClassImportReviewReceipt


@dataclass(frozen=True, slots=True)
class BeClassImportReviewWriteReceipt:
    owning_record_identity: str


class BeClassImportReviewWriterPort(Protocol):
    def apply_corrected_row(
        self,
        candidate: BeClassImportReviewCandidate,
    ) -> BeClassImportReviewWriteReceipt: ...


class BeClassImportReviewRepository(Protocol):
    def load(
        self,
        review_identity: str,
        *,
        for_update: bool,
    ) -> BeClassImportReviewFacts | None: ...

    def claim_command(
        self,
        command: ApplyBeClassImportReview,
        command_fingerprint: PreviewFingerprint,
    ) -> BeClassImportReviewClaimState: ...

    def find_receipt(
        self,
        key: IdempotencyKey,
    ) -> StoredBeClassImportReviewReceipt | None: ...

    def append_resolution_event(
        self,
        command: ApplyBeClassImportReview,
        candidate: BeClassImportReviewCandidate,
        write_receipt: BeClassImportReviewWriteReceipt,
    ) -> int: ...

    def append_outbox(
        self,
        candidate: BeClassImportReviewCandidate,
        review_event_id: int,
    ) -> int: ...

    def save_receipt(
        self,
        key: IdempotencyKey,
        receipt: StoredBeClassImportReviewReceipt,
    ) -> None: ...


class BeClassImportReviewWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class BeClassImportReviewStorageError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class BeClassImportReviewWriterError(RuntimeError):
    def __init__(self, code: str, category: ErrorCategory) -> None:
        super().__init__(code)
        self.code = code
        self.category = category


class BeClassImportReviewWorkflow:
    def __init__(
        self,
        repository: BeClassImportReviewRepository,
        writer: BeClassImportReviewWriterPort,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._writer = writer
        self._unit_of_work_factory = unit_of_work_factory

    def query(
        self,
        review_identity: str,
        correlation_id: CorrelationId,
    ) -> BeClassImportReviewQuery:
        try:
            facts = self._repository.load(review_identity, for_update=False)
            return BeClassImportReviewQuery(_require_facts(facts, correlation_id))
        except BeClassImportReviewWorkflowError:
            raise
        except Exception as error:
            raise _query_error(correlation_id, error) from error

    def preview(
        self,
        intent: BeClassImportReviewIntent,
        correlation_id: CorrelationId,
    ) -> BeClassImportReviewPreview:
        try:
            facts = _require_facts(
                self._repository.load(intent.review_identity, for_update=False),
                correlation_id,
            )
            candidate = build_beclass_import_review_candidate(facts, intent)
            return _preview(candidate, facts.review_version)
        except BeClassImportReviewWorkflowError:
            raise
        except BeClassImportReviewDomainError as error:
            raise _domain_error(correlation_id, error) from error
        except Exception as error:
            raise _query_error(correlation_id, error) from error

    def apply(self, command: ApplyBeClassImportReview) -> BeClassImportReviewReceipt:
        command_fingerprint = _command_fingerprint(command)
        try:
            return self._apply_transaction(command, command_fingerprint)
        except BeClassImportReviewWorkflowError:
            raise
        except BeClassImportReviewDomainError as error:
            raise _domain_error(command.correlation_id, error) from error
        except BeClassImportReviewWriterError as error:
            raise _writer_error(command, error) from error
        except BeClassImportReviewStorageError as error:
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

    # Kept cohesive because this is one owning-row, review-event, and outbox transaction.
    def _apply_fresh(self, command, command_fingerprint):
        facts = _require_facts(
            self._repository.load(command.intent.review_identity, for_update=True),
            command.correlation_id,
        )
        _validate_expected_version(command, facts.review_version)
        candidate = build_beclass_import_review_candidate(facts, command.intent)
        preview = _preview(candidate, facts.review_version)
        _validate_preview(command, preview)
        write_receipt = self._writer.apply_corrected_row(candidate)
        event_id = self._repository.append_resolution_event(
            command,
            candidate,
            write_receipt,
        )
        outbox_id = self._repository.append_outbox(candidate, event_id)
        receipt = _receipt(
            candidate,
            write_receipt,
            event_id,
            outbox_id,
            preview.fingerprint,
        )
        self._repository.save_receipt(
            command.idempotency_key,
            StoredBeClassImportReviewReceipt(command_fingerprint, receipt),
        )
        return receipt


def _preview(candidate, expected_version) -> BeClassImportReviewPreview:
    fingerprint = fingerprint_payload(
        {
            "candidate_fingerprint": candidate.fingerprint.value,
            "expected_version": expected_version,
            "review_outbox_snapshot": review_outbox_snapshot(candidate),
        }
    )
    return BeClassImportReviewPreview(
        candidate,
        ExpectedVersion(expected_version),
        fingerprint,
    )


def _receipt(candidate, write_receipt, event_id, outbox_id, fingerprint):
    return BeClassImportReviewReceipt(
        candidate.review_identity,
        write_receipt.owning_record_identity,
        candidate.resulting_version,
        event_id,
        outbox_id,
        fingerprint,
    )


def _command_fingerprint(command) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "review_identity": command.intent.review_identity,
            "expected_version": command.expected_version.value,
            "preview_fingerprint": command.preview_fingerprint.value,
            "actor": command.actor.actor_id,
            "reason": command.reason,
        }
    )


def _require_facts(facts, correlation_id):
    if facts is not None:
        return facts
    raise _workflow_error(
        correlation_id,
        ErrorCategory.NOT_FOUND,
        "beclass_import_review_not_found",
        "BeClass import review row was not found.",
    )


def _validate_expected_version(command, current_version) -> None:
    if command.expected_version.value == current_version:
        return
    raise _workflow_error(
        command.correlation_id,
        ErrorCategory.CONFLICT,
        "beclass_import_review_stale",
        "BeClass import review changed after Preview.",
        current_version=ExpectedVersion(current_version),
    )


def _validate_preview(command, preview) -> None:
    if command.preview_fingerprint == preview.fingerprint:
        return
    raise _workflow_error(
        command.correlation_id,
        ErrorCategory.CONFLICT,
        "beclass_import_review_stale",
        "BeClass import review facts changed after Preview.",
        current_version=preview.expected_version,
    )


def _raise_if_claim_mismatched(command, claim) -> None:
    if claim is BeClassImportReviewClaimState.MISMATCH:
        raise _idempotency_error(command)


def _raise_if_claim_incomplete(command, claim) -> None:
    if claim is not BeClassImportReviewClaimState.MATCHED:
        return
    raise _workflow_error(
        command.correlation_id,
        ErrorCategory.INTERNAL,
        "idempotency_evidence_incomplete",
        "BeClass review command claim exists without a receipt.",
    )


def _idempotency_error(command):
    return _workflow_error(
        command.correlation_id,
        ErrorCategory.IDEMPOTENCY_MISMATCH,
        "idempotency_mismatch",
        "Idempotency key belongs to another BeClass review payload.",
    )


def _domain_error(correlation_id, error):
    category = (
        ErrorCategory.CONFLICT
        if error.issue is BeClassImportReviewIssue.ALREADY_RESOLVED
        else ErrorCategory.DOMAIN_BLOCKED
    )
    return _workflow_error(
        correlation_id,
        category,
        error.issue.value,
        str(error),
        blockers=(error.issue.value,),
    )


def _query_error(correlation_id, error):
    retryable = (
        error.retryable
        if isinstance(error, BeClassImportReviewStorageError)
        else False
    )
    category = ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL
    return _workflow_error(
        correlation_id,
        category,
        "beclass_import_review_query_failed",
        "BeClass import review query failed.",
        retryable=retryable,
    )


def _transaction_error(command, retryable):
    category = ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL
    return _workflow_error(
        command.correlation_id,
        category,
        "beclass_import_review_transaction_failed",
        "BeClass import review transaction was rolled back.",
        retryable=retryable,
    )


def _writer_error(command, error):
    return _workflow_error(
        command.correlation_id,
        error.category,
        error.code,
        "Corrected BeClass row cannot be written to its owning table.",
        blockers=(error.code,),
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
    return BeClassImportReviewWorkflowError(
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
    "ApplyBeClassImportReview",
    "BeClassImportReviewClaimState",
    "BeClassImportReviewPreview",
    "BeClassImportReviewQuery",
    "BeClassImportReviewReceipt",
    "BeClassImportReviewStorageError",
    "BeClassImportReviewWorkflow",
    "BeClassImportReviewWorkflowError",
    "BeClassImportReviewWriteReceipt",
    "BeClassImportReviewWriterError",
    "StoredBeClassImportReviewReceipt",
]
