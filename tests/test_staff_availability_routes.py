"""
File: test_staff_availability_routes.py
Description: 驗證 Staff Availability public route 的 typed success、競態與錯誤 envelope。
"""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymysql.err import OperationalError

import api.dependencies.staff_availability as staff_availability_dependency
from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_availability import get_staff_availability_application
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes.staff_availability import _mysql_error_code, router
from domains.scheduling.staff_availability import (
    StaffAvailabilityBlockStatus,
    StaffAvailabilityDomainError,
    StaffAvailabilityErrorCode,
    StaffAvailabilityFacts,
    StaffUnavailabilityBlock,
    StaffUnavailabilityKind,
    build_staff_availability_preview,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.staff_availability_workflow import StaffAvailabilityApplyReceipt


class FakeApplication:
    def __init__(self, apply_error=None):
        self.apply_error = apply_error

    def query(self, _request):
        return (_block(),)

    def preview(self, request):
        return build_staff_availability_preview(
            request.intent,
            StaffAvailabilityFacts(request.intent.staff_id, 2, (), ()),
        )

    def apply(self, request):
        if self.apply_error is not None:
            raise self.apply_error
        return StaffAvailabilityApplyReceipt(
            request.intent.staff_id,
            request.intent.action,
            _block(),
            3,
            request.preview_fingerprint,
            request.idempotency_key,
        )


def test_query_returns_typed_staff_availability_blocks():
    response = _client().get(
        "/api/v1/scheduling/staff/7/availability-blocks",
        params={"range_start": "2026-09-01", "range_end": "2026-09-30"},
        headers={"X-Correlation-ID": "availability-query-01"},
    )

    assert response.status_code == 200
    block = response.json()["data"][0]
    assert block["kind"] == "long_leave"
    assert block["status"] == "effective"
    assert response.headers["X-Correlation-ID"] == "availability-query-01"


def test_preview_rejects_unknown_fields_and_returns_source_version():
    client = _client()
    invalid = client.post(
        "/api/v1/scheduling/staff/7/availability-blocks/preview",
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "unknown": True,
        },
    )
    valid = client.post(
        "/api/v1/scheduling/staff/7/availability-blocks/preview",
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
        },
    )

    assert invalid.status_code == 422
    assert valid.status_code == 200
    assert valid.json()["data"]["source_version"] == 2
    assert valid.json()["data"]["can_apply"] is True


def test_apply_receipt_preserves_header_identities_and_strict_shape():
    response = _client().post(
        "/api/v1/scheduling/staff/7/availability-blocks/apply",
        headers={
            "Idempotency-Key": "pause-7-001",
            "X-Correlation-ID": "pause-7-correlation",
        },
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "expected_version": 2,
            "preview_fingerprint": "0" * 64,
        },
    )

    assert response.status_code == 200
    receipt = response.json()["data"]
    assert set(receipt) == {
        "staff_id",
        "action",
        "block",
        "aggregate_version",
        "preview_fingerprint",
        "idempotency_key",
    }
    assert receipt["idempotency_key"] == "pause-7-001"
    assert response.headers["X-Correlation-ID"] == "pause-7-correlation"


def test_apply_uses_header_identities_and_typed_receipt():
    response = _client().post(
        "/api/v1/scheduling/staff/7/availability-blocks/apply",
        headers={
            "Idempotency-Key": "pause-7-001",
            "X-Correlation-ID": "pause-7-correlation",
        },
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "expected_version": 2,
            "preview_fingerprint": "0" * 64,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["idempotency_key"] == "pause-7-001"
    assert response.json()["data"]["aggregate_version"] == 3


def test_apply_invalid_command_shape_returns_typed_validation_error():
    response = _client().post(
        "/api/v1/scheduling/staff/7/availability-blocks/apply",
        headers={
            "Idempotency-Key": "invalid-pause",
            "X-Correlation-ID": "invalid-pause-correlation",
        },
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "end_date": "2026-10-02",
            "expected_version": 2,
            "preview_fingerprint": "0" * 64,
        },
    )

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "invalid_staff_availability_intent"
    assert error["category"] == "validation"


def test_apply_idempotency_mismatch_uses_dedicated_global_error_category():
    response = _client(
        FakeApplication(
            StaffAvailabilityDomainError(
                StaffAvailabilityErrorCode.IDEMPOTENCY_CONFLICT
            )
        )
    ).post(
        "/api/v1/scheduling/staff/7/availability-blocks/apply",
        headers={
            "Idempotency-Key": "availability-replay-mismatch",
            "X-Correlation-ID": "availability-replay-correlation",
        },
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "expected_version": 2,
            "preview_fingerprint": "0" * 64,
        },
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "idempotency_mismatch"
    assert error["code"] == "staff_availability_idempotency_conflict"
    assert error["correlation_id"] == "availability-replay-correlation"


def test_invalid_fingerprint_is_rejected_before_application_call():
    application = FakeApplication()
    client = _client(application)
    response = client.post(
        "/api/v1/scheduling/staff/7/availability-blocks/apply",
        headers={
            "Idempotency-Key": "invalid-fingerprint",
            "X-Correlation-ID": "availability-invalid-fingerprint",
        },
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "expected_version": 2,
            "preview_fingerprint": "A" * 64,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "request_validation_error"


def test_missing_session_is_rejected_before_availability_application(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    response = TestClient(_unauthenticated_app()).get(
        "/api/v1/scheduling/staff/7/availability-blocks",
        params={"range_start": "2026-09-01", "range_end": "2026-09-30"},
        headers={"X-Correlation-ID": "availability-auth-01"},
    )

    assert response.status_code == 401
    error = response.json()["detail"]["error"]
    assert error["category"] == "forbidden"
    assert error["correlation_id"] == "availability-auth-01"


def test_non_numeric_mysql_error_code_falls_back_without_raising():
    assert _mysql_error_code(OperationalError("driver-code", "failure")) == 0


def test_dependency_connection_failure_uses_global_typed_correlation(monkeypatch):
    def fail_connection():
        raise OperationalError(2003, "database unavailable")

    monkeypatch.setattr(staff_availability_dependency, "get_connection", fail_connection)
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7,
        "tester",
        "測試人員",
        "system_admin",
    )

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/scheduling/staff/7/availability-blocks",
        params={"range_start": "2026-09-01", "range_end": "2026-09-30"},
        headers={"X-Correlation-ID": "availability-connect-failure-01"},
    )

    assert response.status_code == 500
    error = response.json()["detail"]["error"]
    assert error["category"] == "internal"
    assert error["code"] == "internal_error"
    assert error["message"] == "伺服器發生未預期錯誤"
    assert error["correlation_id"] == "availability-connect-failure-01"
    assert response.headers["X-Correlation-ID"] == "availability-connect-failure-01"


def _client(application=None):
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7,
        "tester",
        "測試人員",
        "system_admin",
    )
    app.dependency_overrides[get_staff_availability_application] = lambda: (
        application or FakeApplication()
    )
    return TestClient(app)


def _unauthenticated_app():
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    return app


def _block():
    return StaffUnavailabilityBlock(
        91,
        7,
        StaffUnavailabilityKind.LONG_LEAVE,
        date(2026, 9, 1),
        date(2026, 9, 30),
        StaffAvailabilityBlockStatus.EFFECTIVE,
        "照顧家人",
    )
