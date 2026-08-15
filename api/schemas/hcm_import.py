"""
File: hcm_import.py
Description: 定義 HCM workbook Preview／Apply 的嚴格 HTTP view。
"""

from pydantic import BaseModel, ConfigDict, Field


class HcmWorkbookPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    ready_with_warning_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


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


class HcmResubmissionPreviewView(BaseModel):
    """De-identified owner preview; corrected values never cross this API boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)

    occurrence_identity: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    source_field: str = Field(min_length=1, max_length=191)
    target_fields: tuple[str, ...] = Field(min_length=1)
    occurrence_version: int = Field(ge=1)
    root_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HcmResubmissionReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    event_identity: str = Field(min_length=1, max_length=191)
    occurrence_identity: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    target_fields: tuple[str, ...] = Field(min_length=1)
    replayed: bool
