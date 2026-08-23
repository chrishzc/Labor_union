"""
File: account_center.py
Description: 定義僅 root 可使用之帳號中心 API 的 typed 傳輸契約。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.admin_auth import AdminPublic


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountCreateRequest(_ClosedModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=100)
    linked_line_user_id: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AccountEnabledRequest(_ClosedModel):
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AccountPasswordResetRequest(_ClosedModel):
    password: str = Field(min_length=12, max_length=256)
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AccountSecurityActionRequest(_ClosedModel):
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AccountCenterUser(AdminPublic):
    enabled: bool = True


class AccountDirectoryItemView(BaseModel):
    """最小帳號清冊查詢投影；不得攜帶角色、能力或個人聯絡資料。"""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    enabled: bool
    is_root: bool
    access_control_version: int = Field(ge=1)


class AccountMutationReceiptView(_ClosedModel):
    operation: Literal[
        "account-create",
        "account-enabled",
        "account-password-reset",
        "account-mfa-reset",
        "account-sessions-revoke",
    ]
    target_account_id: int = Field(gt=0)
    resulting_access_control_version: int = Field(ge=1)
    receipt_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool
    account: AccountDirectoryItemView | None = None
