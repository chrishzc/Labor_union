"""
File: test_historical_baseline_scheduling_owner_adapter.py
Description: 驗證 Scheduling owner observations 的鎖定、日期集合與時鐘語意。
"""

from __future__ import annotations

from datetime import date, datetime, time

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalOrderIdentity,
)
from infrastructure.mysql.historical_baseline_scheduling_owner_adapter import (
    MySqlHistoricalBaselineSchedulingOwnerAdapter,
)
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE


IDENTITY = HistoricalOrderIdentity("order:CASE-1", "CASE-1")
DATE_DESCRIPTOR = next(
    item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.root_identity_kind == "confirmed_service_date"
)
GENERATION_DESCRIPTOR = next(
    item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.root_identity_kind == "effective_generation"
)
ASSIGNMENT_DATE_DESCRIPTOR = next(
    item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.root_identity_kind == "assignment_official_date"
)
OFFICIAL_DESCRIPTOR = next(
    item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.root_identity_kind == "official_service"
)


class Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))

    def fetchall(self):
        return self.responses.pop(0)


class Connection:
    def __init__(self, responses):
        self.cursor_instance = Cursor(responses)

    def cursor(self):
        return self.cursor_instance


def _clock(value):
    return FixedBusinessClock(datetime.combine(value[0], value[1], tzinfo=TAIPEI_TIME_ZONE))


def _date_rows(days=2):
    return [
        {"order_case_no": "CASE-1", "service_days": days, "version_id": 9, "confirmed_version": 3, "is_current": 1}
    ], [
        {"confirmed_version_id": 9, "ordinal": 1, "service_date": date(2026, 8, 1)},
        {"confirmed_version_id": 9, "ordinal": 2, "service_date": date(2026, 8, 2)},
    ][:days]


def _official_rows():
    common = {
        "order_case_no": "CASE-1",
        "service_days": 2,
        "service_start_time": time(9),
        "service_end_time": time(17),
        "service_end_day_offset": 0,
        "assignment_case_no": "CASE-1",
        "assignment_generation_id": 21,
        "assignment_staff_id": 100,
        "assignment_status": "completed",
        "assigned_start_date": date(2026, 8, 1),
        "assigned_end_date": date(2026, 8, 2),
        "schedule_case_no": "CASE-1",
        "schedule_generation_id": 21,
        "schedule_staff_id": 100,
        "schedule_effective_marker": 1,
        "schedule_is_work_day": 1,
        "generation_id": 21,
        "generation_status": "effective",
        "generation_effective_marker": 1,
        "effective_generation_id": 21,
        "aggregate_version": 4,
        "rebuild_event_id": 31,
        "resulting_scheduling_version": 4,
    }
    return [
        {
            **common,
            "assignment_id": 101,
            "schedule_id": 201,
            "schedule_assignment_id": 101,
            "work_date": date(2026, 8, 1),
        },
        {
            **common,
            "assignment_id": 102,
            "schedule_id": 202,
            "schedule_assignment_id": 102,
            "assignment_staff_id": 101,
            "schedule_staff_id": 101,
            "work_date": date(2026, 8, 2),
        },
    ]


def test_confirmed_dates_are_exact_and_for_update_is_forwarded_to_every_read():
    first, second = _date_rows()
    connection = Connection([first, second])
    result = MySqlHistoricalBaselineSchedulingOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DATE_DESCRIPTOR, for_update=True
    )
    assert [item.root_identity.split(":")[-1] for item in result.observations] == ["2026-08-01", "2026-08-02"]
    assert len(connection.cursor_instance.calls) == 2
    assert all("FOR UPDATE" in statement for statement, _ in connection.cursor_instance.calls)


def test_confirmed_dates_count_drift_is_typed_unavailable():
    first, second = _date_rows(days=3)
    connection = Connection([first, second])
    result = MySqlHistoricalBaselineSchedulingOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DATE_DESCRIPTOR
    )
    assert not result.observations[0].available
    assert result.observations[0].unavailable_code.endswith("count_drift")


def test_effective_generation_requires_exact_rebuild_event_version():
    connection = Connection([[{
        "aggregate_case_no": "CASE-1", "aggregate_version": 4, "effective_generation_id": 21,
        "generation_id": 21, "generation_case_no": "CASE-1", "resulting_aggregate_version": 4,
        "generation_status": "effective", "effective_marker": 1,
        "rebuild_event_id": 31, "rebuild_case_no": "CASE-1", "new_generation_id": 21,
        "expected_scheduling_version": 3, "resulting_scheduling_version": 4,
    }]])
    result = MySqlHistoricalBaselineSchedulingOwnerAdapter(connection).read_owner_observations(
        IDENTITY, GENERATION_DESCRIPTOR, for_update=True
    )
    assert result.observations[0].available
    assert result.observations[0].source_version == 4
    assert "FOR UPDATE" in connection.cursor_instance.calls[0][0]


def test_assignment_dates_bind_each_date_to_non_cancelled_assignment_owner():
    connection = Connection([_official_rows()])
    result = MySqlHistoricalBaselineSchedulingOwnerAdapter(connection).read_owner_observations(
        IDENTITY, ASSIGNMENT_DATE_DESCRIPTOR
    )
    assert len(result.observations) == 2
    assert {"assignment:101" in item.root_identity for item in result.observations} == {True, False}


def test_official_service_is_not_terminal_before_schedule_and_is_terminal_after_all_dates():
    future = Connection([_official_rows()])
    before = MySqlHistoricalBaselineSchedulingOwnerAdapter(
        future, _clock((date(2026, 7, 31), time(23)))
    ).read_owner_observations(IDENTITY, OFFICIAL_DESCRIPTOR)
    assert before.observations[0].terminal_result is False

    elapsed = Connection([_official_rows()])
    after = MySqlHistoricalBaselineSchedulingOwnerAdapter(
        elapsed, _clock((date(2026, 8, 2), time(18)))
    ).read_owner_observations(IDENTITY, OFFICIAL_DESCRIPTOR)
    assert after.observations[0].terminal_result is True


def test_malformed_unhashable_fields_fail_closed_as_typed_unavailable():
    malformed_case = _official_rows()
    malformed_case[0]["order_case_no"] = ["CASE-1"]
    result = MySqlHistoricalBaselineSchedulingOwnerAdapter(
        Connection([malformed_case])
    ).read_owner_observations(IDENTITY, ASSIGNMENT_DATE_DESCRIPTOR)
    assert not result.observations[0].available

    malformed_date = _official_rows()
    malformed_date[0]["work_date"] = [date(2026, 8, 1)]
    result = MySqlHistoricalBaselineSchedulingOwnerAdapter(
        Connection([malformed_date])
    ).read_owner_observations(IDENTITY, OFFICIAL_DESCRIPTOR)
    assert not result.observations[0].available

    malformed_generation = [{
        "aggregate_case_no": "CASE-1", "aggregate_version": [4],
        "effective_generation_id": 21, "generation_id": 21,
        "generation_case_no": "CASE-1", "resulting_aggregate_version": 4,
        "generation_status": "effective", "effective_marker": 1,
        "rebuild_event_id": 31, "rebuild_case_no": "CASE-1",
        "new_generation_id": 21, "expected_scheduling_version": 3,
        "resulting_scheduling_version": 4,
    }]
    result = MySqlHistoricalBaselineSchedulingOwnerAdapter(
        Connection([malformed_generation])
    ).read_owner_observations(IDENTITY, GENERATION_DESCRIPTOR)
    assert not result.observations[0].available


def test_assignment_and_schedule_staff_ids_must_be_positive_integers_and_equal():
    for field, value in (
        ("assignment_staff_id", None),
        ("assignment_staff_id", True),
        ("assignment_staff_id", "100"),
        ("schedule_staff_id", None),
        ("schedule_staff_id", False),
        ("schedule_staff_id", "100"),
    ):
        rows = _official_rows()
        rows[0][field] = value
        result = MySqlHistoricalBaselineSchedulingOwnerAdapter(
            Connection([rows])
        ).read_owner_observations(IDENTITY, ASSIGNMENT_DATE_DESCRIPTOR)
        assert not result.observations[0].available

    rows = _official_rows()
    rows[0]["schedule_staff_id"] = 101
    result = MySqlHistoricalBaselineSchedulingOwnerAdapter(
        Connection([rows])
    ).read_owner_observations(IDENTITY, OFFICIAL_DESCRIPTOR)
    assert not result.observations[0].available
