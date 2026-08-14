"""
File: hcm_import.py
Description: 定義 HCM workbook upload 的嚴格 HTTP receipt view。
"""

from pydantic import BaseModel, ConfigDict, Field


class HcmWorkbookReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    inserted_count: int = Field(ge=0)
    exact_replay_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    replayed_workbook: bool
