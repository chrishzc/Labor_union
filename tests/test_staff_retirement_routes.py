"""
File: test_staff_retirement_routes.py
Description: 驗證 Staff lifecycle 的 aware datetime、strict fingerprint 與獨立 receipt route。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_retirement import get_staff_retirement_application
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes.staff_retirement import router
from api.schemas.staff_retirement import StaffLifecycleApplyReceiptView
from domains.staff.retirement import (
    StaffLifecycleFact,
    StaffLifecycleState,
    StaffLifecycleTransition,
    build_transition,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.retirement_workflow import (
    StaffLifecyclePreview,
    StaffLifecycleReceipt,
)


_FINGERPRINT = "a" * 64
_EFFECTIVE_AT = datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc)


class _Application:
    def __init__(self):
        self.workflow = _Workflow()


class _Workflow:
    def __init__(self):
        self.fact = StaffLifecycleFact(7, StaffLifecycleState.ACTIVE, 2)

    def query(self, staff_id):
        if staff_id == 404:
            raise ValueError("staff_not_found")
        return self.fact

    def preview(self, staff_id, transition, effective_at, reason_code):
        if staff_id == 409:
            raise ValueError("stale_preview")
        candidate = build_transition(
            self.fact,
            transition,
            effective_at=effective_at,
            reason_code=reason_code,
        )
        return StaffLifecyclePreview(candidate, PreviewFingerprint(_FINGERPRINT))

    def apply(self, request):
        if request.staff_id == 410:
            raise ValueError("idempotency_mismatch")
        if request.staff_id == 409:
            raise ValueError("stale_version")
        candidate = build_transition(
            self.fact,
            request.transition,
            effective_at=request.effective_at,
            reason_code=request.reason_code,
        )
        return StaffLifecycleReceipt(
            request.staff_id,
            candidate.after.state,
            candidate.after.version,
            request.preview_fingerprint,
            request.idempotency_key,
        )


def _client():
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7,
        "lifecycle-test",
        "測試人員",
        "admin",
    )
    app.dependency_overrides[get_staff_retirement_application] = lambda: _Application()
    return TestClient(app)


def _transition_body():
    return {
        "effective_at": _EFFECTIVE_AT.isoformat(),
        "reason_code": "left_union",
    }


def test_query_and_preview_use_server_state_and_lowercase_fingerprint():
    client = _client()
    query = client.get("/api/v1/staff/7/lifecycle")
    preview = client.post(
        "/api/v1/staff/7/retirement/preview",
        json=_transition_body(),
        headers={"X-Correlation-ID": "lifecycle-preview-01"},
    )

    assert query.status_code == 200
    assert query.json()["data"]["state"] == "active"
    assert preview.status_code == 200
    assert preview.json()["data"]["after_state"] == "retired"
    assert preview.json()["data"]["preview_fingerprint"] == _FINGERPRINT


def test_apply_returns_independent_typed_receipt_with_header_identities():
    response = _client().post(
        "/api/v1/staff/7/retirement/apply",
        headers={
            "Idempotency-Key": "lifecycle-apply-01",
            "X-Correlation-ID": "lifecycle-apply-correlation",
        },
        json={
            **_transition_body(),
            "expected_version": 2,
            "preview_fingerprint": _FINGERPRINT,
        },
    )

    assert response.status_code == 200
    receipt = response.json()["data"]
    assert receipt["staff_id"] == 7
    assert receipt["state"] == "retired"
    assert receipt["resulting_version"] == 3
    assert receipt["preview_fingerprint"] == _FINGERPRINT
    assert receipt["idempotency_key"] == "lifecycle-apply-01"
    assert response.headers["X-Correlation-ID"] == "lifecycle-apply-correlation"
    assert "effective_at" not in receipt


def test_naive_effective_at_and_uppercase_fingerprint_are_global_validation_errors():
    client = _client()
    naive = client.post(
        "/api/v1/staff/7/retirement/preview",
        json={
            "effective_at": "2026-08-15T09:00:00",
            "reason_code": "left_union",
        },
        headers={"X-Correlation-ID": "lifecycle-naive-01"},
    )
    uppercase = client.post(
        "/api/v1/staff/7/retirement/apply",
        headers={
            "Idempotency-Key": "lifecycle-uppercase",
            "X-Correlation-ID": "lifecycle-uppercase-correlation",
        },
        json={
            **_transition_body(),
            "expected_version": 2,
            "preview_fingerprint": "A" * 64,
        },
    )

    assert naive.status_code == 422
    assert naive.json()["detail"]["error"]["category"] == "validation"
    assert uppercase.status_code == 422
    assert uppercase.json()["detail"]["error"]["category"] == "validation"


def test_unknown_lifecycle_action_is_not_a_dynamic_route():
    response = _client().post(
        "/api/v1/staff/7/promote/preview",
        json=_transition_body(),
        headers={"X-Correlation-ID": "lifecycle-action-01"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "request_validation_error"


def test_lifecycle_business_conflict_is_typed_and_not_success():
    response = _client().post(
        "/api/v1/staff/409/retirement/apply",
        headers={
            "Idempotency-Key": "lifecycle-stale-01",
            "X-Correlation-ID": "lifecycle-stale-correlation",
        },
        json={
            **_transition_body(),
            "expected_version": 2,
            "preview_fingerprint": _FINGERPRINT,
        },
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "conflict"
    assert error["code"] == "stale_version"


def test_lifecycle_not_found_is_typed_and_reason_is_masked():
    response = _client().get(
        "/api/v1/staff/404/lifecycle",
        headers={"X-Correlation-ID": "lifecycle-not-found"},
    )

    assert response.status_code == 404
    error = response.json()["detail"]["error"]
    assert error["category"] == "not_found"
    assert error["code"] == "staff_not_found"


def test_lifecycle_idempotency_mismatch_uses_dedicated_global_error_category():
    response = _client().post(
        "/api/v1/staff/410/retirement/apply",
        headers={
            "Idempotency-Key": "lifecycle-replay-mismatch",
            "X-Correlation-ID": "lifecycle-replay-correlation",
        },
        json={
            **_transition_body(),
            "expected_version": 2,
            "preview_fingerprint": _FINGERPRINT,
        },
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "idempotency_mismatch"
    assert error["code"] == "idempotency_mismatch"
    assert error["correlation_id"] == "lifecycle-replay-correlation"


def test_apply_receipt_rejects_nonpositive_staff_identity():
    with pytest.raises(ValidationError):
        StaffLifecycleApplyReceiptView.model_validate(
            {
                "staff_id": 0,
                "state": "retired",
                "resulting_version": 3,
                "preview_fingerprint": _FINGERPRINT,
                "idempotency_key": "lifecycle-invalid-staff",
            }
        )
