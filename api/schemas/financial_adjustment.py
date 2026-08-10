"""Typed HTTP contracts for conserved financial adjustments."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinancialAdjustmentAllocationBody(_StrictModel):
    assignment_id: int = Field(gt=0)
    amount_delta_ntd: int

    @model_validator(mode="after")
    def require_nonzero_amount(self):
        if self.amount_delta_ntd == 0:
            raise ValueError("financial_adjustment_amount_must_be_nonzero")
        return self


class FinancialAdjustmentPreviewBody(_StrictModel):
    scope: Literal["client_only", "client_and_staff"] = "client_and_staff"
    source_event_identity: str = Field(min_length=1, max_length=191)
    amount_delta_ntd: int
    reason: str = Field(min_length=1, max_length=255)
    reversal_of_adjustment_identity: str | None = Field(
        default=None,
        min_length=1,
        max_length=191,
    )
    assignment_allocations: list[FinancialAdjustmentAllocationBody] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def require_valid_scope_allocation(self):
        if self.amount_delta_ntd == 0:
            raise ValueError("financial_adjustment_amount_must_be_nonzero")
        if self.scope == "client_only":
            if self.assignment_allocations:
                raise ValueError("client_only_adjustment_allocations_forbidden")
            return self
        if not self.assignment_allocations:
            raise ValueError("financial_adjustment_allocations_required")
        allocated = sum(item.amount_delta_ntd for item in self.assignment_allocations)
        if allocated != self.amount_delta_ntd:
            raise ValueError("financial_adjustment_not_conserved")
        return self


class FinancialAdjustmentApplyBody(FinancialAdjustmentPreviewBody):
    expected_client_account_version: int = Field(ge=0)
    expected_payroll_version: int | None = Field(default=None, ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_applicable_payroll_version(self):
        payroll_version_present = self.expected_payroll_version is not None
        if self.scope == "client_only" and payroll_version_present:
            raise ValueError("client_only_payroll_version_forbidden")
        if self.scope == "client_and_staff" and not payroll_version_present:
            raise ValueError("financial_adjustment_payroll_version_required")
        return self


class FinancialAdjustmentPreviewView(_StrictModel):
    client_account_version: int = Field(ge=0)
    payroll_version: int | None = Field(default=None, ge=0)
    candidate: dict[str, Any]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinancialAdjustmentReceiptView(_StrictModel):
    case_no: str
    adjustment_identity: str
    amount_delta_ntd: int
    client_account_version: int = Field(ge=0)
    payroll_version: int | None = Field(default=None, ge=0)
    assignment_allocation_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinancialAdjustmentQueryView(_StrictModel):
    case_no: str
    client_account_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    effective_assignments: list[dict[str, Any]]
    adjustments: list[dict[str, Any]]


__all__ = [
    "FinancialAdjustmentApplyBody",
    "FinancialAdjustmentPreviewBody",
    "FinancialAdjustmentPreviewView",
    "FinancialAdjustmentQueryView",
    "FinancialAdjustmentReceiptView",
]
