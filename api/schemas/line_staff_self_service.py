"""File: line_staff_self_service.py
Description: 定義已驗證月嫂 LIFF 查詢與請假申請的傳輸模型。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StaffLiffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_id: str = Field(default="", max_length=191)
    line_id_token: str = Field(default="", max_length=4096)
    development_line_user_id: str = Field(default="", max_length=191)


class StaffOrderSearchRequest(StaffLiffRequest):
    keyword: str = Field(min_length=1, max_length=100)


class StaffOrderView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    client_name: str
    client_phone: str | None = None
    city: str | None = None
    address: str | None = None
    order_status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    service_days: int | None = None
    service_hours_per_day: int | None = None
    due_month: str | None = None
    service_start_date: str | None = None
    service_time: str | None = None
    residence_type: str | None = None
    delivery_type: str | None = None
    service_type: str | None = None
    baby_info: str | None = None
    notes: str | None = None


class StaffOrderPageView(BaseModel):
    staff_id: int
    staff_name: str
    items: list[StaffOrderView]


class StaffScheduleDayView(BaseModel):
    model_config = ConfigDict(extra="ignore")
    work_date: date
    status: Literal[
        "available",
        "working",
        "resting",
        "historical_assignment",
        "waiting_deposit_lock",
        "staff_unavailability",
    ]
    assignment_id: int | None = None
    case_no: str | None = None
    staff_id: int
    client_name: str | None = None
    order_status: str | None = None
    staff_name: str | None = None
    is_work_day: bool
    is_double_pay: bool
    notes: str | None = None
    lock_id: int | None = None
    plan_id: int | None = None
    unavailability_block_id: int | None = None
    unavailability_kind: Literal["long_leave", "paused_service"] | None = None
    unavailability_reason: str | None = None


class StaffScheduleView(BaseModel):
    staff_id: int
    staff_name: str
    year: int
    month: int
    days: list[StaffScheduleDayView]


class StaffLeaveRequestCreate(StaffLiffRequest):
    model_config = ConfigDict(extra="forbid")

    leave_start_date: date
    leave_end_date: date
    leave_reason: str = Field(default="", max_length=1000)


class StaffLeaveRequestCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: int
    status: str
    staff_id: int
    staff_name: str
    version: int


class StaffLeaveRequestApply(StaffLeaveRequestCreate):
    """帶入 Preview 指紋的正式請假 Apply payload。"""

    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffLeaveRequestPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int
    staff_name: str
    leave_start_date: date
    leave_end_date: date
    leave_reason: str
    can_apply: bool
    blockers: list[str]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffLeaveRequestReadbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: int
    status: str
    staff_id: int
    staff_name: str
    leave_start_date: date
    leave_end_date: date
    leave_reason: str
    version: int


class StaffLeaveRequestCancel(StaffLiffRequest):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class StaffServiceDayLogCreate(StaffLiffRequest):
    model_config = ConfigDict(extra="forbid")
    assignment_id: int = Field(gt=0)
    service_date: date
    baby_log_text: str = Field(min_length=1, max_length=5000)
    meal_photo_media_ids: list[str] = Field(default_factory=list, max_length=10)


class StaffServiceDayLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    log_id: int
    case_no: str
    service_date: str
    requires_cooking: bool
    outcome: str


class StaffServiceDayMediaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: str
    content_type: str
    size_bytes: int
    outcome: str
