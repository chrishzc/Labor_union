"""Response and command schemas for persisted runtime health and LINE alerts."""

from datetime import datetime
from pydantic import BaseModel, Field


class RuntimeHealthRecordResponse(BaseModel):
    check_name: str
    component: str
    status: str
    raw_status: str
    message: str
    response_ms: int | None
    consecutive_failures: int
    consecutive_successes: int
    checked_at: datetime
    status_changed_at: datetime


class RuntimeHealthEventResponse(BaseModel):
    event_id: int
    check_name: str
    component: str
    transition_type: str
    before_status: str | None
    resulting_status: str
    message: str
    occurred_at: datetime


class AlertAdminTargetRequest(BaseModel):
    admin_user_id: int = Field(gt=0)
    display_name: str = Field(min_length=1, max_length=191)
    minimum_status: str = Field(pattern="^(warning|critical)$")


class AlertTargetEnabledRequest(BaseModel):
    enabled: bool
