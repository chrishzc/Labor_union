"""Preview and ensure a case's canonical cross-domain bootstrap roots."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

from domains.bootstrap.case_architecture import (
    BootstrapDomainError,
    BootstrapIssue,
    BootstrapMutation,
    CaseArchitectureBootstrapCandidate,
    CaseArchitectureBootstrapFacts,
    CaseArchitectureBootstrapIntent,
    build_case_architecture_bootstrap_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text

_REASON_MAXIMUM_LENGTH = 500


class CommandClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class CaseArchitectureBootstrapPreview:
    candidate: CaseArchitectureBootstrapCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class EnsureCaseArchitectureBootstrap:
    intent: CaseArchitectureBootstrapIntent
    expected_order_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "bootstrap reason", _REASON_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class CaseArchitectureBootstrapReceipt:
    case_no: str
    order_version: int
    client_finance_version: int
    payroll_version: int
    scheduling_version: int
    scheduling_generation: int
    bootstrap_created: bool
    bootstrap_event_id: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredCaseArchitectureBootstrapReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: CaseArchitectureBootstrapReceipt


class CaseArchitectureBootstrapRepository(Protocol):
    def load_for_preview(self, intent: CaseArchitectureBootstrapIntent) -> CaseArchitectureBootstrapFacts: ...
    def load_for_ensure(self, intent: CaseArchitectureBootstrapIntent) -> CaseArchitectureBootstrapFacts: ...
    def claim_command(self, command: EnsureCaseArchitectureBootstrap, command_fingerprint: PreviewFingerprint) -> CommandClaimState: ...
    def find_receipt(self, key: IdempotencyKey, *, for_update: bool) -> StoredCaseArchitectureBootstrapReceipt | None: ...
    def create_bootstrap(self, command: EnsureCaseArchitectureBootstrap, candidate: CaseArchitectureBootstrapCandidate) -> int: ...
    def existing_bootstrap_event_id(self, case_no: str) -> int: ...
    def save_receipt(self, key: IdempotencyKey, stored: StoredCaseArchitectureBootstrapReceipt) -> None: ...


class CaseArchitectureBootstrapWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class CaseArchitectureBootstrapWorkflow:
    def __init__(self, repository: CaseArchitectureBootstrapRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, intent: CaseArchitectureBootstrapIntent, correlation_id: CorrelationId) -> CaseArchitectureBootstrapPreview:
        try:
            candidate = build_case_architecture_bootstrap_candidate(self._repository.load_for_preview(intent), intent)
            return CaseArchitectureBootstrapPreview(candidate, candidate.fingerprint)
        except BootstrapDomainError as exception:
            raise _domain_error(correlation_id, exception) from exception

    def ensure(self, command: EnsureCaseArchitectureBootstrap) -> CaseArchitectureBootstrapReceipt:
        command_fingerprint = _command_fingerprint(command)
        try:
            return self._ensure_transaction(command, command_fingerprint)
        except CaseArchitectureBootstrapWorkflowError:
            raise
        except BootstrapDomainError as exception:
            raise _domain_error(command.correlation_id, exception) from exception
        except Exception as exception:
            raise _workflow_error(
                command.correlation_id,
                ErrorCategory.INTERNAL,
                "transaction_failed",
                "The case bootstrap transaction failed and was rolled back.",
            ) from exception

    def _ensure_transaction(self, command: EnsureCaseArchitectureBootstrap, command_fingerprint: PreviewFingerprint) -> CaseArchitectureBootstrapReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            claim = self._repository.claim_command(command, command_fingerprint)
            _raise_if_claim_mismatched(command, claim)
            replay = self._find_replay(command, command_fingerprint)
            if replay is not None:
                return replay
            _raise_if_claim_has_no_receipt(command, claim)
            receipt = self._ensure_fresh(command, command_fingerprint)
            unit_of_work.commit()
            return receipt

    def _find_replay(self, command: EnsureCaseArchitectureBootstrap, command_fingerprint: PreviewFingerprint) -> CaseArchitectureBootstrapReceipt | None:
        stored = self._repository.find_receipt(command.idempotency_key, for_update=True)
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _workflow_error(command.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")

    def _ensure_fresh(self, command: EnsureCaseArchitectureBootstrap, command_fingerprint: PreviewFingerprint) -> CaseArchitectureBootstrapReceipt:
        facts = self._repository.load_for_ensure(command.intent)
        _validate_order_version(command, facts)
        candidate = build_case_architecture_bootstrap_candidate(facts, command.intent)
        _validate_preview(command, candidate)
        event_id = self._persist_candidate(command, candidate)
        receipt = _build_receipt(candidate, event_id)
        self._repository.save_receipt(command.idempotency_key, StoredCaseArchitectureBootstrapReceipt(command_fingerprint, receipt))
        return receipt

    def _persist_candidate(self, command: EnsureCaseArchitectureBootstrap, candidate: CaseArchitectureBootstrapCandidate) -> int:
        if candidate.mutation is BootstrapMutation.CREATE:
            return self._repository.create_bootstrap(command, candidate)
        return self._repository.existing_bootstrap_event_id(candidate.case_no)


def _validate_order_version(command, facts) -> None:
    current_version = facts.order.order_version
    if current_version == command.expected_order_version.value:
        return
    raise _workflow_error(command.correlation_id, ErrorCategory.CONFLICT, "case_architecture_bootstrap_stale", "The order changed after bootstrap Preview.", current_version=current_version)


def _validate_preview(command, candidate) -> None:
    if candidate.fingerprint == command.preview_fingerprint:
        return
    raise _workflow_error(command.correlation_id, ErrorCategory.CONFLICT, "case_architecture_bootstrap_stale", "The bootstrap facts changed after Preview.", current_version=candidate.order_version)


def _raise_if_claim_mismatched(command, claim) -> None:
    if claim is CommandClaimState.MISMATCH:
        raise _workflow_error(command.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")


def _raise_if_claim_has_no_receipt(command, claim) -> None:
    if claim is CommandClaimState.MATCHED:
        raise _workflow_error(command.correlation_id, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "The bootstrap command claim exists without its receipt.")


def _build_receipt(candidate, event_id) -> CaseArchitectureBootstrapReceipt:
    return CaseArchitectureBootstrapReceipt(
        case_no=candidate.case_no,
        order_version=candidate.order_version,
        client_finance_version=0,
        payroll_version=0,
        scheduling_version=candidate.scheduling_version,
        scheduling_generation=candidate.scheduling_generation,
        bootstrap_created=candidate.mutation is not BootstrapMutation.KEEP_EXISTING,
        bootstrap_event_id=event_id,
        preview_fingerprint=candidate.fingerprint,
    )


def _command_fingerprint(command: EnsureCaseArchitectureBootstrap) -> PreviewFingerprint:
    return fingerprint_payload({
        "case_no": command.intent.case_no,
        "expected_order_version": command.expected_order_version.value,
        "preview_fingerprint": command.preview_fingerprint.value,
        "client_payment_policy_version": command.intent.client_payment_terms.policy_version,
        "payroll_policy_version": command.intent.payroll_policy_version,
        "actor": command.actor.actor_id,
        "reason": command.reason,
    })


def _domain_error(correlation_id: CorrelationId, exception: BootstrapDomainError) -> CaseArchitectureBootstrapWorkflowError:
    category = ErrorCategory.NOT_FOUND if exception.issue is BootstrapIssue.CASE_NOT_FOUND else ErrorCategory.DOMAIN_BLOCKED
    return _workflow_error(correlation_id, category, exception.issue.value, str(exception), blockers=(exception.issue.value,))


def _workflow_error(correlation_id: CorrelationId, category: ErrorCategory, code: str, message: str, *, blockers: tuple[str, ...] = (), current_version: int | None = None) -> CaseArchitectureBootstrapWorkflowError:
    return CaseArchitectureBootstrapWorkflowError(
        TypedError(
            category=category,
            code=code,
            message=message,
            correlation_id=correlation_id,
            domain_blockers=tuple(sorted(set(blockers))),
            current_version=(ExpectedVersion(current_version) if current_version is not None else None),
        )
    )


__all__ = [
    "CaseArchitectureBootstrapPreview",
    "CaseArchitectureBootstrapReceipt",
    "CaseArchitectureBootstrapWorkflow",
    "CaseArchitectureBootstrapWorkflowError",
    "CommandClaimState",
    "EnsureCaseArchitectureBootstrap",
    "StoredCaseArchitectureBootstrapReceipt",
]
