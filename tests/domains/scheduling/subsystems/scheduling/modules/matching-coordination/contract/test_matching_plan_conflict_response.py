"""Recommendation rejection preserves source case and datetime evidence through HTTP JSON."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import matches
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.matching_plan_workflow import MatchingPlanAvailabilityConflict, MatchingPlanOccupancyConflict


def test_matching_plan_conflict_serializes_source_case_and_actual_shift(monkeypatch):
    evidence = MatchingPlanOccupancyConflict(0, 7, "2026-11-23", "schedule", "OTHER", "2026-11-20",
        "2026-11-22T21:00:00+08:00", "2026-11-23T09:00:00+08:00")
    def reject(**_):
        raise MatchingPlanAvailabilityConflict((evidence,))
    monkeypatch.setattr(matches, "create_matching_plan_version", reject)
    app = FastAPI()
    app.include_router(matches.router)
    app.dependency_overrides[matches.require_system_admin] = lambda: AdminPrincipal(1, "admin", "Admin", "admin", is_root=True)
    with TestClient(app) as client:
        response = client.post("/api/v1/orders/CURRENT/matching-plans", json={
            "segments": [{"staff_id": 7, "assigned_start_date": "2026-11-23", "assigned_end_date": "2026-11-23"}],
            "created_by": "admin", "as_of": "2026-11-20", "event_key": "conflict-evidence",
        })
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "matching_plan_staff_occupancy_conflict"
    conflict, = detail["occupancy_conflicts"]
    assert conflict["case_no"] == "OTHER"
    assert conflict["actual_start_date"] == "2026-11-20"
    assert conflict["service_start_at"] == "2026-11-22T21:00:00+08:00"
    assert conflict["service_end_at"] == "2026-11-23T09:00:00+08:00"
