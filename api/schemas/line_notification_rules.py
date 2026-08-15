"""
File: line_notification_rules.py
Description: 定義 LINE 通知規則矩陣、預覽、儲存啟用與刪除 API 的 typed 輸入。
"""

from typing import Any

from pydantic import BaseModel, Field


class PreviewLineNotificationRulesRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    definition: dict[str, Any]


class SaveLineNotificationRulesRequest(PreviewLineNotificationRulesRequest):
    reason: str = Field(min_length=1, max_length=1_000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class DeleteLineNotificationRuleRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1_000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class ApplyLineNotificationManualReplayRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1_000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


__all__ = [
    "DeleteLineNotificationRuleRequest",
    "ApplyLineNotificationManualReplayRequest",
    "PreviewLineNotificationRulesRequest",
    "SaveLineNotificationRulesRequest",
]
