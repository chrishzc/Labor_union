"""
File: historical_order_adoption.py
Description: 定義訂單狀態與月嫂歷史配對 workbook 的嚴格 Preview／Apply HTTP view。
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HistoricalOrderStatusCountsView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    cancelled_0: int = Field(ge=0)
    completed_1: int = Field(ge=0)
    discussion_2: int = Field(ge=0)
    invalid_or_blank: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.cancelled_0 + self.completed_1 + self.discussion_2 + self.invalid_or_blank


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
    status_counts: HistoricalOrderStatusCountsView
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_status_count_conservation(self):
        if self.status_counts.total != self.source_row_count:
            raise ValueError("historical_order_status_counts_not_conserved")
        return self


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
    status_counts: HistoricalOrderStatusCountsView

    @model_validator(mode="after")
    def validate_status_count_conservation(self):
        if self.status_counts.total != self.source_row_count:
            raise ValueError("historical_order_status_counts_not_conserved")
        return self
