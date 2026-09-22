"""
File: terms_workflow.py
Description: 協調 Orders Terms 的 Query／Preview／Apply、跨域影響與原子 receipt。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

from domains.client_finance.obligation_planning import (
    build_preassignment_client_finance_noop,
    build_client_finance_terms_impact,
)
from domains.orders.lifecycle import (
    build_preassignment_terms_lifecycle_impact,
    build_terms_lifecycle_impact,
)
from domains.orders.service_date_confirmation import ConfirmedServiceDateCandidate
from domains.orders.terms import (
    is_unique_cooking_requirement_correction,
    validate_terms_change,
)
from domains.scheduling.generation import (
    build_generation_candidate,
    build_preassignment_cooking_correction_candidate,
    build_preassignment_terms_candidate,
)
from shared_kernel.clock import BusinessClock
from shared_kernel.errors import TypedError
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text
from subsystems.payroll.terms_impact import (
    build_payroll_terms_impact,
    build_preassignment_payroll_noop,
    PayrollSpecialPayEventCandidate,
)


_TERMS_SOURCE_EVENT_FAMILY = "order-terms"


@dataclass(frozen=True, slots=True)
class TermsWorkflowFacts:
    order: Any
    scheduling: Any
    planned_service_dates: tuple[Any, ...]
    planned_end_date: Any
    client_finance: Any | None
    payroll: Any | None
    lifecycle: Any
    confirmed_service_date_version: int | None = None
    confirmed_service_dates: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class OrderTermsApplyRequest:
    case_no: str
    proposed_terms: Any
    expected_order_version: Any
    expected_scheduling_version: Any
    expected_client_finance_version: Any | None
    expected_payroll_version: Any | None
    preview_fingerprint: Any
    idempotency_key: Any | None
    actor: Any
    reason: str | None
    correlation_id: Any
    replacement_service_dates: tuple[date, ...] | None = None
    replacement_allocations: tuple[tuple[int, int], ...] = ()
    requires_formal_apply: bool = True

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if self.reason is not None:
            require_canonical_text(self.reason, "terms change reason", 500)
        if self.requires_formal_apply and (self.idempotency_key is None or self.reason is None):
            raise ValueError("formal terms Apply requires idempotency key and reason")


@dataclass(frozen=True, slots=True)
class OrderTermsPreview:
    before: Any
    after: Any
    scheduling: Any
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int | None
    payroll_version: int | None
    client_finance_impact: Any | None
    payroll_impact: Any | None
    lifecycle_impact: Any
    planned_end_date: Any
    confirmed_service_date_candidate: ConfirmedServiceDateCandidate | None
    confirmed_service_date_current_version: int | None
    fingerprint: Any
    requires_formal_apply: bool = True


@dataclass(frozen=True, slots=True)
class OrderTermsReceipt:
    case_no: str
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int | None
    payroll_version: int | None
    lifecycle_status: Any
    service_data_lock_formed: bool
    cancelled_assignment_ids: tuple[int, ...]
    created_assignment_keys: tuple[str, ...]
    official_service_day_count: int
    official_service_hours: float | int
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
    special_pay_events: tuple[PayrollSpecialPayEventCandidate, ...] = ()


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

    def preview(self, case_no: str, proposed_terms: Any, *,
                replacement_service_dates=None, replacement_allocations=()) -> Any:
        return self._build_preview(
            self._repository.load_for_preview(case_no), proposed_terms,
            replacement_service_dates, replacement_allocations,
        )

    def apply(self, request: OrderTermsApplyRequest) -> Any:
        command_fingerprint = _command_fingerprint(request) if request.requires_formal_apply else None
        staff_ids = self._repository.preflight_impacted_staff_ids(request.case_no)
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self._apply_in_current_uow(
                request, command_fingerprint, staff_ids
            )
            unit_of_work.commit()
            return receipt

    def apply_in_current_uow(self, request: OrderTermsApplyRequest) -> Any:
        command_fingerprint = _command_fingerprint(request) if request.requires_formal_apply else None
        staff_ids = self._repository.preflight_impacted_staff_ids(request.case_no)
        return self._apply_in_current_uow(request, command_fingerprint, staff_ids)

    def _apply_in_current_uow(self, request, command_fingerprint, staff_ids):
        if request.requires_formal_apply:
            replay = self._claim_or_replay(request, command_fingerprint)
            if replay is not None:
                return replay
        facts = self._repository.load_for_apply(request.case_no, staff_ids)
        preview = self._fresh_preview(request, facts, staff_ids)
        receipt = _build_receipt(preview)
        if preview.requires_formal_apply:
            self._persist(request, preview, command_fingerprint, receipt)
        else:
            self._persist_ordinary(request, preview, receipt)
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
        if facts.order.case_no != request.case_no:
            raise _workflow_error(
                request,
                ErrorCategory.CONFLICT,
                "order_case_mismatch",
                "The locked Orders root belongs to another case.",
            )
        _validate_locked_staff_set(request, facts, staff_ids)
        _validate_versions(request, facts)
        preview = self._build_preview(facts, request.proposed_terms,
                                      request.replacement_service_dates,
                                      request.replacement_allocations)
        if preview.requires_formal_apply != request.requires_formal_apply:
            raise _workflow_error(
                request,
                ErrorCategory.CONFLICT,
                "terms_apply_mode_changed",
                "The Terms Apply mode changed after Preview.",
            )
        if preview.fingerprint != request.preview_fingerprint:
            raise _workflow_error(
                request,
                ErrorCategory.CONFLICT,
                "stale_preview",
                "The business facts changed after Preview.",
            )
        _raise_if_impacts_blocked(request, preview)
        return preview

    def _build_preview(self, facts, proposed_terms, replacement_service_dates=None,
                       replacement_allocations=()):
        validate_terms_change(facts.order, proposed_terms)
        candidate_facts = _replacement_facts(
            facts, proposed_terms, replacement_service_dates, replacement_allocations
        )
        scheduling = _scheduling_candidate(candidate_facts, proposed_terms)
        change_identity = f"terms:{scheduling.case_no}:{scheduling.generation_number}"
        if not facts.scheduling.segments:
            if facts.client_finance is None and facts.payroll is None:
                client_finance = None
                payroll = None
                lifecycle = build_preassignment_terms_lifecycle_impact(
                    facts.lifecycle,
                    scheduling,
                    self._clock.now(),
                )
            else:
                client_finance = build_preassignment_client_finance_noop(
                    facts.client_finance, proposed_terms, scheduling, change_identity
                )
                payroll = build_preassignment_payroll_noop(
                    facts.payroll, scheduling, proposed_terms, change_identity
                )
                lifecycle = build_terms_lifecycle_impact(
                    facts.lifecycle,
                    proposed_terms,
                    scheduling,
                    client_finance.settlement,
                    self._clock.now(),
                )
        else:
            if facts.client_finance is None or facts.payroll is None:
                raise ValueError("assigned_terms_downstream_facts_required")
            client_finance = build_client_finance_terms_impact(
                facts.client_finance, proposed_terms, scheduling, change_identity
            )
            payroll = build_payroll_terms_impact(
                facts.payroll, scheduling, proposed_terms, change_identity
            )
            lifecycle = build_terms_lifecycle_impact(
                facts.lifecycle,
                proposed_terms,
                scheduling,
                client_finance.settlement,
                self._clock.now(),
            )
        return _preview_result(facts, proposed_terms, scheduling, client_finance, payroll, lifecycle,
                               replacement_service_dates)

    def _persist_ordinary(self, request, preview, receipt):
        self._repository.update_order_terms(
            OrderTermsPersistenceCommand(
                case_no=request.case_no,
                terms=request.proposed_terms,
                expected_order_version=preview.order_version,
                resulting_order_version=receipt.order_version,
                planned_end_date=preview.planned_end_date,
                actual_end_date=preview.lifecycle_impact.actual_end_date,
                lifecycle_status=preview.lifecycle_impact.after_status,
            )
        )

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
        if preview.client_finance_impact is not None and _client_finance_impact_mutates(preview.client_finance_impact):
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
        if preview.payroll_impact is not None and _payroll_impact_mutates(preview.payroll_impact):
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
                client_settlement_fingerprint=(
                    preview.client_finance_impact.settlement.fingerprint
                    if preview.client_finance_impact is not None
                    else None
                ),
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
                planned_end_date=preview.planned_end_date,
                actual_end_date=preview.lifecycle_impact.actual_end_date,
                lifecycle_status=preview.lifecycle_impact.after_status,
            )
        )
        if preview.confirmed_service_date_candidate is not None:
            self._repository.replace_confirmed_service_dates(
                preview.confirmed_service_date_candidate,
                request,
                command_fingerprint,
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

def _replacement_facts(facts, terms, dates, allocations):
    if dates is None:
        if allocations:
            raise ValueError("confirmed_service_dates_reconfirmation_required")
        return facts
    if facts.scheduling.service_started:
        raise ValueError("service_started_replacement_blocked")
    if facts.confirmed_service_date_version is None and not facts.scheduling.segments:
        raise ValueError("preassignment_replacement_not_required")
    # The same target count is used for dates and Scheduling, before any writer runs.
    ConfirmedServiceDateCandidate(facts.order.case_no, facts.order.version,
                                 facts.scheduling.aggregate_version, dates, terms.service_days)
    if any(d < terms.planned_start_date or
           d >= terms.planned_start_date + timedelta(days=terms.service_days + 45)
           for d in dates):
        raise ValueError("replacement_service_date_outside_selectable_range")
    segments = facts.scheduling.segments
    if segments:
        counts = dict(allocations)
        if (len(counts) != len(allocations)
                or set(counts) != {s.assignment_id for s in segments}
                or any(type(n) is not int or n <= 0 for n in counts.values())
                or sum(counts.values()) != terms.service_days):
            raise ValueError("scheduling_reallocation_required")
        rebuilt = []
        offset = 0
        for segment in sorted(segments, key=lambda s: s.sequence):
            count = counts[segment.assignment_id]
            segment_dates = dates[offset:offset + count]
            offset += count
            rebuilt.append(replace(segment, service_day_count=count,
                                   assigned_start_date=segment_dates[0],
                                   assigned_end_date=segment_dates[-1],
                                   official_service_dates=segment_dates))
        segments = tuple(rebuilt)
    elif allocations:
        raise ValueError("scheduling_reallocation_required")
    # Dates already belong to the proposed start; avoid shifting them a second time.
    return replace(facts, order=replace(facts.order, terms=replace(
        facts.order.terms, planned_start_date=terms.planned_start_date)),
        scheduling=replace(facts.scheduling, segments=segments), planned_service_dates=dates)


def _scheduling_candidate(facts, proposed_terms):
    if not facts.scheduling.segments:
        if is_unique_cooking_requirement_correction(
            facts.order.terms, proposed_terms
        ):
            return build_preassignment_cooking_correction_candidate(
                facts.scheduling,
                facts.order.terms,
                proposed_terms,
            )
        return build_preassignment_terms_candidate(
            facts.scheduling,
            facts.order.terms,
            proposed_terms,
        )
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
            official_service_dates=tuple(
                value + timedelta(days=day_shift)
                for value in segment.official_service_dates
            ),
        )
        for segment in facts.scheduling.segments
    )
    return build_generation_candidate(
        replace(facts.scheduling, segments=shifted_segments),
        proposed_terms,
        shifted_dates,
    )


def _preview_result(
    facts,
    proposed_terms,
    scheduling,
    client_finance,
    payroll,
    lifecycle,
    replacement_service_dates=None,
):
    planned_end_date = _planned_end_date(
        scheduling,
        facts.planned_end_date,
        facts.order.terms,
        proposed_terms,
    )
    confirmed_service_date_candidate = _confirmed_service_date_candidate(
        facts,
        proposed_terms,
        scheduling,
        replacement_service_dates,
    )
    if replacement_service_dates is not None:
        planned_end_date = replacement_service_dates[-1]
    requires_formal_apply = _requires_formal_apply(
        facts,
        client_finance,
        payroll,
        lifecycle,
        confirmed_service_date_candidate,
    )
    return OrderTermsPreview(
        before=facts.order.terms,
        after=proposed_terms,
        scheduling=scheduling,
        order_version=facts.order.version,
        scheduling_version=facts.scheduling.aggregate_version,
        scheduling_generation=facts.scheduling.generation_number,
        client_finance_version=(
            facts.client_finance.account_version
            if facts.client_finance is not None
            else None
        ),
        payroll_version=(
            facts.payroll.payroll_version if facts.payroll is not None else None
        ),
        client_finance_impact=client_finance,
        payroll_impact=payroll,
        lifecycle_impact=lifecycle,
        planned_end_date=planned_end_date,
        confirmed_service_date_candidate=confirmed_service_date_candidate,
        confirmed_service_date_current_version=facts.confirmed_service_date_version,
        requires_formal_apply=requires_formal_apply,
        fingerprint=fingerprint_payload(
            _preview_fingerprint_payload(
                facts,
                proposed_terms,
                scheduling,
                client_finance,
                payroll,
                lifecycle,
                planned_end_date,
                confirmed_service_date_candidate,
            )
        ),
    )


def _preview_fingerprint_payload(
    facts,
    proposed_terms,
    scheduling,
    client_finance,
    payroll,
    lifecycle,
    planned_end_date,
    confirmed_service_date_candidate,
):
    return {
        "case_no": facts.order.case_no,
        "terms": proposed_terms.canonical_payload(),
        "order_version": facts.order.version,
        "scheduling_version": facts.scheduling.aggregate_version,
        "client_finance_version": (
            facts.client_finance.account_version
            if facts.client_finance is not None
            else None
        ),
        "payroll_version": (
            facts.payroll.payroll_version if facts.payroll is not None else None
        ),
        "scheduling": _scheduling_payload(scheduling),
        "client_finance": (
            client_finance.fingerprint.value if client_finance is not None else None
        ),
        "payroll": payroll.fingerprint.value if payroll is not None else None,
        "lifecycle": lifecycle.fingerprint.value,
        "requires_formal_apply": _requires_formal_apply(
            facts,
            client_finance,
            payroll,
            lifecycle,
            confirmed_service_date_candidate,
        ),
        "planned_end_date": (
            planned_end_date.isoformat()
            if planned_end_date is not None
            else None
        ),
        "confirmed_service_dates": (
            None
            if confirmed_service_date_candidate is None
            else {
                "current_version": facts.confirmed_service_date_version,
                "replacement_fingerprint": confirmed_service_date_candidate.fingerprint.value,
            }
        ),
    }


def _scheduling_payload(scheduling):
    return tuple(
        (item.candidate_key, item.staff_id, tuple(value.isoformat() for value in item.service_dates))
        for item in scheduling.assignments
    )


def _build_receipt(preview):
    assignments = preview.scheduling.assignments
    scheduling_version = (
        preview.scheduling.resulting_aggregate_version
        if preview.requires_formal_apply
        else preview.scheduling_version
    )
    scheduling_generation = (
        preview.scheduling.generation_number
        if preview.requires_formal_apply
        else preview.scheduling_generation
    )
    return OrderTermsReceipt(
        preview.scheduling.case_no,
        preview.order_version + 1,
        scheduling_version,
        scheduling_generation,
        (
            preview.client_finance_impact.resulting_account_version
            if preview.requires_formal_apply and preview.client_finance_impact is not None
            else preview.client_finance_version
        ),
        (
            preview.payroll_impact.resulting_payroll_version
            if preview.requires_formal_apply and preview.payroll_impact is not None
            else preview.payroll_version
        ),
        preview.lifecycle_impact.after_status,
        (
            preview.requires_formal_apply
            and preview.lifecycle_impact.service_data_lock_should_exist
            and not preview.lifecycle_impact.service_data_lock_was_present
        ),
        preview.scheduling.cancelled_assignment_ids if preview.requires_formal_apply else (),
        tuple(item.candidate_key for item in assignments) if preview.requires_formal_apply else (),
        sum(len(item.service_dates) for item in assignments) if preview.requires_formal_apply else 0,
        sum(item.actual_hours for item in assignments) if preview.requires_formal_apply else 0,
        preview.fingerprint,
    )


def _requires_formal_apply(facts, client_finance, payroll, lifecycle, confirmed_dates):
    return bool(
        facts.scheduling.segments
        or confirmed_dates is not None
        or (client_finance is not None and _client_finance_impact_mutates(client_finance))
        or (payroll is not None and _payroll_impact_mutates(payroll))
        or lifecycle.after_status != lifecycle.before_status
        or lifecycle.service_data_lock_should_exist != lifecycle.service_data_lock_was_present
        or lifecycle.alert_codes
    )


def _planned_end_date(
    scheduling,
    current_planned_end_date,
    current_terms,
    proposed_terms,
):
    service_dates = tuple(
        value for item in scheduling.assignments for value in item.service_dates
    )
    if service_dates:
        return max(service_dates)
    day_shift = proposed_terms.planned_start_date - current_terms.planned_start_date
    service_day_delta = proposed_terms.service_days - current_terms.service_days
    if current_planned_end_date is None:
        if day_shift.days == 0 and service_day_delta == 0:
            return None
        return proposed_terms.planned_start_date + timedelta(
            days=proposed_terms.service_days - 1
        )
    return current_planned_end_date + day_shift + timedelta(days=service_day_delta)


def _confirmed_service_date_candidate(facts, proposed_terms, scheduling, replacement_dates=None):
    if replacement_dates is not None:
        return ConfirmedServiceDateCandidate(
            case_no=facts.order.case_no,
            order_version=facts.order.version + 1,
            scheduling_version=scheduling.resulting_aggregate_version,
            service_dates=replacement_dates,
            contracted_service_days=proposed_terms.service_days,
            current_confirmed_version=facts.confirmed_service_date_version,
        )
    if facts.confirmed_service_date_version is None:
        return None
    if facts.order.terms.service_days != proposed_terms.service_days:
        raise ValueError("confirmed_service_dates_reconfirmation_required")
    day_shift = (
        proposed_terms.planned_start_date - facts.order.terms.planned_start_date
    ).days
    if day_shift == 0:
        return None
    shifted_dates = tuple(
        value + timedelta(days=day_shift)
        for value in facts.confirmed_service_dates
    )
    return ConfirmedServiceDateCandidate(
        case_no=facts.order.case_no,
        order_version=facts.order.version + 1,
        scheduling_version=scheduling.resulting_aggregate_version,
        service_dates=shifted_dates,
        contracted_service_days=proposed_terms.service_days,
    )


def _client_finance_impact_mutates(candidate):
    return candidate.resulting_account_version != candidate.expected_account_version


def _payroll_impact_mutates(candidate):
    return candidate.resulting_payroll_version != candidate.expected_payroll_version


def _validate_versions(request, facts):
    values = (
        (request.expected_order_version.value, facts.order.version, "order"),
        (request.expected_scheduling_version.value, facts.scheduling.aggregate_version, "scheduling"),
        (
            _optional_version_value(request.expected_client_finance_version),
            facts.client_finance.account_version if facts.client_finance is not None else None,
            "client_finance",
        ),
        (
            _optional_version_value(request.expected_payroll_version),
            facts.payroll.payroll_version if facts.payroll is not None else None,
            "payroll",
        ),
    )
    for expected, current, domain in values:
        if expected == current:
            continue
        code = "client_finance_candidate_stale" if domain == "client_finance" else f"{domain}_version_conflict"
        raise _workflow_error(request, ErrorCategory.CONFLICT, code, f"The {domain} version changed before Apply.")


def _optional_version_value(value):
    return value.value if value is not None else None


def _validate_locked_staff_set(request, facts, staff_ids):
    current = {segment.staff_id for segment in facts.scheduling.segments}
    if current.issubset(set(staff_ids)):
        return
    raise _workflow_error(request, ErrorCategory.CONFLICT, "scheduling_lock_set_stale", "The impacted caregiver set expanded after preflight.")


def _raise_if_impacts_blocked(request, preview):
    blockers = tuple(sorted(
        set(preview.client_finance_impact.blockers if preview.client_finance_impact is not None else ())
        | set(preview.payroll_impact.blockers if preview.payroll_impact is not None else ())
    ))
    if not blockers:
        return
    raise _workflow_error(request, ErrorCategory.DOMAIN_BLOCKED, "terms_impact_blocked", "A downstream Domain blocked the Terms change.")


def _command_fingerprint(request):
    return fingerprint_payload({
        "case_no": request.case_no,
        "terms": request.proposed_terms.canonical_payload(),
        "order_version": request.expected_order_version.value,
        "scheduling_version": request.expected_scheduling_version.value,
        "client_finance_version": _optional_version_value(request.expected_client_finance_version),
        "payroll_version": _optional_version_value(request.expected_payroll_version),
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor": request.actor.actor_id,
        "reason": request.reason,
        **({"replacement_service_dates": ([d.isoformat() for d in request.replacement_service_dates]
                                             if request.replacement_service_dates is not None else None),
            "replacement_allocations": request.replacement_allocations}
           if request.replacement_service_dates is not None or request.replacement_allocations else {}),
    })


def _matched_receipt(request, command_fingerprint, stored):
    if stored.receipt.case_no != request.case_no:
        raise _workflow_error(
            request,
            ErrorCategory.CONFLICT,
            "receipt_case_mismatch",
            "The stored receipt belongs to another case.",
        )
    if stored.command_fingerprint == command_fingerprint:
        return stored.receipt
    raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")


def _workflow_error(request, category, code, message):
    return TermsWorkflowError(TypedError(category, code, message, request.correlation_id))
