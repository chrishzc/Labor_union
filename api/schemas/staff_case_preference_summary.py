"""
File: staff_case_preference_summary.py
Description: 定義 Staff roster 接案偏好摘要的嚴格唯讀契約。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OtherDetailStatus = Literal["ready", "not_recorded", "source_not_ready"]


class PreferenceTopicSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str]
    other_detail: str | None = None
    other_detail_status: OtherDetailStatus


class StaffCasePreferenceSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    service_regions: PreferenceTopicSummaryView
    service_periods: PreferenceTopicSummaryView
    rest_schedule: PreferenceTopicSummaryView
    baby_counts: PreferenceTopicSummaryView
    holiday_availability: PreferenceTopicSummaryView
    transportation: PreferenceTopicSummaryView
