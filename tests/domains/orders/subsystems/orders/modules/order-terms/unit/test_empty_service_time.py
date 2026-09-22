"""Issue #337: unchanged empty service time does not block independent edits."""

from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from domains.orders.terms import OrderAggregateFacts, OrderTerms, ServiceTimeTerms, validate_terms_change
from shared_kernel.money import MoneyNTD


def _facts(service_time=None, *, locked=False):
    terms = OrderTerms(
        date(2026, 10, 1),
        5,
        8,
        MoneyNTD(0),
        service_time or ServiceTimeTerms(None, None, None),
        None,
    )
    return OrderAggregateFacts("ISSUE-337-TEST", 3, terms, locked, "一般市民")


@pytest.mark.parametrize(
    "change",
    [
        {"planned_start_date": date(2026, 10, 2)},
        {"service_days": 6},
        {"service_hours_per_day": 4.5},
        {"floor_fee": MoneyNTD(100)},
        {"requires_cooking": True},
        {"requires_cooking": False},
    ],
)
def test_independent_edits_preserve_empty_service_time(change):
    current = _facts()
    proposed = replace(current.terms, **change)

    validate_terms_change(current, proposed)

    assert proposed.service_time.canonical_payload() == {
        "start_time": None,
        "end_time": None,
        "end_day_offset": None,
    }


def test_clearing_existing_complete_time_is_not_authorized():
    current = _facts(ServiceTimeTerms(time(9), time(17), 0))

    with pytest.raises(ValueError, match="^service_time_terms_incomplete$"):
        validate_terms_change(
            current,
            replace(current.terms, service_time=ServiceTimeTerms(None, None, None)),
        )


@pytest.mark.parametrize(
    "values",
    [
        (None, time(17), 0),
        (time(9), None, 0),
        (time(9), time(17), None),
        (None, None, 0),
    ],
)
def test_partial_time_tuple_is_rejected(values):
    with pytest.raises(ValueError, match="all empty or all present"):
        ServiceTimeTerms(*values)


def test_empty_time_completion_remains_taipei_day_end():
    service_day = date(2026, 10, 5)

    assert _facts().terms.service_time.completion_instant(service_day) == datetime.combine(
        service_day,
        time.max,
        tzinfo=ZoneInfo("Asia/Taipei"),
    )


def test_cross_day_completion_remains_next_day_end_time():
    service_time = ServiceTimeTerms(time(21), time(5), 1)

    assert service_time.completion_instant(date(2026, 10, 5)) == datetime(
        2026,
        10,
        6,
        5,
        tzinfo=ZoneInfo("Asia/Taipei"),
    )
