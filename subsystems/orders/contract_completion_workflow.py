"""Coordinate the typed Orders contract-completion transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Callable, Protocol

from domains.client_finance.obligation_planning import (
    ClientFinanceTermsCandidate,
    ClientFinanceTermsFacts,
    build_client_finance_terms_candidate,
)
from domains.client_finance.reconciliation import PaymentStage
from domains.orders.contract_completion import (
    ContractCompletionBlocker,
    ContractCompletionCandidate,
    ContractCompletionCandidateError,
    ContractCompletionFacts,
    ContractCompletionIntent,
    build_contract_completion_candidate,
    contract_completion_blockers,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.clock import BusinessClock
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

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_REASON_MAXIMUM_LENGTH = 500


class ContractCompletionCommandClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class ContractCompletionWorkflowFacts:
    order: ContractCompletionFacts
    client_finance: ClientFinanceTermsFacts
    contracted_service_day_count: int

    def __post_init__(self) -> None:
        if self.order.case_no != self.client_finance.case_no:
            raise ValueError("contract completion case numbers must match")
        if self.contracted_service_day_count <= 0:
            raise ValueError("contracted service day count must be positive")


@dataclass(frozen=True, slots=True)
class ContractCompletionQuery:
    facts: ContractCompletionFacts
    client_finance_version: int
    completion_available: bool
    domain_blockers: tuple[ContractCompletionBlocker, ...]


@dataclass(frozen=True, slots=True)
class ContractCompletionPreview:
    candidate: ContractCompletionCandidate
    client_finance_impact: ClientFinanceTermsCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ContractCompletionApplyRequest:
    case_no: str
    intent: ContractCompletionIntent
    expected_order_version: ExpectedVersion
    expected_client_finance_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        require_canonical_text(self.reason, "contract completion reason", _REASON_MAXIMUM_LENGTH)
        if not isinstance(self.intent, ContractCompletionIntent):
            raise TypeError("contract completion intent is invalid")


@dataclass(frozen=True, slots=True)
class ContractCompletionReceipt:
    case_no: str
    contract_identity: str
    order_version: int
    client_finance_version: int
    established_obligation_count: int
    lifecycle_status: OrderLifecycleStatus
    contract_completed: bool
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredContractCompletionReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: ContractCompletionReceipt


@dataclass(frozen=True, slots=True)
class ContractCompletionLifecycleEventCommand:
    request: ContractCompletionApplyRequest
    candidate: ContractCompletionCandidate
    business_date: date


@dataclass(frozen=True, slots=True)
class ContractCompletionProjectionCommand:
    case_no: str
    expected_order_version: int
    resulting_order_version: int
    lifecycle_status: OrderLifecycleStatus


@dataclass(frozen=True, slots=True)
class ContractCompletionReceiptCommand:
    request: ContractCompletionApplyRequest
    stored_receipt: StoredContractCompletionReceipt
    contract_event_id: int
    lifecycle_event_id: int


@dataclass(frozen=True, slots=True)
class ContractCompletionClientFinanceCommand:
    candidate: ClientFinanceTermsCandidate
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    source_event_family: str
    source_event_id: int


class ContractCompletionWorkflowRepository(Protocol):
    def load_for_preview(self, case_no: str) -> ContractCompletionWorkflowFacts: ...
    def load_for_apply(self, case_no: str) -> ContractCompletionWorkflowFacts: ...
    def claim_command(self, request: ContractCompletionApplyRequest, command_fingerprint: PreviewFingerprint) -> ContractCompletionCommandClaimState: ...
    def find_receipt(self, key: IdempotencyKey, *, for_update: bool) -> StoredContractCompletionReceipt | None: ...
    def append_contract_completion_event(self, request: ContractCompletionApplyRequest, preview: ContractCompletionPreview) -> int: ...
    def append_lifecycle_event(self, command: ContractCompletionLifecycleEventCommand) -> int: ...
    def persist_client_finance_impact(self, command: ContractCompletionClientFinanceCommand) -> None: ...
    def update_order_projection(self, command: ContractCompletionProjectionCommand) -> None: ...
    def append_outbox_intent(self, request: ContractCompletionApplyRequest, preview: ContractCompletionPreview, lifecycle_event_id: int) -> None: ...
    def save_receipt(self, command: ContractCompletionReceiptCommand) -> None: ...


class ContractCompletionWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class ContractCompletionWorkflow:
    def __init__(self, repository: ContractCompletionWorkflowRepository, unit_of_work_factory: Callable[[], UnitOfWork], clock: BusinessClock) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def query(self, case_no: str) -> ContractCompletionQuery:
        facts = self._repository.load_for_preview(case_no)
        blockers = _workflow_blockers(facts)
        return ContractCompletionQuery(facts.order, facts.client_finance.account_version, not blockers, blockers)

    def preview(self, case_no: str, intent: ContractCompletionIntent) -> ContractCompletionPreview:
        return _build_preview(self._repository.load_for_preview(case_no), intent)

    def apply(self, request: ContractCompletionApplyRequest) -> ContractCompletionReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self.apply_borrowed(request)
            unit_of_work.commit()
            return receipt

    def apply_borrowed(
        self, request: ContractCompletionApplyRequest
    ) -> ContractCompletionReceipt:
        """Apply under an existing outer transaction without committing it."""
        command_fingerprint = _command_fingerprint(request)
        replay = self._claim_or_replay(request, command_fingerprint)
        if replay is not None:
            return replay
        preview = self._fresh_preview(request)
        receipt = _build_receipt(preview)
        self._persist(request, preview, command_fingerprint, receipt)
        return receipt

    def _claim_or_replay(self, request, command_fingerprint):
        state = self._repository.claim_command(request, command_fingerprint)
        if state is ContractCompletionCommandClaimState.MISMATCH:
            raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was used with a different command.")
        stored = self._repository.find_receipt(request.idempotency_key, for_update=True)
        return _matched_or_missing_receipt(request, command_fingerprint, state, stored)

    def _fresh_preview(self, request):
        facts = self._repository.load_for_apply(request.case_no)
        _validate_versions(request, facts)
        preview = _build_preview(facts, request.intent)
        if preview.fingerprint != request.preview_fingerprint:
            raise _workflow_error(request, ErrorCategory.CONFLICT, "stale_preview", "The contract-completion facts changed after Preview.")
        return preview

    def _persist(self, request, preview, command_fingerprint, receipt):
        contract_event_id = self._repository.append_contract_completion_event(request, preview)
        self._repository.persist_client_finance_impact(ContractCompletionClientFinanceCommand(preview.client_finance_impact, request.idempotency_key, request.actor, request.reason, request.correlation_id, "contract-completion", contract_event_id))
        lifecycle_event_id = self._repository.append_lifecycle_event(ContractCompletionLifecycleEventCommand(request, preview.candidate, self._clock.today()))
        self._repository.update_order_projection(_projection_command(preview.candidate))
        self._repository.append_outbox_intent(request, preview, lifecycle_event_id)
        self._repository.save_receipt(ContractCompletionReceiptCommand(request, StoredContractCompletionReceipt(command_fingerprint, receipt), contract_event_id, lifecycle_event_id))


def _build_preview(facts, intent):
    blockers = _workflow_blockers(facts)
    if blockers:
        raise ContractCompletionCandidateError(blockers)
    candidate = build_contract_completion_candidate(facts.order, intent)
    finance_impact = build_client_finance_terms_candidate(facts.client_finance, f"contract-completion:{candidate.contract_identity}")
    fingerprint = fingerprint_payload({"orders": candidate.fingerprint.value, "client_finance": finance_impact.fingerprint.value})
    return ContractCompletionPreview(candidate, finance_impact, fingerprint)


def _build_receipt(preview):
    candidate = preview.candidate
    return ContractCompletionReceipt(candidate.case_no, candidate.contract_identity, candidate.resulting_order_version, preview.client_finance_impact.resulting_account_version, _established_obligation_count(preview.client_finance_impact), candidate.after_status, candidate.after_completed, preview.fingerprint)


def _projection_command(candidate):
    return ContractCompletionProjectionCommand(candidate.case_no, candidate.expected_order_version, candidate.resulting_order_version, candidate.after_status)


def _validate_versions(request, facts):
    _validate_expected_version(request, request.expected_order_version, facts.order.aggregate_version, "order_version_conflict", "The order version changed before Apply.")
    _validate_expected_version(request, request.expected_client_finance_version, facts.client_finance.account_version, "client_finance_candidate_stale", "The Client Finance version changed before Apply.")


def _validate_expected_version(request, expected, current, code, message):
    if expected.value == current:
        return
    raise ContractCompletionWorkflowError(TypedError(ErrorCategory.CONFLICT, code, message, request.correlation_id, current_version=ExpectedVersion(current)))


def _matched_or_missing_receipt(request, command_fingerprint, state, stored):
    if stored is not None:
        return _matched_receipt(request, command_fingerprint, stored)
    if state is ContractCompletionCommandClaimState.MATCHED:
        raise _workflow_error(request, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "The command claim exists without its receipt.")
    return None


def _matched_receipt(request, command_fingerprint, stored):
    if stored.command_fingerprint == command_fingerprint:
        return stored.receipt
    raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was used with a different command.")


def _command_fingerprint(request):
    return fingerprint_payload({"case_no": request.case_no, "intent": request.intent.value, "expected_order_version": request.expected_order_version.value, "expected_client_finance_version": request.expected_client_finance_version.value, "preview_fingerprint": request.preview_fingerprint.value, "actor": request.actor.actor_id, "reason": request.reason})


def _workflow_error(request, category, code, message):
    return ContractCompletionWorkflowError(TypedError(category, code, message, request.correlation_id))


def _workflow_blockers(facts):
    blockers = list(contract_completion_blockers(facts.order))
    if len(facts.client_finance.charge_days) != facts.contracted_service_day_count:
        blockers.append(ContractCompletionBlocker.OFFICIAL_SERVICE_DATES_INCOMPLETE)
    if _has_incompatible_obligation_history(facts.client_finance):
        blockers.append(ContractCompletionBlocker.CLIENT_OBLIGATION_HISTORY_CONFLICT)
    return tuple(sorted(set(blockers), key=lambda blocker: blocker.value))


def _has_incompatible_obligation_history(client_finance) -> bool:
    """A precontract deposit is deliberately carried into contract completion."""

    stages = tuple(item.payment_stage for item in client_finance.existing_obligations)
    return any(stage is not PaymentStage.DEPOSIT for stage in stages) or len(stages) > 1


def _established_obligation_count(candidate):
    return sum(action.action.value == "create_stage" for action in candidate.actions)


__all__ = [
    "ContractCompletionApplyRequest", "ContractCompletionClientFinanceCommand",
    "ContractCompletionCommandClaimState", "ContractCompletionLifecycleEventCommand",
    "ContractCompletionPreview", "ContractCompletionProjectionCommand",
    "ContractCompletionQuery", "ContractCompletionReceipt",
    "ContractCompletionReceiptCommand", "ContractCompletionWorkflow",
    "ContractCompletionWorkflowFacts", "ContractCompletionWorkflowError",
    "ContractCompletionWorkflowRepository", "StoredContractCompletionReceipt",
]
