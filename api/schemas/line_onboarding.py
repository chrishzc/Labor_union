"""
File: line_onboarding.py
Description: 定義 LINE Onboarding 歡迎訊息的資料合約與請求／回應 Schema。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LineOnboardingView(_StrictModel):
    template_id: str = "customer_onboarding_welcome"
    content: str
    revision: StrictInt = Field(ge=0)
    sample_preview: str
    variables: list[str] = Field(default_factory=lambda: ["url"])


class PreviewLineOnboardingRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class PreviewLineOnboardingView(_StrictModel):
    sample_preview: str
    variables: list[str]


class UpdateLineOnboardingRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    expected_revision: int = Field(ge=0)
    reason: str = Field(default="更新新好友歡迎訊息", min_length=1, max_length=200)


__all__ = [
    "LineOnboardingView",
    "PreviewLineOnboardingRequest",
    "PreviewLineOnboardingView",
    "UpdateLineOnboardingRequest",
]
