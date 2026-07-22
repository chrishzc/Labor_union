from datetime import date

import pytest

from services.multi_caregiver_assignment_rules import (
    validate_non_overlapping_assignment_interval,
)


def _assignment(assignment_id, start, end, status="active"):
    return {
        "id": assignment_id,
        "status": status,
        "assigned_start_date": start,
        "assigned_end_date": end,
    }


def test_adjacent_service_intervals_are_valid():
    interval = validate_non_overlapping_assignment_interval(
        "2026-06-11",
        "2026-06-20",
        [_assignment(1, "2026-06-01", "2026-06-10")],
    )

    assert interval == (date(2026, 6, 11), date(2026, 6, 20))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-06-10", "2026-06-15"),
        ("2026-06-05", "2026-06-10"),
        ("2026-06-01", "2026-06-20"),
    ],
)
def test_any_shared_service_date_is_rejected(start, end):
    with pytest.raises(ValueError, match="overlaps assignment 1"):
        validate_non_overlapping_assignment_interval(
            start,
            end,
            [_assignment(1, "2026-06-01", "2026-06-10")],
        )


def test_cancelled_and_current_assignment_do_not_reserve_dates():
    interval = validate_non_overlapping_assignment_interval(
        "2026-06-01",
        "2026-06-10",
        [
            _assignment(1, "2026-06-01", "2026-06-10"),
            _assignment(2, "2026-06-01", "2026-06-10", status="cancelled"),
        ],
        candidate_assignment_id=1,
    )

    assert interval == (date(2026, 6, 1), date(2026, 6, 10))


def test_active_assignment_without_complete_dates_requires_review():
    with pytest.raises(ValueError, match="requires review"):
        validate_non_overlapping_assignment_interval(
            "2026-06-11",
            "2026-06-20",
            [_assignment(1, None, "2026-06-10")],
        )


def test_invalid_candidate_range_is_rejected():
    with pytest.raises(ValueError, match="must not be after"):
        validate_non_overlapping_assignment_interval(
            "2026-06-20",
            "2026-06-11",
            [],
        )
