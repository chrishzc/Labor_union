"""
File: account_center.py
Description: 定義僅 root 可使用之帳號中心 API 的 typed 傳輸契約。
"""

from pydantic import BaseModel, Field

from api.schemas.admin_auth import AdminPublic


class AccountCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=100)
    linked_line_user_id: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AccountEnabledRequest(BaseModel):
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AccountPasswordResetRequest(BaseModel):
    password: str = Field(min_length=12, max_length=256)
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AccountSecurityActionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AccountCenterUser(AdminPublic):
    enabled: bool = True
