"""
File: line_configurations.py
Description: 定義 LINE 設定 mutation 輸入與封閉去敏的安全查詢輸出。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from domains.line.configuration import LineConfigurationKind
from subsystems.line.configuration_contracts import LineConfigurationSafeState


class PreviewLineConfigurationRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    definition: dict[str, Any]


class ApplyLineConfigurationRequest(PreviewLineConfigurationRequest):
    reason: str = Field(min_length=1, max_length=1_000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class _StrictPublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LineConfigurationSafePublicView(_StrictPublicModel):
    kind: LineConfigurationKind = Field(strict=False)
    revision: StrictInt = Field(ge=0)
    state: LineConfigurationSafeState = Field(strict=False)


class LineConfigurationSafeResponse(_StrictPublicModel):
    success: Literal[True] = True
    message: Literal["Success"] = "Success"
    data: LineConfigurationSafePublicView
    error: None = None


__all__ = [
    "ApplyLineConfigurationRequest",
    "LineConfigurationSafePublicView",
    "LineConfigurationSafeResponse",
    "PreviewLineConfigurationRequest",
]
