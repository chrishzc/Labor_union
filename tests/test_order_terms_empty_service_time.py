"""Issue #337: unchanged empty time terms do not block independent edits."""
from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from domains.orders.terms import (
    OrderAggregateFacts,
    OrderTerms,
    ServiceTimeTerms,
    is_unique_cooking_requirement_correction,
    validate_terms_change,
)
from shared_kernel.money import MoneyNTD


def _facts(service_time=None, *, cooking=None, locked=False):
    terms = OrderTerms(
        date(2026, 10, 1), 5, 8, MoneyNTD(0),
        service_time or ServiceTimeTerms(None, None, None), cooking,
    )
    return OrderAggregateFacts('ISSUE-337-TEST', 3, terms, locked, '一般市民')


@pytest.mark.parametrize('change', [
    {'planned_start_date': date(2026, 10, 2)},
    {'service_days': 6},
    {'service_hours_per_day': 4.5},
    {'floor_fee': MoneyNTD(100)},
    {'requires_cooking': True},
    {'requires_cooking': False},
])
def test_independent_edits_preserve_empty_service_time(change):
    current = _facts()
    proposed = replace(current.terms, **change)
    validate_terms_change(current, proposed)
    assert proposed.service_time.canonical_payload() == {
        'start_time': None, 'end_time': None, 'end_day_offset': None,
    }
    assert current.terms.planned_start_date == date(2026, 10, 1)
    assert current.version == 3


@pytest.mark.parametrize('before,after', [(True, False), (False, True), (True, None)])
def test_existing_cooking_value_can_change_without_filling_time(before, after):
    current = _facts(cooking=before)
    validate_terms_change(current, replace(current.terms, requires_cooking=after))


@pytest.mark.parametrize('cooking', [True, False])
def test_unique_cooking_classification_remains_available(cooking):
    current = _facts()
    proposed = replace(current.terms, requires_cooking=cooking)
    assert is_unique_cooking_requirement_correction(current.terms, proposed)
    assert not is_unique_cooking_requirement_correction(
        current.terms, replace(proposed, service_days=6),
    )


@pytest.mark.parametrize('service_time', [
    ServiceTimeTerms(None, None, None),
    ServiceTimeTerms(time(9), time(17), 0),
])
def test_locked_order_is_still_rejected(service_time):
    current = _facts(service_time, locked=True)
    with pytest.raises(ValueError, match='^service_data_locked$'):
        validate_terms_change(current, replace(current.terms, planned_start_date=date(2026, 10, 2)))


def test_clearing_existing_complete_time_is_not_newly_authorized():
    current = _facts(ServiceTimeTerms(time(9), time(17), 0))
    with pytest.raises(ValueError, match='^service_time_terms_incomplete$'):
        validate_terms_change(current, replace(current.terms, service_time=ServiceTimeTerms(None, None, None)))


@pytest.mark.parametrize('values', [
    (None, time(17), 0), (time(9), None, 0), (time(9), time(17), None),
    (None, None, 0), (time(9), None, None), (None, time(17), None),
])
def test_partial_time_tuple_still_rejected(values):
    with pytest.raises(ValueError, match='all empty or all present'):
        ServiceTimeTerms(*values)


@pytest.mark.parametrize('values', [(time(9), time(17), -1), (time(9), time(17), 2)])
def test_invalid_offset_still_rejected(values):
    with pytest.raises(ValueError, match='offset must be 0 or 1'):
        ServiceTimeTerms(*values)


@pytest.mark.parametrize('hours', [0, -1, 4.25, True, float('inf')])
def test_invalid_hour_precision_is_not_relaxed(hours):
    with pytest.raises(ValueError, match='half-hour precision'):
        replace(_facts().terms, service_hours_per_day=hours)


@pytest.mark.parametrize('values', [(time(9), time(13, 30), 0), (time(21), time(5), 1)])
def test_filling_complete_time_remains_allowed(values):
    current = _facts()
    proposed = replace(current.terms, service_time=ServiceTimeTerms(*values))
    validate_terms_change(current, proposed)
    assert proposed.service_time.complete


def test_empty_time_completion_remains_taipei_day_end():
    when = date(2026, 10, 5)
    assert _facts().terms.service_time.completion_instant(when) == datetime.combine(
        when, time.max, tzinfo=ZoneInfo('Asia/Taipei'),
    )


def test_cross_day_completion_remains_next_day_end_time():
    service_time = ServiceTimeTerms(time(21), time(5), 1)
    assert service_time.completion_instant(date(2026, 10, 5)) == datetime(
        2026, 10, 6, 5, tzinfo=ZoneInfo('Asia/Taipei'),
    )
