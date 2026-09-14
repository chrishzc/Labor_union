"""
File: test_availability_lock_matching_decision_gate.py
Description: 驗證工會確認正式配對時，以 current 正式服務日期建立等待訂金檔期鎖。
"""

from datetime import date

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
