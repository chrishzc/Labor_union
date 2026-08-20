"""
File: government_subsidy_report.py
Description: 定義季度與年度補助報表的strict server-redacted JSON views。
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GovernmentSubsidyReportRowView(_StrictModel):
    serial_number: int = Field(gt=0)
    case_no: str
    eligibility: str
    service_start: date
    service_end: date
    subsidy_hours: Decimal = Field(gt=0)
    subsidy_days: Decimal = Field(gt=0)
    service_days: int = Field(gt=0)
    subsidy_amount_ntd: int = Field(ge=0)
    unit_price_ntd: int = Field(ge=0)
    employer_name_masked: str
    staff_name_masked: str
    identity_card_masked: str
    address_masked: str


class GovernmentSubsidyReportPartitionView(_StrictModel):
    citizen_kind: Literal["general", "subsidized"]
    row_count: int = Field(ge=0)
    total_amount_ntd: int = Field(ge=0)
    rows: list[GovernmentSubsidyReportRowView]


class GovernmentSubsidyReportPreviewView(_StrictModel):
    period_kind: Literal["quarterly", "annual"]
    application_year: int = Field(ge=1912)
    quarter: int | None = Field(default=None, ge=1, le=4)
    generated_at: datetime
    source_revision: str
    total_row_count: int = Field(ge=0)
    total_amount_ntd: int = Field(ge=0)
    partitions: list[GovernmentSubsidyReportPartitionView]
