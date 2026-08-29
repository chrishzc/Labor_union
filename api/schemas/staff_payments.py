"""Typed HTTP views for the historical Staff Payables compatibility projection."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import ConfigDict, BaseModel, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StaffPaymentTransactionView(_StrictModel):
    id: int = Field(gt=0)
    staff_payment_id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    transaction_type: str
    transaction_status: str
    amount: Decimal = Field(gt=0)
    occurred_at: date | None
    external_reference: str | None
    reversal_of_transaction_id: int | None = Field(default=None, gt=0)
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None


class StaffPaymentSummaryView(_StrictModel):
    id: int = Field(gt=0)
    assignment_id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    service_hours: Decimal = Field(ge=0)
    hourly_rate: Decimal = Field(ge=0)
    service_salary: Decimal = Field(ge=0)
    floor_fee_amount: Decimal = Field(ge=0)
    adjustment_amount: Decimal
    total_payable: Decimal = Field(ge=0)
    amount_paid: Decimal = Field(ge=0)
    due_date: date | None
    paid_at: date | None
    payment_status: str
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None
    transactions: list[StaffPaymentTransactionView] = Field(default_factory=list)


__all__ = ["StaffPaymentSummaryView", "StaffPaymentTransactionView"]
