"""Strict HTTP contract for Staff's six-relation manual QPA."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


RelationKey = Literal[
    "service_regions",
    "service_periods",
    "cooking_skills",
    "holiday_availability",
    "rest_schedule",
    "baby_types",
]


class RelationValueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=50)
    detail: str | None = Field(default=None, max_length=100)


class RelationsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_regions: list[RelationValueBody]
    service_periods: list[RelationValueBody]
    cooking_skills: list[RelationValueBody]
    holiday_availability: list[RelationValueBody]
    rest_schedule: list[RelationValueBody]
    baby_types: list[RelationValueBody]

    def as_relations(self) -> dict[str, list[dict[str, object]]]:
        return {
            key: [item.model_dump() for item in getattr(self, key)]
            for key in (
                "service_regions",
                "service_periods",
                "cooking_skills",
                "holiday_availability",
                "rest_schedule",
                "baby_types",
            )
        }


class ManualApplyBody(RelationsBody):
    expected_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ManualRelationView(RelationValueBody):
    pass


class ManualSnapshotView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    before: dict[RelationKey, list[ManualRelationView]]
    after: dict[RelationKey, list[ManualRelationView]]
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ManualReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    relations: dict[RelationKey, list[ManualRelationView]]
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    replayed: bool


__all__ = ["ManualApplyBody", "ManualReceiptView", "ManualSnapshotView", "RelationValueBody", "RelationsBody"]
