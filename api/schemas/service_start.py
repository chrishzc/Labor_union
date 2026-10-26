"""Typed service-start and substitute transports. Identity is always server verified."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from api.schemas.line_staff_self_service import StaffLiffRequest


class StaffServiceStartSubmission(StaffLiffRequest):
    model_config = ConfigDict(extra='forbid')
    case_no: str = Field(min_length=1,max_length=50)
    segment_id: int | None = Field(default=None,gt=0)
    assignment_id: int | None = Field(default=None,gt=0)
    decision: Literal['accepted','declined']
    start_date: date | None = None
    expected_order_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1,max_length=140)


class ServiceStartCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1,max_length=140)


class ServiceStartInquiry(ServiceStartCommand):
    staff_id: int = Field(gt=0)
    start_date: date
    end_date: date


class LeaveDateChangeBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    original_date: date
    new_date: date | None = None


class ServiceStartDates(ServiceStartCommand):
    start_date: date
    date_changes: list[LeaveDateChangeBody] | None = None


class StaffLeaveResultSubmission(StaffLiffRequest):
    model_config = ConfigDict(extra='forbid')
    case_no: str = Field(min_length=1, max_length=50)
    assignment_id: int = Field(gt=0)
    decision: Literal['defer', 'substitute']
    dates: list[LeaveDateChangeBody] = Field(min_length=1, max_length=366)
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=140)


class LeaveDeferDates(ServiceStartCommand):
    dates: list[LeaveDateChangeBody] = Field(min_length=1, max_length=366)


class ServiceStartView(BaseModel):
    request_id: int
    case_no: str
    staff_id: int
    staff_name: str
    segment_id: int | None
    order_version: int
    version: int
    status: Literal['awaiting_peers','substitute_required','applied']
    requested_start_date: str | None
    selected_staff_id: int | None
    selected_staff_name: str | None
    willingness: Literal['pending','willing','unwilling'] | None
    invitation_status: str | None
    joined: bool
    result: dict | None
    proposed_start_date: str | None
    proposed_end_date: str | None
    workflow_kind: Literal['service_start', 'leave', 'handover'] = 'service_start'
    leave_dates: list[LeaveDateChangeBody] = Field(default_factory=list)
    conflict_message: str | None = None
    handover_dates: list[str] = Field(default_factory=list)


class HandoverContext(BaseModel):
    case_no: str
    assignment_id: int
    staff_id: int
    staff_name: str
    order_version: int
    scheduling_version: int
    service_dates: list[str]
    request: ServiceStartView | None = None


class HandoverInquiry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_no: str = Field(min_length=1,max_length=50)
    assignment_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1,max_length=140)


class ServiceStartPage(BaseModel):
    items: list[ServiceStartView]
    total: int
    page: int
    page_size: int


class ServiceStartStaffOption(BaseModel):
    staff_id: int
    name: str
