"""Typed HTTP views for Form Management read-only template facts."""

from pydantic import BaseModel, ConfigDict, Field


class _View(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FormManagementStatisticsView(_View):
    global_active_orders_count: int = Field(ge=0)
    global_active_staff_count: int = Field(ge=0)
    global_subsidy_orders_count: int = Field(ge=0)
    global_total_receivable_sum: int = Field(ge=0)
    global_govt_claim_count: int = Field(ge=0)


class FormManagementCaseContextView(_View):
    case_no: str
    service_time: str | None
    service_type: str | None
    delivery_type: str | None
    residence_type: str | None
    city: str | None
    identity_status: str | None


__all__ = [
    "FormManagementCaseContextView",
    "FormManagementStatisticsView",
]
