from typing import Optional
from pydantic import BaseModel, Field

class MatchReplyRequest(BaseModel):
    accepted: Optional[bool] = Field(None, description="月嫂接案意願: True=願意(1), False=拒絕(0), None=待回覆(NULL)")

class MatchAssignRequest(BaseModel):
    staff_id: int = Field(..., description="擬定案指派之月嫂 staff_id")
