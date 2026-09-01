"""Typed HTTP views for staff order-information Query/Preview."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class OrderInformationFieldView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str
    label: str
    owner: str
    source: str | None
    requiredness: str
    status: str
    value: str | int | float | Decimal | date | datetime | None


class OrderInformationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    case_no: str
    assignment_id: int = Field(ge=1)
    fields: list[OrderInformationFieldView]
    owner_fingerprints: dict[str, str]
    blockers: list[str]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    can_render: bool


__all__ = ["OrderInformationFieldView", "OrderInformationView"]
