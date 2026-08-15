"""
File: staff_historical_workbook.py
Description: 定義 Staff 歷史 workbook Preview 與 Apply 的嚴格 HTTP views。
"""

from pydantic import BaseModel, ConfigDict, Field


class _StrictView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StaffHistoricalWorkbookPreviewView(_StrictView):
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    adopted_existing_count: int = Field(ge=0)
    blocked_identity_count: int = Field(ge=0)
    identity_conflict_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffHistoricalWorkbookReceiptView(StaffHistoricalWorkbookPreviewView):
    exact_replay_count: int = Field(ge=0)
    replayed_workbook: bool


__all__ = ["StaffHistoricalWorkbookPreviewView", "StaffHistoricalWorkbookReceiptView"]
