"""Typed HTTP contracts for Payroll query and staff adjustments."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PayrollAdjustmentAllocationBody(_StrictModel):
    assignment_id: StrictInt = Field(gt=0)
    amount_ntd: StrictInt


class PayrollAdjustmentPreviewBody(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    source_event_identity: str = Field(min_length=1, max_length=191)
    allocations: list[PayrollAdjustmentAllocationBody] = Field(min_length=1)


class PayrollAdjustmentApplyBody(PayrollAdjustmentPreviewBody):
    expected_payroll_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class PayrollAdjustmentAllocationView(_StrictModel):
    assignment_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    signed_amount_ntd: int
    obligation_identity: str
    obligation_kind: str
    direction: str
    amount_due_ntd: int = Field(gt=0)
    source_obligation_identity: str | None
    payout_history_exists: bool


class PayrollAdjustmentCandidateView(_StrictModel):
    case_no: str
    source_event_identity: str
    adjustment_identity: str
    amount_ntd: int
    due_date: date
    allocations: list[PayrollAdjustmentAllocationView]
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PayrollAdjustmentPreviewView(_StrictModel):
    payroll_version: int = Field(ge=0)
    candidate: PayrollAdjustmentCandidateView
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PayrollAdjustmentReceiptView(_StrictModel):
    case_no: str
    payroll_version: int = Field(gt=0)
    adjustment_identity: str
    allocation_count: int = Field(gt=0)
    amount_ntd: int
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PayrollObligationView(_StrictModel):
    obligation_identity: str
    assignment_id: int = Field(gt=0)
    case_no: str
    staff_id: int = Field(gt=0)
    obligation_kind: str
    direction: str
    source_obligation_identity: str | None
    amount_due_ntd: int = Field(gt=0)
    due_date: date | None
    status: str
    payout_history_exists: bool


class PayrollAdjustmentEventView(_StrictModel):
    adjustment_identity: str
    amount_ntd: int
    source_event_identity: str
    actor: str
    reason: str
    created_at: datetime


class CasePayrollQueryView(_StrictModel):
    case_no: str
    payroll_version: int = Field(ge=0)
    staff_payment_due_date: date | None
    obligations: list[PayrollObligationView]
    adjustments: list[PayrollAdjustmentEventView]


class StaffPayrollObligationsQueryView(_StrictModel):
    staff_id: int = Field(gt=0)
    obligations: list[PayrollObligationView]


class PayrollTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "CasePayrollQueryView",
    "PayrollAdjustmentApplyBody",
    "PayrollAdjustmentPreviewBody",
    "PayrollAdjustmentPreviewView",
    "PayrollAdjustmentReceiptView",
    "PayrollTypedErrorView",
    "StaffPayrollObligationsQueryView",
]
