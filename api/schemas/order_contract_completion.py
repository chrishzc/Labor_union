"""Typed HTTP views for Orders contract completion."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractCompletionStagePlanView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_stage: str
    service_day_count: int = Field(ge=0)
    amount_ntd: int = Field(ge=0)
    due_date: date | None


class ContractCompletionClientFinanceImpactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_account_version: int = Field(ge=0)
    resulting_account_version: int = Field(ge=0)
    established_obligation_count: int = Field(ge=0)
    stage_plans: list[ContractCompletionStagePlanView]


class ContractCompletionQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    contract_identity: str | None
    contract_completed: bool
    lifecycle_status: str
    deposit_settled: bool
    service_time_terms_complete: bool
    completion_available: bool
    domain_blockers: list[str]


class ContractCompletionPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    contract_identity: str
    order_version: int = Field(ge=0)
    resulting_order_version: int = Field(ge=1)
    client_finance_version: int = Field(ge=0)
    client_finance_impact: ContractCompletionClientFinanceImpactView
    before_completed: bool
    after_completed: bool
    before_status: str
    after_status: str
    deposit_settled: bool
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ContractCompletionReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    contract_identity: str
    order_version: int = Field(ge=1)
    client_finance_version: int = Field(ge=1)
    established_obligation_count: int = Field(ge=0)
    lifecycle_status: str
    contract_completed: bool
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ContractCompletionTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "ContractCompletionClientFinanceImpactView",
    "ContractCompletionPreviewView",
    "ContractCompletionQueryView",
    "ContractCompletionReceiptView",
    "ContractCompletionStagePlanView",
    "ContractCompletionTypedErrorView",
]
