"""Typed, read-only Client Finance query contracts.

The legacy ``client_payments`` table is a compatibility projection.  These
contracts deliberately expose only the bounded Client Finance roots needed by
the authenticated query surface; callers must not receive arbitrary table
rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ClientFinanceAllocationFact:
    obligation_identity: str
    amount_ntd: int


@dataclass(frozen=True, slots=True)
class ClientFinanceObligationFact:
    obligation_identity: str
    obligation_type: str
    direction: str
    amount_due_ntd: int
    due_date: date | None
    status: str
    projection_version: str


@dataclass(frozen=True, slots=True)
class ClientFinanceLedgerEntryFact:
    entry_id: int
    entry_type: str
    amount_ntd: int
    occurred_on: date
    reconciliation_reference: str
    reversal_of_entry_id: int | None
    created_at: datetime
    allocations: tuple[ClientFinanceAllocationFact, ...]


@dataclass(frozen=True, slots=True)
class ClientFinanceCaseSummary:
    case_no: str
    account_version: str
    open_receivable_amount_ntd: int
    open_payable_amount_ntd: int
    obligation_count: int
    ledger_entry_count: int


@dataclass(frozen=True, slots=True)
class ClientFinanceCaseQuery:
    case_no: str
    account_version: str
    obligations: tuple[ClientFinanceObligationFact, ...]
    ledger_entries: tuple[ClientFinanceLedgerEntryFact, ...]


@dataclass(frozen=True, slots=True)
class ClientFinancePageQuery:
    cases: tuple[ClientFinanceCaseSummary, ...]


class ClientFinanceQueryRepository(Protocol):
    def query_all(self) -> ClientFinancePageQuery: ...

    def query_case(self, case_no: str) -> ClientFinanceCaseQuery: ...


class ClientFinanceQueryApplication:
    """Read-only Client Finance application over a typed repository port."""

    def __init__(self, repository: ClientFinanceQueryRepository) -> None:
        self._repository = repository

    def query_all(self) -> ClientFinancePageQuery:
        return self._repository.query_all()

    def query_case(self, case_no: str) -> ClientFinanceCaseQuery:
        return self._repository.query_case(case_no)


__all__ = [
    "ClientFinanceAllocationFact",
    "ClientFinanceCaseQuery",
    "ClientFinanceCaseSummary",
    "ClientFinanceLedgerEntryFact",
    "ClientFinanceObligationFact",
    "ClientFinancePageQuery",
    "ClientFinanceQueryApplication",
    "ClientFinanceQueryRepository",
]
