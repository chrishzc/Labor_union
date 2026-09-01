"""Strict HTTP contract for historical per-caregiver service-day accounting."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class HistoricalCaregiverDaysBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    assignment_identity: str = Field(min_length=1, max_length=191)
    staff_id: StrictInt = Field(gt=0)
    actual_service_days: StrictInt = Field(gt=0)


class HistoricalServiceAccountingPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    caregivers: list[HistoricalCaregiverDaysBody] = Field(min_length=1, max_length=20)


class HistoricalServiceAccountingApplyBody(HistoricalServiceAccountingPreviewBody):
    expected_lifecycle_version: StrictInt = Field(ge=0)
    expected_historical_day_revision: StrictInt = Field(ge=0)
    expected_client_finance_version: StrictInt = Field(ge=0)
    expected_payroll_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class HistoricalServiceAccountingAssignmentView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    assignment_identity: str
    staff_id: int
    staff_name: str
    policy_version: str
    policy_kind: str
    hourly_rate_ntd: int


class HistoricalServiceAccountingQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str
    lifecycle_status: str
    lifecycle_version: int
    adoption_receipt_id: int
    adoption_source_identity: str
    historical_day_revision: int
    client_finance_version: int
    payroll_version: int
    contracted_service_days: int
    service_hours_per_day: int
    contractual_floor_fee_ntd: int
    client_identity_status: str
    assignments: list[HistoricalServiceAccountingAssignmentView]


class HistoricalServiceDaysAllocationView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    assignment_identity: str
    staff_id: int
    actual_service_days: int
    actual_service_hours: str
    floor_fee_ntd: int


class HistoricalPayrollAssignmentView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    assignment_identity: str
    staff_id: int
    actual_service_days: int
    actual_hours: int
    double_pay_hours: int
    hourly_rate_ntd: int
    service_salary_ntd: int
    floor_fee_allocated_ntd: int
    effective_adjustments_ntd: int
    total_payable_ntd: int


class HistoricalServiceAccountingPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    facts: HistoricalServiceAccountingQueryView
    total_actual_service_days: int
    total_actual_service_hours: str
    historical_floor_fee_ntd: int
    historical_double_pay_days: int
    historical_double_pay_hours: str
    allocations: list[HistoricalServiceDaysAllocationView]
    payroll_assignments: list[HistoricalPayrollAssignmentView]
    staff_obligation_amount_ntd: int
    client_obligation_amount_ntd: int
    client_service_receivable_ntd: int
    client_subsidy_hours: int
    client_self_pay_service_hours: int
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalServiceAccountingReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str
    resulting_historical_day_revision: int
    resulting_client_finance_version: int
    resulting_payroll_version: int
    total_actual_service_days: int
    client_obligation_amount_ntd: int
    staff_obligation_amount_ntd: int
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool


class HistoricalPrecisionRestartPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HistoricalPrecisionRestartApplyBody(HistoricalPrecisionRestartPreviewBody):
    expected_order_version: StrictInt = Field(ge=0)
    expected_scheduling_version: StrictInt = Field(ge=0)
    expected_historical_day_revision: StrictInt = Field(ge=0)
    expected_confirmed_service_date_version: StrictInt | None = Field(default=None, ge=1)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class HistoricalPrecisionRestartQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str
    lifecycle_status: str
    order_version: int
    scheduling_version: int
    client_finance_version: int
    payroll_version: int
    historical_day_revision: int
    confirmed_service_date_version: int | None
    planned_start_date: date
    actual_start_date: date | None
    contracted_service_days: int
    assignments: list[dict]
    blockers: list[str]


class HistoricalPrecisionRestartPreviewView(HistoricalPrecisionRestartQueryView):
    target_status: str
    actual_end_date: date | None
    official_service_dates: list[date] = Field(max_length=0)
    client_finance_resulting_version: int
    payroll_resulting_version: int
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalPrecisionRestartReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str
    lifecycle_status: str
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int
    payroll_version: int
    historical_day_revision: int
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool


__all__ = [name for name in globals() if name.startswith("Historical")]
