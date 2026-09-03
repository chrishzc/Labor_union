"""HTTP contract regression for the Staff case-preference summary route."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_case_preference_summary import (
    get_staff_case_preference_summary_application,
)
from api.routes.staff import router
from subsystems.staff.case_preference_summary_query import (
    PreferenceTopicSummary,
    StaffCasePreferenceSummary,
)


class _StubApplication:
    def __init__(self, summary: StaffCasePreferenceSummary | None) -> None:
        self._summary = summary
        self.requested_staff_ids: list[int] = []

    def get(self, staff_id: int) -> StaffCasePreferenceSummary | None:
        self.requested_staff_ids.append(staff_id)
        return self._summary


def test_case_preference_summary_returns_typed_success_shape():
    application = _StubApplication(_summary())
    client = _client(application)

    response = client.get(
        "/api/v1/staff/42/case-preference-summary",
        headers={"X-Correlation-ID": "issue-150-success"},
    )

    assert response.status_code == 200
    assert application.requested_staff_ids == [42]
    assert response.json() == {
        "success": True,
        "message": "成功取得服務人員案件偏好摘要",
        "data": {
            "staff_id": 42,
            "service_regions": {
                "values": ["北區", "新竹縣"],
                "other_detail": "偏好竹北",
                "other_detail_status": "ready",
            },
            "service_periods": {
                "values": ["8小時"],
                "other_detail": None,
                "other_detail_status": "not_recorded",
            },
            "rest_schedule": {
                "values": ["週休1日"],
                "other_detail": None,
                "other_detail_status": "not_recorded",
            },
            "baby_counts": {
                "values": ["單胞胎"],
                "other_detail": None,
                "other_detail_status": "not_recorded",
            },
            "holiday_availability": {
                "values": ["端午節"],
                "other_detail": None,
                "other_detail_status": "not_recorded",
            },
            "transportation": {
                "values": ["機車"],
                "other_detail": None,
                "other_detail_status": "source_not_ready",
            },
        },
        "error": None,
    }


def test_case_preference_summary_returns_typed_404_for_missing_staff():
    application = _StubApplication(None)
    client = _client(application)

    response = client.get(
        "/api/v1/staff/404/case-preference-summary",
        headers={"X-Correlation-ID": "issue-150-not-found"},
    )

    assert response.status_code == 404
    assert application.requested_staff_ids == [404]
    assert response.json()["detail"]["error"] == {
        "category": "not_found",
        "code": "staff_not_found",
        "message": "查無服務人員。",
        "correlation_id": "issue-150-not-found",
        "field_errors": [],
        "domain_blockers": [],
        "retryable": False,
        "current_version": None,
    }


def test_case_preference_summary_requires_admin():
    application = _StubApplication(_summary())
    client = _client(application, authorized=False)

    response = client.get("/api/v1/staff/42/case-preference-summary")

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_authorization_header"}
    assert application.requested_staff_ids == []


def _client(
    application: _StubApplication,
    *,
    authorized: bool = True,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if authorized:
        app.dependency_overrides[require_admin] = lambda: object()
    else:
        app.dependency_overrides[require_admin] = _reject_admin
    app.dependency_overrides[
        get_staff_case_preference_summary_application
    ] = lambda: application
    return TestClient(app)


def _reject_admin():
    raise HTTPException(status_code=401, detail="invalid_authorization_header")


def _summary() -> StaffCasePreferenceSummary:
    return StaffCasePreferenceSummary(
        staff_id=42,
        service_regions=PreferenceTopicSummary(
            values=("北區", "新竹縣"),
            other_detail="偏好竹北",
            other_detail_status="ready",
        ),
        service_periods=PreferenceTopicSummary(
            values=("8小時",),
            other_detail=None,
            other_detail_status="not_recorded",
        ),
        rest_schedule=PreferenceTopicSummary(
            values=("週休1日",),
            other_detail=None,
            other_detail_status="not_recorded",
        ),
        baby_counts=PreferenceTopicSummary(
            values=("單胞胎",),
            other_detail=None,
            other_detail_status="not_recorded",
        ),
        holiday_availability=PreferenceTopicSummary(
            values=("端午節",),
            other_detail=None,
            other_detail_status="not_recorded",
        ),
        transportation=PreferenceTopicSummary(
            values=("機車",),
            other_detail=None,
            other_detail_status="source_not_ready",
        ),
    )
