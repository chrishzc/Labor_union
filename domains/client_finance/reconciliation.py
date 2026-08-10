"""Exact same-stage reconciliation of bank facts and client obligations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text, require_positive_integer

_IDENTITY_MAXIMUM_LENGTH = 191


class PaymentStage(StrEnum):
    DEPOSIT = "deposit"
    FIRST = "first"
    SECOND = "second"
    ADJUSTMENT = "adjustment"
    REFUND = "refund"
    SUBSIDY_RETURN = "subsidy_return"


class ReconciliationStatus(StrEnum):
    EXACT = "exact"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class IncomingBankFact:
    identity: str
    amount: MoneyNTD
    payment_stage: PaymentStage

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "bank fact identity")
        _require_positive_money(self.amount, "bank fact amount")


@dataclass(frozen=True, slots=True)
class ClientObligation:
    identity: str
    case_no: str
    amount_due: MoneyNTD
    payment_stage: PaymentStage

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "obligation identity")
        _validate_identity(self.case_no, "case number")
        _require_positive_money(self.amount_due, "obligation amount")


@dataclass(frozen=True, slots=True)
class ReconciliationAllocation:
    bank_fact_identity: str
    obligation_identity: str
    amount: MoneyNTD


@dataclass(frozen=True, slots=True)
class ClientReconciliationCandidate:
    status: ReconciliationStatus
    payment_stage: PaymentStage
    bank_total: MoneyNTD
    obligation_total: MoneyNTD
    allocations: tuple[ReconciliationAllocation, ...]
    blockers: tuple[str, ...]
    settlement_identity: PreviewFingerprint


def build_reconciliation_candidate(
    bank_facts: tuple[IncomingBankFact, ...],
    obligations: tuple[ClientObligation, ...],
) -> ClientReconciliationCandidate:
    payment_stage = _validate_inputs(bank_facts, obligations)
    bank_facts = tuple(sorted(bank_facts, key=lambda item: item.identity))
    obligations = tuple(sorted(obligations, key=lambda item: item.identity))
    bank_total = _sum_bank_facts(bank_facts)
    obligation_total = _sum_obligations(obligations)
    blocker = _amount_blocker(bank_total, obligation_total)
    allocations = () if blocker else _allocate_exactly(bank_facts, obligations)
    return ClientReconciliationCandidate(
        status=_candidate_status(blocker),
        payment_stage=payment_stage,
        bank_total=bank_total,
        obligation_total=obligation_total,
        allocations=allocations,
        blockers=(blocker,) if blocker else (),
        settlement_identity=_settlement_identity(bank_facts, obligations),
    )


def _candidate_status(blocker: str | None) -> ReconciliationStatus:
    if blocker:
        return ReconciliationStatus.REVIEW_REQUIRED
    return ReconciliationStatus.EXACT


def _validate_inputs(
    bank_facts: tuple[IncomingBankFact, ...],
    obligations: tuple[ClientObligation, ...],
) -> PaymentStage:
    if not bank_facts:
        raise ValueError("incoming_bank_facts_required")
    if not obligations:
        raise ValueError("client_obligations_required")
    stages = {
        *(fact.payment_stage for fact in bank_facts),
        *(obligation.payment_stage for obligation in obligations),
    }
    if len(stages) != 1:
        raise ValueError("cross_stage_reconciliation_forbidden")
    return next(iter(stages))


def _sum_bank_facts(bank_facts: tuple[IncomingBankFact, ...]) -> MoneyNTD:
    return MoneyNTD(sum(fact.amount.amount for fact in bank_facts))


def _sum_obligations(obligations: tuple[ClientObligation, ...]) -> MoneyNTD:
    return MoneyNTD(sum(item.amount_due.amount for item in obligations))


def _amount_blocker(bank_total: MoneyNTD, obligation_total: MoneyNTD) -> str | None:
    if bank_total.amount < obligation_total.amount:
        return "client_receipt_underpaid"
    if bank_total.amount > obligation_total.amount:
        return "client_receipt_overpaid"
    return None


def _allocate_exactly(
    bank_facts: tuple[IncomingBankFact, ...],
    obligations: tuple[ClientObligation, ...],
) -> tuple[ReconciliationAllocation, ...]:
    allocations: list[ReconciliationAllocation] = []
    bank_index = obligation_index = 0
    bank_remaining = bank_facts[0].amount.amount
    obligation_remaining = obligations[0].amount_due.amount
    while bank_index < len(bank_facts):
        amount = min(bank_remaining, obligation_remaining)
        allocations.append(_allocation(bank_facts, obligations, bank_index, obligation_index, amount))
        bank_remaining -= amount
        obligation_remaining -= amount
        bank_index, bank_remaining = _advance_bank(bank_facts, bank_index, bank_remaining)
        obligation_index, obligation_remaining = _advance_obligation(
            obligations,
            obligation_index,
            obligation_remaining,
        )
    return tuple(allocations)


def _allocation(bank_facts, obligations, bank_index, obligation_index, amount):
    return ReconciliationAllocation(
        bank_fact_identity=bank_facts[bank_index].identity,
        obligation_identity=obligations[obligation_index].identity,
        amount=MoneyNTD(amount),
    )


def _advance_bank(bank_facts, index: int, remaining: int) -> tuple[int, int]:
    if remaining:
        return index, remaining
    next_index = index + 1
    next_amount = (
        bank_facts[next_index].amount.amount
        if next_index < len(bank_facts)
        else 0
    )
    return next_index, next_amount


def _advance_obligation(obligations, index: int, remaining: int) -> tuple[int, int]:
    if remaining:
        return index, remaining
    next_index = index + 1
    next_amount = (
        obligations[next_index].amount_due.amount
        if next_index < len(obligations)
        else 0
    )
    return next_index, next_amount


def _settlement_identity(bank_facts, obligations) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "bank_facts": tuple(
                {"identity": item.identity, "amount_ntd": item.amount.amount}
                for item in bank_facts
            ),
            "obligations": tuple(
                {
                    "identity": item.identity,
                    "amount_ntd": item.amount_due.amount,
                    "case_no": item.case_no,
                    "payment_stage": item.payment_stage.value,
                }
                for item in obligations
            ),
        }
    )


def _require_positive_money(value: MoneyNTD, field_name: str) -> None:
    if not isinstance(value, MoneyNTD):
        raise TypeError(f"{field_name} must be MoneyNTD")
    require_positive_integer(value.amount, field_name)


def _validate_identity(value: str, field_name: str) -> None:
    require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)
