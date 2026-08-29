"""Bounded typed HTTP views for the Client Finance query surface."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientFinanceAllocationView(_StrictModel):
    obligation_identity: str = Field(min_length=1, max_length=191)
    amount_ntd: int = Field(gt=0)


class ClientFinanceObligationView(_StrictModel):
    obligation_identity: str = Field(min_length=1, max_length=191)
    obligation_type: Literal[
        "deposit", "first", "second", "refund", "subsidy_return", "adjustment"
    ]
    direction: Literal["receivable_from_client", "payable_to_client"]
    amount_due_ntd: int = Field(ge=0)
    due_date: date | None
    status: Literal["open", "settled", "cancelled"]
    projection_version: str = Field(pattern=r"^(0|[1-9][0-9]*)$")


class ClientFinanceLedgerEntryView(_StrictModel):
    entry_id: int = Field(gt=0)
    entry_type: Literal["receipt", "refund", "adjustment", "reversal"]
    amount_ntd: int = Field(gt=0)
    occurred_on: date
    reconciliation_reference: str = Field(min_length=1, max_length=191)
    reversal_of_entry_id: int | None = Field(default=None, gt=0)
    created_at: datetime
    allocations: list[ClientFinanceAllocationView]


class ClientFinanceCaseSummaryView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    account_version: str = Field(pattern=r"^(0|[1-9][0-9]*)$")
    open_receivable_amount_ntd: int = Field(ge=0)
    open_payable_amount_ntd: int = Field(ge=0)
    obligation_count: int = Field(ge=0)
    ledger_entry_count: int = Field(ge=0)


class ClientFinanceCaseView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    account_version: str = Field(pattern=r"^(0|[1-9][0-9]*)$")
    obligations: list[ClientFinanceObligationView]
    ledger_entries: list[ClientFinanceLedgerEntryView]


class ClientFinancePageView(_StrictModel):
    cases: list[ClientFinanceCaseSummaryView]


__all__ = [
    "ClientFinanceAllocationView",
    "ClientFinanceCaseSummaryView",
    "ClientFinanceCaseView",
    "ClientFinanceLedgerEntryView",
    "ClientFinanceObligationView",
    "ClientFinancePageView",
]
