"""Orders terms transaction contracts.

This source restores the canonical public contracts consumed by the MySQL
adapters.  Behavioural workflow recovery is kept separate from these stable
cross-domain persistence contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from enum import StrEnum
from typing import Any

from domains.client_finance.obligation_planning import (
    build_client_finance_terms_impact,
)
from domains.orders.lifecycle import build_terms_lifecycle_impact
from domains.orders.terms import validate_terms_change
from domains.scheduling.generation import build_generation_candidate
from shared_kernel.clock import BusinessClock
from shared_kernel.errors import TypedError
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork
from subsystems.payroll.terms_impact import build_payroll_terms_impact


_TERMS_SOURCE_EVENT_FAMILY = "order-terms"


@dataclass(frozen=True, slots=True)
class TermsWorkflowFacts:
    order: Any
    scheduling: Any
    planned_service_dates: tuple[Any, ...]
    client_finance: Any
    payroll: Any
    lifecycle: Any


@dataclass(frozen=True, slots=True)
class OrderTermsApplyRequest:
    case_no: str
    proposed_terms: Any
    expected_order_version: Any
    expected_scheduling_version: Any
    expected_client_finance_version: Any
    expected_payroll_version: Any
    preview_fingerprint: Any
    idempotency_key: Any
    actor: Any
    reason: str
    correlation_id: Any


@dataclass(frozen=True, slots=True)
class OrderTermsPreview:
    before: Any
    after: Any
    scheduling: Any
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int
    payroll_version: int
    client_finance_impact: Any
    payroll_impact: Any
    lifecycle_impact: Any
    fingerprint: Any


@dataclass(frozen=True, slots=True)
class OrderTermsReceipt:
    case_no: str
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int
    payroll_version: int
    lifecycle_status: Any
    service_data_lock_formed: bool
    cancelled_assignment_ids: tuple[int, ...]
    created_assignment_keys: tuple[str, ...]
    official_service_day_count: int
    official_service_hours: int
    preview_fingerprint: Any


@dataclass(frozen=True, slots=True)
class StoredTermsReceipt:
    command_fingerprint: Any
    receipt: OrderTermsReceipt


@dataclass(frozen=True, slots=True)
class SchedulingReplacementCommand:
    candidate: Any
    command_family: str
    expected_order_version: int
    command_fingerprint: Any
    preview_fingerprint: Any
    idempotency_key: Any
    actor: Any
    reason: str
    correlation_id: Any


@dataclass(frozen=True, slots=True)
class SchedulingReplacementResult:
    generation_id: int
    scheduling_version: int
    rebuild_event_id: int
    scheduling_receipt_id: int
    assignment_resolution: Any


@dataclass(frozen=True, slots=True)
class OrderTermsPersistenceCommand:
    case_no: str
    terms: Any
    expected_order_version: int
    resulting_order_version: int
    planned_end_date: Any
    actual_end_date: Any
    lifecycle_status: Any


@dataclass(frozen=True, slots=True)
class ClientFinanceImpactPersistenceCommand:
    candidate: Any
    idempotency_key: Any
    actor: Any
    reason: str
    correlation_id: Any
    source_event_family: str
    source_event_id: int


@dataclass(frozen=True, slots=True)
class PayrollImpactPersistenceCommand:
    candidate: Any
    assignment_resolution: Any
    idempotency_key: Any
    actor: Any
    reason: str
    correlation_id: Any
    source_event_id: int


@dataclass(frozen=True, slots=True)
class LifecycleImpactPersistenceCommand:
    candidate: Any
    expected_order_version: int
    resulting_order_version: int
    client_settlement_fingerprint: Any
    idempotency_key: Any
    actor: Any
    reason: str
    correlation_id: Any
    trigger_event: str


@dataclass(frozen=True, slots=True)
class OrderTermsReceiptPersistenceCommand:
    key: Any
    stored_receipt: StoredTermsReceipt
    terms_event_id: int
    scheduling_receipt_id: int
    lifecycle_event_id: int
    correlation_id: Any


class CommandClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


class TermsWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class OrderTermsWorkflow:
    def __init__(
        self,
        repository: Any,
        unit_of_work_factory: Any,
        clock: BusinessClock,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def preview(self, case_no: str, proposed_terms: Any) -> Any:
        return self._build_preview(
            self._repository.load_for_preview(case_no), proposed_terms
        )

    def apply(self, request: OrderTermsApplyRequest) -> Any:
        command_fingerprint = _command_fingerprint(request)
        staff_ids = self._repository.preflight_impacted_staff_ids(request.case_no)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._claim_or_replay(request, command_fingerprint)
            if replay is not None:
                return replay
            facts = self._repository.load_for_apply(request.case_no, staff_ids)
            preview = self._fresh_preview(request, facts, staff_ids)
            receipt = _build_receipt(preview)
            self._persist(request, preview, command_fingerprint, receipt)
            unit_of_work.commit()
            return receipt

    def _claim_or_replay(self, request, command_fingerprint):
        claim_state = self._repository.claim_command(request, command_fingerprint)
        if claim_state is CommandClaimState.MISMATCH:
            raise _workflow_error(
                request,
                ErrorCategory.IDEMPOTENCY_MISMATCH,
                "idempotency_mismatch",
                "Idempotency key was already used with a different command.",
            )
        stored = self._repository.find_receipt(
            request.idempotency_key,
            for_update=True,
        )
        if stored is not None:
            return _matched_receipt(request, command_fingerprint, stored)
        if claim_state is CommandClaimState.MATCHED:
            raise _workflow_error(
                request,
                ErrorCategory.INTERNAL,
                "idempotency_evidence_incomplete",
                "The command claim exists without its receipt.",
            )
        return None

    def _fresh_preview(self, request, facts, staff_ids):
        _validate_locked_staff_set(request, facts, staff_ids)
        _validate_versions(request, facts)
        preview = self._build_preview(facts, request.proposed_terms)
        if preview.fingerprint != request.preview_fingerprint:
            raise _workflow_error(
                request,
                ErrorCategory.CONFLICT,
                "stale_preview",
                "The business facts changed after Preview.",
            )
        _raise_if_impacts_blocked(request, preview)
        return preview

    def _build_preview(self, facts, proposed_terms):
        validate_terms_change(facts.order, proposed_terms)
        scheduling = _scheduling_candidate(facts, proposed_terms)
        change_identity = f"terms:{scheduling.case_no}:{scheduling.generation_number}"
        client_finance = build_client_finance_terms_impact(
            facts.client_finance,
            proposed_terms,
            scheduling,
            change_identity,
        )
        payroll = build_payroll_terms_impact(
            facts.payroll,
            scheduling,
            proposed_terms,
            change_identity,
        )
        lifecycle = build_terms_lifecycle_impact(
            facts.lifecycle,
            proposed_terms,
            scheduling,
            client_finance.settlement,
            self._clock.now(),
        )
        return _preview_result(facts, proposed_terms, scheduling, client_finance, payroll, lifecycle)

    def _persist(self, request, preview, command_fingerprint, receipt):
        event_id = self._repository.append_terms_event(request, preview)
        scheduling_result = self._repository.replace_scheduling_generation(
            SchedulingReplacementCommand(
                candidate=preview.scheduling,
                command_family="orders_terms_rebuild",
                expected_order_version=preview.order_version,
                command_fingerprint=command_fingerprint,
                preview_fingerprint=preview.fingerprint,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                reason=request.reason,
                correlation_id=request.correlation_id,
            )
        )
        self._repository.persist_client_finance_impact(
            ClientFinanceImpactPersistenceCommand(
                candidate=preview.client_finance_impact,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                reason=request.reason,
                correlation_id=request.correlation_id,
                source_event_family=_TERMS_SOURCE_EVENT_FAMILY,
                source_event_id=event_id,
            )
        )
        self._repository.persist_payroll_impact(
            PayrollImpactPersistenceCommand(
                candidate=preview.payroll_impact,
                assignment_resolution=scheduling_result.assignment_resolution,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                reason=request.reason,
                correlation_id=request.correlation_id,
                source_event_id=event_id,
            )
        )
        lifecycle_event_id = self._repository.persist_lifecycle_impact(
            LifecycleImpactPersistenceCommand(
                candidate=preview.lifecycle_impact,
                expected_order_version=preview.order_version,
                resulting_order_version=receipt.order_version,
                client_settlement_fingerprint=preview.client_finance_impact.settlement.fingerprint,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                reason=request.reason,
                correlation_id=request.correlation_id,
                trigger_event="terms_changed",
            )
        )
        self._repository.update_order_terms(
            OrderTermsPersistenceCommand(
                case_no=request.case_no,
                terms=request.proposed_terms,
                expected_order_version=preview.order_version,
                resulting_order_version=receipt.order_version,
                planned_end_date=_planned_end_date(preview.scheduling),
                actual_end_date=preview.lifecycle_impact.actual_end_date,
                lifecycle_status=preview.lifecycle_impact.after_status,
            )
        )
        self._repository.save_receipt(
            OrderTermsReceiptPersistenceCommand(
                key=request.idempotency_key,
                stored_receipt=StoredTermsReceipt(command_fingerprint, receipt),
                terms_event_id=event_id,
                scheduling_receipt_id=scheduling_result.scheduling_receipt_id,
                lifecycle_event_id=lifecycle_event_id,
                correlation_id=request.correlation_id,
            )
        )


def _scheduling_candidate(facts, proposed_terms):
    day_shift = (
        proposed_terms.planned_start_date - facts.order.terms.planned_start_date
    ).days
    shifted_dates = tuple(
        value + timedelta(days=day_shift) for value in facts.planned_service_dates
    )
    shifted_segments = tuple(
        replace(
            segment,
            assigned_start_date=segment.assigned_start_date + timedelta(days=day_shift),
            assigned_end_date=segment.assigned_end_date + timedelta(days=day_shift),
        )
        for segment in facts.scheduling.segments
    )
    return build_generation_candidate(
        replace(facts.scheduling, segments=shifted_segments),
        proposed_terms,
        shifted_dates,
    )


def _preview_result(facts, proposed_terms, scheduling, client_finance, payroll, lifecycle):
    return OrderTermsPreview(
        before=facts.order.terms,
        after=proposed_terms,
        scheduling=scheduling,
        order_version=facts.order.version,
        scheduling_version=facts.scheduling.aggregate_version,
        scheduling_generation=facts.scheduling.generation_number,
        client_finance_version=facts.client_finance.account_version,
        payroll_version=facts.payroll.payroll_version,
        client_finance_impact=client_finance,
        payroll_impact=payroll,
        lifecycle_impact=lifecycle,
        fingerprint=fingerprint_payload(_preview_fingerprint_payload(facts, proposed_terms, scheduling, client_finance, payroll, lifecycle)),
    )


def _preview_fingerprint_payload(facts, proposed_terms, scheduling, client_finance, payroll, lifecycle):
    return {
        "case_no": facts.order.case_no,
        "terms": proposed_terms.canonical_payload(),
        "order_version": facts.order.version,
        "scheduling_version": facts.scheduling.aggregate_version,
        "client_finance_version": facts.client_finance.account_version,
        "payroll_version": facts.payroll.payroll_version,
        "scheduling": _scheduling_payload(scheduling),
        "client_finance": client_finance.fingerprint.value,
        "payroll": payroll.fingerprint.value,
        "lifecycle": lifecycle.fingerprint.value,
    }


def _scheduling_payload(scheduling):
    return tuple(
        (item.candidate_key, item.staff_id, tuple(value.isoformat() for value in item.service_dates))
        for item in scheduling.assignments
    )


def _build_receipt(preview):
    assignments = preview.scheduling.assignments
    return OrderTermsReceipt(
        preview.scheduling.case_no,
        preview.order_version + 1,
        preview.scheduling.resulting_aggregate_version,
        preview.scheduling.generation_number,
        preview.client_finance_impact.resulting_account_version,
        preview.payroll_impact.resulting_payroll_version,
        preview.lifecycle_impact.after_status,
        preview.lifecycle_impact.service_data_lock_should_exist and not preview.lifecycle_impact.service_data_lock_was_present,
        preview.scheduling.cancelled_assignment_ids,
        tuple(item.candidate_key for item in assignments),
        sum(len(item.service_dates) for item in assignments),
        sum(item.actual_hours for item in assignments),
        preview.fingerprint,
    )


def _planned_end_date(scheduling):
    return max(value for item in scheduling.assignments for value in item.service_dates)


def _validate_versions(request, facts):
    values = (
        (request.expected_order_version.value, facts.order.version, "order"),
        (request.expected_scheduling_version.value, facts.scheduling.aggregate_version, "scheduling"),
        (request.expected_client_finance_version.value, facts.client_finance.account_version, "client_finance"),
        (request.expected_payroll_version.value, facts.payroll.payroll_version, "payroll"),
    )
    for expected, current, domain in values:
        if expected == current:
            continue
        code = "client_finance_candidate_stale" if domain == "client_finance" else f"{domain}_version_conflict"
        raise _workflow_error(request, ErrorCategory.CONFLICT, code, f"The {domain} version changed before Apply.")


def _validate_locked_staff_set(request, facts, staff_ids):
    current = {segment.staff_id for segment in facts.scheduling.segments}
    if current.issubset(set(staff_ids)):
        return
    raise _workflow_error(request, ErrorCategory.CONFLICT, "scheduling_lock_set_stale", "The impacted caregiver set expanded after preflight.")


def _raise_if_impacts_blocked(request, preview):
    blockers = tuple(sorted(set(preview.client_finance_impact.blockers) | set(preview.payroll_impact.blockers)))
    if not blockers:
        return
    raise _workflow_error(request, ErrorCategory.DOMAIN_BLOCKED, "terms_impact_blocked", "A downstream Domain blocked the Terms change.")


def _command_fingerprint(request):
    return fingerprint_payload({
        "case_no": request.case_no,
        "terms": request.proposed_terms.canonical_payload(),
        "order_version": request.expected_order_version.value,
        "scheduling_version": request.expected_scheduling_version.value,
        "client_finance_version": request.expected_client_finance_version.value,
        "payroll_version": request.expected_payroll_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor": request.actor.actor_id,
        "reason": request.reason,
    })


def _matched_receipt(request, command_fingerprint, stored):
    if stored.command_fingerprint == command_fingerprint:
        return stored.receipt
    raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")


def _workflow_error(request, category, code, message):
    return TermsWorkflowError(TypedError(category, code, message, request.correlation_id))
