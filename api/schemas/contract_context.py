"""Closed HTTP view for the staff contract context query."""

from __future__ import annotations

from datetime import date, datetime
from typing import Mapping

from pydantic import BaseModel, ConfigDict

from subsystems.contract_integration.contract_context import (
    ContractContextView as ContractContextProjection,
)


DateValue = str | date | datetime | None
NumberValue = int | float | None


class _ContractContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContractOrderContextView(_ContractContextModel):
    case_no: str
    status: str | None
    contract_identity: str | None
    service_days: int | None
    service_hours_per_day: NumberValue
    floor_fee: NumberValue
    start_date: DateValue
    end_date: DateValue
    actual_start_date: DateValue
    actual_end_date: DateValue


class ContractClientContextView(_ContractContextModel):
    id: int
    name: str | None
    phone: str | None
    city: str | None
    address: str | None
    identity_status: str | None
    service_type: str | None
    service_time: str | None
    baby_info: str | None
    notes: str | None


class ContractBeClassContextView(_ContractContextModel):
    query_no: str | None
    survey_details: Mapping[str, object] | str | None
    admin_notes: str | None


class ContractAssignmentContextView(_ContractContextModel):
    assignment_id: int
    case_no: str
    staff_id: int
    assignment_sequence: int | None
    assigned_start_date: DateValue
    assigned_end_date: DateValue
    planned_hours: NumberValue
    actual_hours: NumberValue
    hourly_rate: NumberValue
    floor_fee_allocated: NumberValue
    status: str | None
    replacement_reason: str | None


class ContractStaffContextView(_ContractContextModel):
    id: int
    name: str | None
    identity_card: str | None
    phone: str | None
    email: str | None
    city: str | None
    address: str | None


class ContractContextView(_ContractContextModel):
    order: ContractOrderContextView
    client: ContractClientContextView
    beclass: ContractBeClassContextView
    assignment: ContractAssignmentContextView
    staff: ContractStaffContextView
    unmapped_template_fields: None = None

    @classmethod
    def from_projection(
        cls, projection: ContractContextProjection
    ) -> "ContractContextView":
        return cls(
            order=ContractOrderContextView.model_validate(projection.order, from_attributes=True),
            client=ContractClientContextView.model_validate(projection.client, from_attributes=True),
            beclass=ContractBeClassContextView.model_validate(projection.beclass, from_attributes=True),
            assignment=ContractAssignmentContextView.model_validate(
                projection.assignment, from_attributes=True
            ),
            staff=ContractStaffContextView.model_validate(projection.staff, from_attributes=True),
            unmapped_template_fields=None,
        )


__all__ = [
    "ContractAssignmentContextView",
    "ContractBeClassContextView",
    "ContractClientContextView",
    "ContractContextView",
    "ContractOrderContextView",
    "ContractStaffContextView",
]
