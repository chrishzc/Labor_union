"""Public typed API contract for official date correction."""

from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.official_service_date_correction import (
    get_official_service_date_correction_workflow,
)
from api.routes.official_service_date_correction import router
from subsystems.orders.official_service_date_correction_workflow import (
    OfficialAssignmentDates,
    OfficialDateFacts,
)


class _Workflow:
    def query(self, case_no):
        return OfficialDateFacts(
            case_no, 1, "訂單完成", date(2026, 9, 19), date(2026, 9, 20),
            True, 2, 8, 1, 11, 1,
            (OfficialAssignmentDates(13, 7, 1, "completed",
                                     (date(2026, 9, 19), date(2026, 9, 20)), "王月嫂"),),
        )

    def preview(self, *_args):
        raise ValueError("official_date_version_conflict")

    def apply(self, *_args, **_kwargs):
        raise RuntimeError("scheduling_version_conflict")


def _client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(username="admin")
    app.dependency_overrides[get_official_service_date_correction_workflow] = _Workflow
    return TestClient(app)


def test_query_exposes_effective_assignment_dates_and_lock():
    response = _client().get("/api/v1/orders/ISSUE-346/official-service-dates")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["generation_id"] == 11
    assert data["service_data_locked"] is True
    assert data["assignments"][0]["service_dates"] == ["2026-09-19", "2026-09-20"]


def test_stale_preview_and_writer_version_conflict_are_typed():
    assignments = [{"assignment_id": 13, "service_dates": ["2026-09-19", "2026-09-21"]}]
    client = _client()
    preview = client.post(
        "/api/v1/orders/ISSUE-346/official-service-dates/preview",
        json={"assignments": assignments},
    )
    assert preview.status_code == 409
    assert preview.json()["detail"]["error"]["category"] == "conflict"
    apply = client.post(
        "/api/v1/orders/ISSUE-346/official-service-dates/apply",
        headers={"Idempotency-Key": "test-issue346", "X-Correlation-ID": "test-issue346"},
        json={"assignments": assignments, "expected_order_version": 1,
              "expected_scheduling_version": 1, "preview_fingerprint": "a" * 64,
              "reason": "date correction"},
    )
    assert apply.status_code == 409
    assert apply.json()["detail"]["error"]["code"] == "scheduling_version_conflict"
