"""
================================================================================
檔案名稱: api/schemas/line_rich_menus.py
功能說明: LINE 下方選單發布與重試 API 的輸入資料格式
================================================================================
"""

from pydantic import BaseModel, Field


class RichMenuPublishRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class RichMenuPublicationRetryRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
