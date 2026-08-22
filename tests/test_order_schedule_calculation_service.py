"""
================================================================================
檔案名稱: tests/test_order_schedule_calculation_service.py
功能說明: 驗證 OrderScheduleCalculationService 排休聯集合併與完整參數轉傳功能
================================================================================
"""

import pytest
from datetime import date
from subsystems.scheduling.attendance_schedule_query import calculate_order_attendance_schedule


class _HolidayCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query):
        return None

    def fetchall(self):
        return [{"holiday_date": date(2026, 10, 10), "holiday_name": "測試國定假日"}]


class _HolidayConnection:
    def cursor(self):
        return _HolidayCursor()

    def close(self):
        return None


@pytest.fixture(autouse=True)
def _isolated_holiday_repository(monkeypatch):
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(mysql_adapter, "get_connection", _HolidayConnection)

def test_order_schedule_calculation_union_dates():
    """驗證 custom_holiday_rest_dates 與 custom_leave_dates 會取聯集，不互斥遺失"""
    start_d = date(2026, 10, 1)
    holiday_dates = [date(2026, 10, 10)]
    leave_dates = [date(2026, 10, 15)]

    res = calculate_order_attendance_schedule(
        actual_start_date=start_d,
        target_service_days=20,
        service_mode="週休1日",
        custom_holiday_rest_dates=holiday_dates,
        custom_leave_dates=leave_dates,
    )

    assert "actual_end_date" in res
    assert "day_by_day" in res

    day_dates = {item["date"]: item["is_rest_day"] for item in res["day_by_day"]}
    assert day_dates.get(date(2026, 10, 10)) is True
    assert day_dates.get(date(2026, 10, 15)) is True

def test_order_schedule_calculation_custom_weekdays_and_salary():
    """驗證 custom_rest_weekdays 與 monthly_salary_base 可順利轉傳與計算"""
    start_d = date(2026, 7, 1)
    res = calculate_order_attendance_schedule(
        actual_start_date=start_d,
        target_service_days=10,
        service_mode="週休2日",
        custom_rest_weekdays=[5, 6],
        monthly_salary_base=60000.0,
    )

    assert "actual_end_date" in res
    assert res.get("target_service_days") == 10
