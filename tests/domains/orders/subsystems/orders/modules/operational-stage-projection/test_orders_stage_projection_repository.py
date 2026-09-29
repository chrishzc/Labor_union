"""Verify that service projection reads only current assignment-owned dates."""

import sqlite3

import pytest

from infrastructure.mysql.orders_stage_projection_repository import _PAGE_SQL


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
