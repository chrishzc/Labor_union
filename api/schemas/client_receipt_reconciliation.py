"""Typed HTTP contracts for Client Receipt reconciliation."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ReceiptStage = Literal["deposit", "first", "second", "adjustment"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientReceiptPreviewBody(_StrictModel):
    payment_stage: ReceiptStage
    finance_import_row_ids: list[int] = Field(min_length=1)
    obligation_identities: list[str] = Field(min_length=1)


class ClientReceiptApplyBody(ClientReceiptPreviewBody):
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ClientReceiptBankFactView(_StrictModel):
    finance_import_row_id: int = Field(gt=0)
    amount_ntd: int = Field(gt=0)
    transaction_date: date
    dedup_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClientReceiptObligationView(_StrictModel):
    obligation_identity: str
    payment_stage: ReceiptStage
    amount_due_ntd: int = Field(gt=0)
    due_date: date | None


class ClientReceiptQueryView(_StrictModel):
    case_no: str
    account_version: int = Field(ge=0)
    bank_facts: list[ClientReceiptBankFactView]
    obligations: list[ClientReceiptObligationView]


class MoneyNTDView(_StrictModel):
    amount: int = Field(ge=0)


class ClientReceiptAllocationView(_StrictModel):
    bank_fact_identity: str = Field(min_length=1, max_length=191)
    obligation_identity: str = Field(min_length=1, max_length=191)
    amount: MoneyNTDView


class ClientReceiptCandidateView(_StrictModel):
    status: Literal["exact", "overage", "review_required"]
    payment_stage: ReceiptStage
    bank_total: MoneyNTDView
    obligation_total: MoneyNTDView
    overage_amount: MoneyNTDView
    allocations: list[ClientReceiptAllocationView]
    blockers: list[str]
    settlement_identity: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClientReceiptPreviewView(_StrictModel):
    account_version: int = Field(ge=0)
    candidate: ClientReceiptCandidateView
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClientReceiptReceiptView(_StrictModel):
    case_no: str
    account_version: int = Field(ge=0)
    status: str
    settlement_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_entry_count: int = Field(ge=0)
    allocation_count: int = Field(ge=0)
    blockers: list[str]


class ClientReceiptTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "ClientReceiptApplyBody",
    "ClientReceiptPreviewBody",
    "ClientReceiptPreviewView",
    "ClientReceiptQueryView",
    "ClientReceiptReceiptView",
    "ClientReceiptTypedErrorView",
]
