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
