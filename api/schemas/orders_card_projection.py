"""
File: orders_card_projection.py
Description: 定義 Orders 卡片 composite projection 的 typed HTTP view。
"""

from __future__ import annotations

from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict


T = TypeVar("T")
Availability = Literal["available", "unavailable", "blocked"]


class OrdersCardProjectionFieldView(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    value: T | None
    owner: str
    source_identity: str
    source_version: str | None
    availability: Availability
    availability_reason: str | None


class OrdersCardAssignmentSegmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: OrdersCardProjectionFieldView[int]
    staff_id: OrdersCardProjectionFieldView[int]
    staff_name: OrdersCardProjectionFieldView[str]
    sequence: OrdersCardProjectionFieldView[int]
    assigned_start_date: OrdersCardProjectionFieldView[date]
    assigned_end_date: OrdersCardProjectionFieldView[date]
    status: OrdersCardProjectionFieldView[str]


class OrdersCardProjectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    contact_phone: OrdersCardProjectionFieldView[str]
    contact_address: OrdersCardProjectionFieldView[str]
    requires_cooking: OrdersCardProjectionFieldView[bool]
    floor_fee_ntd: OrdersCardProjectionFieldView[int]
    deposit_amount_ntd: OrdersCardProjectionFieldView[int]
    deposit_settlement_state: OrdersCardProjectionFieldView[
        Literal["unsettled", "settled"]
    ]
    deposit_settled_on: OrdersCardProjectionFieldView[date]
    actual_start_date: OrdersCardProjectionFieldView[date]
    actual_end_date: OrdersCardProjectionFieldView[date]
    historical_source_start_date: OrdersCardProjectionFieldView[date]
    historical_source_end_date: OrdersCardProjectionFieldView[date]
    historical_paired_staff_name: OrdersCardProjectionFieldView[str]
    assignment_segments: OrdersCardProjectionFieldView[
        list[OrdersCardAssignmentSegmentView]
    ]


__all__ = [
    "Availability",
    "OrdersCardAssignmentSegmentView",
    "OrdersCardProjectionFieldView",
    "OrdersCardProjectionView",
]
