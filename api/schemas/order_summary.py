"""Typed HTTP views for the bounded Orders summary query."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class OrderSummaryItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    client_name: str
    order_status: str
    staff_name: str | None
    identity_status: str | None
    start_date: date
    end_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    service_days: int = Field(gt=0)
    total_employer_self_pay_payable: int = Field(ge=0)


class OrderSummaryPageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderSummaryItemView]
    next_cursor: str | None
    etag: str = Field(pattern=r"^[0-9a-f]{64}$")


__all__ = [
    "OrderSummaryItemView",
    "OrderSummaryPageView",
]
