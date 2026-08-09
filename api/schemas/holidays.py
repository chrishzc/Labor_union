from typing import Literal
from pydantic import BaseModel, Field, model_validator
from datetime import date

class HolidayCreateRequest(BaseModel):
    holiday_date: date = Field(..., description="假日日期")
    holiday_name: str = Field(..., description="假日名稱")
    is_double_pay_default: bool = Field(
        False,
        description="相容欄位；排班不會因國定假日自動套用雙倍薪資",
    )


class HolidayPreviewRequest(BaseModel):
    action: Literal["upsert", "delete"]
    holiday_date: date
    holiday_name: str | None = Field(None, max_length=100)
    is_double_pay_default: bool = False

    @model_validator(mode="after")
    def validate_upsert_name(self):
        if self.action == "upsert" and not (self.holiday_name or "").strip():
            raise ValueError("holiday_name_required")
        return self

    def command(self):
        return {"action": self.action, "holiday_date": self.holiday_date.isoformat(), "holiday_name": (self.holiday_name or "").strip(), "is_double_pay_default": self.is_double_pay_default}


class HolidayApplyRequest(HolidayPreviewRequest):
    preview_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
