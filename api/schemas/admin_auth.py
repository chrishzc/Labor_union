"""
File: admin_auth.py
Description: 定義管理後台登入、Session 與 root 身分的公開傳輸契約。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, min_length=6, max_length=32)


class AdminPasswordChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class AdminPasswordChallengeResponse(BaseModel):
    challenge_type: Literal["factor_verification", "mfa_enrollment"]
    challenge_id: str
    challenge_token: str
    expires_at: datetime
    provisioning_uri: str | None = None

    @model_validator(mode="after")
    def validate_challenge_payload(self):
        if self.challenge_type == "mfa_enrollment":
            if not self.provisioning_uri or not self.provisioning_uri.startswith(
                "otpauth://totp/"
            ):
                raise ValueError("mfa_enrollment requires a TOTP provisioning URI")
        elif self.provisioning_uri is not None:
            raise ValueError("factor_verification must not include a provisioning URI")
        return self


class AdminFactorVerificationRequest(BaseModel):
    challenge_token: str = Field(min_length=32, max_length=256)
    factor_code: str = Field(min_length=6, max_length=32)


class AdminPublic(BaseModel):
    id: int | None
    username: str
    display_name: str
    role: str
    linked_line_user_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    is_root: bool = False
    access_control_version: int = 1


class AdminSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    admin: AdminPublic


class AdminRefreshResponse(BaseModel):
    expires_at: datetime


class AdminLogoutResponse(BaseModel):
    """Closed success result for revoking the current administrator session."""

    model_config = ConfigDict(extra="forbid", strict=True)

    logged_out: Literal[True]


class MfaEnrollmentVerificationRequest(BaseModel):
    challenge_token: str = Field(min_length=32, max_length=256)
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class MfaEnrollmentVerificationResponse(BaseModel):
    recovery_codes: list[str]
