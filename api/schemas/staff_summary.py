"""
File: staff_summary.py
Description: 定義 bounded Staff 摘要 cursor 查詢的嚴格公開契約。
"""

from pydantic import BaseModel, ConfigDict, Field


class StaffSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    name: str | None = None
    phone: str | None = None


class StaffSummaryPageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StaffSummaryView]
    next_cursor: int | None = Field(default=None, gt=0)
