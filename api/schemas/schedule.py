from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class ScheduleDateItem(BaseModel):
    work_date: date = Field(..., description="排班日期")
    is_work_day: bool = Field(True, description="是否為工作日")
    is_double_pay: bool = Field(False, description="是否為雙倍薪資日")
    notes: Optional[str] = Field(None, description="備註")


class SaveScheduleRequest(BaseModel):
    case_no: str = Field(..., min_length=1, description="案件編號")
    staff_id: int = Field(..., description="服務人員 ID")
    schedule_dates: List[ScheduleDateItem] = Field(..., description="每日排班列表")
