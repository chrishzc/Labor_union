"""Direct regression contracts for Orders domain-owned business rules."""

from datetime import date, datetime, timezone

import pytest

from domains.orders.auto_completion import build_auto_completion_candidate
from domains.orders.floor_fee import allocate_largest_remainder, prorate_floor_fee
from domains.orders.lifecycle import OrderLifecycleRootFacts, OrderLifecycleStatus
from domains.orders.service_date_confirmation import (
    ConfirmedServiceDateCandidate,
    group_service_dates_by_calendar_week,
)
from shared_kernel.money import MoneyNTD


def test_auto_completion_requires_completion_time_and_advances_exactly_one_version() -> None:
    completion = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="auto_completion_time_not_reached"):
        build_auto_completion_candidate(
            case_no="CASE-100",
            expected_order_version=7,
            completion_instant=completion,
            evaluation_at=datetime(2026, 8, 31, 11, 59, tzinfo=timezone.utc),
        )

    candidate = build_auto_completion_candidate(
        case_no="CASE-100",
        expected_order_version=7,
        completion_instant=completion,
        evaluation_at=completion,
    )
    assert candidate.expected_order_version == 7
    assert candidate.resulting_order_version == 8


def test_auto_completion_fingerprint_is_deterministic_and_tracks_evaluation_identity() -> None:
    completion = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    first = build_auto_completion_candidate(
        case_no="CASE-100",
        expected_order_version=7,
        completion_instant=completion,
        evaluation_at=completion,
    )
    same = build_auto_completion_candidate(
        case_no="CASE-100",
        expected_order_version=7,
        completion_instant=completion,
        evaluation_at=completion,
    )
    later = build_auto_completion_candidate(
        case_no="CASE-100",
        expected_order_version=7,
        completion_instant=completion,
        evaluation_at=datetime(2026, 8, 31, 12, 1, tzinfo=timezone.utc),
    )

    assert first.fingerprint == same.fingerprint
    assert first.fingerprint != later.fingerprint


def test_floor_fee_proration_uses_integer_half_up_rounding_and_bounds() -> None:
    assert prorate_floor_fee(MoneyNTD(101), 2, 1) == MoneyNTD(51)
    assert prorate_floor_fee(MoneyNTD(100), 3, 1) == MoneyNTD(33)
    assert prorate_floor_fee(MoneyNTD(500), 5, 0) == MoneyNTD(0)

    with pytest.raises(ValueError, match="exceed"):
        prorate_floor_fee(MoneyNTD(500), 5, 6)
    with pytest.raises((TypeError, ValueError)):
        prorate_floor_fee(MoneyNTD(500), 0, 0)


def test_largest_remainder_allocation_preserves_total_and_breaks_ties_deterministically() -> None:
    allocation = allocate_largest_remainder(
        MoneyNTD(5),
        {"b": 1, "a": 1, "c": 1},
    )

    assert allocation == {
        "b": MoneyNTD(2),
        "a": MoneyNTD(2),
        "c": MoneyNTD(1),
    }
    assert sum(value.amount for value in allocation.values()) == 5


def test_largest_remainder_handles_zero_without_weights_and_rejects_positive_unallocated_total() -> None:
    assert allocate_largest_remainder(MoneyNTD(0), {}) == {}
    with pytest.raises(ValueError, match="requires weights"):
        allocate_largest_remainder(MoneyNTD(1), {})
    with pytest.raises(ValueError, match="positive integers"):
        allocate_largest_remainder(MoneyNTD(10), {"a": 0})


def test_confirmed_service_dates_require_sorted_unique_exact_contract_count() -> None:
    dates = (date(2026, 8, 30), date(2026, 9, 1))
    candidate = ConfirmedServiceDateCandidate(
        case_no="CASE-200",
        order_version=3,
        scheduling_version=5,
        service_dates=dates,
        contracted_service_days=2,
    )
    assert candidate.service_dates == dates

    with pytest.raises(ValueError, match="unique and sorted"):
        ConfirmedServiceDateCandidate("CASE-200", 3, 5, (dates[1], dates[0]), 2)
    with pytest.raises(ValueError, match="unique and sorted"):
        ConfirmedServiceDateCandidate("CASE-200", 3, 5, (dates[0], dates[0]), 2)
    with pytest.raises(ValueError, match="count"):
        ConfirmedServiceDateCandidate("CASE-200", 3, 5, dates, 3)


def test_confirmed_service_date_fingerprint_tracks_owner_versions() -> None:
    dates = (date(2026, 8, 30), date(2026, 9, 1))
    base = ConfirmedServiceDateCandidate("CASE-200", 3, 5, dates, 2)
    order_changed = ConfirmedServiceDateCandidate("CASE-200", 4, 5, dates, 2)
    scheduling_changed = ConfirmedServiceDateCandidate("CASE-200", 3, 6, dates, 2)

    assert base.fingerprint == base.fingerprint
    assert base.fingerprint != order_changed.fingerprint
    assert base.fingerprint != scheduling_changed.fingerprint


def test_calendar_week_grouping_uses_sunday_to_saturday_boundaries() -> None:
    grouped = group_service_dates_by_calendar_week(
        (date(2026, 8, 29), date(2026, 8, 30), date(2026, 9, 1))
    )

    assert grouped == (
        {
            "week_number": 1,
            "period_start": "2026-08-23",
            "period_end": "2026-08-29",
            "service_dates": ["2026-08-29"],
            "service_day_count": 1,
        },
        {
            "week_number": 2,
            "period_start": "2026-08-30",
            "period_end": "2026-09-05",
            "service_dates": ["2026-08-30", "2026-09-01"],
            "service_day_count": 2,
        },
    )


def test_order_lifecycle_root_facts_reject_noncanonical_identity_and_non_boolean_roots() -> None:
    valid = OrderLifecycleRootFacts(
        case_no="CASE-300",
        current_status=OrderLifecycleStatus.DISCUSSION,
        contract_completed=False,
        actual_start_date=None,
        actual_start_reconfirmed=False,
        cancellation_effective=False,
        service_data_locked=False,
    )
    assert valid.current_status is OrderLifecycleStatus.DISCUSSION

    with pytest.raises((TypeError, ValueError)):
        OrderLifecycleRootFacts(
            case_no=" CASE-300 ",
            current_status=OrderLifecycleStatus.DISCUSSION,
            contract_completed=False,
            actual_start_date=None,
            actual_start_reconfirmed=False,
            cancellation_effective=False,
            service_data_locked=False,
        )
    with pytest.raises(TypeError, match="boolean root"):
        OrderLifecycleRootFacts(
            case_no="CASE-300",
            current_status=OrderLifecycleStatus.DISCUSSION,
            contract_completed=1,
            actual_start_date=None,
            actual_start_reconfirmed=False,
            cancellation_effective=False,
            service_data_locked=False,
        )
