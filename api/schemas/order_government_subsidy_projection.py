"""Strict public schema for the Order Workbench Government Subsidy side lane."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from api.schemas.orders_stage_projection import (
    AvailableActionView,
    ProjectionNoticeView,
    SourceLineageView,
)
from subsystems.orders.government_subsidy_projection_query import (
    GovernmentSubsidySubstatusCode,
)


class OrderGovernmentSubsidyProjectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    substatus_code: GovernmentSubsidySubstatusCode
    identity_status: str | None
    source: SourceLineageView
    occurred_at: datetime | None
    blockers: list[ProjectionNoticeView]
    warnings: list[ProjectionNoticeView]
    available_read_actions: list[AvailableActionView]
    claim_batch_id: int | None = Field(default=None, gt=0)
    claim_item_count: int = Field(ge=0)
    claimed_hours: int = Field(ge=0)
    unit_price_ntd: int | None = Field(default=None, ge=0)
    requested_amount_ntd: int = Field(ge=0)
    approved_amount_ntd: int = Field(ge=0)
    net_allocated_ntd: int = Field(ge=0)
    overpayment_identity: str | None
    overpayment_remaining_ntd: int | None = Field(default=None, ge=0)


class GovernmentSubsidySubstatusCountsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_lineage_missing: int = Field(ge=0)
    draft: int = Field(ge=0)
    submitted: int = Field(ge=0)
    approved: int = Field(ge=0)
    partially_paid: int = Field(ge=0)
    paid: int = Field(ge=0)
    pending_review: int = Field(ge=0)
    offset_reserved: int = Field(ge=0)
    offset_applied: int = Field(ge=0)
    return_payable: int = Field(ge=0)
    partially_returned: int = Field(ge=0)
    returned: int = Field(ge=0)


class OrderGovernmentSubsidyProjectionPageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderGovernmentSubsidyProjectionView]
    substatus_counts: GovernmentSubsidySubstatusCountsView
    next_cursor: str | None
    etag: str = Field(pattern=r"^[0-9a-f]{64}$")


__all__ = ["OrderGovernmentSubsidyProjectionPageView"]
