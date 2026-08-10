"""Pure candidate builder for a case's first canonical architecture state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191
_CASE_NUMBER_MAXIMUM_LENGTH = 50
_HOURLY_RATE_BY_POLICY = {
    "citizen": MoneyNTD(300),
    "subsidized_citizen": MoneyNTD(350),
    "non_citizen": MoneyNTD(320),
}


class BootstrapIssue(StrEnum):
    CASE_NOT_FOUND = "case_not_found"
    INVALID_ROOT_FACTS = "invalid_case_architecture_root_facts"
    RATE_POLICY_NOT_FOUND = "payroll_rate_policy_not_found"
    INTEGRITY_VIOLATION = "case_architecture_bootstrap_integrity_violation"


class PayrollPolicyKind(StrEnum):
    CITIZEN = "citizen"
    SUBSIDIZED_CITIZEN = "subsidized_citizen"
    NON_CITIZEN = "non_citizen"


class BootstrapMutation(StrEnum):
    CREATE = "create"
    CREATE_WITH_EXISTING_SCHEDULING = "create_with_existing_scheduling"
    KEEP_EXISTING = "keep_existing"


class BootstrapDomainError(ValueError):
    def __init__(self, issue: BootstrapIssue, message: str) -> None:
        super().__init__(message)
        self.issue = issue


@dataclass(frozen=True, slots=True)
class RatePolicyFacts:
    policy_version: str
    policy_kind: PayrollPolicyKind
    hourly_rate: MoneyNTD
    effective_from: date
    effective_until: date | None

    # Kept cohesive so one policy object cannot bypass interval or money checks.
    def __post_init__(self) -> None:
        require_canonical_text(
            self.policy_version,
            "rate policy version",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        if not isinstance(self.policy_kind, PayrollPolicyKind):
            raise TypeError("payroll policy kind is invalid")
        if not isinstance(self.hourly_rate, MoneyNTD):
            raise TypeError("hourly rate must be MoneyNTD")
        if self.hourly_rate.amount <= 0:
            raise ValueError("hourly rate must be positive")
        if self.hourly_rate != _HOURLY_RATE_BY_POLICY[self.policy_kind.value]:
            raise ValueError("payroll rate policy amount is not approved")
        _require_date(self.effective_from, "rate policy effective from")
        if self.effective_until is not None:
            _require_date(self.effective_until, "rate policy effective until")
        if (
            self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("rate policy interval is inverted")

    def applies_on(self, service_start_date: date) -> bool:
        if service_start_date < self.effective_from:
            return False
        return (
            self.effective_until is None
            or service_start_date <= self.effective_until
        )


@dataclass(frozen=True, slots=True)
class ClientPaymentTermsRootFacts:
    policy_version: str
    client_hourly_rate: MoneyNTD
    deposit_service_days: int
    deposit_due_date: date
    first_payment_due_date: date
    second_payment_due_date: date | None = None

    def __post_init__(self) -> None:
        require_canonical_text(
            self.policy_version,
            "client payment policy version",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        if not isinstance(self.client_hourly_rate, MoneyNTD):
            raise TypeError("client hourly rate must be MoneyNTD")
        if self.client_hourly_rate.amount <= 0:
            raise ValueError("client hourly rate must be positive")
        require_nonnegative_integer(
            self.deposit_service_days,
            "deposit service days",
        )
        _require_date(self.deposit_due_date, "deposit due date")
        _require_date(self.first_payment_due_date, "first payment due date")
        if self.second_payment_due_date is not None:
            _require_date(
                self.second_payment_due_date,
                "second payment due date",
            )


@dataclass(frozen=True, slots=True)
class CaseArchitectureBootstrapIntent:
    case_no: str
    client_payment_terms: ClientPaymentTermsRootFacts
    payroll_policy_version: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        if not isinstance(
            self.client_payment_terms,
            ClientPaymentTermsRootFacts,
        ):
            raise TypeError("client payment terms are invalid")
        require_canonical_text(
            self.payroll_policy_version,
            "payroll policy version",
            _IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class CaseRootFacts:
    case_no: str
    order_version: int
    planned_start_date: date | None
    service_days: int
    service_hours_per_day: int
    source_identity_status: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        require_nonnegative_integer(self.order_version, "order version")
        require_canonical_text(
            self.source_identity_status,
            "source identity status",
            _IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class BootstrapPresence:
    client_finance_account: bool = False
    client_payment_terms: bool = False
    payroll_case_account: bool = False
    payroll_case_policy: bool = False
    scheduling_aggregate: bool = False
    root_event_fingerprint: PreviewFingerprint | None = None
    components_consistent: bool = True
    scheduling_version: int = 0
    scheduling_generation: int = 0

    def __post_init__(self) -> None:
        values = (
            self.client_finance_account,
            self.client_payment_terms,
            self.payroll_case_account,
            self.payroll_case_policy,
            self.scheduling_aggregate,
        )
        if any(not isinstance(value, bool) for value in values):
            raise TypeError("bootstrap presence flags must be bool")
        if not isinstance(self.components_consistent, bool):
            raise TypeError("bootstrap consistency flag must be bool")
        require_nonnegative_integer(
            self.scheduling_version,
            "scheduling version",
        )
        require_nonnegative_integer(
            self.scheduling_generation,
            "scheduling generation",
        )
        if not self.scheduling_aggregate and (
            self.scheduling_version or self.scheduling_generation
        ):
            raise ValueError("missing scheduling aggregate has state")

    @property
    def has_component(self) -> bool:
        return any(
            (
                self.client_finance_account,
                self.client_payment_terms,
                self.payroll_case_account,
                self.payroll_case_policy,
                self.scheduling_aggregate,
            )
        )

    @property
    def complete(self) -> bool:
        return all(
            (
                self.client_finance_account,
                self.client_payment_terms,
                self.payroll_case_account,
                self.payroll_case_policy,
                self.scheduling_aggregate,
                self.root_event_fingerprint is not None,
                self.components_consistent,
            )
        )


@dataclass(frozen=True, slots=True)
class CaseArchitectureBootstrapFacts:
    order: CaseRootFacts
    payroll_rate_policy: RatePolicyFacts | None
    presence: BootstrapPresence = BootstrapPresence()


@dataclass(frozen=True, slots=True)
class CaseArchitectureBootstrapCandidate:
    case_no: str
    order_version: int
    source_identity_status: str
    client_payment_terms: ClientPaymentTermsRootFacts
    payroll_rate_policy: RatePolicyFacts
    scheduling_generation: int
    mutation: BootstrapMutation
    fingerprint: PreviewFingerprint
    scheduling_version: int = 0


def build_case_architecture_bootstrap_candidate(
    facts: CaseArchitectureBootstrapFacts,
    intent: CaseArchitectureBootstrapIntent,
) -> CaseArchitectureBootstrapCandidate:
    _validate_case_identity(facts, intent)
    _validate_order_root_facts(facts.order)
    _validate_client_payment_terms(facts.order, intent.client_payment_terms)
    payroll_policy = _require_rate_policy(facts, intent)
    scheduling_version = facts.presence.scheduling_version
    scheduling_generation = facts.presence.scheduling_generation
    fingerprint = _candidate_fingerprint(
        facts.order,
        intent,
        payroll_policy,
        scheduling_version,
        scheduling_generation,
    )
    mutation = _resolve_mutation(facts.presence, fingerprint)
    return CaseArchitectureBootstrapCandidate(
        case_no=intent.case_no,
        order_version=facts.order.order_version,
        source_identity_status=facts.order.source_identity_status,
        client_payment_terms=intent.client_payment_terms,
        payroll_rate_policy=payroll_policy,
        scheduling_version=scheduling_version,
        scheduling_generation=scheduling_generation,
        mutation=mutation,
        fingerprint=fingerprint,
    )


def policy_kind_for_identity(identity_status: str) -> PayrollPolicyKind:
    mappings = {
        "一般市民": PayrollPolicyKind.CITIZEN,
        "補助市民": PayrollPolicyKind.SUBSIDIZED_CITIZEN,
        "低收入戶": PayrollPolicyKind.SUBSIDIZED_CITIZEN,
        "中低收入戶": PayrollPolicyKind.SUBSIDIZED_CITIZEN,
        "非市民": PayrollPolicyKind.NON_CITIZEN,
    }
    policy_kind = mappings.get(identity_status)
    if policy_kind is None:
        _raise_invalid("client identity has no confirmed payroll policy mapping")
    return policy_kind


def _validate_case_identity(facts, intent) -> None:
    if facts.order.case_no == intent.case_no:
        return
    raise BootstrapDomainError(
        BootstrapIssue.INTEGRITY_VIOLATION,
        "Bootstrap case facts do not belong to the requested case.",
    )


def _validate_order_root_facts(order: CaseRootFacts) -> None:
    if order.planned_start_date is None:
        _raise_invalid("planned service start date is required")
    _require_date(order.planned_start_date, "planned service start date")
    try:
        require_positive_integer(order.service_days, "service days")
        require_positive_integer(
            order.service_hours_per_day,
            "service hours per day",
        )
    except (TypeError, ValueError) as exception:
        _raise_invalid(str(exception))
def _validate_client_payment_terms(order, payment_terms) -> None:
    if payment_terms.deposit_service_days > order.service_days:
        _raise_invalid("deposit service days exceed contracted service days")
    expected_deposit_days = _deposit_days_for_identity(
        order.source_identity_status
    )
    if payment_terms.deposit_service_days != expected_deposit_days:
        _raise_invalid("deposit service days do not match identity policy")
    if payment_terms.deposit_due_date > payment_terms.first_payment_due_date:
        _raise_invalid("deposit due date cannot follow service start")
    if payment_terms.first_payment_due_date != order.planned_start_date:
        _raise_invalid("first payment due date must equal planned start date")
    if payment_terms.second_payment_due_date is not None:
        _raise_invalid("second payment due date is formed after first settlement")


def _deposit_days_for_identity(identity_status: str) -> int:
    policy_kind = policy_kind_for_identity(identity_status)
    if policy_kind is PayrollPolicyKind.SUBSIDIZED_CITIZEN:
        return 0
    return 5


def _require_rate_policy(facts, intent) -> RatePolicyFacts:
    rate_policy = facts.payroll_rate_policy
    if rate_policy is None:
        raise BootstrapDomainError(
            BootstrapIssue.RATE_POLICY_NOT_FOUND,
            "No effective Payroll rate policy exists for the case.",
        )
    expected_kind = policy_kind_for_identity(
        facts.order.source_identity_status
    )
    if rate_policy.policy_version != intent.payroll_policy_version:
        _raise_rate_policy_not_found()
    if rate_policy.policy_kind is not expected_kind:
        _raise_invalid("payroll policy kind does not match client identity")
    if not rate_policy.applies_on(facts.order.planned_start_date):
        _raise_rate_policy_not_found()
    return rate_policy


def _resolve_mutation(
    presence: BootstrapPresence,
    fingerprint: PreviewFingerprint,
) -> BootstrapMutation:
    if not presence.has_component and presence.root_event_fingerprint is None:
        return BootstrapMutation.CREATE
    if _can_adopt_existing_scheduling(presence):
        return BootstrapMutation.CREATE_WITH_EXISTING_SCHEDULING
    if (
        presence.complete
        and presence.root_event_fingerprint == fingerprint
    ):
        return BootstrapMutation.KEEP_EXISTING
    raise BootstrapDomainError(
        BootstrapIssue.INTEGRITY_VIOLATION,
        "Existing bootstrap state is partial or conflicts with root facts.",
    )


def _can_adopt_existing_scheduling(presence) -> bool:
    return all(
        (
            presence.scheduling_aggregate,
            not presence.client_finance_account,
            not presence.client_payment_terms,
            not presence.payroll_case_account,
            not presence.payroll_case_policy,
            presence.root_event_fingerprint is None,
            presence.components_consistent,
        )
    )


def _candidate_fingerprint(
    order,
    intent,
    payroll_policy,
    scheduling_version,
    scheduling_generation,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "case_no": intent.case_no,
            "order_version": order.order_version,
            "source_identity_status": order.source_identity_status,
            "client_payment_terms": _client_terms_payload(
                intent.client_payment_terms
            ),
            "payroll_rate_policy": _rate_policy_payload(payroll_policy),
            "scheduling_version": scheduling_version,
            "scheduling_generation": scheduling_generation,
        }
    )


def _client_terms_payload(payment_terms) -> dict[str, object]:
    return {
        "policy_version": payment_terms.policy_version,
        "hourly_rate_ntd": payment_terms.client_hourly_rate.amount,
        "deposit_service_days": payment_terms.deposit_service_days,
        "deposit_due_date": payment_terms.deposit_due_date.isoformat(),
        "first_payment_due_date": (
            payment_terms.first_payment_due_date.isoformat()
        ),
        "second_payment_due_date": None,
    }


def _rate_policy_payload(rate_policy) -> dict[str, object]:
    return {
        "policy_version": rate_policy.policy_version,
        "policy_kind": rate_policy.policy_kind.value,
        "hourly_rate_ntd": rate_policy.hourly_rate.amount,
        "effective_from": rate_policy.effective_from.isoformat(),
        "effective_until": (
            rate_policy.effective_until.isoformat()
            if rate_policy.effective_until
            else None
        ),
    }


def _raise_invalid(message: str) -> None:
    raise BootstrapDomainError(BootstrapIssue.INVALID_ROOT_FACTS, message)


def _raise_rate_policy_not_found() -> None:
    raise BootstrapDomainError(
        BootstrapIssue.RATE_POLICY_NOT_FOUND,
        "The requested Payroll rate policy is not effective for the case.",
    )


def _require_date(value: object, name: str) -> None:
    if type(value) is not date:
        raise TypeError(f"{name} must be a date")
