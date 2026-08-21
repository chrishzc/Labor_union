"""
File: holidays.py
Description: 定義國定假日 Query、Preview、Apply 與 receipt 的封閉 HTTP 契約。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HolidayHorizonView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_date: date
    to_date: date


class HolidayRowView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holiday_date: date
    holiday_name: str = Field(min_length=1, max_length=100)
    is_double_pay_default: bool


class HolidayCalendarView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planning_horizon: HolidayHorizonView
    source_identity: str = Field(min_length=1)
    calendar_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    holidays: list[HolidayRowView]


class HolidayPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["upsert", "delete"]
    holiday_date: date
    holiday_name: str | None = Field(default=None, max_length=100)
    is_double_pay_default: bool = False
    from_date: date | None = None
    to_date: date | None = None

    @field_validator("holiday_name")
    @classmethod
    def normalize_holiday_name(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None

    @model_validator(mode="after")
    def validate_command_and_horizon(self):
        if self.action == "upsert" and self.holiday_name is None:
            raise ValueError("holiday_name_required")
        if (self.from_date is None) != (self.to_date is None):
            raise ValueError("holiday_horizon_pair_required")
        if self.from_date is None:
            self.from_date = self.holiday_date
            self.to_date = self.holiday_date
        if self.from_date > self.to_date:
            raise ValueError("holiday_horizon_invalid")
        if not self.from_date <= self.holiday_date <= self.to_date:
            raise ValueError("holiday_date_outside_horizon")
        return self

    def command_payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "holiday_date": self.holiday_date.isoformat(),
            "holiday_name": self.holiday_name,
            "is_double_pay_default": self.is_double_pay_default,
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
        }


class HolidayApplyRequest(HolidayPreviewRequest):
    expected_calendar_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason_required")
        return normalized


class HolidayPreviewCommandView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["upsert", "delete"]
    holiday_date: date
    holiday_name: str | None
    is_double_pay_default: bool
    from_date: date
    to_date: date
    expected_calendar_version: str = Field(pattern=r"^[0-9a-f]{64}$")


class HolidayPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: HolidayPreviewCommandView
    before: HolidayRowView | None
    planning_horizon: HolidayHorizonView
    source_identity: str
    calendar_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    schedule_impact: Literal["none"]
    payroll_impact: Literal["none"]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HolidayReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_key: str = Field(min_length=1, max_length=191)
    action: Literal["upsert", "delete"]
    holiday_date: date
    changed: bool
    planning_horizon: HolidayHorizonView
    source_identity: str
    previous_calendar_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    resulting_calendar_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
