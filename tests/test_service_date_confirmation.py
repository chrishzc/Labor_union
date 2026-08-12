from datetime import date

import pytest

from domains.orders.service_date_confirmation import (
    ConfirmedServiceDateCandidate,
    group_service_dates_by_calendar_week,
)
from subsystems.orders.service_date_confirmation_workflow import (
    ServiceDateConfirmationFacts,
    _candidate,
)


def test_service_dates_must_match_the_contracted_day_count():
    with pytest.raises(ValueError, match="service date count"):
        ConfirmedServiceDateCandidate(
            "CASE-68",
            1,
            1,
            (date(2026, 8, 2),),
            2,
        )


def test_service_date_week_grouping_starts_on_sunday():
    weeks = group_service_dates_by_calendar_week(
        (date(2026, 8, 8), date(2026, 8, 9), date(2026, 8, 10))
    )

    assert weeks == (
        {
            "week_number": 1,
            "period_start": "2026-08-02",
            "period_end": "2026-08-08",
            "service_dates": ["2026-08-08"],
            "service_day_count": 1,
        },
        {
            "week_number": 2,
            "period_start": "2026-08-09",
            "period_end": "2026-08-15",
            "service_dates": ["2026-08-09", "2026-08-10"],
            "service_day_count": 2,
        },
    )


def test_service_date_must_be_in_the_server_selectable_range():
    facts = ServiceDateConfirmationFacts(
        "CASE-68", 1, 1, 2, (), (date(2026, 8, 1), date(2026, 8, 2)), None, ()
    )

    with pytest.raises(ValueError, match="outside_selectable_range"):
        _candidate(facts, (date(2026, 8, 1), date(2026, 8, 3)))
