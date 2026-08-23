"""
File: scheduling_eligibility_collision.py
Description: 定義 Scheduling eligibility、collision 與 coverage 的 strict HTTP view。
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from subsystems.scheduling.eligibility_collision_query import (
    AvailabilityState,
    CollisionKind,
    CollisionSeverity,
    CoverageState,
    EligibilityState,
    QualificationCheckState,
)


class SchedulingQualificationCheckView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    status: QualificationCheckState
    owner: str = Field(min_length=1, max_length=191)
    source_identity: str = Field(min_length=1, max_length=191)
    source_version: int | None = Field(default=None, ge=0)
    detail: str = Field(min_length=1, max_length=500)


class SchedulingCollisionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CollisionKind
    severity: CollisionSeverity
    staff_id: int = Field(gt=0)
    case_no: str | None = Field(default=None, min_length=1, max_length=50)
    assignment_id: int | None = Field(default=None, gt=0)
    source_id: int | None = Field(default=None, gt=0)
    collision_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    owner: str = Field(min_length=1, max_length=191)
    source_identity: str = Field(min_length=1, max_length=191)
    detail: str = Field(min_length=1, max_length=500)


class SchedulingCoverageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date | None = None
    end_date: date | None = None
    required_day_count: int | None = Field(default=None, ge=0)
    available_day_count: int | None = Field(default=None, ge=0)
    missing_dates: list[date]
    review_dates: list[date]
    status: CoverageState


class SchedulingStaffEligibilityCollisionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    eligibility: EligibilityState
    availability: AvailabilityState
    qualification_checks: list[SchedulingQualificationCheckView]
    collisions: list[SchedulingCollisionView]
    coverage: SchedulingCoverageView
    partial_data: list[str]


class SchedulingEligibilityCollisionProjectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str = Field(min_length=1, max_length=50)
    case_status: str = Field(min_length=1, max_length=50)
    as_of: date
    evaluated_at: datetime
    scheduling_version: int | None = Field(default=None, ge=0)
    staff: list[SchedulingStaffEligibilityCollisionView]
    partial_data: list[str]


class SchedulingEligibilityCollisionTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, object]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "SchedulingCollisionView",
    "SchedulingCoverageView",
    "SchedulingEligibilityCollisionProjectionView",
    "SchedulingEligibilityCollisionTypedErrorView",
    "SchedulingQualificationCheckView",
    "SchedulingStaffEligibilityCollisionView",
]
