"""
File: leave_substitution.py
Description: 定義Scheduling請假代班assignment query、command、Preview與receipt嚴格HTTP契約。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas.assignment_plan import AssignmentPlanSegmentView
from domains.scheduling.leave_substitution import (
    LeaveResolutionType,
    LeaveSubstitutionBatchIntent,
    LeaveSubstitutionItem,
)


class LeaveSubstitutionItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_schedule_id: int = Field(gt=0)
    work_date: date
    resolution_type: LeaveResolutionType
    substitute_staff_id: int | None = Field(default=None, gt=0)
    is_double_pay: bool = False

    def to_domain(self) -> LeaveSubstitutionItem:
        return LeaveSubstitutionItem(
            self.original_schedule_id,
            self.work_date,
            self.resolution_type,
            self.substitute_staff_id,
            self.is_double_pay,
        )


class LeaveSubstitutionPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_assignment_id: int = Field(gt=0)
    items: tuple[LeaveSubstitutionItemInput, ...] = ()
    leave_request_id: int | None = Field(default=None, gt=0)
    expected_leave_request_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_complete_linked_request_identity(self):
        if (self.leave_request_id is None) != (
            self.expected_leave_request_version is None
        ):
            raise ValueError("leave_request_identity_pair_required")
        return self

    def to_intent(self) -> LeaveSubstitutionBatchIntent:
        return LeaveSubstitutionBatchIntent(
            self.original_assignment_id,
            tuple(item.to_domain() for item in self.items),
        )


class LeaveSubstitutionApplyBody(LeaveSubstitutionPreviewBody):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    expected_client_finance_version: int = Field(ge=0)
    expected_payroll_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class LeaveSubstitutionOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_index: int = Field(ge=0)
    original_schedule_id: int = Field(gt=0)
    original_assignment_id: int = Field(gt=0)
    original_staff_id: int = Field(gt=0)
    original_work_date: date
    resolution_type: str
    leave_occupancy_date: date
    resulting_service_date: date
    resulting_staff_id: int = Field(gt=0)
    resulting_assignment_key: str
    is_double_pay: bool


class LeaveCalendarDayView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calendar_date: date
    before_kind: str
    after_kind: str
    change_kind: str
    before_staff_id: int | None
    after_staff_id: int | None


class LeaveCalendarCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before_service_day_count: int = Field(ge=0)
    after_service_day_count: int = Field(ge=0)
    before_service_start_date: date | None
    before_service_end_date: date | None
    after_service_start_date: date | None
    after_service_end_date: date | None
    contracted_service_day_count: int = Field(ge=0)
    deferred_day_count: int = Field(ge=0)
    substitute_day_count: int = Field(ge=0)
    leave_day_count: int = Field(ge=0)
    holiday_rest_day_count: int = Field(ge=0)
    fixed_rest_day_count: int = Field(ge=0)
    holiday_version: str = Field(min_length=1)
    holiday_rows: list[tuple[date, str]]
    conservation_status: str
    day_cells: list[LeaveCalendarDayView]


class LeaveApplyReadinessView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    blockers: list[str]


class LeaveOfficialScheduleSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_id: int = Field(gt=0)
    work_date: date


class LeaveAssignmentSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignment_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    assigned_start_date: date
    assigned_end_date: date
    official_schedules: list[LeaveOfficialScheduleSummaryView]


class LeaveImpactSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    resulting_version: int = Field(ge=0)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    blockers: list[str]


class LinkedLeaveRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: int = Field(gt=0)
    expected_version: int = Field(ge=1)
    resolved_version: int | None = Field(default=None, ge=1)
    status: Literal["accepted_for_processing", "resolved"]
    receipt_key: str | None
    notification_intent: Literal["not_requested", "enqueued"]


class LeaveSubstitutionPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    cancelled_assignment_ids: list[int]
    assignments: list[AssignmentPlanSegmentView]
    outcomes: list[LeaveSubstitutionOutcomeView]
    client_finance_impact: LeaveImpactSummaryView
    payroll_impact: LeaveImpactSummaryView
    orders_impact: LeaveImpactSummaryView
    calendar_candidate: LeaveCalendarCandidateView
    apply_readiness: LeaveApplyReadinessView
    linked_request: LinkedLeaveRequestView | None
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class LeaveSubstitutionReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_key: str
    case_no: str
    order_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    outcome_event_ids: list[int]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    linked_request: LinkedLeaveRequestView | None


class StaffPayablesEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_identity: str
    assignment_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    amount_due_ntd: int = Field(gt=0)
    due_date: date | None
    obligation_status: Literal["open", "settled", "cancelled"]
    obligation_payroll_version: int = Field(ge=0)
    obligation_event_id: int = Field(gt=0)
    projection_status: Literal["payable", "completed", "anomaly"] | None
    projection_amount_ntd: int | None = Field(default=None, gt=0)
    projection_net_paid_ntd: int | None = Field(default=None, ge=0)
    projection_balance_ntd: int | None
    projection_version: int | None = Field(default=None, ge=0)
    projection_event_id: int | None = Field(default=None, gt=0)
    blockers: list[str]


class SubstitutionPayablesLineageItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_index: int = Field(ge=0)
    outcome_event_id: int = Field(gt=0)
    original_assignment_id: int = Field(gt=0)
    original_schedule_id: int = Field(gt=0)
    original_staff_id: int = Field(gt=0)
    original_work_date: date
    resolution_type: Literal["defer_following_assignments", "substitute"]
    resulting_assignment_id: int = Field(gt=0)
    resulting_staff_id: int = Field(gt=0)
    resulting_service_date: date
    payroll_event_id: int | None = Field(default=None, gt=0)
    payroll_event_expected_version: int | None = Field(default=None, ge=0)
    payroll_event_resulting_version: int | None = Field(default=None, ge=0)
    payroll_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    payables_evidence: StaffPayablesEvidenceView | None
    lineage_subject: str
    blockers: list[str]


class SubstitutionPayablesLineageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    batch_key: str
    scheduling_receipt_id: int = Field(gt=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    expected_payroll_version: int = Field(ge=0)
    resulting_payroll_version: int = Field(ge=0)
    items: list[SubstitutionPayablesLineageItemView]
    authoritative_complete: bool
    blockers: list[str]
