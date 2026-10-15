"""Verify that service projection reads only current assignment-owned dates."""

import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from infrastructure.mysql.orders_stage_projection_repository import _PAGE_SQL, MySqlOrdersStageProjectionRepository
from infrastructure.mysql.historical_orders_stage_projection_repository import MySqlHistoricalAwareOrdersStageProjectionRepository


@pytest.mark.parametrize('repository_type', [MySqlOrdersStageProjectionRepository, MySqlHistoricalAwareOrdersStageProjectionRepository])
def test_completion_receipt_timestamp_keeps_its_instant_across_browser_and_db_zones(repository_type):
    instant = datetime(2026, 10, 15, 3, 43, tzinfo=timezone.utc)
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, _params):
            assert 'UNIX_TIMESTAMP(completion_fact.completed_at) AS service_completed_at' in sql
        def fetchall(self):
            return [{'service_completed_at': instant.timestamp(), 'client_updated_at': instant.timestamp() - 60, 'staff_updated_at': instant.timestamp() - 120}, {'service_completed_at': None, 'client_updated_at': None, 'staff_updated_at': None}]
    rows = repository_type(SimpleNamespace(cursor=Cursor)).fetch_page(after_case_no=None, page_size=10)
    assert rows[0]['service_completed_at'].isoformat() == '2026-10-15T03:43:00+00:00'
    assert rows[0]['service_completed_at'].astimezone(ZoneInfo('Asia/Taipei')).hour == 11
    assert max(rows[0].values()) == rows[0]['service_completed_at']
    assert rows[1]['service_completed_at'] is None


@pytest.mark.parametrize("effective_generation_id", [2, 3])
def test_replaced_assignments_cannot_supply_current_service_period(
    effective_generation_id: int,
) -> None:
    # Execute the production aggregate against current and retained old facts.
    aggregate_sql = _PAGE_SQL.split(
        "       SELECT assignment.case_no,", 1
    )[1].split("  ) assignments ON assignments.case_no = o.case_no", 1)[0]
    aggregate_sql = "SELECT assignment.case_no," + aggregate_sql
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE scheduling_aggregates (
                case_no TEXT, effective_generation_id INTEGER
            );
            CREATE TABLE case_staff_assignments (
                id INTEGER, case_no TEXT, generation_id INTEGER,
                status TEXT, updated_at TEXT
            );
            CREATE TABLE staff_schedule (
                assignment_id INTEGER, work_date TEXT,
                effective_marker INTEGER, is_work_day INTEGER
            );
            INSERT INTO case_staff_assignments VALUES
                (1, 'CASE-CURRENT', 1, 'active', '2026-09-01'),
                (2, 'CASE-CURRENT', 2, 'planned', '2026-09-29');
            INSERT INTO staff_schedule VALUES
                (1, '2026-08-01', 1, 1),
                (1, '2026-11-30', 1, 1),
                (2, '2026-09-14', 1, 1),
                (2, '2026-10-23', 1, 1),
                (2, '2026-10-24', 1, 0),
                (2, '2026-10-25', 0, 1);
        """)
        connection.execute(
            "INSERT INTO scheduling_aggregates VALUES (?, ?)",
            ("CASE-CURRENT", effective_generation_id),
        )
        rows = connection.execute(aggregate_sql).fetchall()

    if effective_generation_id == 3:
        assert rows == []  # An empty current generation must not revive old work.
    else:
        assert len(rows) == 1
        assert dict(rows[0]) == {
            "case_no": "CASE-CURRENT",
            "assignment_count": 1,
            "assignment_active_count": 0,
            "assignment_completed_count": 0,
            "assignment_updated_at": "2026-09-29",
            "assignment_first_service_date": "2026-09-14",
            "assignment_last_service_date": "2026-10-23",
        }
