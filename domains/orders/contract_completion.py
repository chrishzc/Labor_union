"""Pure Orders contract-completion root facts and candidate builder."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.terms import ServiceTimeTerms
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_CONTRACT_IDENTITY_MAXIMUM_LENGTH = 191


class ContractCompletionIntent(StrEnum):
    CONFIRM_COMPLETED = "confirm_completed"


class ContractCompletionBlocker(StrEnum):
    CONTRACT_IDENTITY_MISSING = "contract_identity_missing"
    CONTRACT_COMPLETION_ALREADY_RECORDED = (
        "contract_completion_already_recorded"
    )
    SERVICE_TIME_TERMS_INCOMPLETE = "service_time_terms_incomplete"
    OFFICIAL_SERVICE_DATES_INCOMPLETE = (
        "official_service_dates_incomplete"
    )
    CLIENT_OBLIGATION_HISTORY_CONFLICT = (
        "client_obligation_history_conflict"
    )


class ContractCompletionCandidateError(ValueError):
    def __init__(self, blockers: tuple[ContractCompletionBlocker, ...]) -> None:
        self.blockers = blockers
        super().__init__(blockers[0].value)


@dataclass(frozen=True, slots=True)
class ContractCompletionFacts:
    case_no: str
    aggregate_version: int
    contract_identity: str | None
    contract_completed: bool
    lifecycle_status: OrderLifecycleStatus
    deposit_settled: bool
    service_time: ServiceTimeTerms

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        require_nonnegative_integer(self.aggregate_version, "order version")
        _validate_optional_contract_identity(self.contract_identity)
        _validate_fact_types(self)


@dataclass(frozen=True, slots=True)
class ContractCompletionCandidate:
    case_no: str
    intent: ContractCompletionIntent
    contract_identity: str
    expected_order_version: int
    resulting_order_version: int
    before_completed: bool
    after_completed: bool
    before_status: OrderLifecycleStatus
    after_status: OrderLifecycleStatus
    deposit_settled: bool
    fingerprint: PreviewFingerprint


def contract_completion_blockers(
    facts: ContractCompletionFacts,
) -> tuple[ContractCompletionBlocker, ...]:
    blockers: list[ContractCompletionBlocker] = []
    if facts.contract_identity is None:
        blockers.append(ContractCompletionBlocker.CONTRACT_IDENTITY_MISSING)
    if facts.contract_completed:
        blockers.append(
            ContractCompletionBlocker.CONTRACT_COMPLETION_ALREADY_RECORDED
        )
    if not facts.service_time.complete:
        blockers.append(
            ContractCompletionBlocker.SERVICE_TIME_TERMS_INCOMPLETE
        )
    return tuple(sorted(blockers, key=lambda blocker: blocker.value))


def build_contract_completion_candidate(
    facts: ContractCompletionFacts,
    intent: ContractCompletionIntent,
) -> ContractCompletionCandidate:
    _validate_intent(intent)
    blockers = contract_completion_blockers(facts)
    if blockers:
        raise ContractCompletionCandidateError(blockers)
    after_status = _derived_status(facts)
    return _candidate(facts, intent, after_status)


# Kept cohesive so the fingerprint and returned immutable candidate cannot drift.
def _candidate(
    facts: ContractCompletionFacts,
    intent: ContractCompletionIntent,
    after_status: OrderLifecycleStatus,
) -> ContractCompletionCandidate:
    contract_identity = _required_contract_identity(facts)
    fingerprint = fingerprint_payload(
        _fingerprint_payload(facts, intent, contract_identity, after_status)
    )
    return ContractCompletionCandidate(
        facts.case_no,
        intent,
        contract_identity,
        facts.aggregate_version,
        facts.aggregate_version + 1,
        facts.contract_completed,
        True,
        facts.lifecycle_status,
        after_status,
        facts.deposit_settled,
        fingerprint,
    )


def _fingerprint_payload(
    facts: ContractCompletionFacts,
    intent: ContractCompletionIntent,
    contract_identity: str,
    after_status: OrderLifecycleStatus,
) -> dict[str, object]:
    return {
        "case_no": facts.case_no,
        "intent": intent.value,
        "contract_identity": contract_identity,
        "expected_order_version": facts.aggregate_version,
        "before_completed": facts.contract_completed,
        "after_completed": True,
        "before_status": facts.lifecycle_status.value,
        "after_status": after_status.value,
        "deposit_settled": facts.deposit_settled,
        "service_time": facts.service_time.canonical_payload(),
    }


def _derived_status(
    facts: ContractCompletionFacts,
) -> OrderLifecycleStatus:
    if facts.lifecycle_status is not OrderLifecycleStatus.DISCUSSION:
        return facts.lifecycle_status
    if facts.deposit_settled:
        return OrderLifecycleStatus.ESTABLISHED
    return OrderLifecycleStatus.DISCUSSION


def _required_contract_identity(facts: ContractCompletionFacts) -> str:
    if facts.contract_identity is None:
        raise ValueError("contract_identity_missing")
    return facts.contract_identity


def _validate_intent(intent: object) -> None:
    if not isinstance(intent, ContractCompletionIntent):
        raise TypeError("contract completion intent is invalid")


def _validate_optional_contract_identity(value: object) -> None:
    if value is None:
        return
    require_canonical_text(
        value,
        "contract identity",
        _CONTRACT_IDENTITY_MAXIMUM_LENGTH,
    )


def _validate_fact_types(facts: ContractCompletionFacts) -> None:
    if not isinstance(facts.contract_completed, bool):
        raise TypeError("contract completed must be bool")
    if not isinstance(facts.lifecycle_status, OrderLifecycleStatus):
        raise TypeError("lifecycle status is invalid")
    if not isinstance(facts.deposit_settled, bool):
        raise TypeError("deposit settled must be bool")
    if not isinstance(facts.service_time, ServiceTimeTerms):
        raise TypeError("service time must be ServiceTimeTerms")


__all__ = [
    "ContractCompletionBlocker",
    "ContractCompletionCandidate",
    "ContractCompletionCandidateError",
    "ContractCompletionFacts",
    "ContractCompletionIntent",
    "build_contract_completion_candidate",
    "contract_completion_blockers",
]
