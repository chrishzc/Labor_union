"""Typed HTTP view for the Orders service auto-completion receipt."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderAutoCompletionReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    idempotency_key: str
    order_version: int = Field(ge=1)
    lifecycle_event_id: int = Field(gt=0)
    completion_instant: datetime
    evaluation_at: datetime
    command_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
