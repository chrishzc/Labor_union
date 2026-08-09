"""
================================================================================
檔案名稱: api/schemas/line_rich_menus.py
功能說明: LINE 下方選單發布與重試 API 的輸入資料格式
================================================================================
"""

from pydantic import BaseModel, Field


class RichMenuPublishRequest(BaseModel):
    preview_id: int = Field(ge=1)
    reason: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=191)
    correlation_id: str = Field(default="", max_length=191)


class RichMenuPublicationRetryRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=191)
    correlation_id: str = Field(default="", max_length=191)
