"""A missing planned-end projection must not reject an otherwise current plan."""
from datetime import date
import pytest
from subsystems.scheduling import availability_lock_acquisition_workflow as workflow


@pytest.mark.parametrize("end_date,allowed", [(None, True), (date(2026, 12, 11), True), (date(2026, 12, 4), False)])
def test_lock_does_not_require_a_persisted_planned_end(monkeypatch, end_date, allowed):
    order = {"case_no": "TEST", "status": "洽談中", "start_date": date(2026, 11, 15), "end_date": end_date}
    plan = {"id": 1, "case_no": "TEST", "status": "proposed", "is_active": 1, "start_date": date(2026, 11, 15), "end_date": date(2026, 12, 11)}
    snapshot = object()
    monkeypatch.setattr(workflow, "normalize_plan_snapshot", lambda *args: snapshot)
    if allowed:
        assert workflow._canonical_snapshot("TEST", 1, order, plan, []) is snapshot
    else:
        with pytest.raises(ValueError, match="plan dates do not match order"):
            workflow._canonical_snapshot("TEST", 1, order, plan, [])
