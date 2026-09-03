"""HTTP models for the Staff case-preference summary and six-topic mutation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from subsystems.staff.case_preference_summary_mutation import (
    PreferenceTopicInput,
    StaffCasePreferenceSnapshot,
)
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
    def from_summary(cls, summary: PreferenceTopicSummary) -> "StaffCasePreferenceTopicView":
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
    def from_summary(cls, summary: StaffCasePreferenceSummary) -> "StaffCasePreferenceSummaryView":
        return cls(
            staff_id=summary.staff_id,
            service_regions=StaffCasePreferenceTopicView.from_summary(summary.service_regions),
            service_periods=StaffCasePreferenceTopicView.from_summary(summary.service_periods),
            rest_schedule=StaffCasePreferenceTopicView.from_summary(summary.rest_schedule),
            baby_counts=StaffCasePreferenceTopicView.from_summary(summary.baby_counts),
            holiday_availability=StaffCasePreferenceTopicView.from_summary(summary.holiday_availability),
            transportation=StaffCasePreferenceTopicView.from_summary(summary.transportation),
        )


class StaffCasePreferenceTopicInputView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str]
    other_detail: str | None = None

    def to_domain(self) -> PreferenceTopicInput:
        return PreferenceTopicInput(tuple(self.values), self.other_detail)

    @classmethod
    def from_domain(cls, topic: PreferenceTopicInput) -> "StaffCasePreferenceTopicInputView":
        return cls(values=list(topic.values), other_detail=topic.other_detail)


class StaffCasePreferenceSnapshotView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_regions: StaffCasePreferenceTopicInputView
    service_periods: StaffCasePreferenceTopicInputView
    rest_schedule: StaffCasePreferenceTopicInputView
    baby_counts: StaffCasePreferenceTopicInputView
    holiday_availability: StaffCasePreferenceTopicInputView
    transportation: StaffCasePreferenceTopicInputView

    def to_domain(self) -> StaffCasePreferenceSnapshot:
        return StaffCasePreferenceSnapshot(
            service_regions=self.service_regions.to_domain(),
            service_periods=self.service_periods.to_domain(),
            rest_schedule=self.rest_schedule.to_domain(),
            baby_counts=self.baby_counts.to_domain(),
            holiday_availability=self.holiday_availability.to_domain(),
            transportation=self.transportation.to_domain(),
        )

    @classmethod
    def from_domain(cls, snapshot: StaffCasePreferenceSnapshot) -> "StaffCasePreferenceSnapshotView":
        return cls(**{
            name: StaffCasePreferenceTopicInputView.from_domain(getattr(snapshot, name))
            for name in (
                "service_regions",
                "service_periods",
                "rest_schedule",
                "baby_counts",
                "holiday_availability",
                "transportation",
            )
        })


class StaffCasePreferencePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int
    before: StaffCasePreferenceSnapshotView
    after: StaffCasePreferenceSnapshotView
    preview_fingerprint: str


class StaffCasePreferenceApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: StaffCasePreferenceSnapshotView
    preview_fingerprint: str


class StaffCasePreferenceApplyReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int
    preview_fingerprint: str
    snapshot: StaffCasePreferenceSnapshotView


__all__ = [
    "StaffCasePreferenceApplyReceiptView",
    "StaffCasePreferenceApplyRequest",
    "StaffCasePreferencePreviewView",
    "StaffCasePreferenceSnapshotView",
    "StaffCasePreferenceSummaryView",
    "StaffCasePreferenceTopicInputView",
    "StaffCasePreferenceTopicView",
]
