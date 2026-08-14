"""Typed LIFF staff self-service schemas."""

from __future__ import annotations

from datetime import date

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
    status: str
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


class StaffScheduleView(BaseModel):
    staff_id: int
    staff_name: str
    year: int
    month: int
    days: list[StaffScheduleDayView]
