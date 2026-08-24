"""
File: test_availability_lock_contract_signing_gate.py
Description: 驗證等待訂金檔期鎖只接受有效且精確的簽約前服務承諾。
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


def test_deposit_established_case_is_eligible_after_contract_signing():
    snapshot = workflow._canonical_snapshot(
        "CASE-1", 8, _order("訂單成立"), _plan(), [_segment()],
    )
    cursor = _Cursor([
        {"id": 14, "case_no": "CASE-1"},
        {"service_days": 5, "commitment_days": 5, "distinct_service_dates": 5},
        [
            {"matching_segment_id": 18, "staff_id": 99, "service_date": date(2026, 8, day)}
            for day in (10, 11, 12, 13, 14)
        ],
        {"id": 15},
    ])

    workflow._require_active_precontract_commitment(cursor, 8)
    workflow._require_customer_pre_execution_commitment(cursor, "CASE-1", 8)

    assert snapshot["case_no"] == "CASE-1"
    assert "precontract_service_commitments" in cursor.executed[0][0]
    assert "precontract_service_commitment_days" in cursor.executed[1][0]
    assert "contract_signing_events" in cursor.executed[3][0]


def test_waiting_lock_uses_signed_exact_service_days_not_calendar_range():
    snapshot = workflow._canonical_snapshot(
        "CASE-1", 8, _order("訂單成立"), _plan(), [_segment()],
    )
    exact_snapshot = workflow._with_exact_commitment_lock_rows(snapshot, [
        {"matching_segment_id": 18, "staff_id": 99, "service_date": date(2026, 8, day)}
        for day in (10, 11, 14)
    ])
    occupancy = workflow._proposed_occupancy_rows(exact_snapshot)

    service_days = [row for row in occupancy if row["lock_kind"] == "service"]

    assert [row["lock_date"] for row in service_days] == [
        date(2026, 8, day) for day in (10, 11, 14)
    ]


def test_invalid_commitment_day_count_cannot_reserve_a_waiting_deposit_lock():
    cursor = _Cursor([
        {"id": 14, "case_no": "CASE-1"},
        {"service_days": 5, "commitment_days": 7, "distinct_service_dates": 7},
    ])

    with pytest.raises(ValueError, match="active staff service commitment days mismatch"):
        workflow._require_active_precontract_commitment(cursor, 8)


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
