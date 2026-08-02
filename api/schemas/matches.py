"""
================================================================================
檔案名稱: api/schemas/matches.py
功能說明: 訂單媒合意願回覆與月嫂定案指派 API 的輸入資料格式
================================================================================
"""

from typing import Optional
from pydantic import BaseModel, Field

class MatchReplyRequest(BaseModel):
    accepted: Optional[bool] = Field(None, description="月嫂接案意願: True=願意(1), False=拒絕(0), None=待回覆(NULL)")

class MatchAssignRequest(BaseModel):
    staff_id: int = Field(..., description="擬定案指派之月嫂 staff_id")

class MatchCreateRequest(BaseModel):
    staff_id: int = Field(..., description="月嫂 staff_id")


class MatchLineTestBindingRequest(BaseModel):
    client_line_user_id: str = Field(..., min_length=1, description="測試客戶 LINE userId")
    staff_id: int = Field(..., description="要測試的月嫂 staff_id")
    staff_line_user_id: str = Field(..., min_length=1, description="測試月嫂 LINE userId")
