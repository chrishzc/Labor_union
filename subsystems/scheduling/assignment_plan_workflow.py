"""Coordinate the canonical Scheduling Assignment Plan query, preview, and apply flow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from domains.client_finance.obligation_planning import ClientFinanceTermsSourceFacts
from domains.orders.lifecycle import OrderLifecycleRootFacts
from domains.orders.terms import OrderTerms
from domains.scheduling.assignment_plan import (
    AssignmentPlanCandidate,
    AssignmentPlanDomainError,
    AssignmentPlanFacts,
    AssignmentPlanIntent,
    build_assignment_plan_candidate,
    impacted_staff_ids,
)
from domains.scheduling.generation import SchedulingGenerationCandidate
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
from subsystems.payroll.terms_impact import PayrollTermsSourceFacts

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_REASON_MAXIMUM_LENGTH = 500


@dataclass(frozen=True, slots=True)
class AssignmentPlanWorkflowFacts:
    assignment_plan: AssignmentPlanFacts
    order_terms: OrderTerms
    client_finance: ClientFinanceTermsSourceFacts
    payroll: PayrollTermsSourceFacts
    lifecycle: OrderLifecycleRootFacts


@dataclass(frozen=True, slots=True)
class AssignmentPlanPreviewRequest:
    case_no: str
    intent: AssignmentPlanIntent
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_case_number(self.case_no)


@dataclass(frozen=True, slots=True)
class AssignmentPlanApplyRequest:
    case_no: str
    intent: AssignmentPlanIntent
    expected_order_version: ExpectedVersion
    expected_scheduling_version: ExpectedVersion
    expected_client_finance_version: ExpectedVersion
    expected_payroll_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_case_number(self.case_no)
        require_canonical_text(self.reason, "assignment plan reason", _REASON_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class AssignmentPlanPreview:
    candidate: AssignmentPlanCandidate
    client_finance_impact: "VersionedImpactCandidate"
    payroll_impact: "VersionedImpactCandidate"
    orders_impact: "VersionedImpactCandidate"
    order_version: int
    scheduling_version: int
    client_finance_version: int
    payroll_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class AssignmentPlanReceipt:
    case_no: str
    order_version: int
    scheduling_generation: int
    scheduling_version: int
    client_finance_version: int
    payroll_version: int
    cancelled_assignment_ids: tuple[int, ...]
    created_assignment_keys: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredAssignmentPlanReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: AssignmentPlanReceipt


@dataclass(frozen=True, slots=True)
class AssignmentPlanApplyEvidence:
    facts: AssignmentPlanWorkflowFacts
    claim_state: "CommandClaimState"
    receipt: StoredAssignmentPlanReceipt | None


@dataclass(frozen=True, slots=True)
class AssignmentPlanPersistenceContext:
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    preview_fingerprint: PreviewFingerprint
    command_fingerprint: PreviewFingerprint
    expected_order_version: int
    waiting_lock_ids: tuple[int, ...]


class CommandClaimState(Enum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


class VersionedImpactCandidate(Protocol):
    expected_version: int
    resulting_version: int
    fingerprint: PreviewFingerprint
    blockers: tuple[str, ...]


class AssignmentPlanRepository(Protocol):
    def load_for_query(self, case_no: str) -> AssignmentPlanWorkflowFacts: ...
    def load_for_preview(self, case_no: str, intent: AssignmentPlanIntent) -> AssignmentPlanWorkflowFacts: ...
    def preflight_impacted_staff_ids(self, case_no: str, intent: AssignmentPlanIntent) -> tuple[int, ...]: ...
    def load_for_apply(self, request: AssignmentPlanApplyRequest, preflight_staff_ids: tuple[int, ...], command_fingerprint: PreviewFingerprint) -> AssignmentPlanApplyEvidence: ...
    def replace_scheduling_generation(self, candidate: SchedulingGenerationCandidate, context: AssignmentPlanPersistenceContext) -> object: ...
    def save_receipt(self, key: IdempotencyKey, stored: StoredAssignmentPlanReceipt, scheduling_result: object, context: AssignmentPlanPersistenceContext) -> None: ...


class ClientFinanceAssignmentImpactPort(Protocol):
    def preview_assignment_plan(self, facts: AssignmentPlanWorkflowFacts, scheduling: SchedulingGenerationCandidate) -> VersionedImpactCandidate: ...
    def persist_assignment_plan(self, candidate: VersionedImpactCandidate, context: AssignmentPlanPersistenceContext, scheduling_result: object) -> None: ...


class PayrollAssignmentImpactPort(Protocol):
    def preview_assignment_plan(self, facts: AssignmentPlanWorkflowFacts, scheduling: SchedulingGenerationCandidate) -> VersionedImpactCandidate: ...
    def persist_assignment_plan(self, candidate: VersionedImpactCandidate, context: AssignmentPlanPersistenceContext, scheduling_result: object) -> None: ...


class OrdersAssignmentImpactPort(Protocol):
    def preview_assignment_plan(self, facts: AssignmentPlanWorkflowFacts, scheduling: SchedulingGenerationCandidate, client_finance: VersionedImpactCandidate) -> VersionedImpactCandidate: ...
    def persist_assignment_plan(self, candidate: VersionedImpactCandidate, context: AssignmentPlanPersistenceContext, scheduling_result: object) -> None: ...


class AssignmentPlanWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class AssignmentPlanWorkflow:
    def __init__(self, repository: AssignmentPlanRepository, client_finance_port: ClientFinanceAssignmentImpactPort, payroll_port: PayrollAssignmentImpactPort, orders_port: OrdersAssignmentImpactPort, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._client_finance_port = client_finance_port
        self._payroll_port = payroll_port
        self._orders_port = orders_port
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, case_no: str) -> AssignmentPlanWorkflowFacts:
        _validate_case_number(case_no)
        return self._repository.load_for_query(case_no)

    def preview(self, request: AssignmentPlanPreviewRequest) -> AssignmentPlanPreview:
        _validate_case_number(request.case_no)
        facts = self._repository.load_for_preview(request.case_no, request.intent)
        return self._build_preview(facts, request.intent, request.correlation_id)

    def apply(self, request: AssignmentPlanApplyRequest) -> AssignmentPlanReceipt:
        try:
            return self._apply_transaction(request)
        except AssignmentPlanWorkflowError:
            raise
        except Exception as exception:
            raise _workflow_error(request.correlation_id, ErrorCategory.INTERNAL, "transaction_failed", "The Assignment Plan transaction failed and was rolled back.") from exception

    def _apply_transaction(self, request: AssignmentPlanApplyRequest) -> AssignmentPlanReceipt:
        command_fingerprint = _command_fingerprint(request)
        preflight = _canonical_staff_ids(self._repository.preflight_impacted_staff_ids(request.case_no, request.intent))
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self._replay_or_apply(request, command_fingerprint, preflight)
            unit_of_work.commit()
            return receipt

    def _replay_or_apply(self, request: AssignmentPlanApplyRequest, command_fingerprint: PreviewFingerprint, preflight: tuple[int, ...]) -> AssignmentPlanReceipt:
        evidence = self._repository.load_for_apply(request, preflight, command_fingerprint)
        _raise_if_claim_mismatched(request, evidence.claim_state)
        replay = self._find_replay(request, command_fingerprint, evidence.receipt)
        if replay is not None:
            return replay
        if evidence.claim_state is CommandClaimState.MATCHED:
            raise _workflow_error(request.correlation_id, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "The command claim exists without its receipt.")
        return self._apply_fresh(request, command_fingerprint, preflight, evidence.facts)

    def _find_replay(self, request: AssignmentPlanApplyRequest, command_fingerprint: PreviewFingerprint, stored: StoredAssignmentPlanReceipt | None) -> AssignmentPlanReceipt | None:
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")

    def _apply_fresh(self, request: AssignmentPlanApplyRequest, command_fingerprint: PreviewFingerprint, preflight: tuple[int, ...], facts: AssignmentPlanWorkflowFacts) -> AssignmentPlanReceipt:
        assignment_facts = facts.assignment_plan
        _validate_locked_staff_set(request, assignment_facts, preflight)
        _validate_expected_versions(request, assignment_facts)
        preview = self._build_preview(facts, request.intent, request.correlation_id)
        _validate_preview_fingerprint(request, preview)
        receipt = _build_receipt(preview)
        self._persist(request, preview, command_fingerprint, receipt)
        return receipt

    def _build_preview(self, facts: AssignmentPlanWorkflowFacts, intent: AssignmentPlanIntent, correlation_id: CorrelationId) -> AssignmentPlanPreview:
        try:
            candidate = build_assignment_plan_candidate(facts.assignment_plan, intent)
        except AssignmentPlanDomainError as exception:
            raise _domain_workflow_error(correlation_id, exception) from exception
        try:
            client_finance = self._client_finance_port.preview_assignment_plan(facts, candidate.scheduling)
            payroll = self._payroll_port.preview_assignment_plan(facts, candidate.scheduling)
            orders = self._orders_port.preview_assignment_plan(facts, candidate.scheduling, client_finance)
        except ValueError as exception:
            raise _impact_workflow_error(correlation_id, exception) from exception
        _raise_if_impacts_blocked(correlation_id, client_finance, payroll, orders)
        return _preview_result(facts.assignment_plan, candidate, client_finance, payroll, orders)

    def _persist(self, request: AssignmentPlanApplyRequest, preview: AssignmentPlanPreview, command_fingerprint: PreviewFingerprint, receipt: AssignmentPlanReceipt) -> None:
        context = AssignmentPlanPersistenceContext(request.idempotency_key, request.actor, request.reason, request.correlation_id, preview.fingerprint, command_fingerprint, preview.order_version, preview.candidate.waiting_lock_ids)
        scheduling_result = self._repository.replace_scheduling_generation(preview.candidate.scheduling, context)
        self._client_finance_port.persist_assignment_plan(preview.client_finance_impact, context, scheduling_result)
        self._payroll_port.persist_assignment_plan(preview.payroll_impact, context, scheduling_result)
        self._orders_port.persist_assignment_plan(preview.orders_impact, context, scheduling_result)
        self._repository.save_receipt(request.idempotency_key, StoredAssignmentPlanReceipt(command_fingerprint, receipt), scheduling_result, context)


def _preview_result(facts: AssignmentPlanFacts, candidate: AssignmentPlanCandidate, client_finance: VersionedImpactCandidate, payroll: VersionedImpactCandidate, orders: VersionedImpactCandidate) -> AssignmentPlanPreview:
    return AssignmentPlanPreview(candidate, client_finance, payroll, orders, facts.order_version, facts.scheduling_version, facts.client_finance_version, facts.payroll_version, _combined_preview_fingerprint(candidate, client_finance, payroll, orders))


def _combined_preview_fingerprint(candidate: AssignmentPlanCandidate, client_finance: VersionedImpactCandidate, payroll: VersionedImpactCandidate, orders: VersionedImpactCandidate) -> PreviewFingerprint:
    return fingerprint_payload({"assignment_plan": candidate.fingerprint.value, "client_finance_impact": client_finance.fingerprint.value, "payroll_impact": payroll.fingerprint.value, "orders_impact": orders.fingerprint.value})


def _build_receipt(preview: AssignmentPlanPreview) -> AssignmentPlanReceipt:
    scheduling = preview.candidate.scheduling
    return AssignmentPlanReceipt(scheduling.case_no, preview.orders_impact.resulting_version, scheduling.generation_number, scheduling.resulting_aggregate_version, preview.client_finance_impact.resulting_version, preview.payroll_impact.resulting_version, scheduling.cancelled_assignment_ids, tuple(item.candidate_key for item in scheduling.assignments), preview.fingerprint)


def _validate_locked_staff_set(request: AssignmentPlanApplyRequest, facts: AssignmentPlanFacts, preflight: tuple[int, ...]) -> None:
    if set(impacted_staff_ids(facts, request.intent)).issubset(set(preflight)):
        return
    raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "scheduling_lock_set_stale", "Fresh impacted staff exceed the preflight lock set.")


def _validate_expected_versions(request: AssignmentPlanApplyRequest, facts: AssignmentPlanFacts) -> None:
    if _request_versions(request) == _fact_versions(facts):
        return
    raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_version", "One or more aggregate versions changed after Preview.")


def _validate_preview_fingerprint(request: AssignmentPlanApplyRequest, preview: AssignmentPlanPreview) -> None:
    if request.preview_fingerprint == preview.fingerprint:
        return
    raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_preview", "The business facts changed after Preview.")


def _raise_if_impacts_blocked(correlation_id: CorrelationId, client_finance: VersionedImpactCandidate, payroll: VersionedImpactCandidate, orders: VersionedImpactCandidate) -> None:
    blockers = tuple(sorted(set(client_finance.blockers + payroll.blockers + orders.blockers)))
    if not blockers:
        return
    raise AssignmentPlanWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, "assignment_plan_impact_blocked", "A downstream impact requires human resolution.", correlation_id, domain_blockers=blockers))


def _raise_if_claim_mismatched(request: AssignmentPlanApplyRequest, claim: CommandClaimState) -> None:
    if claim is not CommandClaimState.MISMATCH:
        return
    raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")


def _command_fingerprint(request: AssignmentPlanApplyRequest) -> PreviewFingerprint:
    return fingerprint_payload({"case_no": request.case_no, "intent": _intent_payload(request.intent), "versions": _request_versions(request), "preview_fingerprint": request.preview_fingerprint.value, "actor_id": request.actor.actor_id, "permission_scope": request.actor.permission_scope, "reason": request.reason})


def _intent_payload(intent: AssignmentPlanIntent) -> tuple[dict[str, object], ...]:
    return tuple({"staff_id": segment.staff_id, "assigned_start_date": segment.assigned_start_date.isoformat(), "assigned_end_date": segment.assigned_end_date.isoformat(), "official_service_dates": tuple(value.isoformat() for value in segment.official_service_dates)} for segment in intent.segments)


def _request_versions(request: AssignmentPlanApplyRequest) -> dict[str, int]:
    return {"order": request.expected_order_version.value, "scheduling": request.expected_scheduling_version.value, "client_finance": request.expected_client_finance_version.value, "payroll": request.expected_payroll_version.value}


def _fact_versions(facts: AssignmentPlanFacts) -> dict[str, int]:
    return {"order": facts.order_version, "scheduling": facts.scheduling_version, "client_finance": facts.client_finance_version, "payroll": facts.payroll_version}


def _domain_workflow_error(correlation_id: CorrelationId, exception: AssignmentPlanDomainError) -> AssignmentPlanWorkflowError:
    return AssignmentPlanWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, exception.issue.value, str(exception), correlation_id, domain_blockers=(exception.issue.value,)))


def _impact_workflow_error(correlation_id: CorrelationId, exception: ValueError) -> AssignmentPlanWorkflowError:
    code = str(exception).strip() or "assignment_plan_impact_invalid"
    return AssignmentPlanWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, code, "A downstream root fact requires human resolution.", correlation_id, domain_blockers=(code,)))


def _workflow_error(correlation_id: CorrelationId, category: ErrorCategory, code: str, message: str) -> AssignmentPlanWorkflowError:
    return AssignmentPlanWorkflowError(TypedError(category, code, message, correlation_id))


def _validate_case_number(case_no: str) -> None:
    require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)


def _canonical_staff_ids(staff_ids: tuple[int, ...]) -> tuple[int, ...]:
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in staff_ids):
        raise ValueError("preflight staff ids must be positive integers")
    return tuple(sorted(set(staff_ids)))
