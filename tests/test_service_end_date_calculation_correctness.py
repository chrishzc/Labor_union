"""Hand-verified correctness checks for the two independent service
end-date calculators, plus explicit cross-consistency checks between them.

Logic A: scripts/imports/import_client_hcm.py::_calculate_service_end_date
    Used when importing client HCM Excel data to auto-fill orders.end_date.
    Pure function: takes an explicit holiday_dates set, no DB access.

Logic B: infrastructure/mysql/mysql_adapter.py::calculate_attendance_schedule
    Used by the live "出勤精算 Preview" feature
    (subsystems/scheduling/attendance_schedule_query.py). Reads holidays
    from the `holidays` table unless custom_holiday_rest_dates overrides it,
    and additionally supports per-day custom leave and custom rest weekdays
    that Logic A has no equivalent for.

Expected end dates below were computed with a small independent oracle
(plain day-by-day loop, not sharing code with either implementation under
test) and cross-checked by hand for two scenarios (C6, C7) before being
hardcoded here. See the scenario comments for the reasoning.

Requires a reachable local MySQL with the fixed 2026 holiday set already
loaded by scripts/init_db.py (same precondition as the existing
tests/test_order_schedule_calculation_service.py).
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.imports.import_client_hcm import _calculate_service_end_date
from subsystems.scheduling.attendance_schedule_query import (
    calculate_order_attendance_schedule,
)


# The fixed 2026 national-holiday set preloaded by scripts/init_db.py.
HOLIDAYS_2026 = {
    date(2026, 1, 1), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19),
    date(2026, 2, 20), date(2026, 2, 21), date(2026, 2, 22), date(2026, 2, 27),
    date(2026, 2, 28), date(2026, 4, 3), date(2026, 4, 4), date(2026, 6, 19),
    date(2026, 9, 25), date(2026, 10, 9), date(2026, 10, 10),
}


class _HolidayCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query):
        return None

    def fetchall(self):
        return [
            {"holiday_date": holiday_date, "holiday_name": "測試國定假日"}
            for holiday_date in sorted(HOLIDAYS_2026)
        ]


class _HolidayConnection:
    def cursor(self):
        return _HolidayCursor()

    def close(self):
        return None


@pytest.fixture(autouse=True)
def _isolated_holiday_repository(monkeypatch):
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(mysql_adapter, "get_connection", _HolidayConnection)


# (name, start, service_days, service_type, holiday_dates, expected_end)
SCENARIOS = [
    # C1: 連續服務 never skips a weekday and no holiday falls in range,
    # so 5 service days is just 5 consecutive calendar days.
    ("C1_continuous_no_holiday", date(2026, 3, 2), 5, "連續服務", frozenset(), date(2026, 3, 6)),
    # C2: 週休1日 only skips Sunday. Mon 3/2 .. Sat 3/7 has no Sunday in it,
    # so all 6 days count and end date is Sat 3/7.
    ("C2_weekly1_no_sunday_in_range", date(2026, 3, 2), 6, "週休1日", frozenset(), date(2026, 3, 7)),
    # C3: 週休2日 skips Sat+Sun. Mon 3/2..Fri 3/6 = 5 days, then Sat 3/7 and
    # Sun 3/8 are skipped, so day 6 lands on Mon 3/9.
    ("C3_weekly2_skips_weekend", date(2026, 3, 2), 6, "週休2日", frozenset(), date(2026, 3, 9)),
    # C4: 週休1日 starting the Monday right before the 6-day Spring Festival
    # holiday block (2/17 Tue .. 2/22 Sun). Only 2/16 counts before the
    # block; the block itself is entirely holiday (its one Sunday, 2/22, is
    # already a holiday so it changes nothing extra); next working days are
    # 2/23 (Mon) and 2/24 (Tue) -> day 3.
    ("C4_weekly1_across_spring_festival", date(2026, 2, 16), 3, "週休1日", HOLIDAYS_2026, date(2026, 2, 24)),
    # C5: same window as C4 but 連續服務 (no weekday skip at all) - result is
    # identical here because the only weekend day in the window (2/22) was
    # already a holiday, so weekday-skipping made no difference in C4 either.
    ("C5_continuous_across_spring_festival", date(2026, 2, 16), 3, "連續服務", HOLIDAYS_2026, date(2026, 2, 24)),
    # C6: 週休1日 starting on a Saturday (2/14). Saturday is a working day
    # under 週休1日 (only Sunday rests), so 2/14 is day 1, 2/15 (Sun) is
    # skipped, 2/16 (Mon) day 2, 2/17 (Tue) day 3. No holiday_dates passed,
    # so 2/17 being a real holiday is irrelevant here.
    ("C6_weekly1_starts_saturday", date(2026, 2, 14), 3, "週休1日", frozenset(), date(2026, 2, 17)),
    # C7: same start/day-count but 週休2日 - Saturday now also rests, so
    # 2/14 (Sat) and 2/15 (Sun) both skip, day 1 is 2/16 (Mon), day 2 is
    # 2/17 (Tue), day 3 is 2/18 (Wed).
    ("C7_weekly2_starts_saturday", date(2026, 2, 14), 3, "週休2日", frozenset(), date(2026, 2, 18)),
    # C8: a longer run with no holiday interaction, sanity-checking the loop
    # over multiple weeks.
    ("C8_weekly2_longer_run", date(2026, 7, 1), 10, "週休2日", frozenset(), date(2026, 7, 14)),
]


@pytest.mark.parametrize("name,start,days,mode,holidays,expected", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_logic_a_hcm_import_end_date(name, start, days, mode, holidays, expected):
    result = _calculate_service_end_date(start, days, mode, holidays)
    assert result == expected, f"{name}: expected {expected}, got {result}"


@pytest.mark.parametrize("name,start,days,mode,holidays,expected", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_logic_b_attendance_preview_end_date_matches_same_holidays(
    name, start, days, mode, holidays, expected
):
    """Logic B given the *same explicit* holiday set as Logic A must reach
    the same end date, even though B additionally supports per-day leave
    and custom rest-weekday overrides that A has no equivalent for."""
    result = calculate_order_attendance_schedule(
        actual_start_date=start,
        target_service_days=days,
        service_mode=mode,
        custom_holiday_rest_dates=list(holidays),
    )
    assert result["actual_end_date"] == expected, f"{name}: expected {expected}, got {result['actual_end_date']}"


def test_logic_a_and_logic_b_agree_on_default_holiday_handling():
    """With no explicit override, Logic B reads *all* DB holidays as rest
    days - algebraically the same behaviour as Logic A when Logic A is given
    the full holiday set. This is the actual default path both the HCM
    import and a Preview call with no manual holiday selection go through,
    so if this test fails, real orders imported via Excel and orders
    checked via the Preview UI would land on different end dates for the
    same input, which is a genuine cross-module bug worth flagging."""
    start, days, mode = date(2026, 2, 16), 3, "週休1日"

    logic_a_result = _calculate_service_end_date(start, days, mode, HOLIDAYS_2026)
    logic_b_result = calculate_order_attendance_schedule(
        actual_start_date=start,
        target_service_days=days,
        service_mode=mode,
    )

    assert logic_a_result == date(2026, 2, 24)
    assert logic_b_result["actual_end_date"] == date(2026, 2, 24)
    assert logic_a_result == logic_b_result["actual_end_date"]


def test_logic_b_custom_leave_date_extends_completion_like_a_holiday():
    """A single ad-hoc leave day (not a national holiday) should push the
    end date out by one day, same as a holiday would, since both count as
    non-work days in the day-by-day loop."""
    start = date(2026, 3, 2)  # Monday
    result_no_leave = calculate_order_attendance_schedule(
        actual_start_date=start,
        target_service_days=5,
        service_mode="連續服務",
        custom_holiday_rest_dates=[],
    )
    result_with_leave = calculate_order_attendance_schedule(
        actual_start_date=start,
        target_service_days=5,
        service_mode="連續服務",
        custom_holiday_rest_dates=[],
        custom_leave_dates=[date(2026, 3, 4)],
    )
    assert result_no_leave["actual_end_date"] == date(2026, 3, 6)
    assert result_with_leave["actual_end_date"] == date(2026, 3, 7)


def test_logic_b_partial_attendance_within_consecutive_holidays():
    """Regression test for the documented business rule in
    document/文件整併工作區/01_管理端UI與排班_無損合併稿.md:1420-1426
    ("國定假日單日個體決策規範"): during a run of consecutive national
    holidays, each individual day must be selectable as worked or rested
    independently - e.g. a caregiver rests on the first holiday of a block
    but works normally through the rest of it.

    2026-02-27 and 2026-02-28 are both real national holidays (和平紀念日
    補假／和平紀念日). Only 2/27 is selected as a rest day here; 2/28 must
    be treated as a normal work day and must NOT push the completion date
    out, even though it is still a real holiday in the `holidays` table.

    This is the exact wrapper bug fixed in
    subsystems/scheduling/attendance_schedule_query.py: before the fix, the
    wrapper always forced custom_holiday_rest_dates to None before calling
    the underlying calculator, so both holidays were always rest days
    regardless of what the caller selected.
    """
    result = calculate_order_attendance_schedule(
        actual_start_date=date(2026, 2, 25),
        target_service_days=5,
        service_mode="連續服務",
        custom_holiday_rest_dates=[date(2026, 2, 27)],
    )
    assert result["actual_end_date"] == date(2026, 3, 2)

    by_date = {item["date"]: item for item in result["day_by_day"]}
    assert by_date[date(2026, 2, 27)]["is_rest_day"] is True
    assert by_date[date(2026, 2, 28)]["is_rest_day"] is False
    assert by_date[date(2026, 2, 28)]["is_work_day"] is True


def test_logic_b_custom_rest_weekdays_overrides_service_mode_default():
    """Passing custom_rest_weekdays must take priority over the
    service_mode default mapping (this is the exact regression the
    existing test_order_schedule_calculation_service.py guards, verified
    here with an exact date instead of just checking the key exists)."""
    start = date(2026, 3, 2)  # Monday
    result = calculate_order_attendance_schedule(
        actual_start_date=start,
        target_service_days=6,
        service_mode="週休1日",  # would normally only skip Sunday
        custom_holiday_rest_dates=[],
        custom_rest_weekdays=[5, 6],  # force Sat+Sun rest instead
    )
    assert result["actual_end_date"] == date(2026, 3, 9)
