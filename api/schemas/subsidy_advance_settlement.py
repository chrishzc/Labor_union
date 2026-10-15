"""Strict authenticated advance-recovery query and human-command contracts."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from domains.client_finance.subsidy_advance_settlement import SettlementStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AdvanceSettlementRowView(StrictModel):
    advance_id: int = Field(gt=0)
    case_no: str
    client_name: str
    advanced_on: date
    advance_amount_ntd: int = Field(gt=0)
    government_received_ntd: int = Field(ge=0)
    received_on: date | None
    recovered_amount_ntd: int = Field(ge=0)
    status: SettlementStatus
    review_reason: str | None


class AdvanceSettlementPageView(StrictModel):
    rows: list[AdvanceSettlementRowView]
    next_cursor: int | None = Field(gt=0)


class AdvanceSettlementPreviewView(StrictModel):
    row: AdvanceSettlementRowView
    account_version: int = Field(ge=0)
    batch_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


class AdvanceSettlementApplyBody(StrictModel):
    expected_account_version: int = Field(ge=0)
    expected_batch_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AdvanceSettlementReceiptView(StrictModel):
    advance_id: int = Field(gt=0)
    case_no: str
    recovered_amount_ntd: int = Field(gt=0)
    account_version: int = Field(ge=0)
