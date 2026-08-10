"""
================================================================================
檔案名稱: api/schemas/line_tasks.py
功能說明: LINE 發送任務管理 API 的輸入資料格式與欄位驗證
================================================================================
"""

from pydantic import BaseModel, Field


class LineTaskActionRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=191)
    correlation_id: str = Field(default="", max_length=191)
