"""Manual Finance Import correction candidates without mutable bank inputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.finance_import.planning import FinanceClassificationType
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191
_EVIDENCE_MAXIMUM_LENGTH = 500


class FinanceOwningDomain(StrEnum):
    CLIENT_FINANCE = "client_finance"
    GOVERNMENT_SUBSIDY = "government_subsidy"
    STAFF_PAYABLES = "staff_payables"


@dataclass(frozen=True, slots=True)
class CorrectionTargetObligation:
    obligation_identity: str
    owning_domain: FinanceOwningDomain
    remaining_amount: MoneyNTD

    def __post_init__(self) -> None:
        require_canonical_text(
            self.obligation_identity,
            "target obligation identity",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        if not isinstance(self.owning_domain, FinanceOwningDomain):
            raise TypeError("owning domain is invalid")
        _require_positive_money(self.remaining_amount, "remaining amount")


@dataclass(frozen=True, slots=True)
class FinanceImportCorrectionSelection:
    row_identity: str
    classification_type: FinanceClassificationType
    target_obligation_identities: tuple[str, ...]
    reason: str
    evidence: tuple[str, ...]
    refund_ledger_entry_identity: str | None = None
    allow_partial_refund_recovery: bool = False
    allow_refund_overage_recovery: bool = False
    allow_client_receipt_overage: bool = False

    # Kept whole so one immutable selection validates every operator-supplied fact.
    def __post_init__(self) -> None:
        require_canonical_text(
            self.row_identity,
            "canonical row identity",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        _validate_business_classification(self.classification_type)
        _validate_sorted_text(
            self.target_obligation_identities,
            "target obligation identities",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        if not self.target_obligation_identities:
            raise ValueError("correction_target_required")
        _validate_refund_return_target(self)
        _validate_partial_refund_recovery(self)
        _validate_refund_overage_recovery(self)
        _validate_client_receipt_overage(self)
        require_canonical_text(
            self.reason,
            "correction reason",
            _EVIDENCE_MAXIMUM_LENGTH,
        )
        _validate_sorted_text(
            self.evidence,
            "correction evidence",
            _EVIDENCE_MAXIMUM_LENGTH,
        )
        if not self.evidence:
            raise ValueError("manual_evidence_required")


@dataclass(frozen=True, slots=True)
class FinanceImportCorrectionFacts:
    batch_identity: str
    batch_version: int
    canonical_fact_version: int
    alert_version: int
    bank_amount: MoneyNTD
    active_manual_review: bool
    target_obligations: tuple[CorrectionTargetObligation, ...]
    integrity_violations: tuple[str, ...] = ()
    fingerprint_collision: bool = False
    formal_reference_conflict: bool = False

    def __post_init__(self) -> None:
        _validate_correction_facts(self)


@dataclass(frozen=True, slots=True)
class CorrectionAllocation:
    obligation_identity: str
    amount: MoneyNTD


@dataclass(frozen=True, slots=True)
class FinanceImportCorrectionCandidate:
    row_identity: str
    batch_identity: str
    classification_type: FinanceClassificationType
    owning_domain: FinanceOwningDomain
    bank_amount: MoneyNTD
    allocations: tuple[CorrectionAllocation, ...]
    reason: str
    evidence: tuple[str, ...]
    fingerprint: PreviewFingerprint
    refund_ledger_entry_identity: str | None = None
    allow_partial_refund_recovery: bool = False
    allow_refund_overage_recovery: bool = False
    allow_client_receipt_overage: bool = False


def build_finance_import_correction_candidate(
    selection: FinanceImportCorrectionSelection,
    facts: FinanceImportCorrectionFacts,
) -> FinanceImportCorrectionCandidate:
    _validate_correction_blockers(facts)
    owning_domain, allocations = _build_allocations(selection, facts)
    fingerprint = fingerprint_payload(
        _candidate_payload(selection, facts, owning_domain, allocations)
    )
    return _correction_candidate(
        selection,
        facts,
        owning_domain,
        allocations,
        fingerprint,
    )


def _build_allocations(selection, facts):
    obligations = _selected_obligations(selection, facts)
    owning_domain = _single_owning_domain(obligations)
    _validate_classification_owner(selection.classification_type, owning_domain)
    allocations = tuple(
        CorrectionAllocation(item.obligation_identity, item.remaining_amount)
        for item in obligations
    )
    if selection.allow_partial_refund_recovery:
        return owning_domain, _build_refund_recovery_allocations(
            facts.bank_amount,
            allocations,
        )
    if selection.allow_refund_overage_recovery:
        return owning_domain, _build_refund_overage_allocations(facts.bank_amount, allocations)
    if selection.allow_client_receipt_overage:
        return owning_domain, _build_client_receipt_overage_allocations(facts.bank_amount, allocations)
    _validate_exact_allocation(facts.bank_amount, allocations)
    return owning_domain, allocations


def _correction_candidate(
    selection,
    facts,
    owning_domain,
    allocations,
    fingerprint,
):
    return FinanceImportCorrectionCandidate(
        selection.row_identity,
        facts.batch_identity,
        selection.classification_type,
        owning_domain,
        facts.bank_amount,
        allocations,
        selection.reason,
        selection.evidence,
        fingerprint,
        selection.refund_ledger_entry_identity,
        selection.allow_partial_refund_recovery,
        selection.allow_refund_overage_recovery,
        selection.allow_client_receipt_overage,
    )


def _selected_obligations(selection, facts):
    obligations = {
        item.obligation_identity: item for item in facts.target_obligations
    }
    selected = tuple(
        obligations.get(identity)
        for identity in selection.target_obligation_identities
    )
    if any(item is None for item in selected):
        raise ValueError("correction_target_not_found")
    return selected


def _single_owning_domain(obligations) -> FinanceOwningDomain:
    owners = {item.owning_domain for item in obligations}
    if len(owners) != 1:
        raise ValueError("correction_targets_cross_owning_domain")
    return owners.pop()


def _validate_classification_owner(classification_type, owning_domain) -> None:
    expected_owner = _classification_owner(classification_type)
    if owning_domain is not expected_owner:
        raise ValueError("classification_target_owner_mismatch")


def _classification_owner(
    classification_type: FinanceClassificationType,
) -> FinanceOwningDomain:
    if classification_type is FinanceClassificationType.GOVERNMENT_SUBSIDY:
        return FinanceOwningDomain.GOVERNMENT_SUBSIDY
    if classification_type is FinanceClassificationType.STAFF_PAYOUT:
        return FinanceOwningDomain.STAFF_PAYABLES
    return FinanceOwningDomain.CLIENT_FINANCE


def _validate_exact_allocation(bank_amount, allocations) -> None:
    allocated = sum(item.amount.amount for item in allocations)
    if allocated != bank_amount.amount:
        raise ValueError("allocation_not_exact")


def _build_refund_recovery_allocations(bank_amount, allocations):
    remaining_amount = bank_amount.amount
    total_due = sum(item.amount.amount for item in allocations)
    if remaining_amount >= total_due:
        raise ValueError("refund_recovery_requires_underpayment")
    selected: list[CorrectionAllocation] = []
    for allocation in allocations:
        if not remaining_amount:
            break
        amount = min(remaining_amount, allocation.amount.amount)
        selected.append(CorrectionAllocation(allocation.obligation_identity, MoneyNTD(amount)))
        remaining_amount -= amount
    if remaining_amount:
        raise ValueError("allocation_not_exact")
    return tuple(selected)


def _build_refund_overage_allocations(bank_amount, allocations):
    total_due = sum(item.amount.amount for item in allocations)
    if bank_amount.amount <= total_due:
        raise ValueError("refund_overage_required")
    return allocations


def _build_client_receipt_overage_allocations(bank_amount, allocations):
    total_due = sum(item.amount.amount for item in allocations)
    if bank_amount.amount <= total_due:
        raise ValueError("client_receipt_overage_required")
    return allocations


def _validate_correction_blockers(facts) -> None:
    blockers = set(facts.integrity_violations)
    if facts.fingerprint_collision:
        blockers.add("fingerprint_collision")
    if facts.formal_reference_conflict:
        blockers.add("formal_reference_conflict")
    if not facts.active_manual_review:
        blockers.add("recovery_action_not_available")
    if blockers:
        raise ValueError(",".join(sorted(blockers)))


def _candidate_payload(selection, facts, owning_domain, allocations):
    return {
        "selection": _selection_payload(selection),
        "facts": _facts_payload(facts),
        "owning_domain": owning_domain.value,
        "allocations": tuple(
            {
                "obligation_identity": item.obligation_identity,
                "amount_ntd": item.amount.amount,
            }
            for item in allocations
        ),
    }


def _selection_payload(selection):
    return {
        "row_identity": selection.row_identity,
        "classification_type": selection.classification_type.value,
        "target_obligation_identities": selection.target_obligation_identities,
        "reason": selection.reason,
        "evidence": selection.evidence,
        "refund_ledger_entry_identity": selection.refund_ledger_entry_identity,
        "allow_partial_refund_recovery": selection.allow_partial_refund_recovery,
        "allow_refund_overage_recovery": selection.allow_refund_overage_recovery,
        "allow_client_receipt_overage": selection.allow_client_receipt_overage,
    }


def _facts_payload(facts):
    return {
        "batch_identity": facts.batch_identity,
        "batch_version": facts.batch_version,
        "canonical_fact_version": facts.canonical_fact_version,
        "alert_version": facts.alert_version,
        "bank_amount_ntd": facts.bank_amount.amount,
    }


def _validate_correction_facts(facts: FinanceImportCorrectionFacts) -> None:
    _validate_correction_versions(facts)
    _require_positive_money(facts.bank_amount, "bank amount")
    if not isinstance(facts.active_manual_review, bool):
        raise TypeError("active manual review must be bool")
    if not isinstance(facts.fingerprint_collision, bool):
        raise TypeError("fingerprint collision must be bool")
    if not isinstance(facts.formal_reference_conflict, bool):
        raise TypeError("formal reference conflict must be bool")
    _validate_obligations(facts.target_obligations)
    _validate_sorted_text(
        facts.integrity_violations,
        "integrity violations",
        _IDENTITY_MAXIMUM_LENGTH,
    )


def _validate_partial_refund_recovery(selection) -> None:
    if not isinstance(selection.allow_partial_refund_recovery, bool):
        raise TypeError("partial refund recovery must be bool")
    if (
        selection.allow_partial_refund_recovery
        and selection.classification_type is not FinanceClassificationType.CLIENT_REFUND
    ):
        raise ValueError("partial_refund_recovery_not_allowed")


def _validate_refund_overage_recovery(selection) -> None:
    if not isinstance(selection.allow_refund_overage_recovery, bool):
        raise TypeError("refund overage recovery must be bool")
    if selection.allow_partial_refund_recovery and selection.allow_refund_overage_recovery:
        raise ValueError("refund_recovery_mode_conflict")
    if (
        selection.allow_refund_overage_recovery
        and selection.classification_type is not FinanceClassificationType.CLIENT_REFUND
    ):
        raise ValueError("refund_overage_recovery_not_allowed")


def _validate_client_receipt_overage(selection) -> None:
    if not isinstance(selection.allow_client_receipt_overage, bool):
        raise TypeError("client receipt overage must be bool")
    if selection.allow_client_receipt_overage and selection.classification_type is not FinanceClassificationType.CLIENT_RECEIPT:
        raise ValueError("client_receipt_overage_not_allowed")


def _validate_correction_versions(facts) -> None:
    require_canonical_text(
        facts.batch_identity,
        "finance import batch identity",
        _IDENTITY_MAXIMUM_LENGTH,
    )
    require_nonnegative_integer(facts.batch_version, "batch version")
    require_nonnegative_integer(
        facts.canonical_fact_version,
        "canonical fact version",
    )
    require_nonnegative_integer(facts.alert_version, "alert version")


def _validate_obligations(
    obligations: tuple[CorrectionTargetObligation, ...],
) -> None:
    if not isinstance(obligations, tuple) or not obligations:
        raise ValueError("target obligations must be a non-empty tuple")
    identities = tuple(item.obligation_identity for item in obligations)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("target obligations must be sorted and unique")


def _validate_business_classification(classification_type) -> None:
    if not isinstance(classification_type, FinanceClassificationType):
        raise TypeError("classification type is invalid")
    if classification_type is FinanceClassificationType.NON_BUSINESS_REVIEW:
        raise ValueError("classification_conflict")


def _validate_refund_return_target(selection) -> None:
    identity = selection.refund_ledger_entry_identity
    is_return = selection.classification_type is FinanceClassificationType.CLIENT_REFUND_RETURN
    if is_return and not isinstance(identity, str):
        raise ValueError("refund_return_ledger_target_required")
    if not is_return and identity is not None:
        raise ValueError("refund_return_ledger_target_invalid")
    if identity is not None:
        require_canonical_text(identity, "refund ledger entry identity", _IDENTITY_MAXIMUM_LENGTH)


def _validate_sorted_text(values, field_name, maximum_length) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    for value in values:
        require_canonical_text(value, field_name, maximum_length)
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _require_positive_money(value, field_name) -> None:
    if not isinstance(value, MoneyNTD):
        raise TypeError(f"{field_name} must be MoneyNTD")
    require_positive_integer(value.amount, field_name)


__all__ = [
    "CorrectionAllocation",
    "CorrectionTargetObligation",
    "FinanceImportCorrectionCandidate",
    "FinanceImportCorrectionFacts",
    "FinanceImportCorrectionSelection",
    "FinanceOwningDomain",
    "build_finance_import_correction_candidate",
]
