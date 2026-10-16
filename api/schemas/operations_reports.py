"""
File: operations_reports.py
Description: 定義實際週界營運報表 operations-report.v3／v4 的獨立 strict wire views。
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.government_subsidy_report import GovernmentSubsidyReportRowView


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WeeklyReportPeriodView(_StrictModel):
    start_date: date
    end_date: date
    timezone: Literal["Asia/Taipei"]
    period_label: str


class WeeklyReportSummaryView(_StrictModel):
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


class WeeklyReportCaseTotalsView(WeeklyReportSummaryView):
    year: int = Field(ge=1)
    month: int | None = Field(ge=1, le=12)
    start_date: date
    end_date: date
    promotion_count: int | None = Field(ge=0)
    inquiry_count: int | None = Field(ge=0)
    review_rejected_count: int = Field(ge=0)
    order_status_counts: dict[str, Annotated[int, Field(ge=0)]]


class CaseStatisticsSummaryView(_StrictModel):
    application_count: int = Field(ge=0)
    general_eligible_count: int = Field(ge=0)
    general_ineligible_count: int | None = Field(ge=0)
    subsidized_eligible_count: int = Field(ge=0)
    subsidized_ineligible_count: int | None = Field(ge=0)
    order_status_counts: dict[Literal["待補件", "洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"], Annotated[int, Field(ge=0)]]
    unclassified_qualification_count: int = Field(ge=0)
    other_status_count: int = Field(ge=0)


class CaseStatisticsView(_StrictModel):
    year: int = Field(ge=1, le=9998)
    quarter: int | None = Field(ge=1, le=4)
    month: int | None = Field(ge=1, le=12)
    start_date: date
    end_date: date
    timezone: Literal["Asia/Taipei"]
    available_years: list[Annotated[int, Field(ge=1, le=9998)]]
    annual_application_count: int = Field(ge=0)
    summary: CaseStatisticsSummaryView
    generated_at: datetime


class WeeklyOperationsSubsidyRowView(GovernmentSubsidyReportRowView):
    application_roc_year: int | None = Field(default=None, ge=1)
    claim_period_label: str
    reconciliation_status: str
    notes: str


class WeeklyOperationsSubsidyPartitionView(_StrictModel):
    citizen_kind: Literal["general", "subsidized"]
    row_count: int = Field(ge=0)
    total_amount_ntd: int = Field(ge=0)
    rows: list[WeeklyOperationsSubsidyRowView]


class WeeklyReportCaseRowView(_StrictModel):
    case_no: str
    applicant_name: str
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
    service_hours_per_day: float | None = Field(default=None, gt=0, le=24, multiple_of=0.5)
    planned_start_date: date | None
    planned_end_date: date | None
    district: str | None
    data_quality_codes: list[str]
    week_start_date: date | None
    week_end_date: date | None
    week_label: str


class WeeklyReportServiceRowView(_StrictModel):
    assignment_id: int = Field(gt=0)
    case_no: str
    client_name: str
    staff_name: str
    staff_union_no: str | None = None
    service_start_date: date | None
    service_end_date: date | None
    period_start_date: date
    period_end_date: date
    service_hours_per_day: float | None = Field(default=None, gt=0, le=24, multiple_of=0.5)
    weekly_work_days: int = Field(gt=0)
    weekly_hours: float | None = Field(default=None, gt=0, multiple_of=0.5)
    order_status: str
    completed: bool
    data_quality_codes: list[str]


class WeeklyReportDataQualityIssueView(_StrictModel):
    code: str
    field: str
    row_count: int = Field(ge=0)
    message: str


class WeeklyReportMetricView(_StrictModel):
    week_start_date: date
    week_end_date: date
    promotion_count: int | None = Field(default=None, ge=0)
    inquiry_count: int | None = Field(default=None, ge=0)
    updated_at: datetime | None


class WeeklyOperationsReportView(_StrictModel):
    schema_version: Literal["operations-report.v3"]
    period: WeeklyReportPeriodView
    generated_at: datetime
    source_revision: str
    summary: WeeklyReportSummaryView
    case_rows: list[WeeklyReportCaseRowView]
    subsidy_partitions: list[WeeklyOperationsSubsidyPartitionView]
    service_rows: list[WeeklyReportServiceRowView]
    weekly_metrics: list[WeeklyReportMetricView]
    data_quality_issues: list[WeeklyReportDataQualityIssueView]


class WeeklyOperationsReportTotalsView(WeeklyOperationsReportView):
    schema_version: Literal["operations-report.v4"]
    annual_totals: list[WeeklyReportCaseTotalsView]
    monthly_subtotals: list[WeeklyReportCaseTotalsView]


WeeklyOperationsReportSchemaVersion = Literal["operations-report.v3", "operations-report.v4"]


class SaveWeeklyReportMetricRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    promotion_count: int | None = Field(..., ge=0)
    inquiry_count: int | None = Field(..., ge=0)


__all__ = [
    "WeeklyOperationsReportView",
    "WeeklyOperationsReportTotalsView",
    "WeeklyOperationsReportSchemaVersion",
    "WeeklyReportMetricView",
    "SaveWeeklyReportMetricRequest",
]
