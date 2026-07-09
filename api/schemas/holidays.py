from pydantic import BaseModel, Field
from datetime import date

class HolidayCreateRequest(BaseModel):
    holiday_date: date = Field(..., description="假日日期")
    holiday_name: str = Field(..., description="假日名稱")
    is_double_pay_default: bool = Field(True, description="預設雙倍薪資")
