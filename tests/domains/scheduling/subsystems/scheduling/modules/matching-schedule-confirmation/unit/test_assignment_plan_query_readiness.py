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
        def execute(self, sql, params): assert sql.startswith("SELECT ")
        def fetchone(self): return None

    cursor = Cursor()
    day = date(2026, 11, 16)
    order = {"lifecycle_version": 2, "service_days": 20, "service_hours_per_day": None, "actual_start_date": day}
    rows = ({"id": 5, "staff_id": 2, "assignment_sequence": 1, "assigned_start_date": day, "assigned_end_date": day},) if assigned else ()
    monkeypatch.setattr(repository, "select_order", lambda *a, **k: order)
    monkeypatch.setattr(repository, "select_scheduling_aggregate", lambda *a, **k: {"aggregate_version": 3})
    monkeypatch.setattr(repository, "_select_generation", lambda *a, **k: {"generation_number": 1} if assigned else None)
    monkeypatch.setattr(repository, "_select_assignments", lambda *a, **k: rows)
    monkeypatch.setattr(repository, "_select_schedules", lambda *a, **k: [{"assignment_id": 5, "work_date": day, "is_work_day": 1}] if assigned else [])
    monkeypatch.setattr(repository, "load_preview_facts", lambda *a: pytest.fail("Query must not enforce Finance/Payroll Preview gates"))
    result = repository.MySqlAssignmentPlanRepository(SimpleNamespace(cursor=lambda: cursor)).load_for_query("TEST")
    view = AssignmentPlanQueryView.model_validate(_query_payload(result))
    assert view.client_finance_version is None and view.payroll_version is None
    assert view.service_hours_per_day is None
    assert view.service_started is assigned
    assert [item.official_service_dates for item in view.assignments] == [[day]] if assigned else view.assignments == []
