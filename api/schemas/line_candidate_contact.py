"""Strict public contracts for candidate-contact LIFF coordination."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CandidateIssueCategoryValue = Literal[
    "service_region",
    "service_dates",
    "daily_service_window",
    "daily_service_hours",
    "cooking_requirement",
    "transport_parking_floor",
    "personal_reason",
]
CandidateIssueModeValue = Literal["information_question", "condition_adjustment"]


class CandidateContactIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    line_id_token: str = Field(min_length=1, max_length=4096)
    interaction_reference: str = Field(pattern=r"^[0-9a-f]{64}$")


class CandidateContactIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    category: CandidateIssueCategoryValue
    mode: CandidateIssueModeValue
    detail: str = Field(min_length=1, max_length=500)


class CandidateContactSubmitRequest(CandidateContactIdentityRequest):
    no_interest: bool
    issues: list[CandidateContactIssueRequest] = Field(default_factory=list, max_length=7)
    idempotency_key: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_exclusive_no_interest(self) -> "CandidateContactSubmitRequest":
        if self.no_interest == bool(self.issues):
            raise ValueError("choose either no interest or one or more issues")
        categories = [item.category for item in self.issues]
        if len(categories) != len(set(categories)):
            raise ValueError("issue categories must be unique")
        return self


class CandidateContactFormView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str
    candidate_id: int = Field(gt=0)
    staff_name: str
    status: Literal["open", "closed"]
    deadline_at: str | None = None
    current_response_kind: Literal[
        "coordination_requested", "no_interest", "timed_out"
    ] | None = None


class CandidateContactSubmitView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["recorded", "idempotent_replay"]
    event_id: int = Field(gt=0)
    response_kind: Literal["coordination_requested", "no_interest"]
    customer_message_queued: bool
    union_followup_required: bool


class CandidateContactCustomerQueryRequest(CandidateContactIdentityRequest):
    pass


class CandidateContactCustomerIssueView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: CandidateIssueCategoryValue
    label: str
    detail: str
    candidate_count: int | None = Field(default=None, gt=0)


class CandidateContactCustomerFormView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str
    request_kind: Literal["information_question", "condition_adjustment"]
    status: Literal["open", "closed"]
    issues: list[CandidateContactCustomerIssueView]
    message_text: str | None = None


class CandidateInformationStaffIssueView(BaseModel):
    label: str
    detail: str


class CandidateInformationStaffItemView(BaseModel):
    question_id: int = Field(gt=0)
    pool_id: int = Field(gt=0)
    request_kind: Literal['information_question', 'condition_adjustment']
    customer_answer_event_id: int | None
    review_completed: bool
    case_no: str
    staff_name: str
    issues: list[CandidateInformationStaffIssueView]
    customer_answer: str | None
    customer_message: str | None
    customer_available: bool


class CandidateInformationStaffPageView(BaseModel):
    items: list[CandidateInformationStaffItemView]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)


class CandidateInformationStaffQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    line_id_token: str = Field(min_length=1, max_length=4096)
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=25, ge=1, le=50)


class CandidateInformationStaffSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    line_id_token: str = Field(min_length=1, max_length=4096)
    recipient: Literal["caregiver", "customer"]
    message_text: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=100)


class CandidateInformationStaffSendView(BaseModel):
    status: Literal["queued", "idempotent_replay"]
    event_id: int = Field(gt=0)


class CandidateContactCustomerSubmitRequest(CandidateContactIdentityRequest):
    answer: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=100)


class CandidateContactCustomerSubmitView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["recorded", "idempotent_replay"]
    event_id: int = Field(gt=0)
    caregiver_message_queued: bool
    union_followup_required: bool


__all__ = [
    "CandidateInformationStaffPageView",
    "CandidateInformationStaffQueryRequest",
    "CandidateInformationStaffSendRequest",
    "CandidateInformationStaffSendView",
    "CandidateContactFormView",
    "CandidateContactIdentityRequest",
    "CandidateContactIssueRequest",
    "CandidateContactSubmitRequest",
    "CandidateContactSubmitView",
    "CandidateContactCustomerFormView",
    "CandidateContactCustomerQueryRequest",
    "CandidateContactCustomerSubmitRequest",
    "CandidateContactCustomerSubmitView",
]
