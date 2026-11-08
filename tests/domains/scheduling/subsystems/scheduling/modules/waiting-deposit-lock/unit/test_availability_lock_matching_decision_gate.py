"""
File: test_availability_lock_matching_decision_gate.py
Description: 驗證工會確認正式配對時，以 current 正式服務日期建立等待訂金檔期鎖。
"""

from datetime import date, time

import pytest

from subsystems.scheduling import availability_lock_acquisition_workflow as workflow


class _Cursor:
    def __init__(self, rows):
        self._rows = iter(rows)
        self.executed = []

    def execute(self, statement, parameters):
        self.executed.append((statement, parameters))

    def fetchone(self):
        return next(self._rows)

    def fetchall(self):
        return next(self._rows)


def _order(status: str) -> dict[str, object]:
    return {
        "case_no": "CASE-1",
        "status": status,
        "start_date": date(2026, 8, 10),
        "end_date": date(2026, 8, 14),
    }


def _plan() -> dict[str, object]:
    return {
        "id": 8,
        "case_no": "CASE-1",
        "status": "proposed",
        "is_active": 1,
        "start_date": date(2026, 8, 10),
        "end_date": date(2026, 8, 14),
    }


def _segment() -> dict[str, object]:
    return {
        "id": 18,
        "plan_id": 8,
        "segment_order": 1,
        "staff_id": 99,
        "assigned_start_date": date(2026, 8, 10),
        "assigned_end_date": date(2026, 8, 14),
    }


def test_union_confirmed_plan_uses_current_service_dates_without_staff_contract():
    snapshot = workflow._canonical_snapshot(
        "CASE-1", 8, _order("訂單成立"), _plan(), [_segment()],
    )
    cursor = _Cursor([
        {"id": 14, "service_day_count": 5, "service_days": 5},
        [
            {"service_date": date(2026, 8, day)}
            for day in (10, 11, 12, 13, 14)
        ],
        {"id": 15},
    ])

    exact_snapshot = workflow._with_current_confirmed_service_dates(
        cursor, "CASE-1", snapshot, for_update=True,
    )
    workflow._require_customer_pre_execution_commitment(cursor, "CASE-1", 8)

    assert len(exact_snapshot["lock_rows"]) == 5
    assert "confirmed_service_date_versions" in cursor.executed[0][0]
    assert "confirmed_service_date_days" in cursor.executed[1][0]
    assert all("precontract_service_commitment" not in sql for sql, _ in cursor.executed)
    assert "contract_signing_events" in cursor.executed[2][0]


def test_waiting_lock_uses_confirmed_service_days_not_calendar_range():
    snapshot = workflow._canonical_snapshot(
        "CASE-1", 8, _order("訂單成立"), _plan(), [_segment()],
    )
    cursor = _Cursor([
        {"id": 14, "service_day_count": 3, "service_days": 3},
        [{"service_date": date(2026, 8, day)} for day in (10, 11, 14)],
    ])
    exact_snapshot = workflow._with_current_confirmed_service_dates(
        cursor, "CASE-1", snapshot, for_update=False,
    )
    occupancy = workflow._proposed_occupancy_rows(exact_snapshot)

    service_days = [row for row in occupancy if row["lock_kind"] == "service"]

    assert [row["lock_date"] for row in service_days] == [
        date(2026, 8, day) for day in (10, 11, 14)
    ]


def test_incomplete_current_service_dates_cannot_reserve_a_waiting_deposit_lock():
    cursor = _Cursor([
        {"id": 14, "service_day_count": 5, "service_days": 5},
        [{"service_date": date(2026, 8, day)} for day in (10, 11, 12)],
    ])
    snapshot = workflow._canonical_snapshot(
        "CASE-1", 8, _order("訂單成立"), _plan(), [_segment()],
    )

    with pytest.raises(ValueError, match="current confirmed service dates mismatch"):
        workflow._with_current_confirmed_service_dates(
            cursor, "CASE-1", snapshot, for_update=False,
        )


def test_single_caregiver_reserves_current_dates_after_actual_period_changes():
    snapshot = workflow._canonical_snapshot('CASE-1', 8, _order('訂單成立'), _plan(), [_segment()])
    cursor = _Cursor([
        {'id': 14, 'service_day_count': 3, 'service_days': 3},
        [{'service_date': date(2026, 9, day)} for day in (14, 15, 16)],
    ])
    current = workflow._with_current_confirmed_service_dates(cursor, 'CASE-1', snapshot, for_update=False)
    occupancy = workflow._proposed_occupancy_rows(current)
    assert [row['lock_date'] for row in occupancy if row['lock_kind'] == 'service'] == [date(2026, 9, day) for day in (14, 15, 16)]
    assert min(row['lock_date'] for row in occupancy if row['lock_kind'] == 'buffer') == date(2026, 9, 17)
    assert snapshot['case_start_date'] == '2026-08-10'


def test_legacy_matching_acceptance_remains_a_valid_customer_gate():
    cursor = _Cursor([None, {"response_value": "accepted"}])

    workflow._require_customer_pre_execution_commitment(cursor, "CASE-1", 8)

    assert "contract_signing_events" in cursor.executed[0][0]
    assert "matching_response_events" in cursor.executed[1][0]


def test_terminal_order_cannot_reserve_a_pre_execution_lock():
    with pytest.raises(ValueError, match="not eligible"):
        workflow._canonical_snapshot("CASE-1", 8, _order("已結案"), _plan(), [])


def test_empty_dbapi_tuple_is_a_valid_empty_occupancy_result():
    class TupleCursor:
        def fetchall(self):
            return ()

    assert workflow._rows(TupleCursor(), "invalid") == []


@pytest.mark.parametrize("service_day,expected_allowed", [(12, False), (15, True)])
def test_service_collision_blocks_but_proposed_buffer_collision_only_warns(service_day, expected_allowed):
    snapshot = workflow._canonical_snapshot("CASE-1", 8, _order("訂單成立"), _plan(), [_segment()])
    cursor = _Cursor([
        {"service_start_time": time(9), "service_end_time": time(17),
         "service_end_day_offset": 0},
        [],  # effective service-day schedules
        [],  # active waiting service-day locks
        [{"id": 7, "staff_id": 99, "case_no": "OTHER-CASE-7",
          "assigned_start_date": date(2026, 8, service_day),
          "assigned_end_date": date(2026, 8, service_day)}],
        [],  # staff unavailability
        [],  # registered assignment buffers
        [],  # active waiting-buffer segments
    ])
    conflicts = workflow._occupancy_conflicts(cursor, snapshot)
    preview = workflow._build_acquire_preview(snapshot, conflicts)
    assert preview["apply_allowed"] is expected_allowed
    assert conflicts[0]["source_type"] == ("buffer" if expected_allowed else "assignment")


def test_existing_buffer_on_requested_service_date_is_advisory():
    snapshot = workflow._canonical_snapshot("CASE-1", 8, _order("訂單成立"), _plan(), [_segment()])
    cursor = _Cursor([
        {"service_start_time": time(9), "service_end_time": time(17),
         "service_end_day_offset": 0},
        [],  # effective service-day schedules
        [],  # active waiting service-day locks
        [],  # legacy assignments
        [],  # staff unavailability
        [{"source_id": 7, "staff_id": 99, "lock_date": date(2026, 8, 12)}],
        [],  # active waiting-buffer segments
    ])
    conflicts = workflow._occupancy_conflicts(cursor, snapshot)
    assert workflow._build_acquire_preview(snapshot, conflicts)["apply_allowed"] is True
    assert conflicts[0]["source_type"] == "buffer"


@pytest.mark.parametrize(
    "wanted_clock,source_kind,source_day,source_clock,expected_allowed,expected_conflicts",
    [
        ((9, 17, 0), "schedule", 12, (18, 20, 0), True, []),
        ((9, 17, 0), "schedule", 12, (17, 20, 0), True, []),
        ((9, 17, 0), "schedule", 12, (16, 18, 0), False, [(12, "schedule")]),
        ((9, 17, 0), "schedule", 15, (18, 20, 0), True, [(15, "buffer")]),
        ((9, 17, 0), "schedule", 14, (22, 2, 1), True, [(15, "buffer")]),
        ((9, 17, 0), "schedule", 14, (22, 0, 1), True, []),
        ((22, 2, 1), "schedule", 15, (1, 3, 0), False, [(14, "schedule"), (15, "buffer")]),
        ((22, 2, 1), "schedule", 22, (1, 3, 0), True, []),
        ((9, 17, 0), "schedule", 21, (23, 2, 1), True, [(21, "buffer")]),
        ((9, 17, 0), "schedule", 15, None, True, [(15, "buffer")]),
        ((9, 17, 0), "schedule", 12, None, False, [(12, "schedule")]),
        ((9, 17, 0), "schedule", 22, None, True, []),
        ((9, 17, 0), "active_lock", 15, (18, 20, 0), True, [(15, "buffer")]),
        ((9, 17, 0), "active_lock", 12, (16, 18, 0), False, [(12, "active_lock")]),
    ],
    ids=[
        "same-day-service-nonoverlap", "half-open-service-boundary", "actual-service-overlap",
        "buffer-is-calendar-date", "source-overnight-enters-buffer", "midnight-end-is-exclusive",
        "actual-overnight-block-survives-buffer", "no-proposed-clock-spill-past-seven-days",
        "last-buffer-day-included", "unknown-source-clock-buffer-advisory",
        "unknown-source-clock-service-refused", "unknown-source-outside-buffer-not-invented",
        "waiting-lock-buffer-date", "waiting-lock-actual-service-block",
    ],
)
def test_buffer_dates_and_actual_service_shifts_remain_distinct(
    wanted_clock, source_kind, source_day, source_clock, expected_allowed, expected_conflicts,
):
    snapshot = workflow._canonical_snapshot("CASE-1", 8, _order("訂單成立"), _plan(), [_segment()])
    start, end, offset = wanted_clock
    source_start, source_end, source_offset = source_clock or (None, None, None)
    source_rows = [{
        "source_id": 7, "staff_id": 99, "case_no": "OTHER-CASE-7",
        "occupancy_date": date(2026, 8, source_day),
        "service_start_time": time(source_start) if source_start is not None else None,
        "service_end_time": time(source_end) if source_end is not None else None,
        "service_end_day_offset": source_offset,
    }]
    if source_kind == "active_lock":
        source_rows[0]["lock_id"] = 17
    cursor = _Cursor([
        {"service_start_time": time(start), "service_end_time": time(end),
         "service_end_day_offset": offset},
        source_rows if source_kind == "schedule" else [],
        source_rows if source_kind == "active_lock" else [],
        [], [], [], [],
    ])

    conflicts = workflow._occupancy_conflicts(cursor, snapshot)

    assert workflow._build_acquire_preview(snapshot, conflicts)["apply_allowed"] is expected_allowed
    assert conflicts == [
        {"staff_id": 99, "lock_date": f"2026-08-{day:02d}", "source_type": kind, "source_id": 7}
        for day, kind in expected_conflicts
    ]


@pytest.mark.parametrize("source_kind", ["assignment", "staff_unavailability"])
@pytest.mark.parametrize("source_day", [15, 22])
def test_buffer_date_ranges_do_not_borrow_proposed_overnight_clock(source_kind, source_day):
    snapshot = workflow._canonical_snapshot("CASE-1", 8, _order("訂單成立"), _plan(), [_segment()])
    day = date(2026, 8, source_day)
    assignments = [{"id": 7, "staff_id": 99, "case_no": "OTHER-CASE-7",
                    "assigned_start_date": day, "assigned_end_date": day}]
    blocks = [{"id": 7, "staff_id": 99, "start_date": day, "end_date": day}]
    cursor = _Cursor([
        {"service_start_time": time(22), "service_end_time": time(2),
         "service_end_day_offset": 1},
        [], [],
        assignments if source_kind == "assignment" else [],
        blocks if source_kind == "staff_unavailability" else [],
        [], [],
    ])

    conflicts = workflow._occupancy_conflicts(cursor, snapshot)

    # A source on15 also intersects the real14 overnight service, which must stay blocking.
    if source_day == 15:
        assert conflicts == [
            {"staff_id": 99, "lock_date": "2026-08-14", "source_type": source_kind, "source_id": 7},
            {"staff_id": 99, "lock_date": "2026-08-15", "source_type": "buffer", "source_id": 7},
        ]
        assert workflow._build_acquire_preview(snapshot, conflicts)["apply_allowed"] is False
    else:
        assert conflicts == []
        assert workflow._build_acquire_preview(snapshot, conflicts)["apply_allowed"] is True


@pytest.mark.parametrize("clock_row", [None, {"service_start_time": time(9)}])
def test_missing_orders_clock_is_still_refused_before_occupancy_read(clock_row):
    snapshot = workflow._canonical_snapshot("CASE-1", 8, _order("訂單成立"), _plan(), [_segment()])
    cursor = _Cursor([clock_row])

    with pytest.raises(ValueError, match="service_time_terms_incomplete"):
        workflow._occupancy_conflicts(cursor, snapshot)

    assert len(cursor.executed) == 1


@pytest.mark.parametrize("source_day", [12, 22])
def test_open_ended_pause_preserves_service_and_buffer_date_bounds(source_day):
    snapshot = workflow._canonical_snapshot("CASE-1", 8, _order("訂單成立"), _plan(), [_segment()])
    cursor = _Cursor([
        {"service_start_time": time(9), "service_end_time": time(17),
         "service_end_day_offset": 0},
        [], [], [],
        # The paused_service owner allows a NULL end_date; this is not a missing row.
        [{"id": 7, "staff_id": 99, "start_date": date(2026, 8, source_day), "end_date": None}],
        [], [],
    ])

    conflicts = workflow._occupancy_conflicts(cursor, snapshot)

    if source_day == 12:
        assert conflicts == [
            {"staff_id": 99, "lock_date": f"2026-08-{day:02d}",
             "source_type": "staff_unavailability" if day <= 14 else "buffer", "source_id": 7}
            for day in range(12, 22)
        ]
        assert workflow._build_acquire_preview(snapshot, conflicts)["apply_allowed"] is False
    else:
        assert conflicts == []
        assert workflow._build_acquire_preview(snapshot, conflicts)["apply_allowed"] is True
