"""
File: admin_audit.py
Description: 定義管理員稽核的原始內部模型與 React 遮罩查詢契約。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AdminAuditMaskedItemView(BaseModel):
    """React 可讀的遮罩稽核列；不允許 raw details 或 request metadata 穿透。"""

    model_config = ConfigDict(extra="forbid")

    audit_id: int = Field(gt=0)
    occurred_at: datetime
    actor_label_masked: str | None = Field(default=None, max_length=100)
    action_family: Literal[
        "authentication",
        "account_security",
        "session",
        "mfa",
        "system",
        "other",
    ]
    target_label_masked: str | None = Field(default=None, max_length=191)
    ip_address_masked: str | None = Field(default=None, max_length=64)
    outcome: Literal["success", "denied", "failed", "unknown"]
    reason_code: str | None = Field(
        default=None,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )


class AdminAuditDetailFieldView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Literal["reason", "mfa_method", "account", "enabled", "source", "subject"]
    value_masked: str = Field(min_length=1, max_length=191)


class AdminAuditMaskedDetailView(AdminAuditMaskedItemView):
    details: list[AdminAuditDetailFieldView]


class AdminAuditMaskedPageView(BaseModel):
    """React 稽核分頁的閉合伺服器投影。"""

    model_config = ConfigDict(extra="forbid")

    items: list[AdminAuditMaskedItemView]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=1)
