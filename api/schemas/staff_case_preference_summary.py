"""HTTP response models for the Staff case-preference summary projection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from subsystems.staff.case_preference_summary_query import (
    PreferenceTopicSummary,
    StaffCasePreferenceSummary,
)


class StaffCasePreferenceTopicView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str]
    other_detail: str | None
    other_detail_status: Literal["ready", "not_recorded", "source_not_ready"]

    @classmethod
    def from_summary(
        cls, summary: PreferenceTopicSummary
    ) -> "StaffCasePreferenceTopicView":
        return cls(
            values=list(summary.values),
            other_detail=summary.other_detail,
            other_detail_status=summary.other_detail_status,
        )


class StaffCasePreferenceSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int
    service_regions: StaffCasePreferenceTopicView
    service_periods: StaffCasePreferenceTopicView
    rest_schedule: StaffCasePreferenceTopicView
    baby_counts: StaffCasePreferenceTopicView
    holiday_availability: StaffCasePreferenceTopicView
    transportation: StaffCasePreferenceTopicView

    @classmethod
    def from_summary(
        cls, summary: StaffCasePreferenceSummary
    ) -> "StaffCasePreferenceSummaryView":
        return cls(
            staff_id=summary.staff_id,
            service_regions=StaffCasePreferenceTopicView.from_summary(
                summary.service_regions
            ),
            service_periods=StaffCasePreferenceTopicView.from_summary(
                summary.service_periods
            ),
            rest_schedule=StaffCasePreferenceTopicView.from_summary(
                summary.rest_schedule
            ),
            baby_counts=StaffCasePreferenceTopicView.from_summary(
                summary.baby_counts
            ),
            holiday_availability=StaffCasePreferenceTopicView.from_summary(
                summary.holiday_availability
            ),
            transportation=StaffCasePreferenceTopicView.from_summary(
                summary.transportation
            ),
        )


__all__ = [
    "StaffCasePreferenceSummaryView",
    "StaffCasePreferenceTopicView",
]
