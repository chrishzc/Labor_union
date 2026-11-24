from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from subsystems.orders.lifecycle_authoritative_facts_loader import (
    load_order_lifecycle_authoritative_facts,
)


class _Cursor:
    def __init__(self, rows):
        self._rows = iter(rows)
        self.executions = []

    def execute(self, sql, values):
        self.executions.append((sql, values))

    def fetchone(self):
        return next(self._rows)

    def fetchall(self):
        return next(self._rows)


def _order(*, service_days=1, actual_end_date=date(2026, 8, 4)):
    return {
        "case_no": "G05-FACTS",
        "status": "服務中",
        "lifecycle_version": 3,
        "service_days": service_days,
        "service_hours_per_day": 8,
        "cancel_reason": None,
        "actual_start_date": date(2026, 8, 4),
        "actual_end_date": actual_end_date,
        "service_start_time": datetime.strptime("09:00", "%H:%M").time(),
        "service_end_time": datetime.strptime("17:00", "%H:%M").time(),
        "service_end_day_offset": 0,
    }


def _envelope(cursor):
    return SimpleNamespace(
        cursor=cursor,
        case_no="G05-FACTS",
        lifecycle_version=3,
        existing_lifecycle_event=None,
    )


def _rows(*, order=None, aggregate={"effective_generation_id": 8}, assignments=({"id": 11, "status": "planned"},), schedules=({"id": 21, "assignment_id": 11, "work_date": date(2026, 8, 4)},)):
    return (
        order or _order(),
        [],
        {"settlement_state": "settled", "settlement_identity": "a" * 64, "updated_at": date(2026, 8, 4)},
        aggregate,
        {"id": 8} if aggregate is not None else None,
        list(assignments),
        list(schedules),
    ) if aggregate is not None else (
        order or _order(),
        [],
        {"settlement_state": "settled", "settlement_identity": "a" * 64, "updated_at": date(2026, 8, 4)},
        None,
    )


def _facts(cursor):
    return load_order_lifecycle_authoritative_facts(
        cursor,
        _envelope(cursor),
        "evaluation_time_reached",
        datetime.fromisoformat("2026-08-04T17:00:00+08:00"),
    )["authoritative_facts"]


def test_effective_generation_facts_ignore_historical_cancelled_assignments():
    cursor = _Cursor(_rows())
    facts = _facts(cursor)
    assert facts["completion_facts_consistent"] is True
    assert facts["effective_scheduling_generation_id"] == 8
    assert facts["official_service_dates"] == ("2026-08-04",)
    assignment_lock = next(
        sql for sql, _ in cursor.executions if "case_staff_assignments" in sql
    )
    assert "WHERE generation_id=%s" in assignment_lock
    assert "WHERE case_no" not in assignment_lock


def test_date_only_service_terms_complete_at_taipei_day_end():
    order = _order()
    order.update(
        service_start_time=None,
        service_end_time=None,
        service_end_day_offset=None,
    )

    facts = _facts(_Cursor(_rows(order=order)))

    assert facts["completion_facts_consistent"] is True
    assert facts["completion_instant"] == "2026-08-04T23:59:59.999999+08:00"


@pytest.mark.parametrize(
    "rows, expected_blockers",
    [
        (_rows(aggregate=None), {"auto_complete.effective_generation_missing"}),
        (_rows(schedules=()), {"auto_complete.official_service_days_missing", "auto_complete.official_service_day_count_mismatch"}),
        (_rows(order=_order(service_days=3, actual_end_date=date(2026, 8, 2)), schedules=({"id": 21, "assignment_id": 11, "work_date": date(2026, 8, 4)},)), {"auto_complete.official_service_day_count_mismatch", "auto_complete.actual_end_date_drift"}),
        (_rows(order=_order(service_days=2), schedules=({"id": 21, "assignment_id": 11, "work_date": date(2026, 8, 4)}, {"id": 22, "assignment_id": 11, "work_date": date(2026, 8, 4)})), {"auto_complete.official_service_days_duplicated"}),
    ],
)
def test_effective_schedule_root_drift_blocks_auto_completion(rows, expected_blockers):
    facts = _facts(_Cursor(rows))
    assert facts["completion_facts_consistent"] is False
    assert expected_blockers.issubset(set(facts["transition_blockers"]["auto_complete"]))


@pytest.mark.parametrize(
    "contracted_days,daily_hours,days,overrides,expected_completion",
    [
        (2, 4, (4,), (8,), "2026-08-04T23:59:59.999999+08:00"),
        (1, 8, (4, 5), (4, 4), "2026-08-05T23:59:59.999999+08:00"),
        (3, 8, (1, 2, 4, 5), (4, 4, None, None), "2026-08-05T17:00:00+08:00"),
        (2, 4, (4, 5), (None, None), "2026-08-05T17:00:00+08:00"),
    ],
)
def test_completion_uses_conserved_daily_hours_and_only_the_final_days_time(
    contracted_days, daily_hours, days, overrides, expected_completion,
):
    order = _order(service_days=contracted_days, actual_end_date=date(2026, 8, max(days)))
    order["service_hours_per_day"] = daily_hours
    schedules = tuple(
        {"id": index + 21, "assignment_id": 11, "work_date": date(2026, 8, day),
         "service_hours_override": hours}
        for index, (day, hours) in enumerate(zip(days, overrides, strict=True))
    )

    facts = _facts(_Cursor(_rows(order=order, schedules=schedules)))

    assert facts["completion_facts_consistent"] is True
    assert facts["transition_blockers"]["auto_complete"] == ()
    assert facts["completion_instant"] == expected_completion


@pytest.mark.parametrize("overrides", [(4,), (8, 4), (3, 5)])
def test_adjusted_schedule_with_inconsistent_hours_still_blocks_completion(overrides):
    order = _order(actual_end_date=date(2026, 8, len(overrides) + 3))
    schedules = tuple(
        {"id": index + 21, "assignment_id": 11, "work_date": date(2026, 8, index + 4),
         "service_hours_override": hours}
        for index, hours in enumerate(overrides)
    )

    facts = _facts(_Cursor(_rows(order=order, schedules=schedules)))

    assert facts["completion_facts_consistent"] is False
    assert "auto_complete.official_service_hours_mismatch" in facts["transition_blockers"]["auto_complete"]


def test_adjusted_schedule_does_not_hide_an_unsynchronized_order_end():
    order = _order(actual_end_date=date(2026, 8, 4))
    schedules = ({"id": 21, "assignment_id": 11, "work_date": date(2026, 8, 5),
                  "service_hours_override": 8},)

    facts = _facts(_Cursor(_rows(order=order, schedules=schedules)))

    assert facts["completion_facts_consistent"] is False
    assert facts["transition_blockers"]["auto_complete"] == ("auto_complete.actual_end_date_drift",)


def test_coordinated_final_day_ignores_inapplicable_original_partial_times():
    order = _order()
    order["service_start_time"] = None
    schedules = ({"id": 21, "assignment_id": 11, "work_date": date(2026, 8, 4),
                  "service_hours_override": 8},)
    facts = _facts(_Cursor(_rows(order=order, schedules=schedules)))
    assert facts["completion_facts_consistent"] is True
    assert facts["completion_instant"] == "2026-08-04T23:59:59.999999+08:00"

    facts = _facts(_Cursor(_rows(order=order)))
    assert facts["completion_instant"] is None
    assert "auto_complete.service_time_terms_incomplete" in facts["transition_blockers"]["auto_complete"]
