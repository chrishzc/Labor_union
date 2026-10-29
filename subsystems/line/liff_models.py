"""Validated LIFF configuration shared by owner commands and HTTP presentation."""
from __future__ import annotations
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, Field, model_validator


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
        if "non_citizen_registration" in self.pages:
            if self.pages["non_citizen_registration"].page_type != "registration":
                raise ValueError("non_citizen_registration must use page_type=registration")
            required_fields["non_citizen_registration"] = {
                **required_fields["registration"], **NON_CITIZEN_FIELDS,
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


NON_CITIZEN_FIELDS = {
    "gender": "single_choice", "email": "email", "city": "text", "birth_date": "date",
    "service_start_date": "date", "service_time": "text", "residence_type": "text",
    "delivery_type": "text", "service_type": "text", "baby_info": "textarea",
    "notes": "textarea", "line_id": "text",
    "refund_bank_code": "text", "refund_bank_account": "text",
}


def non_citizen_registration_page(registration: LiffPage) -> LiffPage:
    """Build a new page only for an explicit configuration Apply/bootstrap."""
    page = registration.model_copy(deep=True)
    page.title = "非市民服務申請"
    page.subtitle = "填寫服務需求及退款帳戶，送出後由工會審核。"
    page.success_title = "申請已送出"
    page.success_description = "待工會核准後才建立正式案件並配發案件編號。"
    fields = {field.id: field for field in page.fields}
    labels = {"gender":"性別", "email":"Email", "city":"縣市", "birth_date":"出生日期",
              "service_start_date":"預計服務開始日", "service_time":"服務時間",
              "residence_type":"居住型態", "delivery_type":"生產方式", "service_type":"服務方式",
              "baby_info":"寶寶資訊", "notes":"其他事項（無則填「無」）", "line_id":"LINE ID（未設定填「無」）", "refund_bank_code":"退款銀行與分行代號", "refund_bank_account":"退款帳戶"}
    for index, (name, kind) in enumerate(NON_CITIZEN_FIELDS.items(), start=100):
        previous = fields.get(name)
        fields[name] = LiffField(id=name, label=labels[name], type=kind, required=True, enabled=True,
                                system_field=True, order=previous.order if previous else index,
                                options=[LiffOption(value="女",label="女"), LiffOption(value="男",label="男")] if kind=="single_choice" else [])
    page.fields = sorted(fields.values(), key=lambda field: field.order)
    return page
