"""Inquiry transport is distinct from formal matching and remains authenticated."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes import caregiver_segment_availability as route


def test_inquiry_route_selects_inquiry_query_and_rejects_multiple_segments(monkeypatch):
    calls = []
    def inquiry(**kwargs):
        calls.append(kwargs)
        return {"case_no": "INQUIRY-1", "planned_start_date": "2026-10-05", "planned_end_date": "2026-10-05",
                "feasibility": "partial", "complete_combinations": [], "segment_candidates": [],
                "candidate_options": [], "conflicts": [
                    {"segment_index": 0, "staff_id": 7, "work_date": "2026-10-05", "reason_code": "schedule",
                     "case_no": "OTHER", "assignment_start_date": "2026-10-02", "assignment_end_date": "2026-10-07"},
                    {"segment_index": 0, "staff_id": 7, "work_date": "2026-10-05", "reason_code": "buffer"},
                ]}
    monkeypatch.setattr(route, "search_candidate_inquiry_availability", inquiry)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.require_system_admin] = lambda: object()
    client = TestClient(app)
    payload = {"segment_count": 1, "segment_drafts": [], "as_of": "2026-10-01"}
    path = "/api/v1/orders/INQUIRY-1/candidate-contact-pool/availability/search"
    response = client.post(path, json=payload)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["case_no"] == "INQUIRY-1"
    schedule, buffer = data["conflicts"]
    assert schedule["case_no"] == "OTHER"
    assert schedule["work_date"] == "2026-10-05"
    assert schedule["assignment_start_date"] == "2026-10-02"
    assert schedule["assignment_end_date"] == "2026-10-07"
    assert "assignment_start_date" not in buffer
    assert "assignment_end_date" not in buffer
    assert calls[0]["case_no"] == "INQUIRY-1"
    assert calls[0]["include_assignment_dates"] is True
    assert client.post(path, json={**payload, "segment_count": 2}).status_code == 422
    assert len(calls) == 1
    app.dependency_overrides.clear()
    assert client.post(path, json=payload).status_code in (401, 403)
    assert len(calls) == 1
