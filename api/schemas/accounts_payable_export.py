"""
File: accounts_payable_export.py
Description: 定義應付帳款canonical preview與封存清單的嚴格HTTP views。
"""

from datetime import date

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccountsPayableRowView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_date: date
    payment_type: str
    recipient_name: str
    bank_code: str
    bank_account: str
    amount_ntd: int
    obligation_identities: list[str]
    case_numbers: list[str]
    recipient_identity_card: str


class AccountsPayablePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_payment_date: date
    row_count: int
    total_amount_ntd: int
    rows: list[AccountsPayableRowView]


class CaseStaffPayableAuditItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    staff_id: int | None = Field(default=None, gt=0)
    recipient_name: str | None
    obligation_identity: str | None
    amount_due_ntd: int | None = Field(default=None, ge=0)
    balance_ntd: int | None = Field(default=None, ge=0)
    order_due_date: date | None
    effective_due_date: date | None
    source: Literal["formal_obligation", "historical_projection", "order_facts"]
    disposition: Literal[
        "selected_month",
        "other_month",
        "date_not_formed",
        "missing_calculation_basis",
        "paid_or_settled",
        "blocked",
    ]
    reason: str


class CaseStaffPayableAuditView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    target_payment_date: date
    items: list[CaseStaffPayableAuditItemView]


class AccountsPayableArchiveRecordView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    sha256: str
    size_bytes: int


class AccountsPayableArchiveView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    records: list[AccountsPayableArchiveRecordView]
