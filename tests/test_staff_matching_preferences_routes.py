"""
File: test_staff_matching_preferences_routes.py
Description: 驗證 Staff 偏好 public route 的 typed success、headers 與錯誤 envelope。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_matching_preferences import (
    get_staff_matching_preference_application,
)
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes.staff_matching_preferences import router
from api.schemas.staff_matching_preferences import (
    StaffPreferenceProfileApplyReceiptView,
)
from domains.scheduling.staff_matching_preferences import (
    PreferenceComparisonOperator,
    PreferenceValueKind,
    StaffPreferenceDefinition,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.staff_matching_preference_workflow import ProfilePreview


_FINGERPRINT = "a" * 64
_PROFILE_VALUES = {
    "preferred_service_days": {"minimum": 20, "maximum": 30},
}


class _Application:
    def __init__(self):
        self.workflow = _Workflow()


class _DefinitionsErrorApplication:
    class _Workflow:
        def query_definitions(self, *, active_only):
            del active_only
            raise ValueError("preference_definition_not_found")

    def __init__(self):
        self.workflow = self._Workflow()


class _Workflow:
    def query_profile(self, staff_id):
        if staff_id == 404:
            raise ValueError("staff_not_found")
        return ProfilePreview(staff_id, {}, _PROFILE_VALUES, 0, PreviewFingerprint(_FINGERPRINT))

    def preview_profile(self, staff_id, proposed):
        return ProfilePreview(staff_id, _PROFILE_VALUES, proposed, 0, PreviewFingerprint(_FINGERPRINT))

    def apply_profile(self, staff_id, proposed, request):
        if staff_id == 410:
            raise ValueError("idempotency_conflict")
        if staff_id == 409:
            raise ValueError("stale_version")
        return {
            "staff_id": staff_id,
            "version": 1,
            "values": proposed,
            "preview_fingerprint": request.preview_fingerprint.value,
            "idempotency_key": request.idempotency_key.value,
        }

    def query_definitions(self, *, active_only):
        return (
            (
                StaffPreferenceDefinition(
                    "preferred_service_days",
                    "希望服務天數",
                    PreferenceValueKind.INTEGER_RANGE,
                    True,
                    "service_days",
                    PreferenceComparisonOperator.RANGE_WITH_TOLERANCE,
                ),
                1,
            ),
        )


def _client(application=None):
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7,
        "staff-test",
        "測試人員",
        "admin",
    )
    app.dependency_overrides[get_staff_matching_preference_application] = (
        lambda: application or _Application()
    )
    return TestClient(app)


def _profile_body():
    return {
        "values": [
            {
                "preference_key": "preferred_service_days",
                "value": {
                    "kind": "integer_range",
                    "minimum": 20,
                    "maximum": 30,
                },
            }
        ]
    }


def test_profile_query_and_preview_return_strict_typed_views():
    client = _client()

    query = client.get("/api/v1/scheduling/staff-matching-preferences/staff/7")
    preview = client.post(
        "/api/v1/scheduling/staff-matching-preferences/staff/7/preview",
        json=_profile_body(),
    )

    assert query.status_code == 200
    assert query.json()["data"]["staff_id"] == 7
    assert preview.status_code == 200
    assert preview.json()["data"]["preview_fingerprint"] == _FINGERPRINT


def test_definition_query_business_error_is_global_typed_and_preserves_correlation():
    response = _client(_DefinitionsErrorApplication()).get(
        "/api/v1/scheduling/staff-matching-preferences/definitions",
        headers={"X-Correlation-ID": "preference-definitions-correlation"},
    )

    assert response.status_code == 404
    error = response.json()["detail"]["error"]
    assert error["category"] == "not_found"
    assert error["code"] == "preference_definition_not_found"
    assert error["correlation_id"] == "preference-definitions-correlation"


def test_apply_requires_headers_and_returns_receipt_identity():
    client = _client()
    response = client.post(
        "/api/v1/scheduling/staff-matching-preferences/staff/7/apply",
        headers={
            "Idempotency-Key": "preference-apply-01",
            "X-Correlation-ID": "preference-correlation-01",
        },
        json={
            **_profile_body(),
            "expected_version": 0,
            "preview_fingerprint": _FINGERPRINT,
            "reason": "調整正式偏好",
        },
    )

    assert response.status_code == 200
    receipt = response.json()["data"]
    assert receipt["staff_id"] == 7
    assert receipt["preview_fingerprint"] == _FINGERPRINT
    assert receipt["idempotency_key"] == "preference-apply-01"
    assert response.headers["X-Correlation-ID"] == "preference-correlation-01"
    StaffPreferenceProfileApplyReceiptView.model_validate(receipt)


def test_business_error_is_global_typed_and_preserves_correlation():
    client = _client()
    response = client.get(
        "/api/v1/scheduling/staff-matching-preferences/staff/404",
        headers={"X-Correlation-ID": "preference-not-found-01"},
    )

    assert response.status_code == 404
    error = response.json()["detail"]["error"]
    assert error["code"] == "staff_not_found"
    assert error["category"] == "not_found"
    assert error["correlation_id"] == "preference-not-found-01"


def test_request_validation_unknown_field_is_global_typed_error():
    response = _client().post(
        "/api/v1/scheduling/staff-matching-preferences/staff/7/preview",
        headers={"X-Correlation-ID": "preference-validation-01"},
        json={**_profile_body(), "unexpected": True},
    )

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "request_validation_error"
    assert error["category"] == "validation"
    assert error["correlation_id"] == "preference-validation-01"
    assert error["field_errors"]


def test_apply_conflict_is_not_reported_as_success():
    client = _client()
    response = client.post(
        "/api/v1/scheduling/staff-matching-preferences/staff/409/apply",
        headers={
            "Idempotency-Key": "preference-stale-01",
            "X-Correlation-ID": "preference-stale-correlation",
        },
        json={
            **_profile_body(),
            "expected_version": 0,
            "preview_fingerprint": _FINGERPRINT,
            "reason": "嘗試套用舊預覽",
        },
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "conflict"
    assert error["code"] == "stale_version"


def test_apply_idempotency_mismatch_uses_dedicated_global_error_category():
    response = _client().post(
        "/api/v1/scheduling/staff-matching-preferences/staff/410/apply",
        headers={
            "Idempotency-Key": "preference-replay-mismatch",
            "X-Correlation-ID": "preference-replay-correlation",
        },
        json={
            **_profile_body(),
            "expected_version": 0,
            "preview_fingerprint": _FINGERPRINT,
            "reason": "重送偏好",
        },
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "idempotency_mismatch"
    assert error["code"] == "idempotency_conflict"
    assert error["correlation_id"] == "preference-replay-correlation"
