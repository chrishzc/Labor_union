"""
File: staff_assignment_options.py
Description: 定義 Calendar 案件下拉選單使用的正式指派唯讀 view。
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class StaffAssignmentOptionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    status: str = Field(min_length=1, max_length=50)
    assigned_start_date: date
    assigned_end_date: date
    order_status: str = Field(min_length=1, max_length=100)
    actual_start_date: date | None
    actual_end_date: date | None
    staff_name: str = Field(min_length=1, max_length=200)


class StaffAssignmentOptionsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignments: list[StaffAssignmentOptionView]


__all__ = ["StaffAssignmentOptionView", "StaffAssignmentOptionsView"]
