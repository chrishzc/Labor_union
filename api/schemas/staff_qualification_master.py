"""
File: staff_qualification_master.py
Description: 定義 Staff qualification master 的六區段嚴格 GET 回應契約。
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


QualificationAvailability = Literal["available", "unavailable", "unknown", "partial"]
QualificationSectionKind = Literal[
    "skills",
    "cooking",
    "certifications",
    "medical",
    "validity",
    "unavailability",
]


class StaffQualificationFactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=191)
    value: str | bool | None
    detail: str | None = Field(default=None, max_length=200)
    source_identity: str = Field(min_length=1, max_length=191)
    source_version: str | None = Field(default=None, max_length=191)
    valid_from: date | None = None
    valid_until: date | None = None
    availability: QualificationAvailability
    availability_reason: str = Field(min_length=1, max_length=191)


class StaffQualificationSectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: QualificationSectionKind
    owner: str = Field(min_length=1, max_length=191)
    availability: QualificationAvailability
    availability_reason: str = Field(min_length=1, max_length=191)
    source_identity: str | None = Field(default=None, max_length=191)
    source_version: str | None = Field(default=None, max_length=191)
    items: list[StaffQualificationFactView]


class StaffQualificationMasterView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    staff_name: str = Field(min_length=1, max_length=100)
    as_of: date
    overall_availability: QualificationAvailability
    availability_reason: str = Field(min_length=1, max_length=191)
    sections: list[StaffQualificationSectionView]


__all__ = [
    "QualificationAvailability",
    "QualificationSectionKind",
    "StaffQualificationFactView",
    "StaffQualificationMasterView",
    "StaffQualificationSectionView",
]
