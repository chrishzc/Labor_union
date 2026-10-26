"""
================================================================================
檔案名稱: api/schemas/line_config.py
功能說明: LINE 訊息、排程、下方選單與 LIFF 設定的資料格式及安全驗證規則
================================================================================
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

from subsystems.line.rich_menu_models import (
    LineMenusConfig,
    MenuAction,
    MenuBounds,
    RichMenuAppearance,
    RichMenuButton,
    RichMenuDefinition,
    RichMenuSize,
)


class TemplateVariable(BaseModel):
    name: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    required: bool = True
    description: str = ""


class MessageTemplate(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=100)
    category: Literal[
        "webhook_reply", "push", "scheduled_push", "customer_service",
        "task96_baseline", "leave_coordination", "matching_result", "runtime_alert", "service_day", "order_lifecycle"
    ]
    message_type: Literal["text", "flex"] = "text"
    enabled: bool = True
    content: str | dict[str, Any]
    variables: list[TemplateVariable] = []
    usage: list[Literal["webhook", "push", "schedule", "customer_service", "task96_baseline", "leave_coordination", "matching_result", "runtime_alert", "service_day", "order_lifecycle", "notification"]] = []

    @model_validator(mode="after")
    def validate_content_type(self):
        if self.message_type == "text" and not isinstance(self.content, str):
            raise ValueError("text template content must be a string")
        if self.message_type == "flex" and not isinstance(self.content, dict):
            raise ValueError("flex template content must be an object")
        return self


class MessageTemplatesConfig(BaseModel):
    version: int = Field(default=1, ge=1)
    templates: list[MessageTemplate]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [item.id for item in self.templates]
        if len(ids) != len(set(ids)):
            raise ValueError("message template ids must be unique")
        return self


class MessageTemplatePreviewRequest(BaseModel):
    variables: dict[str, str] = {}


class MessageTemplateDraftPreviewRequest(BaseModel):
    template: MessageTemplate
    variables: dict[str, str] = {}


class MessageScheduleStep(BaseModel):
    day: int = Field(ge=0, le=365)
    send_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    template_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")


class MessageSchedule(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    trigger: Literal["follow"] = "follow"
    restart_on_refollow: bool = False
    steps: list[MessageScheduleStep] = Field(min_length=1)


class MessageSchedulesConfig(BaseModel):
    version: int = Field(default=1, ge=1)
    timezone: str = Field(min_length=1)
    schedules: list[MessageSchedule]

    @model_validator(mode="after")
    def unique_ids(self):
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {self.timezone}") from exc
        ids = [item.id for item in self.schedules]
        if len(ids) != len(set(ids)):
            raise ValueError("message schedule ids must be unique")
        for schedule in self.schedules:
            days = [step.day for step in schedule.steps]
            if len(days) != len(set(days)):
                raise ValueError(f"schedule {schedule.id} contains duplicate days")
        return self


from subsystems.line.liff_models import (
    LiffOption, LiffNavigationAction, LiffField, LiffPage, LiffTheme, LiffSettingsConfig,
)


class ServiceStatus(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    label: str
    color: str


class BusinessHours(BaseModel):
    timezone: str = "Asia/Taipei"
    weekdays: dict[str, dict[str, str]]


class CustomerServiceSettings(BaseModel):
    business_hours: BusinessHours
    auto_assign: bool = False
    idle_timeout_minutes: int = Field(default=30, ge=1)


class CustomerServiceConfig(BaseModel):
    version: int = Field(default=1, ge=1)
    settings: CustomerServiceSettings
    statuses: list[ServiceStatus]
    default_messages: dict[str, str]
