"""
File: historical_order_review_remediation.py
Description: 提供歷史訂單 review 更正 API 的嚴格請求與回應模型。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HistoricalReviewRemediationIntentBody(_StrictModel):
    review_identity: str = Field(min_length=1, max_length=191)


class HistoricalReviewRemediationApplyBody(HistoricalReviewRemediationIntentBody):
    expected_review_version: StrictInt = Field(ge=0)
    expected_remediation_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    evidence: list[str] = Field(min_length=1, max_length=20)


class HistoricalReviewConflictView(_StrictModel):
    issue_code: str
    field_path: str
    field_label: str
    rule: str
    masked_source_value: str
    masked_current_value: str
    allowed_values: list[str]
    process_blocker: str


class HistoricalReviewWorkbookContractView(_StrictModel):
    contract_key: str
    contract_version: StrictInt = Field(gt=0)
    required_columns: list[str] = Field(min_length=1)
    single_row_only: bool
    file_extension: str


class HistoricalReviewRemediationQueryView(_StrictModel):
    review_identity: str
    masked_case_identity: str
    issues: list[HistoricalReviewConflictView]
    review_version: StrictInt = Field(ge=0)
    remediation_version: StrictInt = Field(ge=0)
    workbook_contract: HistoricalReviewWorkbookContractView
    reason_required: bool = True
    evidence_required: bool = True
    completion_condition: str
    prior_alert_active: bool


class HistoricalReviewRemediationCandidateView(_StrictModel):
    prior_review_identity: str
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: str
    successor_required: bool
    blockers: list[str]
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalReviewRemediationPreviewView(_StrictModel):
    prior_review_identity: str
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: str
    remaining_issues: list[HistoricalReviewConflictView]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_version: StrictInt = Field(ge=0)
    remediation_version: StrictInt = Field(ge=0)


class HistoricalReviewRemediationReceiptSnapshotView(_StrictModel):
    remediation_receipt_identity: str
    disposition: str
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    resulting_remediation_version: StrictInt = Field(gt=0)


class HistoricalReviewSuccessorView(_StrictModel):
    review_identity: str
    masked_case_identity: str
    issues: list[HistoricalReviewConflictView]


class HistoricalReviewReadbackView(_StrictModel):
    prior_review_identity: str
    prior_alert_active: bool
    remaining_issues: list[HistoricalReviewConflictView]
    review_version: StrictInt = Field(ge=0)
    remediation_version: StrictInt = Field(ge=0)


class HistoricalReviewRemediationReceiptView(_StrictModel):
    prior_review_identity: str
    disposition: str
    receipt: HistoricalReviewRemediationReceiptSnapshotView
    prior_alert_active: bool
    successor: HistoricalReviewSuccessorView | None
    replayed: bool
    readback: HistoricalReviewReadbackView


class HistoricalReviewRemediationTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    correlation_id: str
    current_version: StrictInt | None = None


__all__ = [
    "HistoricalReviewRemediationApplyBody",
    "HistoricalReviewRemediationCandidateView",
    "HistoricalReviewRemediationIntentBody",
    "HistoricalReviewRemediationPreviewView",
    "HistoricalReviewRemediationQueryView",
    "HistoricalReviewRemediationReceiptView",
    "HistoricalReviewRemediationTypedErrorView",
]
