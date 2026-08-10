"""Typed HTTP contracts for canonical case architecture bootstrap."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CaseArchitectureBootstrapIntentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_payment_policy_version: str = Field(min_length=1, max_length=191)
    client_hourly_rate_ntd: int = Field(gt=0)
    deposit_service_days: int = Field(ge=0)
    deposit_due_date: date
    first_payment_due_date: date
    payroll_policy_version: str = Field(min_length=1, max_length=191)


class CaseArchitectureBootstrapApplyBody(
    CaseArchitectureBootstrapIntentBody
):
    expected_order_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class CaseArchitectureBootstrapPreviewView(BaseModel):
    case_no: str
    order_version: int
    source_identity_status: str
    client_payment_policy_version: str
    client_hourly_rate_ntd: int
    deposit_service_days: int
    deposit_due_date: date
    first_payment_due_date: date
    payroll_policy_version: str
    payroll_policy_kind: str
    payroll_hourly_rate_ntd: int
    scheduling_version: int
    scheduling_generation: int
    mutation: str
    preview_fingerprint: str


class CaseArchitectureBootstrapReceiptView(BaseModel):
    case_no: str
    order_version: int
    client_finance_version: int
    payroll_version: int
    scheduling_version: int
    scheduling_generation: int
    bootstrap_created: bool
    bootstrap_event_id: int
    preview_fingerprint: str


class CaseArchitectureBootstrapStatusView(BaseModel):
    case_no: str
    ready: bool
    scheduling_version: int
    scheduling_generation: int
    service_time_complete: bool
    recommendation: CaseArchitectureBootstrapIntentBody | None = None
    domain_blockers: list[str] = Field(default_factory=list)


class CaseArchitectureBootstrapTypedErrorView(BaseModel):
    category: str
    code: str
    message: str
    correlation_id: str
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "CaseArchitectureBootstrapApplyBody",
    "CaseArchitectureBootstrapIntentBody",
    "CaseArchitectureBootstrapPreviewView",
    "CaseArchitectureBootstrapReceiptView",
    "CaseArchitectureBootstrapStatusView",
    "CaseArchitectureBootstrapTypedErrorView",
]
