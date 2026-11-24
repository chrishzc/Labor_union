"""Request and Query views for confirmed historical zero service."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.base import ExactNtd
from domains.orders.historical_unserved_correction import HistoricalUnservedCorrectionIntent


class HistoricalUnservedCorrectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=500)
    evidence_source: str = Field(default="", max_length=191)
    confirmed_actual_service_day_count: Literal[0]

    @field_validator("confirmed_actual_service_day_count", mode="before")
    @classmethod
    def require_integer_zero(cls, value):
        if type(value) is not int or value != 0:
            raise ValueError("historical_unserved_confirmation_required")
        return value

    @field_validator("reason", "evidence_source")
    @classmethod
    def require_canonical_text(cls, value):
        if value != value.strip():
            raise ValueError("historical_unserved_evidence_text_invalid")
        return value

    def to_intent(self) -> HistoricalUnservedCorrectionIntent:
        return HistoricalUnservedCorrectionIntent(
            self.reason, self.evidence_source, self.confirmed_actual_service_day_count,
        )


class HistoricalUnservedClientObligationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_identity: str
    payment_stage: str
    contracted_ntd: ExactNtd
    settled_ntd: ExactNtd


class HistoricalUnservedPayrollObligationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_identity: str
    obligation_kind: str
    staff_id: int
    contracted_ntd: ExactNtd
    outstanding_ntd: ExactNtd
    paid_ntd: ExactNtd


class HistoricalUnservedCorrectionQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blockers: list[str]
    review_codes: list[str] = Field(default_factory=list)
    establishment_lifecycle_event_ids: list[int]
    establishment_adoption_receipt_ids: list[int]
    establishment_owner_status: str | None
    historical_adoption_receipt_ids: list[int]
    historical_absence_event_ids: list[int]
    adopted_assignment_ids: list[int]
    actual_service_evidence: list[str]
    actual_start_date: date | None
    actual_end_date: date | None
    prior_fee_ntd: ExactNtd
    prior_fee_reason: str
    net_cash_received_ntd: ExactNtd | None
    prior_cancellation_event_id: int | None
    client_obligations: list[HistoricalUnservedClientObligationView]
    payroll_obligations: list[HistoricalUnservedPayrollObligationView]


class HistoricalUnservedPayrollRecoveryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_identity: str
    staff_id: int
    paid_ntd: ExactNtd
    recovery_increase_ntd: ExactNtd


class HistoricalUnservedCorrectionPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification_only: bool
    client_cash_difference_requires_review: bool = False
    retired_adopted_assignment_ids: list[int]
    payroll_recoveries: list[HistoricalUnservedPayrollRecoveryView]
