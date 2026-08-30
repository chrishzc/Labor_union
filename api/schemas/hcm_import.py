"""
File: hcm_import.py
Description: 定義 HCM workbook Preview／Apply 的嚴格 HTTP view。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HcmWorkbookPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    ready_with_warning_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HcmWorkbookRowOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_row: int = Field(gt=0)
    case_no: str | None = Field(default=None, max_length=50)
    outcome: Literal[
        "inserted",
        "inserted_with_warning",
        "exact_replay",
        "review_required",
        "failed",
    ]
    problem_identity: str | None = Field(default=None, max_length=191)
    problem_fields: list[str]
    issue_codes: list[str]
    referral_occurrence_identities: list[str]


class HcmWorkbookReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    inserted_count: int = Field(ge=0)
    inserted_with_warning_count: int = Field(ge=0)
    exact_replay_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    replayed_workbook: bool
    row_outcomes_available: bool
    legacy_summary_only: bool
    row_outcomes: list[HcmWorkbookRowOutcomeView]


class HcmWorkbookResultRecordView(HcmWorkbookReceiptView):
    receipt_id: int = Field(gt=0)
    completed_at: datetime


class HcmWorkbookResultPageView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[HcmWorkbookResultRecordView]
    next_cursor: int | None = Field(default=None, gt=0)


class HcmResubmissionPreviewView(BaseModel):
    """De-identified owner preview; corrected values never cross this API boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)

    review_identity: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    source_field: str = Field(min_length=1, max_length=191)
    target_fields: tuple[str, ...] = Field(min_length=1)
    review_version: int = Field(ge=0)
    root_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HcmResubmissionReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    event_identity: str = Field(min_length=1, max_length=191)
    review_identity: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    target_fields: tuple[str, ...] = Field(min_length=1)
    resulting_review_version: int = Field(ge=1)
    replayed: bool
