"""Replay-safe recovery of a union subsidy advance from government allocation facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.client_finance.subsidy_advance import (
    SubsidyAdvanceFacts,
    SubsidyAdvanceRecovery,
    build_subsidy_advance_recovery,
)
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text, require_positive_integer


@dataclass(frozen=True, slots=True)
class GovernmentReceiptAllocationEvent:
    source_outbox_id: int
    government_allocation_identity: str
    government_transaction_id: int
    case_no: str
    claim_item_id: int
    amount: MoneyNTD

    def __post_init__(self) -> None:
        require_positive_integer(self.source_outbox_id, "source outbox id")
        require_canonical_text(self.government_allocation_identity, "allocation identity", 191)
        require_positive_integer(self.government_transaction_id, "government transaction id")
        require_canonical_text(self.case_no, "case number", 191)
        require_positive_integer(self.claim_item_id, "claim item id")
        if self.amount.amount <= 0:
            raise ValueError("government allocation amount is invalid")


@dataclass(frozen=True, slots=True)
class SubsidyAdvanceRecoveryTarget:
    advance_entry_identity: str
    advance_paid: MoneyNTD
    already_recovered: MoneyNTD
    facts: SubsidyAdvanceFacts


class SubsidyAdvanceRecoveryRepository(Protocol):
    def find_target(
        self,
        event: GovernmentReceiptAllocationEvent,
    ) -> SubsidyAdvanceRecoveryTarget | None: ...

    def save_recovery(
        self,
        event: GovernmentReceiptAllocationEvent,
        recovery: SubsidyAdvanceRecovery,
    ) -> bool: ...

    def record_anomaly(
        self,
        event: GovernmentReceiptAllocationEvent,
        reason: str,
    ) -> None: ...


class SubsidyAdvanceRecoveryWorkflow:
    def __init__(self, repository: SubsidyAdvanceRecoveryRepository) -> None:
        self._repository = repository

    def consume(self, event: GovernmentReceiptAllocationEvent) -> str:
        target = self._repository.find_target(event)
        if target is None:
            self._repository.record_anomaly(event, "subsidy_advance_settlement_ambiguous")
            return "review_required"
        if target.already_recovered.amount:
            return "existing"
        recovery = _build_recovery(event, target)
        if recovery is None:
            self._repository.record_anomaly(event, "subsidy_advance_settlement_ambiguous")
            return "review_required"
        return "recovered" if self._repository.save_recovery(event, recovery) else "existing"


def _build_recovery(event, target):
    facts = SubsidyAdvanceFacts(
        target.facts.case_no,
        target.facts.completed_on,
        target.facts.subsidy_return_due,
        event.amount,
    )
    try:
        return build_subsidy_advance_recovery(
            facts,
            target.advance_entry_identity,
            event.government_allocation_identity,
            target.advance_paid,
            target.already_recovered,
        )
    except ValueError:
        return None
