"""Typed HTTP contracts for Payroll rebuild and monthly aggregation."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PayrollAssignmentCalculationView(_StrictModel):
    assignment_identity: str
    staff_id: int = Field(gt=0)
    official_service_day_count: int = Field(gt=0)
    actual_hours: int = Field(gt=0)
    double_pay_hours: int = Field(ge=0)
    hourly_rate_ntd: int = Field(gt=0)
    service_salary_ntd: int = Field(gt=0)
    floor_fee_allocated_ntd: int = Field(ge=0)
    effective_adjustments_ntd: int
    total_payable_ntd: int = Field(gt=0)


class PayrollRebuildActionView(_StrictModel):
    assignment_identity: str
    obligation_identity: str
    action: str
    before_amount_ntd: int = Field(ge=0)
    after_amount_ntd: int = Field(ge=0)
    delta_amount_ntd: int


class PayrollRebuildPreviewView(_StrictModel):
    case_no: str
    payroll_version: int = Field(ge=0)
    assignments: list[PayrollAssignmentCalculationView]
    actions: list[PayrollRebuildActionView]
    earned_floor_fee_ntd: int = Field(ge=0)
    total_payable_ntd: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PayrollRebuildApplyBody(_StrictModel):
    expected_payroll_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class PayrollRebuildReceiptView(_StrictModel):
    case_no: str
    payroll_version: int = Field(gt=0)
    action_count: int = Field(ge=0)
    total_payable_ntd: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class MonthlyPayrollObligationView(_StrictModel):
    obligation_identity: str
    case_no: str
    assignment_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    due_date: date
    direction: str
    amount_due_ntd: int = Field(gt=0)


class StaffMonthlyPayrollSummaryView(_StrictModel):
    staff_id: int = Field(gt=0)
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)
    case_count: int = Field(ge=0)
    obligation_count: int = Field(ge=0)
    payable_total_ntd: int = Field(ge=0)
    receivable_total_ntd: int = Field(ge=0)
    net_payable_ntd: int
    obligations: list[MonthlyPayrollObligationView]


class PayrollRebuildTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "PayrollRebuildApplyBody",
    "PayrollRebuildPreviewView",
    "PayrollRebuildReceiptView",
    "PayrollRebuildTypedErrorView",
    "StaffMonthlyPayrollSummaryView",
]
