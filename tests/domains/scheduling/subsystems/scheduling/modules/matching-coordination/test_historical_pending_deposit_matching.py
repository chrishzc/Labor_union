"""Owner-local contract for historical pending-deposit Matching roots."""

from __future__ import annotations

from datetime import date

import pytest

from infrastructure.mysql.historical_pending_deposit_matching_repository import (
    HistoricalPendingDepositMatchingConflict,
    MySqlHistoricalPendingDepositMatchingRepository,
)
from subsystems.scheduling.historical_pending_deposit_matching import (
    HistoricalPendingDepositMatchCommand,
)


def test_historical_match_creates_query_visible_proposed_plan_without_commit():
    cursor = _Cursor(active_plan=None)
    connection = _Connection(cursor)

    receipt = MySqlHistoricalPendingDepositMatchingRepository(
        connection
    ).ensure_pending_deposit_match(_command())

    assert receipt.created is True
    assert receipt.plan_id == 73
    assert receipt.plan_version == 1
    assert connection.commits == 0
    assert any(
        "INSERT INTO caregiver_matching_plans" in statement
        and parameters
        == (
            "CASE-1",
            1,
            date(2026, 9, 7),
            date(2026, 10, 6),
            "operator",
        )
        for statement, parameters in cursor.calls
    )
    assert any(
        "INSERT INTO caregiver_matching_plan_segments" in statement
        and parameters
        == (73, 11, date(2026, 9, 7), date(2026, 10, 6))
        for statement, parameters in cursor.calls
    )


def test_exact_active_proposed_plan_is_an_idempotent_owner_root_reuse():
    cursor = _Cursor(
        active_plan={
            "id": 72,
            "version": 4,
            "status": "proposed",
            "is_active": 1,
            "start_date": date(2026, 9, 7),
            "end_date": date(2026, 10, 6),
        },
        segments=(
            {
                "segment_order": 1,
                "staff_id": 11,
                "assigned_start_date": date(2026, 9, 7),
                "assigned_end_date": date(2026, 10, 6),
            },
        ),
    )

    receipt = MySqlHistoricalPendingDepositMatchingRepository(
        _Connection(cursor)
    ).ensure_pending_deposit_match(_command())

    assert receipt.created is False
    assert receipt.plan_id == 72
    assert receipt.plan_version == 4
    assert not any("INSERT INTO" in statement for statement, _ in cursor.calls)


def test_different_active_plan_fails_closed_instead_of_overwriting_matching():
    cursor = _Cursor(
        active_plan={
            "id": 72,
            "version": 4,
            "status": "proposed",
            "is_active": 1,
            "start_date": date(2026, 9, 7),
            "end_date": date(2026, 10, 6),
        },
        segments=(
            {
                "segment_order": 1,
                "staff_id": 99,
                "assigned_start_date": date(2026, 9, 7),
                "assigned_end_date": date(2026, 10, 6),
            },
        ),
    )

    with pytest.raises(
        HistoricalPendingDepositMatchingConflict,
        match="historical_matching_current_plan_conflict",
    ):
        MySqlHistoricalPendingDepositMatchingRepository(
            _Connection(cursor)
        ).ensure_pending_deposit_match(_command())

    assert not any("INSERT INTO" in statement for statement, _ in cursor.calls)


def _command():
    return HistoricalPendingDepositMatchCommand(
        case_no="CASE-1",
        staff_id=11,
        actor="operator",
        source_identity="historical-orders:digest:row:2",
    )


class _Cursor:
    def __init__(self, *, active_plan, segments=()):
        self.active_plan = active_plan
        self.segments = tuple(segments)
        self.calls = []
        self.lastrowid = 0
        self._kind = ""

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        if "FROM orders" in statement:
            self._kind = "order"
        elif "FROM caregiver_matching_plans" in statement:
            self._kind = "plans"
        elif "FROM caregiver_matching_plan_segments" in statement:
            self._kind = "segments"
        elif "INSERT INTO caregiver_matching_plans" in statement:
            self._kind = "insert_plan"
            self.lastrowid = 73
        else:
            self._kind = "write"

    def fetchone(self):
        if self._kind == "order":
            return {
                "case_no": "CASE-1",
                "status": "洽談中",
                "start_date": date(2026, 9, 7),
                "end_date": date(2026, 10, 6),
            }
        return None

    def fetchall(self):
        if self._kind == "plans":
            return () if self.active_plan is None else (self.active_plan,)
        if self._kind == "segments":
            return self.segments
        return ()

    def close(self):
        return None


class _Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.commits = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1
