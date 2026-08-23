"""File: candidate_contact_pool.py
Description: 定義候選聯繫池 API 的 closed request 與 response schemas。
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _EventIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=100)
    event_key: str = Field(min_length=1, max_length=100)


class CandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "CandidateInput":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class AddCandidatesRequest(_EventIdentity):
    candidates: list[CandidateInput] = Field(min_length=1, max_length=50)


class SendCandidateInformationRequest(_EventIdentity):
    info_type: Literal[1, 2]


class CandidateWillingnessRequest(_EventIdentity):
    willingness: Literal["willing", "unwilling"]
    reason: str = Field(default="", max_length=500)


class CandidateInformationDeliveryView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    status: Literal[
        "queued",
        "pending",
        "sent",
        "retryable_failed",
        "failed",
        "cancelled",
    ]
    sent_at: datetime


class CandidateInformationMap(BaseModel):
    model_config = ConfigDict(
        extra="forbid", from_attributes=True, populate_by_name=True
    )

    information_1: CandidateInformationDeliveryView | None = Field(
        default=None, alias="1"
    )
    information_2: CandidateInformationDeliveryView | None = Field(
        default=None, alias="2"
    )


class CandidateContactView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    service_start_date: date
    service_end_date: date
    status: Literal["active", "selected", "withdrawn"]
    created_at: datetime
    staff_name: str = Field(min_length=1, max_length=100)
    willingness: Literal["pending", "willing", "unwilling"]
    reason: str | None = Field(default=None, max_length=500)
    information: CandidateInformationMap

    @model_validator(mode="after")
    def validate_service_date_range(self) -> "CandidateContactView":
        if self.service_start_date > self.service_end_date:
            raise ValueError(
                "service_start_date must be on or before service_end_date"
            )
        return self


class CandidateContactPoolView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    pool_id: int | None = Field(default=None, gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    candidates: list[CandidateContactView] = Field(default_factory=list, max_length=50)


class AddCandidatesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pool_id: int = Field(gt=0)
    candidate_ids: list[int] = Field(min_length=1, max_length=50)
    status: Literal["recorded"]

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> "AddCandidatesResult":
        if any(item <= 0 for item in self.candidate_ids):
            raise ValueError("candidate_ids must contain only positive integers")
        return self


class SendCandidateInformationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["queued", "idempotent_replay"]
    event_id: int = Field(gt=0)
    line_task_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_delivery_reference(self) -> "SendCandidateInformationResult":
        if self.status == "queued" and self.line_task_id is None:
            raise ValueError("queued result must include line_task_id")
        return self


class CandidateWillingnessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["recorded", "idempotent_replay"]
    event_id: int = Field(gt=0)


__all__ = [
    "AddCandidatesRequest",
    "AddCandidatesResult",
    "CandidateInput",
    "CandidateContactPoolView",
    "CandidateContactView",
    "CandidateInformationDeliveryView",
    "CandidateInformationMap",
    "CandidateWillingnessRequest",
    "CandidateWillingnessResult",
    "SendCandidateInformationRequest",
    "SendCandidateInformationResult",
]
