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
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=100)
    category: Literal[
        "webhook_reply", "push", "scheduled_push", "customer_service"
    ]
    message_type: Literal["text", "flex"] = "text"
    enabled: bool = True
    content: str | dict[str, Any]
    variables: list[TemplateVariable] = []
    usage: list[Literal["webhook", "push", "schedule", "customer_service"]] = []

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


class LiffOption(BaseModel):
    value: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)


class LiffNavigationAction(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_-]*$")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    icon: str = Field(default="", max_length=16)
    path: str = Field(min_length=1, max_length=500)
    enabled: bool = True
    order: int = Field(ge=0)

    @model_validator(mode="after")
    def safe_path(self):
        parsed = urlparse(self.path)
        if self.path.startswith("/"):
            return self
        if parsed.scheme not in {"https"} or not parsed.netloc:
            raise ValueError("LIFF action path must be a relative path or HTTPS URL")
        return self


class LiffField(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_-]*$")
    label: str = Field(min_length=1, max_length=100)
    type: Literal[
        "text", "textarea", "phone", "email", "date", "number",
        "single_choice", "multiple_choice", "boolean"
    ]
    required: bool = False
    enabled: bool = True
    order: int = Field(ge=0)
    placeholder: str = Field(default="", max_length=200)
    help_text: str = Field(default="", max_length=500)
    system_field: bool = False
    options: list[LiffOption] = Field(default_factory=list)

    @model_validator(mode="after")
    def choices_require_options(self):
        if self.type in {"single_choice", "multiple_choice"} and not self.options:
            raise ValueError("choice field requires options")
        return self


class LiffPage(BaseModel):
    page_type: Literal["navigation", "bind", "registration"]
    enabled: bool = True
    title: str = Field(min_length=1, max_length=200)
    subtitle: str = Field(default="", max_length=1000)
    submit_button: str = Field(default="送出", max_length=100)
    success_title: str = Field(default="送出成功", max_length=200)
    success_description: str = Field(default="", max_length=2000)
    loading_text: str = Field(default="資料傳送中，請稍候...", max_length=200)
    content: dict[str, str] = Field(default_factory=dict)
    actions: list[LiffNavigationAction] = Field(default_factory=list)
    fields: list[LiffField] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_fields(self):
        ids = [item.id for item in self.fields]
        if len(ids) != len(set(ids)):
            raise ValueError("LIFF field ids must be unique")
        action_ids = [item.id for item in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("LIFF action ids must be unique")
        if self.page_type == "navigation" and not self.actions:
            raise ValueError("navigation page requires at least one action")
        return self


class LiffTheme(BaseModel):
    primary_color: str = Field(default="#4A90E2", pattern=r"^#[0-9A-Fa-f]{6}$")
    primary_hover_color: str = Field(default="#357ABD", pattern=r"^#[0-9A-Fa-f]{6}$")
    background: str = Field(default="#EEF2F7", min_length=1, max_length=200)
    text_color: str = Field(default="#334E68", pattern=r"^#[0-9A-Fa-f]{6}$")
    muted_text_color: str = Field(default="#627D98", pattern=r"^#[0-9A-Fa-f]{6}$")
    font_family: str = Field(default="'Noto Sans TC', sans-serif", min_length=1, max_length=200)

    @model_validator(mode="after")
    def safe_css_values(self):
        forbidden = {";", "{", "}", "<", ">"}
        if any(char in self.background for char in forbidden):
            raise ValueError("background contains unsafe CSS characters")
        if any(char in self.font_family for char in forbidden):
            raise ValueError("font_family contains unsafe CSS characters")
        return self


class LiffSettingsConfig(BaseModel):
    version: int = Field(default=2, ge=2)
    theme: LiffTheme
    pages: dict[str, LiffPage]

    @model_validator(mode="after")
    def validate_page_contracts(self):
        required_pages = {
            "gateway": "navigation",
            "bind": "bind",
            "registration": "registration",
        }
        missing = sorted(set(required_pages) - set(self.pages))
        if missing:
            raise ValueError(f"missing required LIFF pages: {', '.join(missing)}")
        for page_id, page_type in required_pages.items():
            if self.pages[page_id].page_type != page_type:
                raise ValueError(f"{page_id} must use page_type={page_type}")

        required_fields = {
            "bind": {"name": "text", "phone": "phone"},
            "registration": {
                "name": "text",
                "phone": "phone",
                "expected_date": "date",
                "service_days": "number",
                "address": "text",
            },
        }
        for page_id, contract in required_fields.items():
            fields = {field.id: field for field in self.pages[page_id].fields}
            for field_id, field_type in contract.items():
                field = fields.get(field_id)
                if not field:
                    raise ValueError(f"{page_id} is missing system field {field_id}")
                if field.type != field_type or not field.system_field:
                    raise ValueError(f"{page_id}.{field_id} violates the system field contract")
                if not field.enabled or not field.required:
                    raise ValueError(f"{page_id}.{field_id} must remain enabled and required")
        return self


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
