"""Validated schemas for editable LINE/LIFF JSON configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
        ids = [item.id for item in self.schedules]
        if len(ids) != len(set(ids)):
            raise ValueError("message schedule ids must be unique")
        for schedule in self.schedules:
            days = [step.day for step in schedule.steps]
            if len(days) != len(set(days)):
                raise ValueError(f"schedule {schedule.id} contains duplicate days")
        return self


class MenuBounds(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class MenuAction(BaseModel):
    type: Literal["message", "uri", "postback"]
    text: str | None = None
    uri: str | None = None
    uri_source: Literal["literal", "liff"] = "literal"
    data: str | None = None

    @model_validator(mode="after")
    def validate_action_value(self):
        if self.type == "message" and not self.text:
            raise ValueError("message action requires text")
        if self.type == "uri" and self.uri_source == "literal" and not self.uri:
            raise ValueError("literal uri action requires uri")
        if self.type == "postback" and not self.data:
            raise ValueError("postback action requires data")
        return self


class RichMenuButton(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=30)
    text_color: str = "#FFFFFF"
    background_color: str = "#4A90E2"
    bounds: MenuBounds
    action: MenuAction


class RichMenuSize(BaseModel):
    width: Literal[2500] = 2500
    height: Literal[843, 1686] = 843


class RichMenuAppearance(BaseModel):
    background_color: str = "#F5F5F5"
    image_mode: Literal["generated", "uploaded"] = "generated"
    image_path: str | None = None


class RichMenuDefinition(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=300)
    enabled: bool = True
    selected: bool = True
    set_as_default: bool = False
    chat_bar_text: str = Field(min_length=1, max_length=14)
    size: RichMenuSize = RichMenuSize()
    appearance: RichMenuAppearance = RichMenuAppearance()
    buttons: list[RichMenuButton] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_buttons(self):
        ids = [button.id for button in self.buttons]
        if len(ids) != len(set(ids)):
            raise ValueError("rich menu button ids must be unique")
        for button in self.buttons:
            if button.bounds.x + button.bounds.width > self.size.width:
                raise ValueError(f"button {button.id} exceeds menu width")
            if button.bounds.y + button.bounds.height > self.size.height:
                raise ValueError(f"button {button.id} exceeds menu height")
        return self


class LineMenusConfig(BaseModel):
    version: int = Field(default=1, ge=1)
    menus: list[RichMenuDefinition]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [item.id for item in self.menus]
        if len(ids) != len(set(ids)):
            raise ValueError("rich menu ids must be unique")
        return self


class LiffOption(BaseModel):
    value: str
    label: str


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
    placeholder: str = ""
    help_text: str = ""
    system_field: bool = False
    options: list[LiffOption] = []

    @model_validator(mode="after")
    def choices_require_options(self):
        if self.type in {"single_choice", "multiple_choice"} and not self.options:
            raise ValueError("choice field requires options")
        return self


class LiffPage(BaseModel):
    title: str
    subtitle: str = ""
    submit_button: str = "送出"
    success_title: str = "送出成功"
    success_description: str = ""
    loading_text: str = "資料傳送中，請稍候..."
    fields: list[LiffField]

    @model_validator(mode="after")
    def unique_fields(self):
        ids = [item.id for item in self.fields]
        if len(ids) != len(set(ids)):
            raise ValueError("LIFF field ids must be unique")
        return self


class LiffTheme(BaseModel):
    primary_color: str = "#4A90E2"
    primary_hover_color: str = "#357ABD"
    background: str = "#EEF2F7"
    text_color: str = "#334E68"
    muted_text_color: str = "#627D98"
    font_family: str = "'Noto Sans TC', sans-serif"


class LiffSettingsConfig(BaseModel):
    version: int = Field(default=1, ge=1)
    theme: LiffTheme
    pages: dict[str, LiffPage]


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
