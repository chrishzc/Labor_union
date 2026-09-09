"""Strict transport schemas for customer order-change LIFF intake."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OrderChangeKind = Literal[
    "service_address",
    "cooking_requirement",
    "service_days",
    "daily_service_window",
    "other",
]


class LineOrderChangeIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    line_id_token: str = Field(min_length=1, max_length=4096)


class LineOrderChangePreviewRequest(LineOrderChangeIdentityRequest):
    case_no: str = Field(min_length=1, max_length=50)
    expected_order_version: int = Field(ge=0)
    kind: OrderChangeKind
    requested: dict[str, str] = Field(min_length=1, max_length=5)


class LineOrderChangeApplyRequest(LineOrderChangePreviewRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=150)


class LineOrderChangeOrderView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_no: str
    status: str
    order_version: int = Field(ge=0)
    values: dict[str, str]


class LineOrderChangeOrderListView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: list[LineOrderChangeOrderView]


class LineOrderChangePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_no: str
    status: str
    order_version: int = Field(ge=0)
    kind: OrderChangeKind
    before: dict[str, str]
    requested: dict[str, str]
    impact_note: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class LineOrderChangeReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ticket_id: int = Field(gt=0)
    ticket_status: Literal["waiting", "handling", "resolved"]
    case_no: str
    kind: OrderChangeKind
    idempotency_key: str
    replayed: bool


__all__ = [
    "LineOrderChangeApplyRequest",
    "LineOrderChangeIdentityRequest",
    "LineOrderChangeOrderListView",
    "LineOrderChangeOrderView",
    "LineOrderChangePreviewRequest",
    "LineOrderChangePreviewView",
    "LineOrderChangeReceiptView",
]
