"""
================================================================================
檔案名稱: subsystems/scheduling/attendance_schedule_query.py
功能說明: 出勤排班與順延完工日精算服務 (OrderScheduleCalculationService)
================================================================================
"""

from typing import Dict, Any, List, Optional
from datetime import date
from infrastructure.mysql import mysql_adapter as db_service

def calculate_order_attendance_schedule(
    actual_start_date: date,
    target_service_days: int = 20,
    service_mode: str = "週休1日",
    custom_holiday_rest_dates: Optional[List[date]] = None,
    custom_leave_dates: Optional[List[date]] = None,
    custom_rest_weekdays: Optional[List[int]] = None,
    monthly_salary_base: Optional[float] = None,
) -> Dict[str, Any]:
    """
    精算服務人員出勤日、扣除排休與國定假日順延完工日。

    custom_holiday_rest_dates 與 custom_leave_dates 是兩種不同語意，分開轉傳給
    底層精算函式，不合併：
    - custom_holiday_rest_dates：從國定假日中挑出當天算休假的子集合（其餘國定
      假日視為當天正常出勤，完工日不順延）。省略時，底層預設所有國定假日皆休假。
    - custom_leave_dates：與國定假日無關的個別排休/請假日，一律算休假。
    """
    result = db_service.calculate_attendance_schedule(
        actual_start_date=actual_start_date,
        target_service_days=target_service_days,
        service_mode=service_mode,
        custom_leave_dates=custom_leave_dates,
        custom_holiday_rest_dates=custom_holiday_rest_dates,
        custom_rest_weekdays=custom_rest_weekdays,
        monthly_salary_base=monthly_salary_base,
    )
    return result
