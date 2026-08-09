"""Apply the one canonical Orders service-completion transition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol

from domains.orders.auto_completion import (
    AutoCompletionCandidate,
    build_auto_completion_candidate,
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
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.orders.lifecycle_authoritative_facts import (
    validate_order_lifecycle_facts,
)


class AutoCompletionClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class AutoCompletionApplyRequest:
    case_no: str
    expected_order_version: ExpectedVersion
    evaluation_at: datetime
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.reason, "auto completion reason", 500)
        if self.evaluation_at.tzinfo is None or self.evaluation_at.utcoffset() is None:
            raise ValueError("evaluation_at must be timezone-aware")
        object.__setattr__(
            self,
            "evaluation_at",
            self.evaluation_at.astimezone(TAIPEI_TIME_ZONE),
        )


@dataclass(frozen=True, slots=True)
class AutoCompletionReceipt:
    case_no: str
    idempotency_key: IdempotencyKey
    order_version: int
    lifecycle_event_id: int
    completion_instant: datetime
    evaluation_at: datetime
    command_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredAutoCompletionReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: AutoCompletionReceipt


class AutoCompletionWorkflowRepository(Protocol):
    def claim_command(self, request: AutoCompletionApplyRequest, fingerprint: PreviewFingerprint) -> AutoCompletionClaimState: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredAutoCompletionReceipt | None: ...
    def load_locked_facts(self, request: AutoCompletionApplyRequest) -> Mapping[str, Any]: ...
    def append_lifecycle_event(self, request: AutoCompletionApplyRequest, candidate: AutoCompletionCandidate, facts: Mapping[str, Any]) -> int: ...
    def update_order(self, candidate: AutoCompletionCandidate) -> None: ...
    def append_outbox(self, request: AutoCompletionApplyRequest, candidate: AutoCompletionCandidate, lifecycle_event_id: int) -> None: ...
    def save_receipt(self, receipt: AutoCompletionReceipt) -> None: ...


class AutoCompletionWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class AutoCompletionRepositoryNotFoundError(Exception):
    """The requested Orders aggregate does not exist."""


class AutoCompletionRepositoryConflictError(Exception):
    """A concurrent Orders change invalidated the command."""


class AutoCompletionRepositoryIntegrityError(Exception):
    """Locked root facts could not support a safe completion decision."""


class AutoCompleteOrderService:
    def __init__(self, repository: AutoCompletionWorkflowRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def apply(self, request: AutoCompletionApplyRequest) -> AutoCompletionReceipt:
        try:
            return self._apply_in_transaction(request)
        except AutoCompletionWorkflowError:
            raise
        except AutoCompletionRepositoryNotFoundError as error:
            raise _error(request, ErrorCategory.NOT_FOUND, "order_not_found", "The requested Orders aggregate does not exist.") from error
        except AutoCompletionRepositoryConflictError as error:
            raise _error(request, ErrorCategory.CONFLICT, "order_version_conflict", "The Orders lifecycle version changed before Apply.") from error
        except AutoCompletionRepositoryIntegrityError as error:
            raise _error(request, ErrorCategory.DOMAIN_BLOCKED, "auto_completion_authoritative_facts_invalid", "Order service completion is blocked because its authoritative facts are inconsistent.", ("auto_complete.authoritative_facts_invalid",)) from error

    def _apply_in_transaction(self, request: AutoCompletionApplyRequest) -> AutoCompletionReceipt:
        fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._claim_or_replay(request, fingerprint)
            if replay is not None:
                return replay
            facts = self._locked_facts(request)
            candidate = _candidate_or_block(request, facts)
            lifecycle_event_id = self._repository.append_lifecycle_event(request, candidate, facts)
            self._repository.update_order(candidate)
            self._repository.append_outbox(request, candidate, lifecycle_event_id)
            receipt = AutoCompletionReceipt(request.case_no, request.idempotency_key, candidate.resulting_order_version, lifecycle_event_id, candidate.completion_instant, candidate.evaluation_at, fingerprint)
            self._repository.save_receipt(receipt)
            unit_of_work.commit()
            return receipt

    def _claim_or_replay(self, request, fingerprint):
        state = self._repository.claim_command(request, fingerprint)
        if state is AutoCompletionClaimState.MISMATCH:
            raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was used with a different command.")
        stored = self._repository.find_receipt(request.idempotency_key)
        if stored is None:
            if state is AutoCompletionClaimState.MATCHED:
                raise _error(request, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "The command claim exists without its receipt.")
            return None
        if stored.command_fingerprint != fingerprint:
            raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was used with a different command.")
        return stored.receipt

    def _locked_facts(self, request):
        return self._repository.load_locked_facts(request)


def _candidate_or_block(request, facts):
    order = facts["locked_order"]
    authoritative = facts["authoritative_facts"]
    _validate_authoritative_facts(request, order, authoritative)
    blockers = tuple(authoritative["transition_blockers"]["auto_complete"])
    if order["status"] != "服務中":
        blockers = tuple(sorted(set((*blockers, "auto_complete.order_not_in_service"))))
    if authoritative["cancellation"]:
        blockers = tuple(sorted(set((*blockers, "auto_complete.order_cancelled"))))
    if blockers or not authoritative["completion_facts_consistent"]:
        raise _error(request, ErrorCategory.DOMAIN_BLOCKED, "auto_completion_blocked", "Order service completion is blocked by authoritative facts.", blockers)
    completion = authoritative["completion_instant"]
    if completion is None:
        raise _error(request, ErrorCategory.DOMAIN_BLOCKED, "auto_completion_blocked", "Order service completion has no complete service-time facts.", ("auto_complete.service_time_terms_incomplete",))
    try:
        return build_auto_completion_candidate(case_no=request.case_no, expected_order_version=request.expected_order_version.value, completion_instant=datetime.fromisoformat(completion), evaluation_at=request.evaluation_at)
    except ValueError as error:
        if str(error) == "auto_completion_time_not_reached":
            raise _error(request, ErrorCategory.DOMAIN_BLOCKED, "auto_completion_time_not_reached", "Order service completion instant has not been reached.", ("auto_complete.completion_instant_not_reached",)) from error
        raise _error(request, ErrorCategory.DOMAIN_BLOCKED, "auto_completion_candidate_invalid", "Order service completion candidate is invalid.", ("auto_complete.candidate_invalid",)) from error


def _validate_authoritative_facts(request, order, authoritative) -> None:
    try:
        validate_order_lifecycle_facts(
            order["status"],
            "evaluation_time_reached",
            authoritative,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _error(
            request,
            ErrorCategory.DOMAIN_BLOCKED,
            "auto_completion_authoritative_facts_invalid",
            "Order service completion is blocked because its authoritative facts are invalid.",
            ("auto_complete.authoritative_facts_invalid",),
        ) from error


def _command_fingerprint(request):
    return fingerprint_payload({"case_no": request.case_no, "expected_order_version": request.expected_order_version.value, "evaluation_at": request.evaluation_at.isoformat(), "actor": request.actor.actor_id, "reason": request.reason})


def _error(request, category, code, message, blockers=()):
    return AutoCompletionWorkflowError(TypedError(category, code, message, request.correlation_id, domain_blockers=tuple(sorted(set(blockers)))))


__all__ = ["AutoCompleteOrderService", "AutoCompletionApplyRequest", "AutoCompletionClaimState", "AutoCompletionReceipt", "AutoCompletionRepositoryConflictError", "AutoCompletionRepositoryIntegrityError", "AutoCompletionRepositoryNotFoundError", "AutoCompletionWorkflowError", "StoredAutoCompletionReceipt"]
