"""Client refund and receipt-reversal domain rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text

_IDENTITY_MAXIMUM_LENGTH = 191


class ClientFinanceCorrectionType(StrEnum):
    REFUND = "refund"
    REFUND_OVERAGE = "refund_overage"
    REFUND_RETURN = "refund_return"
    REVERSAL = "reversal"


class ClientRefundPurpose(StrEnum):
    CUSTOMER_REFUND = "customer_refund"
    SUBSIDY_RETURN = "subsidy_return"
    SUBSIDY_ADVANCE = "subsidy_advance"


@dataclass(frozen=True, slots=True)
class ClientRefundBankFact:
    identity: str
    case_no: str
    amount: MoneyNTD
    occurred_on: str
    eligible: bool = True

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "refund bank fact identity")
        _validate_identity(self.case_no, "case number")
        _require_positive_money(self.amount, "refund bank amount")
        _validate_identity(self.occurred_on, "refund occurred date")


@dataclass(frozen=True, slots=True)
class ClientRefundReturnBankFact:
    identity: str
    case_no: str
    amount: MoneyNTD
    occurred_on: str
    eligible: bool = True

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "refund return bank fact identity")
        _validate_identity(self.case_no, "case number")
        _require_positive_money(self.amount, "refund return bank amount")
        _validate_identity(self.occurred_on, "refund return occurred date")


@dataclass(frozen=True, slots=True)
class ClientRefundObligation:
    identity: str
    case_no: str
    amount_due: MoneyNTD
    obligation_type: str

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "refund obligation identity")
        _validate_identity(self.case_no, "case number")
        _require_positive_money(self.amount_due, "refund obligation amount")
        if self.obligation_type not in {"refund", "subsidy_return", "adjustment"}:
            raise ValueError("client_obligation_not_found")


@dataclass(frozen=True, slots=True)
class ClientLedgerAllocationFact:
    obligation_identity: str
    amount: MoneyNTD

    def __post_init__(self) -> None:
        _validate_identity(self.obligation_identity, "obligation identity")
        _require_positive_money(self.amount, "ledger allocation amount")


@dataclass(frozen=True, slots=True)
class ClientReversalTarget:
    identity: str
    case_no: str
    entry_type: str
    amount: MoneyNTD
    already_reversed: MoneyNTD
    occurred_on: str
    allocations: tuple[ClientLedgerAllocationFact, ...]

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "reversal target identity")
        _validate_identity(self.case_no, "case number")
        _require_positive_money(self.amount, "reversal target amount")
        _require_nonnegative_money(self.already_reversed, "reversed amount")
        _validate_identity(self.occurred_on, "reversal occurred date")
        if not isinstance(self.allocations, tuple) or not self.allocations:
            raise ValueError("reversal_target_invalid")


@dataclass(frozen=True, slots=True)
class ClientCorrectionAllocation:
    entry_identity: str
    obligation_identity: str
    amount: MoneyNTD


@dataclass(frozen=True, slots=True)
class ClientCorrectionLedgerEntry:
    identity: str
    entry_type: str
    amount: MoneyNTD
    occurred_on: str
    reversal_of_entry_identity: str | None = None
    finance_import_row_identity: str | None = None


@dataclass(frozen=True, slots=True)
class ClientRefundReversalCandidate:
    correction_type: ClientFinanceCorrectionType
    case_no: str
    amount: MoneyNTD
    entries: tuple[ClientCorrectionLedgerEntry, ...]
    allocations: tuple[ClientCorrectionAllocation, ...]
    affected_obligations: tuple[str, ...]
    reversal_entry_type: str | None
    recovery_amount: MoneyNTD
    fingerprint: PreviewFingerprint


def build_client_refund_candidate(
    case_no: str,
    bank_facts: tuple[ClientRefundBankFact, ...],
    obligations: tuple[ClientRefundObligation, ...],
    purpose: ClientRefundPurpose = ClientRefundPurpose.CUSTOMER_REFUND,
    *,
    allow_partial_refund_recovery: bool = False,
) -> ClientRefundReversalCandidate:
    _validate_refund_scope(case_no, bank_facts, obligations)
    ordered_banks = tuple(sorted(bank_facts, key=lambda item: item.identity))
    ordered_obligations = tuple(sorted(obligations, key=lambda item: item.identity))
    _require_bank_total_is_payable(
        ordered_banks,
        ordered_obligations,
        purpose,
        allow_partial_refund_recovery,
    )
    _validate_refund_obligation_types(ordered_obligations, purpose)
    entries = tuple(_refund_entry(item, purpose) for item in ordered_banks)
    allocations = _allocate_refund(ordered_banks, ordered_obligations)
    return _candidate(
        ClientFinanceCorrectionType.REFUND,
        case_no,
        entries,
        allocations,
        None,
    )


def build_client_refund_overage_candidate(
    case_no: str,
    bank_facts: tuple[ClientRefundBankFact, ...],
    obligations: tuple[ClientRefundObligation, ...],
) -> ClientRefundReversalCandidate:
    _validate_refund_scope(case_no, bank_facts, obligations)
    ordered_banks = tuple(sorted(bank_facts, key=lambda item: item.identity))
    ordered_obligations = tuple(sorted(obligations, key=lambda item: item.identity))
    _validate_refund_obligation_types(ordered_obligations, ClientRefundPurpose.CUSTOMER_REFUND)
    bank_total = sum(item.amount.amount for item in ordered_banks)
    obligation_total = sum(item.amount_due.amount for item in ordered_obligations)
    if bank_total <= obligation_total:
        raise ValueError("client_refund_overage_required")
    entries = tuple(_refund_entry(item, ClientRefundPurpose.CUSTOMER_REFUND) for item in ordered_banks)
    allocations = _allocate_refund(ordered_banks, ordered_obligations, allow_overage=True)
    return _candidate(
        ClientFinanceCorrectionType.REFUND_OVERAGE,
        case_no,
        entries,
        allocations,
        None,
        recovery_amount=MoneyNTD(bank_total - obligation_total),
    )


def build_client_reversal_candidate(
    case_no: str,
    targets: tuple[ClientReversalTarget, ...],
) -> ClientRefundReversalCandidate:
    _validate_reversal_scope(case_no, targets)
    ordered_targets = tuple(sorted(targets, key=lambda item: item.identity))
    entries = tuple(_reversal_entry(item) for item in ordered_targets)
    allocations = tuple(
        _reversal_allocation(target, allocation)
        for target in ordered_targets
        for allocation in target.allocations
    )
    _validate_reversal_allocations(ordered_targets, allocations)
    entry_types = {item.entry_type for item in ordered_targets}
    return _candidate(
        ClientFinanceCorrectionType.REVERSAL,
        case_no,
        entries,
        allocations,
        entry_types.pop(),
    )


def build_client_refund_return_candidate(
    case_no: str,
    bank_fact: ClientRefundReturnBankFact,
    target: ClientReversalTarget,
) -> ClientRefundReversalCandidate:
    _validate_identity(case_no, "case number")
    if not bank_fact.eligible or bank_fact.case_no != case_no or target.case_no != case_no:
        raise ValueError("client_refund_return_invalid")
    if target.entry_type != "refund" or target.already_reversed.amount:
        raise ValueError("client_refund_return_invalid")
    if bank_fact.amount != target.amount:
        raise ValueError("client_refund_return_invalid")
    entry = ClientCorrectionLedgerEntry(
        f"refund-return-bank:{bank_fact.identity}",
        "refund_reversal",
        bank_fact.amount,
        bank_fact.occurred_on,
        reversal_of_entry_identity=target.identity,
        finance_import_row_identity=bank_fact.identity,
    )
    allocations = tuple(
        ClientCorrectionAllocation(entry.identity, item.obligation_identity, item.amount)
        for item in target.allocations
    )
    _validate_reversal_allocations((target,), allocations)
    return _candidate(
        ClientFinanceCorrectionType.REFUND_RETURN,
        case_no,
        (entry,),
        allocations,
        target.entry_type,
    )
def _validate_refund_scope(case_no, bank_facts, obligations) -> None:
    _validate_identity(case_no, "case number")
    if not bank_facts or not obligations:
        raise ValueError("invalid_client_finance_intent")
    if any(not item.eligible for item in bank_facts):
        raise ValueError("bank_fact_not_eligible")
    if any(item.case_no != case_no for item in (*bank_facts, *obligations)):
        raise ValueError("client_finance_identity_ambiguous")


def _validate_refund_obligation_types(obligations, purpose) -> None:
    expected = (
        "subsidy_return"
        if purpose in {
            ClientRefundPurpose.SUBSIDY_RETURN,
            ClientRefundPurpose.SUBSIDY_ADVANCE,
        }
        else "refund"
    )
    if any(item.obligation_type != expected for item in obligations):
        raise ValueError("invalid_client_refund_intent")


def _require_bank_total_is_payable(
    bank_facts,
    obligations,
    purpose,
    allow_partial_refund_recovery,
) -> None:
    bank_total = sum(item.amount.amount for item in bank_facts)
    obligation_total = sum(item.amount_due.amount for item in obligations)
    if bank_total > obligation_total:
        raise ValueError("allocation_exceeds_obligation")
    if purpose is not ClientRefundPurpose.CUSTOMER_REFUND:
        return
    if bank_total == obligation_total:
        return
    if allow_partial_refund_recovery and bank_total < obligation_total:
        return
    raise ValueError("refund_requires_exact_settlement")


def _allocate_refund(bank_facts, obligations, *, allow_overage=False):
    remaining_banks = [[item, item.amount.amount] for item in bank_facts]
    remaining_obligations = [[item, item.amount_due.amount] for item in obligations]
    allocations: list[ClientCorrectionAllocation] = []
    while remaining_banks and remaining_obligations:
        allocations.append(_consume_refund_front(remaining_banks, remaining_obligations))
    if remaining_banks and not allow_overage:
        raise ValueError("allocation_exceeds_obligation")
    return tuple(allocations)


def _consume_refund_front(remaining_banks, remaining_obligations):
    bank, bank_amount = remaining_banks[0]
    obligation, obligation_amount = remaining_obligations[0]
    amount = min(bank_amount, obligation_amount)
    _consume_amount(remaining_banks, amount)
    _consume_amount(remaining_obligations, amount)
    return ClientCorrectionAllocation(
        f"refund-bank:{bank.identity}",
        obligation.identity,
        MoneyNTD(amount),
    )


def _consume_amount(remaining_values, amount) -> None:
    remaining_values[0][1] -= amount
    if remaining_values[0][1] == 0:
        remaining_values.pop(0)


def _refund_entry(bank_fact, purpose):
    return ClientCorrectionLedgerEntry(
        f"refund-bank:{bank_fact.identity}",
        _payout_entry_type(purpose),
        bank_fact.amount,
        bank_fact.occurred_on,
        finance_import_row_identity=bank_fact.identity,
    )


def _validate_reversal_scope(case_no, targets) -> None:
    _validate_identity(case_no, "case number")
    if not targets:
        raise ValueError("invalid_client_finance_intent")
    if any(item.case_no != case_no for item in targets):
        raise ValueError("client_finance_identity_ambiguous")
    if any(item.entry_type not in {"receipt", "refund", "subsidy_return", "subsidy_advance"} for item in targets):
        raise ValueError("reversal_target_invalid")
    if len({item.entry_type for item in targets}) != 1:
        raise ValueError("reversal_target_invalid")
    if any(item.already_reversed.amount > 0 for item in targets):
        raise ValueError("reversal_amount_exceeded")


def _reversal_entry(target):
    return ClientCorrectionLedgerEntry(
        f"reversal-of:{target.identity}",
        _reversal_entry_type(target.entry_type),
        target.amount,
        target.occurred_on,
        reversal_of_entry_identity=target.identity,
    )


def _reversal_allocation(target, allocation):
    return ClientCorrectionAllocation(
        f"reversal-of:{target.identity}",
        allocation.obligation_identity,
        allocation.amount,
    )


def _validate_reversal_allocations(targets, allocations) -> None:
    source_total = sum(item.amount.amount for item in targets)
    allocation_total = sum(item.amount.amount for item in allocations)
    if source_total != allocation_total:
        raise ValueError("reversal_target_invalid")


def _candidate(
    correction_type,
    case_no,
    entries,
    allocations,
    reversal_entry_type,
    *,
    recovery_amount=MoneyNTD(0),
):
    amount = MoneyNTD(sum(item.amount.amount for item in entries))
    obligations = tuple(sorted({item.obligation_identity for item in allocations}))
    payload = _candidate_payload(correction_type, case_no, entries, allocations, reversal_entry_type, recovery_amount)
    return ClientRefundReversalCandidate(
        correction_type,
        case_no,
        amount,
        entries,
        allocations,
        obligations,
        reversal_entry_type,
        recovery_amount,
        fingerprint_payload(payload),
    )


def _candidate_payload(correction_type, case_no, entries, allocations, reversal_entry_type, recovery_amount):
    return {
        "correction_type": correction_type.value,
        "case_no": case_no,
        "reversal_entry_type": reversal_entry_type,
        "recovery_amount_ntd": recovery_amount.amount,
        "entries": tuple(_entry_payload(item) for item in entries),
        "allocations": tuple(_allocation_payload(item) for item in allocations),
    }


def _entry_payload(entry):
    return {
        "identity": entry.identity,
        "entry_type": entry.entry_type,
        "amount_ntd": entry.amount.amount,
        "occurred_on": entry.occurred_on,
        "reversal_of": entry.reversal_of_entry_identity,
        "bank_fact": entry.finance_import_row_identity,
    }


def _payout_entry_type(purpose):
    if purpose is ClientRefundPurpose.SUBSIDY_ADVANCE:
        return "subsidy_advance"
    return "subsidy_return" if purpose is ClientRefundPurpose.SUBSIDY_RETURN else "refund"


def _reversal_entry_type(source_entry_type):
    return {
        "receipt": "reversal",
        "refund": "refund_reversal",
        "subsidy_return": "subsidy_return_reversal",
        "subsidy_advance": "subsidy_advance_reversal",
    }[source_entry_type]


def _allocation_payload(allocation):
    return {
        "entry_identity": allocation.entry_identity,
        "obligation_identity": allocation.obligation_identity,
        "amount_ntd": allocation.amount.amount,
    }


def _validate_identity(value, field_name) -> None:
    require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)


def _require_positive_money(value, field_name) -> None:
    if not isinstance(value, MoneyNTD) or value.amount <= 0:
        raise ValueError(f"{field_name} must be positive integer NTD")


def _require_nonnegative_money(value, field_name) -> None:
    if not isinstance(value, MoneyNTD) or value.amount < 0:
        raise ValueError(f"{field_name} must be nonnegative integer NTD")


__all__ = [
    "ClientCorrectionAllocation",
    "ClientCorrectionLedgerEntry",
    "ClientFinanceCorrectionType",
    "ClientRefundPurpose",
    "ClientLedgerAllocationFact",
    "ClientRefundBankFact",
    "ClientRefundReturnBankFact",
    "ClientRefundObligation",
    "ClientRefundReversalCandidate",
    "ClientReversalTarget",
    "build_client_refund_candidate",
    "build_client_refund_overage_candidate",
    "build_client_refund_return_candidate",
    "build_client_reversal_candidate",
]
