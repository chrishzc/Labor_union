"""
File: operations_reports.py
Description: 定義營運報表 operations-report.v2 的 strict 去敏 view。
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.government_subsidy_report import GovernmentSubsidyReportPartitionView


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WeeklyReportPeriodView(_StrictModel):
    start_date: date
    end_date: date
    timezone: Literal["Asia/Taipei"]
    period_label: str


class WeeklyReportSummaryView(_StrictModel):
    promotion_count: int | None = Field(default=None, ge=0)
    inquiry_count: int | None = Field(default=None, ge=0)
    application_count: int = Field(ge=0)
    general_eligible_count: int = Field(ge=0)
    general_ineligible_count: int | None = Field(default=None, ge=0)
    subsidized_eligible_count: int = Field(ge=0)
    subsidized_ineligible_count: int | None = Field(default=None, ge=0)
    rejection_unpartitioned_count: int = Field(ge=0)
    order_established_count: int = Field(ge=0)
    negotiating_count: int = Field(ge=0)
    cancelled_count: int = Field(ge=0)
    incomplete_count: int = Field(ge=0)


class WeeklyReportCaseRowView(_StrictModel):
    case_no: str
    applicant_name_masked: str
    application_date: date | None
    identity_status: str | None
    review_result: Literal[
        "general_eligible",
        "subsidized_eligible",
        "rejected_unpartitioned",
        "pending",
    ]
    order_status: str | None
    service_days: int | None = Field(default=None, gt=0)
    service_hours_per_day: int | None = Field(default=None, gt=0)
    planned_start_date: date | None
    planned_end_date: date | None
    district: str | None
    data_quality_codes: list[str]


class WeeklyReportServiceRowView(_StrictModel):
    assignment_id: int = Field(gt=0)
    case_no: str
    client_name_masked: str
    staff_name_masked: str
    service_start_date: date
    service_end_date: date
    period_start_date: date
    period_end_date: date
    service_hours_per_day: int = Field(gt=0)
    weekly_work_days: int = Field(gt=0)
    weekly_hours: int = Field(gt=0)
    order_status: str
    completed: bool
    data_quality_codes: list[str]


class WeeklyReportDataQualityIssueView(_StrictModel):
    code: str
    field: str
    row_count: int = Field(ge=0)
    message: str


class WeeklyOperationsReportView(_StrictModel):
    schema_version: Literal["operations-report.v2"]
    period: WeeklyReportPeriodView
    generated_at: datetime
    source_revision: str
    summary: WeeklyReportSummaryView
    case_rows: list[WeeklyReportCaseRowView]
    subsidy_partitions: list[GovernmentSubsidyReportPartitionView]
    service_rows: list[WeeklyReportServiceRowView]
    data_quality_issues: list[WeeklyReportDataQualityIssueView]


__all__ = ["WeeklyOperationsReportView"]
