from datetime import date

from subsystems.scheduling.proposed_weekly_service_projection import (
    ProposedServiceSegment,
    project_proposed_weekly_service,
)


def test_proposed_weekly_service_counts_only_plan_work_dates_in_monday_week():
    rows = project_proposed_weekly_service((ProposedServiceSegment(
        segment_id=1, staff_id=100,
        start_date=date(2026, 9, 9), end_date=date(2026, 9, 13),
        weekly_rest_days=frozenset({5, 6}), service_hours_per_day=8,
    ),))

    assert [(row.week_start_date, row.week_end_date, row.weekly_work_days, row.weekly_hours) for row in rows] == [
        (date(2026, 9, 7), date(2026, 9, 13), 3, 24),
    ]


def test_proposed_weekly_service_splits_cross_week_and_honours_special_rest_date():
    rows = project_proposed_weekly_service((ProposedServiceSegment(
        segment_id=1, staff_id=100,
        start_date=date(2026, 12, 29), end_date=date(2027, 1, 5),
        weekly_rest_days=frozenset({6}), service_hours_per_day=8,
        special_rest_dates=frozenset({date(2027, 1, 1)}),
    ),))

    assert [(row.week_start_date, row.weekly_work_days, row.weekly_hours) for row in rows] == [
        (date(2026, 12, 28), 4, 32),
        (date(2027, 1, 4), 2, 16),
    ]
