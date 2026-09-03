"""HTTP schemas for the bounded Staff case-preference Preview -> Apply command."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from subsystems.staff.case_preference_summary_command import (
    PreferenceTopicDraft,
    StaffCasePreferencePreview,
    StaffCasePreferenceReceipt,
    StaffCasePreferenceSnapshot,
)


class StaffCasePreferenceTopicInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str]
    other_detail: str | None = None

    def to_domain(self) -> PreferenceTopicDraft:
        return PreferenceTopicDraft(tuple(self.values), self.other_detail)

    @classmethod
    def from_domain(cls, topic: PreferenceTopicDraft) -> "StaffCasePreferenceTopicInput":
        return cls(values=list(topic.values), other_detail=topic.other_detail)


class StaffCasePreferenceSnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_regions: StaffCasePreferenceTopicInput
    service_periods: StaffCasePreferenceTopicInput
    rest_schedule: StaffCasePreferenceTopicInput
    baby_counts: StaffCasePreferenceTopicInput
    holiday_availability: StaffCasePreferenceTopicInput
    transportation: StaffCasePreferenceTopicInput

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
    def from_domain(cls, snapshot: StaffCasePreferenceSnapshot) -> "StaffCasePreferenceSnapshotInput":
        return cls(
            service_regions=StaffCasePreferenceTopicInput.from_domain(snapshot.service_regions),
            service_periods=StaffCasePreferenceTopicInput.from_domain(snapshot.service_periods),
            rest_schedule=StaffCasePreferenceTopicInput.from_domain(snapshot.rest_schedule),
            baby_counts=StaffCasePreferenceTopicInput.from_domain(snapshot.baby_counts),
            holiday_availability=StaffCasePreferenceTopicInput.from_domain(snapshot.holiday_availability),
            transportation=StaffCasePreferenceTopicInput.from_domain(snapshot.transportation),
        )


class StaffCasePreferencePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: StaffCasePreferenceSnapshotInput


class StaffCasePreferenceApplyRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: StaffCasePreferenceSnapshotInput
    expected_fingerprint: str = Field(min_length=64, max_length=64)
    preview_fingerprint: str = Field(min_length=64, max_length=64)


class StaffCasePreferencePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int
    expected_fingerprint: str
    preview_fingerprint: str
    changed_topics: list[str]
    snapshot: StaffCasePreferenceSnapshotInput

    @classmethod
    def from_domain(cls, preview: StaffCasePreferencePreview) -> "StaffCasePreferencePreviewView":
        return cls(
            staff_id=preview.staff_id,
            expected_fingerprint=preview.expected_fingerprint,
            preview_fingerprint=preview.preview_fingerprint,
            changed_topics=list(preview.changed_topics),
            snapshot=StaffCasePreferenceSnapshotInput.from_domain(preview.snapshot),
        )


class StaffCasePreferenceReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int
    outcome: Literal["applied", "already_observed"]
    snapshot_fingerprint: str
    changed_topics: list[str]

    @classmethod
    def from_domain(cls, receipt: StaffCasePreferenceReceipt) -> "StaffCasePreferenceReceiptView":
        return cls(
            staff_id=receipt.staff_id,
            outcome=receipt.outcome,
            snapshot_fingerprint=receipt.snapshot_fingerprint,
            changed_topics=list(receipt.changed_topics),
        )


__all__ = [
    "StaffCasePreferenceApplyRequestView",
    "StaffCasePreferencePreviewRequest",
    "StaffCasePreferencePreviewView",
    "StaffCasePreferenceReceiptView",
    "StaffCasePreferenceSnapshotInput",
    "StaffCasePreferenceTopicInput",
]
