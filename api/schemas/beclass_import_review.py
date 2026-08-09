"""Strict HTTP schemas for BeClass import review."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BeClassImportReviewIntentBody(_StrictModel):
    review_identity: str = Field(min_length=1, max_length=191)
    corrected_fields: dict[str, Any] = Field(min_length=1)
    resolved_issue_codes: list[str] = Field(min_length=1)


class BeClassImportReviewApplyBody(BeClassImportReviewIntentBody):
    expected_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class BeClassImportReviewQueryView(_StrictModel):
    review_identity: str
    source_kind: str
    source_payload: dict[str, Any]
    issue_codes: list[str]
    review_version: int = Field(ge=0)
    status: str
    effective_payload: dict[str, Any]


class BeClassImportReviewCandidateView(_StrictModel):
    review_identity: str
    source_kind: str
    resulting_version: int = Field(gt=0)
    corrected_payload: dict[str, Any]
    resolved_issue_codes: list[str]
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class BeClassImportReviewPreviewView(_StrictModel):
    candidate: BeClassImportReviewCandidateView
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class BeClassImportReviewReceiptView(_StrictModel):
    review_identity: str
    resulting_version: int = Field(gt=0)
    owning_record_identity: str
    review_event_id: int = Field(gt=0)
    outbox_id: int = Field(gt=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class BeClassImportReviewTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "BeClassImportReviewApplyBody",
    "BeClassImportReviewIntentBody",
    "BeClassImportReviewPreviewView",
    "BeClassImportReviewQueryView",
    "BeClassImportReviewReceiptView",
    "BeClassImportReviewTypedErrorView",
]
