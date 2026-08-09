"""Typed HTTP view for selected Orders calendar terms."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class OrderCalendarDetailView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    service_mode: Literal["週休1日", "週休2日", "連續服務"]


__all__ = ["OrderCalendarDetailView"]
