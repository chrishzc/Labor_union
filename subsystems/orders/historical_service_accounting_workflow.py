"""Cross-domain Q/P/A for historical per-caregiver service-day accounting."""

from __future__ import annotations

from dataclasses import dataclass
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
    service_hours_per_day: int
    contractual_floor_fee: MoneyNTD
    client_identity_status: str
    assignments: tuple[HistoricalServiceAccountingAssignmentFacts, ...]
    client_policy_version: str
    client_hourly_rate: MoneyNTD

    def __post_init__(self) -> None:
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
        require_canonical_text(self.reason, "reason", 500)


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

    def preview(
        self, intent: ConfirmHistoricalServiceDaysIntent
    ) -> HistoricalServiceAccountingCandidate:
        return _candidate(self._repository.load(intent.case_no, for_update=False), intent)

    def apply(
        self, request: ApplyHistoricalServiceAccounting
    ) -> HistoricalServiceAccountingReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit:
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
            receipt = self._repository.persist(request, candidate)
            unit.commit()
            return receipt


def _candidate(
    facts: HistoricalServiceAccountingFacts,
    intent: ConfirmHistoricalServiceDaysIntent,
) -> HistoricalServiceAccountingCandidate:
    if intent.case_no != facts.case_no:
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    if facts.lifecycle_status is not OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED:
        raise ValueError("historical_order_lifecycle_transition_invalid")
    if facts.historical_day_revision != 0:
        raise ValueError("historical_actual_service_days_already_confirmed")
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
            facts.service_hours_per_day,
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
        service_hours_per_day=facts.service_hours_per_day,
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
    }
    return HistoricalServiceAccountingCandidate(
        facts,
        service_days,
        payroll,
        client_finance,
        fingerprint_payload(payload),
    )


def _decimal_hours(value: int):
    from decimal import Decimal

    return Decimal(value)


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
