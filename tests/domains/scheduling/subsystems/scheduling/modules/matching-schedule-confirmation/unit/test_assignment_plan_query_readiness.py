"""An empty assignment query must not require downstream mutation bootstrap."""
from datetime import date
from types import SimpleNamespace

import pytest

from api.schemas.assignment_plan import AssignmentPlanQueryView
from api.routes.assignment_plan import _query_payload
from infrastructure.mysql import assignment_plan_repository as repository


@pytest.mark.parametrize("assigned", [False, True])
def test_query_reports_missing_roots_without_mutation_readiness(monkeypatch, assigned):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params): assert sql.lstrip().startswith("SELECT ")
        def fetchone(self): return None
        def fetchall(self): return rows

    cursor = Cursor()
    day = date(2026, 11, 16)
    order = {"lifecycle_version": 2, "service_days": 20, "service_hours_per_day": None, "actual_start_date": day}
    rows = ({"id": 5, "staff_id": 2, "assignment_sequence": 1, "assigned_start_date": day, "assigned_end_date": day},) if assigned else ()
    monkeypatch.setattr(repository, "select_order", lambda *a, **k: order)
    monkeypatch.setattr(repository, "select_scheduling_aggregate", lambda *a, **k: {"aggregate_version": 3})
    monkeypatch.setattr(repository, "_select_generation", lambda *a, **k: {"id": 1, "generation_number": 1} if assigned else None)
    monkeypatch.setattr(repository, "_select_assignments", lambda *a, **k: rows)
    monkeypatch.setattr(repository, "_select_schedules", lambda *a, **k: [{"assignment_id": 5, "work_date": day, "is_work_day": 1}] if assigned else [])
    monkeypatch.setattr(repository, "load_preview_facts", lambda *a: pytest.fail("Query must not enforce Finance/Payroll Preview gates"))
    result = repository.MySqlAssignmentPlanRepository(SimpleNamespace(cursor=lambda: cursor)).load_for_query("TEST")
    view = AssignmentPlanQueryView.model_validate(_query_payload(result))
    assert view.client_finance_version is None and view.payroll_version is None
    assert view.service_hours_per_day is None
    assert view.service_started is assigned
    assert [item.official_service_dates for item in view.assignments] == [[day]] if assigned else view.assignments == []


@pytest.mark.parametrize("status", ["歷史訂單－服務中", "歷史訂單－服務完成", "歷史訂單－帳務完成"])
def test_saved_historical_assignment_is_the_same_identity_used_by_accounting(monkeypatch, status):
    import sqlite3
    from infrastructure.mysql.historical_service_accounting_repository import _ASSIGNMENTS_SQL

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE orders (case_no TEXT, status TEXT);
        CREATE TABLE case_staff_assignments (id INTEGER,case_no TEXT,staff_id INTEGER,assignment_sequence INTEGER,
            assigned_start_date TEXT,assigned_end_date TEXT,status TEXT,generation_id INTEGER);
        CREATE TABLE historical_order_adoption_receipts (id INTEGER,case_no TEXT,outcome TEXT);
        CREATE TABLE historical_order_pairing_evidence (receipt_id INTEGER,assignment_id INTEGER,staff_id INTEGER);
        CREATE TABLE staff (id INTEGER,name TEXT);
        CREATE TABLE case_payroll_rate_policy_snapshots (case_no TEXT,policy_version TEXT,policy_kind TEXT,hourly_rate_ntd INTEGER);
        CREATE TABLE assignment_payroll_rate_snapshots (assignment_id INTEGER,policy_version TEXT,policy_kind TEXT,hourly_rate_ntd INTEGER);
        CREATE TABLE client_finance_accounts (case_no TEXT,aggregate_version INTEGER);
        CREATE TABLE payroll_case_accounts (case_no TEXT,aggregate_version INTEGER);
        INSERT INTO staff VALUES (9,'合成月嫂');
        INSERT INTO historical_order_adoption_receipts VALUES (1,'H-1','adopted'),(2,'H-1','adopted');
        INSERT INTO historical_order_pairing_evidence VALUES (1,90,9),(2,91,9),(2,92,10),(2,93,9),(2,94,9);
        INSERT INTO case_staff_assignments VALUES
            (90,'H-1',9,1,'2026-08-01','2026-08-31','completed',NULL),
            (91,'H-1',9,2,'2026-08-01','2026-08-31','completed',NULL),
            (92,'H-1',9,3,'2026-08-01','2026-08-31','completed',NULL),
            (93,'OTHER',9,4,'2026-08-01','2026-08-31','completed',NULL),
            (94,'H-1',9,5,'2026-08-01','2026-08-31','cancelled',NULL),
            (95,'H-1',9,6,'2026-08-01','2026-08-31','completed',NULL);
    """)
    connection.execute("INSERT INTO orders VALUES ('H-1',?)", (status,))

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params):
            assert sql.lstrip().startswith("SELECT ")
            self.cursor = connection.execute(sql.replace("%s", "?"), params)
        def fetchone(self):
            row = self.cursor.fetchone()
            return dict(row) if row is not None else None
        def fetchall(self):
            return [{key: date.fromisoformat(row[key]) if key in {"assigned_start_date", "assigned_end_date"} else row[key]
                     for key in row.keys()} for row in self.cursor.fetchall()]

    monkeypatch.setattr(repository, "select_order", lambda *a, **k: {
        "lifecycle_version": 3, "service_days": 30, "service_hours_per_day": 8, "actual_start_date": date(2026, 8, 1),
    })
    monkeypatch.setattr(repository, "select_scheduling_aggregate", lambda *a, **k: {"aggregate_version": 0})
    monkeypatch.setattr(repository, "_select_generation", lambda *a, **k: None)
    monkeypatch.setattr(repository, "_select_schedules", lambda *a, **k: [])
    try:
        result = repository.MySqlAssignmentPlanRepository(SimpleNamespace(cursor=Cursor)).load_for_query("H-1")
        view = AssignmentPlanQueryView.model_validate(_query_payload(result))
        assert [(item.assignment_id, item.staff_id) for item in view.assignments] == [(91, 9)]
        assert view.assignments[0].official_service_dates == []
        assert view.scheduling_generation == 0
        accounting = connection.execute(_ASSIGNMENTS_SQL.replace("%s", "?"), (2,)).fetchall()
        assert [(row["assignment_id"], row["staff_id"]) for row in accounting] == [(91, 9)]
        connection.execute("UPDATE orders SET status='訂單成立'")
        assert repository.MySqlAssignmentPlanRepository(SimpleNamespace(cursor=Cursor)).load_for_query("H-1").assignment_plan.effective_assignments == ()
    finally:
        connection.close()
