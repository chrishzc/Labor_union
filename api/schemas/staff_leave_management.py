"""Typed public views for the Scheduling Staff Leave inbox."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


StaffLeaveStatus = Literal[
    "pending",
    "accepted_for_processing",
    "rejected",
    "cancelled",
    "resolved",
]


class StaffLeaveInboxItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    staff_name: str = Field(min_length=1)
    leave_start_date: date
    leave_end_date: date
    request_reason: str
    request_status: StaffLeaveStatus
    aggregate_version: int = Field(gt=0)


class StaffLeaveReviewReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: int = Field(gt=0)
    status: StaffLeaveStatus
    version: int = Field(gt=0)
    actor: str = Field(min_length=1)
