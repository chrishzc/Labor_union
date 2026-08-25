"""
File: order_auto_completion.py
Description: 定義 Orders 服務完成 Preview 與 Apply receipt 的 typed HTTP view。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderAutoCompletionPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    expected_order_version: int = Field(ge=0)
    resulting_order_version: int = Field(ge=1)
    current_status: str
    completion_instant: datetime
    evaluation_at: datetime
    official_service_dates: tuple[str, ...]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class OrderAutoCompletionReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    idempotency_key: str
    order_version: int = Field(ge=1)
    lifecycle_event_id: int = Field(gt=0)
    completion_instant: datetime
    evaluation_at: datetime
    command_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
