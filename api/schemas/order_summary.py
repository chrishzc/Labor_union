"""
File: order_summary.py
Description: 定義訂單摘要 HTTP 讀模型，允許待補件案件的衍生欄位為空。
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class OrderSummaryItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    client_name: str
    order_status: str
    staff_name: str | None
    identity_status: str | None
    start_date: date | None
    end_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    service_days: int | None = Field(default=None, gt=0)
    total_employer_self_pay_payable: int | None = Field(default=None, ge=0)


class OrderSummaryPageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderSummaryItemView]
    next_cursor: str | None
    etag: str = Field(pattern=r"^[0-9a-f]{64}$")


__all__ = [
    "OrderSummaryItemView",
    "OrderSummaryPageView",
]
