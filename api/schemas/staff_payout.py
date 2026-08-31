"""
File: staff_payout.py
Description: 定義 Staff Payables 付款與追償的嚴格 HTTP 契約。
"""

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
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=191)


class StaffOverpaymentRecoveryApplyBody(StaffOverpaymentRecoveryPreviewBody):
    expected_recovery_version: int = Field(ge=0)
    expected_staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=191)


class StaffOverpaymentRecoveryMatchedPreviewBody(StaffOverpaymentRecoveryPreviewBody):
    matching_identity: str = Field(min_length=1, max_length=191)
    matching_version: int = Field(ge=1)


class StaffOverpaymentRecoveryMatchedApplyBody(StaffOverpaymentRecoveryMatchedPreviewBody):
    expected_recovery_version: int = Field(ge=0)
    expected_staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=191)


class StaffOverpaymentRecoveryMatchingPreviewBody(_StrictModel):
    recovery_identity: str = Field(min_length=1, max_length=191)
    finance_import_row_id: int = Field(gt=0)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=191)

    def model_dump(self, *args, **kwargs):
        payload = super().model_dump(*args, **kwargs)
        if self.evidence_reference is None:
            payload.pop("evidence_reference", None)
        return payload


class StaffOverpaymentRecoveryMatchingApplyBody(
    StaffOverpaymentRecoveryMatchingPreviewBody
):
    expected_recovery_version: int = Field(ge=0)
    expected_staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=191)


class StaffOverpaymentRecoveryAdjustmentPreviewBody(_StrictModel):
    recovery_identity: str = Field(min_length=1, max_length=191)
    adjustment_amount_ntd: int = Field(gt=0)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=191)


class StaffOverpaymentRecoveryAdjustmentApplyBody(
    StaffOverpaymentRecoveryAdjustmentPreviewBody
):
    expected_recovery_version: int = Field(ge=0)
    expected_staff_payables_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=191)


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
    evidence_reference: str | None = None


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
    evidence_reference: str | None = None


class StaffOverpaymentRecoveryMatchingQueryView(_StrictModel):
    matching_identity: str
    matching_version: int = Field(ge=1)
    finance_import_row_identity: str


class StaffOverpaymentRecoveryQueryView(_StrictModel):
    staff_id: int = Field(gt=0)
    recovery_identity: str
    remaining_amount_ntd: int = Field(ge=0)
    status: str
    recovery_version: int = Field(ge=0)
    staff_payables_version: int = Field(ge=0)
    source_bank_fact_references: list[str]
    source_payout_event_references: list[str]
    source_obligation_references: list[str]
    matchings: list[StaffOverpaymentRecoveryMatchingQueryView]


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


class StaffPayoutMoneyView(_StrictModel):
    amount: int


class StaffPayoutAllocationPreviewView(_StrictModel):
    bank_fact_identity: str
    obligation_identity: str
    amount: StaffPayoutMoneyView


class StaffPayoutLedgerEventPreviewView(_StrictModel):
    identity: str
    event_type: Literal["payout", "return", "reversal"]
    status: Literal["succeeded"]
    staff_id: int = Field(gt=0)
    amount: StaffPayoutMoneyView
    finance_import_fact_identity: str | None = None
    reversal_of_event_identity: str | None = None


class StaffPayoutObligationLinkPreviewView(_StrictModel):
    event_identity: str
    obligation_identity: str
    allocated_amount: StaffPayoutMoneyView


class StaffOverpaymentRecoveryCandidateView(_StrictModel):
    identity: str
    staff_id: int = Field(gt=0)
    original_amount: StaffPayoutMoneyView
    source_bank_fact_identities: list[str]
    source_obligation_identities: list[str]


class StaffPayoutCandidatePreviewView(_StrictModel):
    staff_id: int = Field(gt=0)
    bank_total: StaffPayoutMoneyView
    obligation_total: StaffPayoutMoneyView
    allocations: list[StaffPayoutAllocationPreviewView]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    events: list[StaffPayoutLedgerEventPreviewView]
    obligation_links: list[StaffPayoutObligationLinkPreviewView]
    resulting_status: Literal["payable", "partially_paid", "completed", "recovery_required", "anomaly"]
    difference_mode: Literal["underpayment", "overpayment"] | None = None
    recovery: StaffOverpaymentRecoveryCandidateView | None = None


class StaffPayoutReopenCandidatePreviewView(_StrictModel):
    staff_id: int = Field(gt=0)
    event: StaffPayoutLedgerEventPreviewView
    obligation_links: list[StaffPayoutObligationLinkPreviewView]
    resulting_status: Literal["payable", "partially_paid", "completed", "recovery_required", "anomaly"]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffPayablesQueryView(_StrictModel):
    staff_id: int = Field(gt=0)
    staff_payables_version: int = Field(ge=0)
    obligations: list[StaffPayableObligationView]
    events: list[StaffPayoutEventView]


class StaffPayoutPreviewView(_StrictModel):
    event_type: str
    staff_payables_version: int = Field(ge=0)
    bank_facts_version: int = Field(ge=0)
    candidate: StaffPayoutCandidatePreviewView | StaffPayoutReopenCandidatePreviewView
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


class HistoricalStaffPayoutIntentBody(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    confirmation_kind: Literal["paid", "settled"]
    obligation_identities: list[str] = Field(min_length=1)
    payment_date: date | None = None
    payment_date_unknown_reason: str | None = Field(default=None, min_length=1, max_length=500)
    source_availability: Literal["missing", "ambiguous", "unrecoverable"]
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=191)


class HistoricalStaffPayoutApplyBody(HistoricalStaffPayoutIntentBody):
    expected_staff_payables_version: int = Field(ge=0)
    expected_adoption_receipt_id: int = Field(gt=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class HistoricalStaffObligationView(_StrictModel):
    obligation_identity: str
    case_no: str
    staff_id: int = Field(gt=0)
    amount_due_ntd: int = Field(gt=0)
    payroll_version: int = Field(ge=0)
    direction: Literal["payable_to_staff", "receivable_from_staff"]
    status: Literal["open", "settled", "cancelled"]


class HistoricalStaffPayoutQueryView(_StrictModel):
    case_no: str
    staff_id: int = Field(gt=0)
    staff_payables_version: int = Field(ge=0)
    adoption_receipt_id: int | None = Field(default=None, gt=0)
    adopted: bool
    normal_bank_candidate_identities: list[str]
    obligations: list[HistoricalStaffObligationView]


class HistoricalStaffPayoutPreviewView(_StrictModel):
    case_no: str
    staff_id: int = Field(gt=0)
    staff_payables_version: int = Field(ge=0)
    adoption_receipt_id: int | None = Field(default=None, gt=0)
    obligations: list[HistoricalStaffObligationView]
    amount_snapshot_ntd: int = Field(ge=0)
    blockers: list[str]
    can_apply: bool
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalStaffPayoutReceiptView(_StrictModel):
    event_identity: str
    case_no: str
    staff_id: int = Field(gt=0)
    obligation_identities: list[str]
    amount_snapshot_ntd: int = Field(gt=0)
    resulting_staff_payables_version: int = Field(ge=1)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalStaffPayoutProjectionView(_StrictModel):
    obligation_identity: str
    amount_snapshot_ntd: int = Field(gt=0)
    obligation_payroll_version: int = Field(ge=0)


class HistoricalStaffPayoutReadbackView(_StrictModel):
    case_no: str
    staff_id: int = Field(gt=0)
    staff_payables_version: int = Field(ge=0)
    obligations: list[HistoricalStaffObligationView]
    projections: list[HistoricalStaffPayoutProjectionView]
    owner_terminal: bool


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
    "StaffPayoutCandidatePreviewView",
    "StaffPayoutReopenCandidatePreviewView",
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
    "StaffOverpaymentRecoveryMatchingQueryView",
    "StaffOverpaymentRecoveryQueryView",
    "HistoricalStaffObligationView",
    "HistoricalStaffPayoutApplyBody",
    "HistoricalStaffPayoutIntentBody",
    "HistoricalStaffPayoutPreviewView",
    "HistoricalStaffPayoutProjectionView",
    "HistoricalStaffPayoutQueryView",
    "HistoricalStaffPayoutReadbackView",
    "HistoricalStaffPayoutReceiptView",
]
