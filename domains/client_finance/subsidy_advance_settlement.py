"""Pure readback and eligibility for settlement of an existing subsidy advance."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from domains.client_finance.subsidy_advance import (
    SubsidyAdvanceFacts, build_subsidy_advance_recovery,
)
from shared_kernel.money import MoneyNTD

SettlementStatus = Literal['waiting_receipt', 'ready', 'recovered', 'review_required']


@dataclass(frozen=True, slots=True)
class AdvanceEntitlement:
    link_id: int
    claim_item_id: int
    batch_id: int
    batch_version: int
    amount_ntd: int
    approved_amount_ntd: int
    same_case: bool


@dataclass(frozen=True, slots=True)
class AdvanceGovernmentReceipt:
    allocation_id: int
    transaction_id: int
    claim_item_id: int
    amount_ntd: int
    reversed_amount_ntd: int
    received_on: date
    source_outbox_id: int | None
    evidence_matches: bool
    advance_target_count: int


@dataclass(frozen=True, slots=True)
class AdvanceSettlementFacts:
    advance_id: int
    case_no: str
    client_name: str
    advance_amount_ntd: int
    advanced_on: date
    completed_on: date | None
    account_version: int | None
    obligation_count: int
    allocated_advance_ntd: int
    reversed_advance_ntd: int
    entitlements: tuple[AdvanceEntitlement, ...]
    receipts: tuple[AdvanceGovernmentReceipt, ...]
    recovered_amount_ntd: int
    recovered_allocation_id: int | None


@dataclass(frozen=True, slots=True)
class AdvanceSettlementRow:
    advance_id: int
    case_no: str
    client_name: str
    advanced_on: date
    advance_amount_ntd: int
    government_received_ntd: int
    received_on: date | None
    recovered_amount_ntd: int
    status: SettlementStatus
    review_reason: str | None


def project_advance_settlement(facts: AdvanceSettlementFacts) -> AdvanceSettlementRow:
    """Never infer an entitlement from a case number or an equal bank amount."""
    reason = None
    status: SettlementStatus = 'review_required'
    if facts.reversed_advance_ntd or any(r.reversed_amount_ntd for r in facts.receipts):
        reason = 'reversed_source'
    elif facts.account_version is None or facts.completed_on is None:
        reason = 'owner_facts_incomplete'
    elif facts.obligation_count != 1 or facts.allocated_advance_ntd != facts.advance_amount_ntd:
        reason = 'advance_obligation_not_unique'
    elif len(facts.entitlements) != 1 or not facts.entitlements[0].same_case:
        reason = 'entitlement_not_unique'
    else:
        entitlement = facts.entitlements[0]
        if entitlement.amount_ntd != facts.advance_amount_ntd:
            reason = 'amount_mismatch'
        elif not facts.receipts and not facts.recovered_amount_ntd:
            status = 'waiting_receipt'
        elif len(facts.receipts) != 1:
            reason = 'receipt_not_unique'
        else:
            receipt = facts.receipts[0]
            if receipt.advance_target_count != 1:
                reason = 'receipt_not_unique'
            elif not receipt.source_outbox_id or not receipt.evidence_matches:
                reason = 'allocation_evidence_missing'
            elif not (entitlement.approved_amount_ntd == receipt.amount_ntd == facts.advance_amount_ntd):
                reason = 'amount_mismatch'
            elif facts.recovered_amount_ntd:
                if (facts.recovered_amount_ntd == facts.advance_amount_ntd
                        and facts.recovered_allocation_id == receipt.allocation_id):
                    status = 'recovered'
                else:
                    reason = 'recovery_mismatch'
            else:
                # Reuse the canonical full-amount recovery rule.
                build_subsidy_advance_recovery(
                    SubsidyAdvanceFacts(facts.case_no, facts.completed_on,
                                        MoneyNTD(entitlement.amount_ntd), MoneyNTD(receipt.amount_ntd)),
                    f'client-ledger:{facts.advance_id}',
                    f'government-allocation:{receipt.transaction_id}:{receipt.claim_item_id}',
                    MoneyNTD(facts.advance_amount_ntd), MoneyNTD(0),
                )
                status = 'ready'
    return AdvanceSettlementRow(
        facts.advance_id, facts.case_no, facts.client_name, facts.advanced_on,
        facts.advance_amount_ntd,
        sum(r.amount_ntd - r.reversed_amount_ntd for r in facts.receipts),
        facts.receipts[0].received_on if len(facts.receipts) == 1 else None,
        facts.recovered_amount_ntd, status, reason,
    )
