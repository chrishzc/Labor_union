"""Typed HTTP contracts for Staff Payout Reconciliation."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StaffPayoutApplyFields(_StrictModel):
    expected_staff_payables_version: int = Field(ge=0)
    expected_bank_facts_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class PayoutPreviewBody(_StrictModel):
    finance_import_row_ids: list[int] = Field(min_length=1)
    obligation_identities: list[str] = Field(min_length=1)


class PayoutApplyBody(StaffPayoutApplyFields):
    finance_import_row_ids: list[int] = Field(min_length=1)
    obligation_identities: list[str] = Field(min_length=1)


class ReturnPreviewBody(_StrictModel):
    return_finance_import_row_id: int = Field(gt=0)
    source_payout_event_id: int = Field(gt=0)
    obligation_identities: list[str] = Field(min_length=1)


class ReturnApplyBody(StaffPayoutApplyFields):
    return_finance_import_row_id: int = Field(gt=0)
    source_payout_event_id: int = Field(gt=0)
    obligation_identities: list[str] = Field(min_length=1)


class ReversalPreviewBody(_StrictModel):
    source_payout_event_id: int = Field(gt=0)
    occurred_on: date
    obligation_identities: list[str] = Field(min_length=1)


class ReversalApplyBody(StaffPayoutApplyFields):
    source_payout_event_id: int = Field(gt=0)
    occurred_on: date
    obligation_identities: list[str] = Field(min_length=1)


class StaffPayableObligationView(_StrictModel):
    obligation_identity: str
    case_no: str
    amount_due_ntd: int = Field(gt=0)
    due_date: date | None
    net_paid_ntd: int = Field(ge=0)
    balance_ntd: int
    payout_status: str


class StaffPayoutEventView(_StrictModel):
    id: int = Field(gt=0)
    event_type: str
    amount_ntd: int = Field(gt=0)
    occurred_on: date
    finance_import_row_id: int | None
    reversal_of_event_id: int | None
    reconciliation_reference: str


class StaffPayablesQueryView(_StrictModel):
    staff_id: int = Field(gt=0)
    staff_payables_version: int = Field(ge=0)
    obligations: list[StaffPayableObligationView]
    events: list[StaffPayoutEventView]


class StaffPayoutPreviewView(_StrictModel):
    event_type: str
    staff_payables_version: int = Field(ge=0)
    bank_facts_version: int = Field(ge=0)
    candidate: dict[str, Any]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffPayoutReceiptView(_StrictModel):
    event_type: str
    staff_id: int = Field(gt=0)
    staff_payables_version: int = Field(ge=0)
    bank_facts_version: int = Field(ge=0)
    resulting_status: str
    event_count: int = Field(ge=0)
    obligation_link_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffPayoutTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "PayoutApplyBody",
    "PayoutPreviewBody",
    "ReturnApplyBody",
    "ReturnPreviewBody",
    "ReversalApplyBody",
    "ReversalPreviewBody",
    "StaffPayablesQueryView",
    "StaffPayoutPreviewView",
    "StaffPayoutReceiptView",
    "StaffPayoutTypedErrorView",
]
