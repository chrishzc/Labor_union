"""Typed HTTP views for accounts-payable export."""

from datetime import date

from pydantic import BaseModel, ConfigDict


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


class AccountsPayableArchiveRecordView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    sha256: str
    size_bytes: int


class AccountsPayableArchiveView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    records: list[AccountsPayableArchiveRecordView]
