"""
File: historical_order_adoption.py
Description: 定義訂單狀態與月嫂歷史配對 workbook 的嚴格 Preview／Apply HTTP view。
"""

from pydantic import BaseModel, ConfigDict, Field


class HistoricalOrderWorkbookPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sheet_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    adopted_count: int = Field(ge=0)
    unmatched_case_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    current_conflict_count: int = Field(ge=0)
    assignment_candidate_count: int = Field(ge=0)
    evidence_only_pairing_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalOrderWorkbookReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    adopted_count: int = Field(ge=0)
    unmatched_case_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    current_conflict_count: int = Field(ge=0)
    assignments_created: int = Field(ge=0)
    replayed_rows: int = Field(ge=0)
    replayed_workbook: bool
