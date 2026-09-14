from datetime import date, time

from subsystems.case_import.hcm_resubmission_source import hcm_resubmission_target_values


def test_service_time_warning_preserves_half_hour_precision() -> None:
    values = hcm_resubmission_target_values(
        "服務時間",
        {
            "service_start_date": date(2026, 8, 3),
            "service_days": 2,
            "service_type": "連續服務",
            "service_time": "4.5小時 09:00-13:30",
        },
        holiday_dates=set(),
    )

    assert values == {
        "orders.service_hours_per_day": 4.5,
        "orders.service_start_time": time(9),
        "orders.service_end_time": time(13, 30),
        "orders.service_end_day_offset": 0,
    }
