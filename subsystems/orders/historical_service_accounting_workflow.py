"""
File: historical_service_accounting_workflow.py
Description: 保存歷史訂單實際服務天數與帳務比較結果。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Callable, Protocol

from domains.client_finance.historical_obligation_calculation import (
    HistoricalClientObligationCandidate,
    build_historical_client_obligation_candidate,
)
from domains.orders.historical_service_accounting import (
    HistoricalActualServiceDaysCandidate,
    HistoricalActualServiceDaysInput,
    HistoricalServiceAssignmentFacts,
    build_historical_actual_service_days_candidate,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import (
    AssignmentRateSnapshot,
    PayrollAdjustment,
    PayrollTerms,
)
from domains.payroll.historical_calculation import (
    HistoricalAssignmentServiceFacts,
    HistoricalCasePayrollCandidate,
    build_historical_case_payroll_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer
from domains.payroll.installments import allocate_historical_subsidy, confirmed_subsidy_installments
from subsystems.payroll.terms_impact import (
    HistoricalPayrollAllocation, HistoricalPayrollAssignment, PayrollTermsImpactCandidate,
    build_historical_payroll_attribution_impact,
)


@dataclass(frozen=True, slots=True)
class HistoricalServiceAccountingAssignmentFacts:
    assignment_identity: str
    staff_id: int
    staff_name: str
    rate_snapshot: AssignmentRateSnapshot
    effective_adjustment: MoneyNTD

    def __post_init__(self) -> None:
        require_canonical_text(self.assignment_identity, "assignment identity", 191)
        require_canonical_text(self.staff_name, "staff name", 100)
        if self.rate_snapshot.assignment_identity != self.assignment_identity:
            raise ValueError("historical_actual_service_days_assignment_mismatch")
        if not isinstance(self.effective_adjustment, MoneyNTD):
            raise TypeError("payroll adjustment must be MoneyNTD")


@dataclass(frozen=True, slots=True)
class HistoricalServiceAccountingFacts:
    case_no: str
    lifecycle_status: OrderLifecycleStatus
    lifecycle_version: int
    adoption_receipt_id: int
    adoption_source_identity: str
    historical_day_revision: int
    client_finance_version: int
    payroll_version: int
    contracted_service_days: int
    service_hours_per_day: Decimal | int
    contractual_floor_fee: MoneyNTD
    client_identity_status: str
    assignments: tuple[HistoricalServiceAccountingAssignmentFacts, ...]
    client_policy_version: str
    client_hourly_rate: MoneyNTD
    completed_on: date
    staff_payment_due_date: date | None
    attribution_adopted: bool = False
    accounting_pending: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.service_hours_per_day, float):
            raise TypeError("service hours per day must use Decimal or int")
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(
            self.adoption_source_identity, "historical adoption source identity", 191
        )
        require_canonical_text(
            self.client_policy_version, "client payment policy version", 100
        )
        if not isinstance(self.client_hourly_rate, MoneyNTD):
            raise TypeError("client hourly rate must be MoneyNTD")
        if self.client_hourly_rate.amount <= 0:
            raise ValueError("client hourly rate must be positive")
        if not isinstance(self.completed_on, date):
            raise TypeError("completed_on must be a date")
        if self.staff_payment_due_date is not None and not isinstance(
            self.staff_payment_due_date, date
        ):
            raise TypeError("staff_payment_due_date must be a date")
        for value, field in (
            (self.lifecycle_version, "lifecycle version"),
            (self.historical_day_revision, "historical day revision"),
            (self.client_finance_version, "client finance version"),
            (self.payroll_version, "payroll version"),
        ):
            require_nonnegative_integer(value, field)
        if self.adoption_receipt_id <= 0:
            raise ValueError("historical_accounting_obligation_binding_invalid")
        identities = tuple(item.assignment_identity for item in self.assignments)
        if not identities or identities != tuple(sorted(set(identities))):
            raise ValueError("historical_actual_service_days_assignment_mismatch")


@dataclass(frozen=True, slots=True)
class ConfirmHistoricalServiceDaysIntent:
    case_no: str
    caregivers: tuple[HistoricalActualServiceDaysInput, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)


@dataclass(frozen=True, slots=True)
class HistoricalAttributionIntent:
    case_no: str
    days_by_staff: tuple[tuple[int, int], ...]
    evidence: str


@dataclass(frozen=True, slots=True)
class HistoricalAttributionPreview:
    comparison: HistoricalServiceAccountingCandidate
    payroll: PayrollTermsImpactCandidate | None
    fingerprint: PreviewFingerprint
    reopen: bool
    manual_amounts: tuple[tuple[str, int, int, int], ...] = ()
    funding: tuple[tuple[int, str, int, int, date | None], ...] = ()
    original_funding: tuple[tuple[int, str, int, int, date | None], ...] = ()
    accounting_pending: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalServiceAccountingCandidate:
    facts: HistoricalServiceAccountingFacts
    service_days: HistoricalActualServiceDaysCandidate
    payroll: HistoricalCasePayrollCandidate
    client_finance: HistoricalClientObligationCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyHistoricalServiceAccounting:
    intent: ConfirmHistoricalServiceDaysIntent
    expected_lifecycle_version: int
    expected_historical_day_revision: int
    expected_client_finance_version: int
    expected_payroll_version: int
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "reason", 500, allow_empty=True)


@dataclass(frozen=True, slots=True)
class HistoricalServiceAccountingReceipt:
    case_no: str
    resulting_historical_day_revision: int
    resulting_client_finance_version: int
    resulting_payroll_version: int
    total_actual_service_days: int
    client_obligation_amount_ntd: int
    staff_obligation_amount_ntd: int
    preview_fingerprint: PreviewFingerprint
    replayed: bool = False
    accounting_pending: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StoredHistoricalServiceAccountingReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: HistoricalServiceAccountingReceipt


class HistoricalServiceAccountingError(Exception):
    def __init__(self, error: TypedError) -> None:
        self.error = error
        super().__init__(error.code)


class HistoricalServiceAccountingRepository(Protocol):
    def load(
        self, case_no: str, *, for_update: bool
    ) -> HistoricalServiceAccountingFacts: ...

    def find_receipt(
        self, key: IdempotencyKey
    ) -> StoredHistoricalServiceAccountingReceipt | None: ...

    def persist(
        self,
        request: ApplyHistoricalServiceAccounting,
        candidate: HistoricalServiceAccountingCandidate,
    ) -> HistoricalServiceAccountingReceipt: ...


class HistoricalServiceAccountingWorkflow:
    def __init__(
        self,
        repository: HistoricalServiceAccountingRepository,
        unit_of_work_factory: Callable[[], object],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, case_no: str) -> HistoricalServiceAccountingFacts:
        require_canonical_text(case_no, "case number", 50)
        return self._repository.load(case_no, for_update=False)

    def preview_attribution(self, intent: HistoricalAttributionIntent, *, lock=False) -> HistoricalAttributionPreview:
        require_canonical_text(intent.evidence, "service evidence", 500)
        days = dict(intent.days_by_staff)
        if len(days) != len(intent.days_by_staff) or len(days) < 2 or any(
            staff_id <= 0 or count <= 0 for staff_id, count in intent.days_by_staff
        ):
            raise ValueError("historical_attribution_days_invalid")
        facts, source, current_days, people, payable_versions, manual_amounts, previous_funding, pending = self._repository.load_attribution(
            intent.case_no, tuple(sorted(days)), for_update=lock,
        )
        if sum(days.values()) != current_days:
            raise ValueError("historical_attribution_total_days_changed")
        existing = {item.staff_id: item for item in facts.assignments}
        if len(existing) != len(facts.assignments) or set(existing) - days.keys():
            raise ValueError("historical_attribution_assignment_coverage_required")
        assignments = []
        for staff_id in sorted(days):
            if staff_id in existing:
                assignments.append(existing[staff_id])
                continue
            policy = source.case_policy
            if policy is None or policy.hourly_rate is None or policy.tiered is not None:
                raise ValueError("historical_attribution_rate_review_required")
            identity = f"new-staff:{staff_id}"
            assignments.append(HistoricalServiceAccountingAssignmentFacts(
                identity, staff_id, people[staff_id],
                AssignmentRateSnapshot(identity, policy.policy_version, policy.policy_kind, policy.hourly_rate),
                MoneyNTD(0),
            ))
        proposed = replace(facts, assignments=tuple(sorted(assignments, key=lambda item: item.assignment_identity)))
        service_intent = ConfirmHistoricalServiceDaysIntent(intent.case_no, tuple(
            HistoricalActualServiceDaysInput(item.assignment_identity, item.staff_id, days[item.staff_id])
            for item in proposed.assignments
        ))
        comparison = _candidate(proposed, service_intent, attribution=True)
        if pending:
            return HistoricalAttributionPreview(
                comparison, None, fingerprint_payload({
                    "comparison": comparison.fingerprint.value, "pending": pending,
                    "staff_payables": payable_versions, "evidence": intent.evidence,
                }), facts.lifecycle_status is OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
                accounting_pending=pending,
            )
        keys = {item.assignment_identity: f"historical:{facts.historical_day_revision + 1}:{item.staff_id}"
                for item in proposed.assignments}
        impact = build_historical_payroll_attribution_impact(
            source, HistoricalPayrollAllocation(intent.case_no, tuple(
                HistoricalPayrollAssignment(keys[item.assignment_identity],
                    int(item.assignment_identity.removeprefix("assignment:")) if item.staff_id in existing else None)
                for item in proposed.assignments
            )), replace(comparison.payroll, assignments=tuple(
                replace(item, assignment_identity=keys[item.assignment_identity]) for item in comparison.payroll.assignments
            )), tuple(replace(item.rate_snapshot, assignment_identity=keys[item.assignment_identity])
                       for item in proposed.assignments),
            PayrollTerms(facts.contracted_service_days, _decimal_hours(facts.service_hours_per_day), facts.contractual_floor_fee),
            f"historical-attribution:{intent.case_no}:{facts.historical_day_revision + 1}",
        )
        reopen = facts.lifecycle_status is OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED and (
            any(item.action.value == "establish" and item.amount.amount > 0 for item in impact.actions)
            or any(item.recovery_increase.amount > 0 or item.revised_entitlement.amount > item.paid_net_amount.amount
                   for item in impact.frozen_settlements)
        )
        funding = []
        original_funding = tuple(
            (staff_id, portion.funding_kind, portion.amount_ntd, portion.settled_ntd, portion.due_date)
            for staff_id, portion in previous_funding
        )
        if previous_funding:
            subsidy = allocate_historical_subsidy(
                sum(portion.amount_ntd for _, portion in previous_funding if portion.funding_kind == "subsidy"), days,
            )
            paid = {(staff_id, portion.funding_kind): portion.settled_ntd for staff_id, portion in previous_funding}
            due_dates = {(staff_id, portion.funding_kind): portion.due_date for staff_id, portion in previous_funding}
            for item in comparison.payroll.assignments:
                for portion in confirmed_subsidy_installments(
                    item.total_payable.amount, subsidy[item.staff_id], source.staff_payment_due_date, facts.completed_on,
                ):
                    pair = item.staff_id, portion.funding_kind
                    already_paid = paid.get(pair, 0)
                    if already_paid is None or already_paid > portion.amount:
                        raise ValueError("historical_attribution_source_payout_conflict")
                    funding.append((*pair, portion.amount, already_paid, due_dates.get(pair, portion.due_date)))
        return HistoricalAttributionPreview(comparison, impact, fingerprint_payload({
            "comparison": comparison.fingerprint.value, "payroll": impact.fingerprint.value,
            "staff_payables": payable_versions, "manual_amounts": manual_amounts, "evidence": intent.evidence,
            "funding": tuple((*row[:-1], row[-1].isoformat() if row[-1] else None) for row in funding),
            "original_funding": tuple((*row[:-1], row[-1].isoformat() if row[-1] else None) for row in original_funding),
        }), reopen, manual_amounts, tuple(funding), original_funding)

    def apply_attribution(self, intent, fingerprint, *, actor, reason, key, correlation, adopt_calculated_amounts=False):
        require_canonical_text(reason, "reason", 500)
        command = fingerprint_payload({
            "kind": "historical-service-attribution", "case_no": intent.case_no,
            "days": tuple(sorted(intent.days_by_staff)), "evidence": intent.evidence,
            "preview": fingerprint.value, "reason": reason, "actor": actor.actor_id,
            "adopt_calculated_amounts": adopt_calculated_amounts,
        })
        with self._unit_of_work_factory() as unit:
            self._repository.lock_attribution_order(intent.case_no)
            previous = self._repository.find_receipt(key)
            if previous is not None:
                if previous.command_fingerprint != command:
                    raise ValueError("historical_attribution_idempotency_conflict")
                return previous.receipt
            preview = self.preview_attribution(intent, lock=True)
            if preview.fingerprint != fingerprint:
                raise ValueError("historical_attribution_preview_stale")
            if preview.manual_amounts and not adopt_calculated_amounts:
                raise ValueError("historical_attribution_manual_confirmation_required")
            receipt = self._repository.persist_attribution(
                intent, preview, command, actor=actor, reason=reason, key=key, correlation=correlation,
            )
            unit.commit()
            return receipt

    def preview(
        self, intent: ConfirmHistoricalServiceDaysIntent
    ) -> HistoricalServiceAccountingCandidate:
        return _candidate(self._repository.load(intent.case_no, for_update=False), intent)

    def apply(
        self, request: ApplyHistoricalServiceAccounting
    ) -> HistoricalServiceAccountingReceipt:
        with self._unit_of_work_factory() as unit:
            receipt = self.apply_in_current_unit_of_work(request)
            unit.commit()
            return receipt

    def apply_in_current_unit_of_work(
        self, request: ApplyHistoricalServiceAccounting
    ) -> HistoricalServiceAccountingReceipt:
        command_fingerprint = _command_fingerprint(request)
        stored = self._repository.find_receipt(request.idempotency_key)
        if stored is not None:
            if stored.command_fingerprint != command_fingerprint:
                raise _error(
                    request,
                    ErrorCategory.IDEMPOTENCY_MISMATCH,
                    "idempotency_conflict",
                )
            return _replayed(stored.receipt)
        facts = self._repository.load(request.intent.case_no, for_update=True)
        candidate = _candidate(facts, request.intent)
        if (
            facts.lifecycle_version != request.expected_lifecycle_version
            or facts.historical_day_revision
            != request.expected_historical_day_revision
            or facts.client_finance_version
            != request.expected_client_finance_version
            or facts.payroll_version != request.expected_payroll_version
            or candidate.fingerprint != request.preview_fingerprint
        ):
            raise _error(
                request,
                ErrorCategory.CONFLICT,
                "historical_actual_service_days_candidate_stale",
                facts.lifecycle_version,
            )
        return self._repository.persist(request, candidate)

def _candidate(
    facts: HistoricalServiceAccountingFacts,
    intent: ConfirmHistoricalServiceDaysIntent,
    *, attribution: bool = False,
) -> HistoricalServiceAccountingCandidate:
    if intent.case_no != facts.case_no:
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    if facts.attribution_adopted and not attribution:
        raise ValueError("historical_attribution_formal_workflow_required")
    allowed = {OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED}
    if attribution:
        allowed.update({OrderLifecycleStatus.HISTORICAL_IN_SERVICE, OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED})
    if facts.lifecycle_status not in allowed:
        raise ValueError("historical_order_lifecycle_transition_invalid")
    service_days = build_historical_actual_service_days_candidate(
        case_no=facts.case_no,
        assignments=tuple(
            HistoricalServiceAssignmentFacts(item.assignment_identity, item.staff_id)
            for item in facts.assignments
        ),
        inputs=intent.caregivers,
        contracted_service_days=facts.contracted_service_days,
        service_hours_per_day=_decimal_hours(facts.service_hours_per_day),
        contractual_floor_fee_ntd=facts.contractual_floor_fee.amount,
    )
    payroll = build_historical_case_payroll_candidate(
        tuple(
            HistoricalAssignmentServiceFacts(
                item.assignment_identity,
                item.staff_id,
                next(
                    allocation.actual_service_days
                    for allocation in service_days.allocations
                    if allocation.assignment_identity == item.assignment_identity
                ),
            )
            for item in facts.assignments
        ),
        tuple(item.rate_snapshot for item in facts.assignments),
        PayrollTerms(
            facts.contracted_service_days,
            _decimal_hours(facts.service_hours_per_day),
            facts.contractual_floor_fee,
        ),
        tuple(
            PayrollAdjustment(item.assignment_identity, item.effective_adjustment)
            for item in facts.assignments
            if not item.effective_adjustment.is_zero
        ),
    )
    client_finance = build_historical_client_obligation_candidate(
        identity_status=facts.client_identity_status,
        client_policy_version=facts.client_policy_version,
        client_hourly_rate=facts.client_hourly_rate,
        actual_service_days=service_days.total_actual_service_days,
        service_hours_per_day=_decimal_hours(facts.service_hours_per_day),
        historical_floor_fee=MoneyNTD(service_days.historical_floor_fee_ntd),
    )
    payload = {
        "case_no": facts.case_no,
        "lifecycle_status": facts.lifecycle_status.value,
        "lifecycle_version": facts.lifecycle_version,
        "adoption_receipt_id": facts.adoption_receipt_id,
        "adoption_source_identity": facts.adoption_source_identity,
        "historical_day_revision": facts.historical_day_revision,
        "client_finance_version": facts.client_finance_version,
        "payroll_version": facts.payroll_version,
        "service_days_fingerprint": service_days.fingerprint.value,
        "payroll_fingerprint": payroll.fingerprint.value,
        "client_finance_fingerprint": client_finance.fingerprint.value,
        "staff_payment_due_date": facts.staff_payment_due_date.isoformat() if facts.staff_payment_due_date else None,
    }
    return HistoricalServiceAccountingCandidate(
        facts,
        service_days,
        payroll,
        client_finance,
        fingerprint_payload(payload),
    )


def _decimal_hours(value: Decimal | int) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _command_fingerprint(
    request: ApplyHistoricalServiceAccounting,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "case_no": request.intent.case_no,
            "caregivers": tuple(
                {
                    "assignment_identity": item.assignment_identity,
                    "staff_id": item.staff_id,
                    "actual_service_days": item.actual_service_days,
                }
                for item in request.intent.caregivers
            ),
            "expected_versions": (
                request.expected_lifecycle_version,
                request.expected_historical_day_revision,
                request.expected_client_finance_version,
                request.expected_payroll_version,
            ),
            "preview_fingerprint": request.preview_fingerprint.value,
            "idempotency_key": request.idempotency_key.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
        }
    )


def _replayed(
    receipt: HistoricalServiceAccountingReceipt,
) -> HistoricalServiceAccountingReceipt:
    return HistoricalServiceAccountingReceipt(
        receipt.case_no,
        receipt.resulting_historical_day_revision,
        receipt.resulting_client_finance_version,
        receipt.resulting_payroll_version,
        receipt.total_actual_service_days,
        receipt.client_obligation_amount_ntd,
        receipt.staff_obligation_amount_ntd,
        receipt.preview_fingerprint,
        True,
    )


def _error(request, category, code, current_version=None):
    from shared_kernel.identities import ExpectedVersion

    return HistoricalServiceAccountingError(
        TypedError(
            category,
            code,
            "歷史訂單服務天數與帳務無法安全套用。",
            request.correlation_id,
            domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else (),
            current_version=(
                None if current_version is None else ExpectedVersion(current_version)
            ),
        )
    )


__all__ = [name for name in globals() if name.startswith("Historical") or name.startswith("Apply") or name.startswith("Confirm") or name.startswith("Stored")]
