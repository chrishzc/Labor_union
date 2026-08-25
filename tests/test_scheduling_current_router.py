"""
File: test_scheduling_current_router.py
Description: 驗證 current Scheduling route 的 Session、成功 view 與 typed validation error。
"""

from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.scheduling_current import get_scheduling_current_application
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes.scheduling_current import router
from domains.scheduling.current_projection import (
    SchedulingCurrentDay,
    SchedulingDayEntry,
    SchedulingCurrentDomainError,
    SchedulingCurrentErrorCode,
    SchedulingOccupancyKind,
    SchedulingCurrentProjection,
)
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal


class _Application:
    def __init__(self, error=None):
        self.error = error
        self.request = None

    def query(self, request):
        self.request = request
        if self.error is not None:
            raise self.error
        return SchedulingCurrentProjection(
            request.staff_id,
            request.range_start,
            request.range_end,
            datetime(2026, 8, 1, 9, 0, tzinfo=TAIPEI_TIME_ZONE),
            (),
            (SchedulingCurrentDay(request.range_start, True, ()),),
            (),
            PreviewFingerprint("a" * 64),
        )


def _app(application, *, authenticated=True):
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[get_scheduling_current_application] = lambda: application
    if authenticated:
        app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
            7, "scheduling-reader", "Scheduling Reader", "admin"
        )
    return app


def test_current_calendar_requires_admin_session_before_query(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    application = _Application()
    response = TestClient(_app(application, authenticated=False)).get(
        "/api/v1/scheduling/staff/11/current-calendar",
        params={"range_start": "2026-08-01", "range_end": "2026-08-03"},
    )
    assert response.status_code == 401
    assert application.request is None


def test_current_calendar_returns_strict_projection_for_enabled_admin():
    application = _Application()
    response = TestClient(_app(application)).get(
        "/api/v1/scheduling/staff/11/current-calendar",
        params={"range_start": "2026-08-01", "range_end": "2026-08-03"},
        headers={"X-Correlation-ID": "scheduling-router-success"},
    )
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "scheduling-router-success"
    assert response.json()["data"] == {
        "staff_id": 11,
        "range_start": "2026-08-01",
        "range_end": "2026-08-03",
        "evaluated_at": "2026-08-01T09:00:00+08:00",
        "assignments": [],
        "days": [
            {"calendar_date": "2026-08-01", "available": True, "entries": []}
        ],
        "case_versions": [],
        "projection_token": "a" * 64,
    }
    assert application.request.staff_id == 11


def test_current_calendar_domain_validation_uses_typed_global_error():
    application = _Application(
        SchedulingCurrentDomainError(SchedulingCurrentErrorCode.INVALID_QUERY)
    )
    response = TestClient(_app(application)).get(
        "/api/v1/scheduling/staff/11/current-calendar",
        params={"range_start": "2026-08-03", "range_end": "2026-08-01"},
        headers={"X-Correlation-ID": "scheduling-router-invalid"},
    )
    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "invalid_scheduling_query"
    assert error["category"] == "validation"
    assert error["correlation_id"] == "scheduling-router-invalid"


def test_current_calendar_missing_official_dates_is_typed_conflict():
    application = _Application(ValueError("official_service_dates_incomplete"))
    response = TestClient(_app(application)).get(
        "/api/v1/scheduling/staff/11/current-calendar",
        params={"range_start": "2026-08-01", "range_end": "2026-08-03"},
        headers={"X-Correlation-ID": "scheduling-router-missing-dates"},
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["code"] == "official_service_dates_incomplete"
    assert error["category"] == "conflict"
    assert error["correlation_id"] == "scheduling-router-missing-dates"


def test_current_calendar_serializes_unavailability_kind_and_reason():
    class Application(_Application):
        def query(self, request):
            return SchedulingCurrentProjection(
                request.staff_id,
                request.range_start,
                request.range_end,
                datetime(2026, 8, 1, 9, 0, tzinfo=TAIPEI_TIME_ZONE),
                (),
                (
                    SchedulingCurrentDay(
                        request.range_start,
                        False,
                        (
                            SchedulingDayEntry(
                                SchedulingOccupancyKind.STAFF_UNAVAILABILITY,
                                availability_block_id=91,
                                unavailability_kind="paused_service",
                                unavailability_reason="暫停接新案",
                            ),
                        ),
                    ),
                ),
                (),
                PreviewFingerprint("b" * 64),
            )

    response = TestClient(_app(Application())).get(
        "/api/v1/scheduling/staff/11/current-calendar",
        params={"range_start": "2026-08-01", "range_end": "2026-08-01"},
        headers={"X-Correlation-ID": "scheduling-router-unavailability"},
    )

    assert response.status_code == 200
    entry = response.json()["data"]["days"][0]["entries"][0]
    assert entry["unavailability_kind"] == "paused_service"
    assert entry["unavailability_reason"] == "暫停接新案"
