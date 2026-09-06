"""
File: test_historical_orders_scheduling_completion_read_adapter.py
Description: 驗證 Orders／Scheduling 完成根 read adapter 的一致快照與完整性語意。
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.historical_orders_scheduling_completion_read_adapter import (
    MySqlHistoricalOrdersSchedulingCompletionReadAdapter,
    _CURRENT_CASE_READ_SQL,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        normalized = statement.lower()
        if any(keyword in normalized for keyword in ("insert", "update", "delete", "for update")):
            raise AssertionError("completion read adapter must not write or lock")
        self.calls.append((statement, parameters))

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


def _order(**changes):
    row = {
        "row_kind": "order",
        "case_no": "CASE-1",
        "lifecycle_version": 7,
        "status": "訂單完成",
        "actual_start_date": date(2026, 8, 1),
        "service_days": 2,
        "service_start_time": time(9),
        "service_end_time": time(17),
        "service_end_day_offset": 0,
    }
    row.update(changes)
    return row


def _completion(**changes):
    row = {
        "row_kind": "completion",
        "completion_event_id": 77,
        "completion_case_no": "CASE-1",
        "completion_after_status": "訂單完成",
        "completion_expected_version": 6,
    }
    row.update(changes)
    return row


def _aggregate(**changes):
    row = {
        "row_kind": "aggregate",
        "aggregate_case_no": "CASE-1",
        "aggregate_version": 3,
        "effective_generation_id": 9,
    }
    row.update(changes)
    return row


def _generation(**changes):
    row = {
        "row_kind": "generation",
        "generation_id": 9,
        "generation_case_no": "CASE-1",
        "generation_resulting_aggregate_version": 3,
        "generation_status": "effective",
        "generation_effective_marker": 1,
    }
    row.update(changes)
    return row


def _assignment(assignment_id=101, **changes):
    row = {
        "row_kind": "assignment",
        "assignment_id": assignment_id,
        "assignment_case_no": "CASE-1",
        "assignment_generation_id": 9,
        "assignment_staff_id": 501,
        "assignment_status": "completed",
        "assignment_start_date": date(2026, 8, 1),
        "assignment_end_date": date(2026, 8, 2),
    }
    row.update(changes)
    return row


def _schedule(schedule_id, work_date, assignment_id=101, **changes):
    row = {
        "row_kind": "schedule",
        "schedule_id": schedule_id,
        "schedule_case_no": "CASE-1",
        "schedule_generation_id": 9,
        "schedule_assignment_id": assignment_id,
        "schedule_staff_id": 501,
        "work_date": work_date,
        "schedule_effective_marker": 1,
        "schedule_is_work_day": 1,
    }
    row.update(changes)
    return row


def _rows(*, order=None, completion=None, aggregate=None, generation=None, assignments=None, schedules=None):
    rows = [order or _order()]
    rows.extend(completion if completion is not None else [_completion()])
    rows.extend(aggregate if aggregate is not None else [_aggregate()])
    rows.extend(generation if generation is not None else [_generation()])
    rows.extend(assignments if assignments is not None else [_assignment()])
    rows.extend(schedules if schedules is not None else [_schedule(201, date(2026, 8, 1)), _schedule(202, date(2026, 8, 2))])
    return rows


def _adapter(rows=None):
    connection = _Connection(rows if rows is not None else _rows())
    return MySqlHistoricalOrdersSchedulingCompletionReadAdapter(connection), connection


def test_complete_readback_uses_real_completion_event_and_current_generation():
    adapter, connection = _adapter()

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.case_no == "CASE-1"
    assert result.lifecycle_version == 7
    assert result.canonical_status is OrderLifecycleStatus.COMPLETED
    assert result.completion_lineage_identity == "orders-completion-event:CASE-1:77"
    assert result.actual_start_date == date(2026, 8, 1)
    assert result.official_service_dates == (date(2026, 8, 1), date(2026, 8, 2))
    assert result.required_service_day_count == 2
    assert result.service_time_tuple_complete
    assert result.integrity_blockers == ()
    assert len(connection.cursor_instance.calls) == 1
    assert all("FOR UPDATE" not in statement.upper() for statement, _ in connection.cursor_instance.calls)


def test_mysql_timedelta_service_times_are_valid_time_of_day_roots():
    adapter, _ = _adapter(
        rows=_rows(
            order=_order(
                service_start_time=timedelta(hours=9),
                service_end_time=timedelta(hours=17),
            )
        )
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.service_time_tuple_complete is True
    assert "scheduling.service_time_terms_invalid" not in result.integrity_blockers


@pytest.mark.parametrize("invalid", [timedelta(seconds=-1), timedelta(days=1)])
def test_mysql_time_outside_one_day_fails_closed(invalid):
    adapter, _ = _adapter(rows=_rows(order=_order(service_start_time=invalid)))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.service_time_tuple_complete is False
    assert "scheduling.service_time_terms_invalid" in result.integrity_blockers


def test_missing_order_returns_none_from_same_single_read_statement():
    adapter, connection = _adapter(rows=[])

    assert adapter.load_completion_readback("CASE-1") is None
    assert len(connection.cursor_instance.calls) == 1


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"actual_start_date": None}, "orders.actual_start_date_missing"),
        ({"service_start_time": None}, "scheduling.service_time_terms_incomplete"),
        ({"service_start_time": "09:00:00"}, "scheduling.service_time_terms_invalid"),
    ],
)
def test_missing_order_root_is_returned_as_readback_blocker(change, expected):
    adapter, _ = _adapter(rows=_rows(order=_order(**change)))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert expected in result.integrity_blockers


def test_completion_event_must_prove_resulting_current_order_version():
    adapter, _ = _adapter(rows=_rows(completion=[_completion(completion_expected_version=5)]))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.completion_lineage_identity is None
    assert "orders.completion_lineage_version_mismatch" in result.integrity_blockers


def test_oversized_completion_event_identity_returns_actionable_blocker():
    adapter, _ = _adapter(
        rows=_rows(completion=[_completion(completion_event_id=10**191)])
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and result.readback_available
    assert "orders.completion_event_identity_invalid" in result.integrity_blockers
    assert result.completion_lineage_identity is None


@pytest.mark.parametrize(
    "rows",
    [
        _rows(aggregate=[_aggregate(effective_generation_id=9_223_372_036_854_775_808)]),
        _rows(assignments=[_assignment(assignment_id=9_223_372_036_854_775_808)]),
        _rows(schedules=[
            _schedule(9_223_372_036_854_775_808, date(2026, 8, 1)),
            _schedule(202, date(2026, 8, 2)),
        ]),
    ],
)
def test_database_identity_fields_enforce_signed_bigint_upper_bound(rows):
    adapter, _ = _adapter(rows=rows)

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and result.readback_available


def test_older_completion_events_do_not_replace_current_completion_lineage():
    adapter, _ = _adapter(
        rows=_rows(
            completion=[
                _completion(completion_event_id=70, completion_expected_version=5),
                _completion(completion_event_id=77, completion_expected_version=6),
            ]
        )
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.completion_lineage_identity == "orders-completion-event:CASE-1:77"
    assert result.integrity_blockers == ()


def test_duplicate_completion_events_fail_closed():
    adapter, _ = _adapter(rows=_rows(completion=[_completion(), _completion(completion_event_id=78)]))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.completion_lineage_identity is None
    assert "orders.completion_lineage_duplicate" in result.integrity_blockers


def test_missing_completion_and_scheduling_roots_stay_explicitly_incomplete():
    adapter, _ = _adapter(rows=[_order()])

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.completion_lineage_identity is None
    assert result.official_service_fact_identity is None
    assert "orders.completion_lineage_missing" in result.integrity_blockers
    assert "scheduling.aggregate_missing" in result.integrity_blockers


def test_generation_resulting_version_must_match_scheduling_aggregate():
    adapter, _ = _adapter(rows=_rows(generation=[_generation(generation_resulting_aggregate_version=2)]))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.official_service_fact_identity is None
    assert "scheduling.generation_version_mismatch" in result.integrity_blockers


def test_assignment_case_identity_and_generation_are_exact():
    adapter, _ = _adapter(rows=_rows(assignments=[_assignment(assignment_case_no="CASE-2")]))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "scheduling_assignment_case_identity_mismatch" in result.integrity_blockers
    assert result.official_service_fact_identity is None


def test_duplicate_assignment_identity_fails_closed_without_exception():
    adapter, _ = _adapter(rows=_rows(assignments=[_assignment(), _assignment(assignment_staff_id=502)]))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "scheduling.assignment_identity_conflict" in result.integrity_blockers
    assert result.official_service_fact_identity is None


def test_identical_duplicate_assignment_identity_fails_closed():
    adapter, _ = _adapter(rows=_rows(assignments=[_assignment(), _assignment()]))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and result.readback_available
    assert "scheduling.assignment_identity_duplicate" in result.integrity_blockers
    assert result.official_service_fact_identity is None


def test_replaced_assignment_history_is_ignored_when_current_completed_assignment_covers_case():
    historical_assignment = _assignment(
        100,
        assignment_staff_id=499,
        assignment_status="replaced",
    )
    historical_schedules = [
        _schedule(190, date(2026, 8, 1), assignment_id=100, schedule_staff_id=499),
        _schedule(191, date(2026, 8, 2), assignment_id=100, schedule_staff_id=499),
    ]
    adapter, _ = _adapter(
        rows=_rows(
            assignments=[historical_assignment, _assignment(101, assignment_staff_id=501)],
            schedules=historical_schedules
            + [
                _schedule(201, date(2026, 8, 1), assignment_id=101),
                _schedule(202, date(2026, 8, 2), assignment_id=101),
            ],
        )
    )
    baseline_adapter, _ = _adapter(
        rows=_rows(
            assignments=[_assignment(101, assignment_staff_id=501)],
            schedules=[
                _schedule(201, date(2026, 8, 1), assignment_id=101),
                _schedule(202, date(2026, 8, 2), assignment_id=101),
            ],
        )
    )

    result = adapter.load_completion_readback("CASE-1")
    baseline = baseline_adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert baseline is not None
    assert result.integrity_blockers == ()
    assert result.official_service_dates == (date(2026, 8, 1), date(2026, 8, 2))
    assert result.official_service_fact_identity == baseline.official_service_fact_identity


def test_unknown_assignment_status_remains_a_fail_closed_integrity_blocker():
    adapter, _ = _adapter(rows=_rows(assignments=[_assignment(assignment_status="unknown")]))

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "scheduling.assignment_status_invalid" in result.integrity_blockers
    assert result.official_service_fact_identity is None


def test_duplicate_official_date_and_owner_conflict_fail_closed():
    adapter, _ = _adapter(
        rows=_rows(
            schedules=[
                _schedule(201, date(2026, 8, 1)),
                _schedule(202, date(2026, 8, 1), assignment_id=999),
            ]
        )
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "scheduling.official_service_dates_duplicated" in result.integrity_blockers
    assert "scheduling.official_service_owner_inconsistent" in result.integrity_blockers
    assert result.official_service_fact_identity is None
    assert len(result.official_service_dates) == 1


def test_official_schedule_date_must_be_within_assignment_period():
    adapter, _ = _adapter(
        rows=_rows(
            schedules=[
                _schedule(201, date(2026, 7, 31)),
                _schedule(202, date(2026, 8, 2)),
            ]
        )
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and result.readback_available
    assert "scheduling.official_service_date_outside_assignment" in result.integrity_blockers
    assert result.official_service_fact_identity is None


def test_for_update_is_rejected_before_opening_cursor():
    adapter, connection = _adapter()

    with pytest.raises(ValueError, match="read-only"):
        adapter.load_completion_readback("CASE-1", for_update=True)

    assert connection.cursor_instance.calls == []

    with pytest.raises(ValueError, match="read-only"):
        adapter.load_completion_readback("CASE-1", for_update=0)


def test_database_identity_mismatch_is_rejected_for_order_root():
    adapter, _ = _adapter(rows=_rows(order=_order(case_no="CASE-2")))

    with pytest.raises(ValueError, match="identity mismatch"):
        adapter.load_completion_readback("CASE-1")


def test_invalid_canonical_order_status_is_rejected():
    adapter, _ = _adapter(rows=_rows(order=_order(status="not-a-status")))

    with pytest.raises(ValueError, match="canonical status"):
        adapter.load_completion_readback("CASE-1")


def test_unhashable_row_kind_is_rejected_without_raw_type_error():
    rows = _rows()
    rows[-1]["row_kind"] = []
    adapter, _ = _adapter(rows=rows)

    with pytest.raises(ValueError, match="unknown row kind"):
        adapter.load_completion_readback("CASE-1")


def test_unhashable_assignment_status_and_schedule_owner_fail_closed():
    status_adapter, _ = _adapter(
        rows=_rows(assignments=[_assignment(assignment_status=[])])
    )
    status_result = status_adapter.load_completion_readback("CASE-1")

    owner_adapter, _ = _adapter(
        rows=_rows(
            schedules=[
                _schedule(201, date(2026, 8, 1), assignment_id=[]),
                _schedule(202, date(2026, 8, 2)),
            ]
        )
    )
    owner_result = owner_adapter.load_completion_readback("CASE-1")

    assert status_result is not None
    assert "scheduling.assignment_status_invalid" in status_result.integrity_blockers
    assert owner_result is not None
    assert "scheduling.official_service_owner_inconsistent" in owner_result.integrity_blockers


def test_boolean_and_malformed_scheduling_flags_fail_closed():
    generation_adapter, _ = _adapter(
        rows=_rows(generation=[_generation(generation_effective_marker=True)])
    )
    generation_result = generation_adapter.load_completion_readback("CASE-1")

    schedule_rows = _rows()
    schedule_rows.append(
        _schedule(
            203,
            date(2026, 8, 3),
            schedule_effective_marker="garbage",
            schedule_is_work_day="garbage",
        )
    )
    schedule_adapter, _ = _adapter(rows=schedule_rows)
    schedule_result = schedule_adapter.load_completion_readback("CASE-1")

    assert generation_result is not None
    assert "scheduling.effective_generation_invalid" in generation_result.integrity_blockers
    assert schedule_result is not None
    assert "scheduling.schedule_effective_marker_invalid" in schedule_result.integrity_blockers


def test_assignment_staff_dates_and_float_service_offset_fail_closed():
    staff_adapter, _ = _adapter(
        rows=_rows(
            assignments=[_assignment(assignment_staff_id=[])],
            schedules=[
                _schedule(201, date(2026, 8, 1), schedule_staff_id=[]),
                _schedule(202, date(2026, 8, 2), schedule_staff_id=[]),
            ],
        )
    )
    staff_result = staff_adapter.load_completion_readback("CASE-1")

    date_adapter, _ = _adapter(
        rows=_rows(assignments=[_assignment(assignment_start_date="2026-99-99")])
    )
    date_result = date_adapter.load_completion_readback("CASE-1")

    offset_adapter, _ = _adapter(
        rows=_rows(order=_order(service_end_day_offset=0.0))
    )
    offset_result = offset_adapter.load_completion_readback("CASE-1")

    assert staff_result is not None
    assert "scheduling.assignment_staff_identity_invalid" in staff_result.integrity_blockers
    assert date_result is not None
    assert "scheduling.assignment_service_period_invalid" in date_result.integrity_blockers
    assert offset_result is not None
    assert "scheduling.service_time_terms_invalid" in offset_result.integrity_blockers


def test_each_union_branch_has_the_same_engine_column_count() -> None:
    counts = []
    for branch in _CURRENT_CASE_READ_SQL.strip().split("UNION ALL"):
        select_list = branch.split("FROM", 1)[0].removeprefix("SELECT ")
        depth = 0
        count = 1
        for character in select_list:
            depth += character == "("
            depth -= character == ")"
            if character == "," and depth == 0:
                count += 1
        counts.append(count)

    assert counts == [48] * 7
