"""Typed HTTP contracts for Staff Payout Reconciliation."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

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


class PayoutDifferencePreviewBody(PayoutPreviewBody):
    mode: Literal["underpayment", "overpayment"]


class PayoutDifferenceApplyBody(PayoutApplyBody):
    mode: Literal["underpayment", "overpayment"]


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


class StaffOverpaymentRecoveryPreviewBody(_StrictModel):
    recovery_identity: str = Field(min_length=1, max_length=191)
    finance_import_row_id: int = Field(gt=0)


class StaffOverpaymentRecoveryApplyBody(StaffOverpaymentRecoveryPreviewBody):
    expected_recovery_version: int = Field(ge=0)
    expected_staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class StaffOverpaymentRecoveryMatchedPreviewBody(StaffOverpaymentRecoveryPreviewBody):
    matching_identity: str = Field(min_length=1, max_length=191)
    matching_version: int = Field(ge=1)


class StaffOverpaymentRecoveryMatchedApplyBody(StaffOverpaymentRecoveryMatchedPreviewBody):
    expected_recovery_version: int = Field(ge=0)
    expected_staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class StaffOverpaymentRecoveryMatchingPreviewBody(_StrictModel):
    recovery_identity: str = Field(min_length=1, max_length=191)
    finance_import_row_id: int = Field(gt=0)


class StaffOverpaymentRecoveryMatchingApplyBody(
    StaffOverpaymentRecoveryMatchingPreviewBody
):
    expected_recovery_version: int = Field(ge=0)
    expected_staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class StaffOverpaymentRecoveryAdjustmentPreviewBody(_StrictModel):
    recovery_identity: str = Field(min_length=1, max_length=191)
    adjustment_amount_ntd: int = Field(gt=0)


class StaffOverpaymentRecoveryAdjustmentApplyBody(
    StaffOverpaymentRecoveryAdjustmentPreviewBody
):
    expected_recovery_version: int = Field(ge=0)
    expected_staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class StaffOverpaymentRecoveryPreviewView(_StrictModel):
    recovery_identity: str
    recovery_version: int = Field(ge=0)
    staff_payables_version: int = Field(ge=0)
    received_amount_ntd: int = Field(gt=0)
    remaining_before_ntd: int = Field(gt=0)
    remaining_after_ntd: int = Field(ge=0)
    resulting_status: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffOverpaymentRecoveryReceiptView(_StrictModel):
    recovery_identity: str
    recovery_version: int = Field(ge=0)
    staff_payables_version: int = Field(ge=0)
    remaining_after_ntd: int = Field(ge=0)
    resulting_status: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffOverpaymentRecoveryAdjustmentPreviewView(_StrictModel):
    recovery_identity: str
    recovery_version: int = Field(ge=0)
    staff_payables_version: int = Field(ge=0)
    adjustment_amount_ntd: int = Field(gt=0)
    remaining_before_ntd: int = Field(gt=0)
    remaining_after_ntd: int = Field(ge=0)
    resulting_status: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffPayoutDifferenceSourceView(_StrictModel):
    payout_difference_identity: str
    staff_id: int = Field(gt=0)
    difference_mode: Literal["underpayment", "overpayment"]
    bank_total_ntd: int = Field(gt=0)
    obligation_total_ntd: int = Field(gt=0)
    recovery_identity: str | None = None
    resulting_staff_payables_version: int = Field(ge=0)
    source_bank_facts_version: int = Field(ge=0)
    finance_import_row_ids: list[int] = Field(min_length=1)
    obligation_identities: list[str] = Field(min_length=1)


class StaffOverpaymentRecoveryMatchingPreviewView(_StrictModel):
    recovery_identity: str
    staff_id: int = Field(gt=0)
    finance_import_row_identity: str
    recovery_version: int = Field(ge=0)
    staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffOverpaymentRecoveryMatchingReceiptView(_StrictModel):
    matching_identity: str
    matching_version: int = Field(ge=1)
    recovery_identity: str
    staff_id: int = Field(gt=0)
    finance_import_row_identity: str
    recovery_version: int = Field(ge=0)
    staff_payables_version: int = Field(ge=0)


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
    difference_mode: str | None = None
    recovery_identity: str | None = None
    recovery_amount_ntd: int = Field(ge=0)


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
    "PayoutDifferenceApplyBody",
    "PayoutDifferencePreviewBody",
    "PayoutPreviewBody",
    "ReturnApplyBody",
    "ReturnPreviewBody",
    "ReversalApplyBody",
    "ReversalPreviewBody",
    "StaffPayablesQueryView",
    "StaffPayoutPreviewView",
    "StaffPayoutDifferenceSourceView",
    "StaffPayoutReceiptView",
    "StaffPayoutTypedErrorView",
    "StaffOverpaymentRecoveryApplyBody",
    "StaffOverpaymentRecoveryMatchedApplyBody",
    "StaffOverpaymentRecoveryMatchedPreviewBody",
    "StaffOverpaymentRecoveryMatchingApplyBody",
    "StaffOverpaymentRecoveryMatchingPreviewBody",
    "StaffOverpaymentRecoveryMatchingPreviewView",
    "StaffOverpaymentRecoveryMatchingReceiptView",
    "StaffOverpaymentRecoveryAdjustmentApplyBody",
    "StaffOverpaymentRecoveryAdjustmentPreviewBody",
    "StaffOverpaymentRecoveryAdjustmentPreviewView",
    "StaffOverpaymentRecoveryPreviewBody",
    "StaffOverpaymentRecoveryPreviewView",
    "StaffOverpaymentRecoveryReceiptView",
]
