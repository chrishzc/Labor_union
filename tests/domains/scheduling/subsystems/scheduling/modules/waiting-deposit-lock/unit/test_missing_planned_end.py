"""The original recommendation period must not override current service dates."""
from datetime import date
import pytest
from subsystems.scheduling import availability_lock_acquisition_workflow as workflow


@pytest.mark.parametrize("start_date,end_date", [
    (date(2026, 11, 15), None),
    (date(2026, 11, 15), date(2026, 12, 11)),
    (date(2026, 11, 15), date(2026, 12, 4)),
    (date(2026, 12, 1), date(2026, 12, 20)),
])
def test_lock_does_not_require_the_original_recommendation_period(monkeypatch, start_date, end_date):
    order = {"case_no": "TEST", "status": "洽談中", "start_date": start_date, "end_date": end_date}
    plan = {"id": 1, "case_no": "TEST", "status": "proposed", "is_active": 1, "start_date": date(2026, 11, 15), "end_date": date(2026, 12, 11)}
    snapshot = object()
    monkeypatch.setattr(workflow, "normalize_plan_snapshot", lambda *args: snapshot)
    assert workflow._canonical_snapshot("TEST", 1, order, plan, []) is snapshot
