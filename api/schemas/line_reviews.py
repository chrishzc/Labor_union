"""
================================================================================
檔案名稱: api/schemas/line_reviews.py
功能說明: LINE 人工確認核准與拒絕操作的輸入資料格式
================================================================================
"""

from pydantic import BaseModel, Field


class LineReviewDecisionRequest(BaseModel):
    reason: str = Field(default="", max_length=1000)
