"""
File: test_order_schedule_calculation_service.py
Description: 驗證服務日期精算的假日、請假與固定排休覆寫規則。
"""

import pytest
from datetime import date
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.order_schedule_calculation import calculate_schedule, router
from api.schemas.orders import ScheduleCalculationRequest
from api.schemas.schedule_precision import SchedulePrecisionResultView
from subsystems.access.authentication_session import AdminPrincipal
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


def test_fixed_rest_can_be_overridden_to_work_but_not_holiday_or_leave():
    """人工服務日只覆寫固定週休，不能跨越更高優先序的休假。"""
    fixed_rest_overridden = calculate_order_attendance_schedule(
        actual_start_date=date(2026, 9, 12),
        target_service_days=2,
        service_mode="週休2日",
        custom_work_dates=[date(2026, 9, 12)],
    )

    cells = {item["date"]: item for item in fixed_rest_overridden["day_by_day"]}
    assert cells[date(2026, 9, 12)]["is_work_day"] is True
    assert cells[date(2026, 9, 13)]["is_rest_day"] is True
    assert fixed_rest_overridden["actual_end_date"] == date(2026, 9, 14)

    leave_wins = calculate_order_attendance_schedule(
        actual_start_date=date(2026, 9, 12),
        target_service_days=1,
        service_mode="週休2日",
        custom_work_dates=[date(2026, 9, 12)],
        custom_leave_dates=[date(2026, 9, 12)],
    )
    leave_cells = {item["date"]: item for item in leave_wins["day_by_day"]}
    assert leave_cells[date(2026, 9, 12)]["is_rest_day"] is True


def test_schedule_route_forwards_custom_work_dates(monkeypatch):
    """路由不得遺失固定排休覆寫，避免 UI 成功點擊但 server 收不到條件。"""
    received = {}

    def _calculate(**kwargs):
        received.update(kwargs)
        return {
            "actual_start_date": date(2026, 9, 12),
            "actual_end_date": date(2026, 9, 12),
            "target_service_days": 1,
            "total_calendar_days": 1,
            "actual_work_days_count": 1,
            "rest_days_count": 0,
            "national_holidays_found": [],
            "total_estimated_salary": None,
            "weekly_stats": [
                {
                    "week_num": 1,
                    "start_date": date(2026, 9, 12),
                    "end_date": date(2026, 9, 12),
                    "work_days": 1,
                    "rest_days": 0,
                    "holiday_days": 0,
                }
            ],
            "day_by_day": [
                {
                    "date": date(2026, 9, 12),
                    "day_num": 1,
                    "is_work_day": True,
                    "is_rest_day": False,
                    "holiday_name": None,
                }
            ],
        }

    monkeypatch.setattr(
        "api.routes.order_schedule_calculation"
        ".attendance_schedule_query.calculate_order_attendance_schedule",
        _calculate,
    )

    response = calculate_schedule(
        ScheduleCalculationRequest(
            actual_start_date=date(2026, 9, 12),
            target_service_days=1,
            service_mode="週休2日",
            custom_work_dates=[date(2026, 9, 12)],
        ),
        AdminPrincipal(1, "typed-schedule", "Typed Schedule", "system_admin"),
    )

    assert received["custom_work_dates"] == [date(2026, 9, 12)]
    assert isinstance(response.data, SchedulePrecisionResultView)
    assert response.data.actual_end_date == date(2026, 9, 12)


def test_schedule_precision_requires_authenticated_admin():
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).post(
        "/api/v1/orders/calculate-schedule",
        json={
            "actual_start_date": "2026-09-12",
            "target_service_days": 1,
            "service_mode": "週休2日",
            "custom_work_dates": ["2026-09-12"],
        },
    )

    assert response.status_code == 401
