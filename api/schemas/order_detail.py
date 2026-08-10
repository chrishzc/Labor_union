"""HTTP projection for a selected Order detail."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class OrderDetailView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    client_id: int = Field(gt=0)
    staff_id: int | None = Field(default=None, gt=0)
    client_name: str
    staff_name: str | None
    order_status: str
    identity_status: str
    cancel_reason: str | None
    line_group_id: str | None
    contract_identity: str | None
    actual_start_date: date | None
    actual_end_date: date | None
    deposit_date: date | None
    start_date: date | None
    end_date: date | None
    service_days: int = Field(ge=0)
    service_hours_per_day: int = Field(ge=0)
    deposit_service_days: int | None = Field(default=None, ge=0)
    floor_fee: int = Field(ge=0)
    custom_rest_dates: str | None


__all__ = ["OrderDetailView"]
