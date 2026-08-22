"""
File: test_global_typed_error_boundary.py
Description: 以真 FastAPI TestClient 驗證 Global error、correlation 與去敏契約。
"""

from __future__ import annotations

from datetime import datetime, timezone
import re

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.anomaly_registry import get_anomaly_application
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.main import app as production_app
from api.routes import admin_auth, anomaly_registry, data_browser_admin
from api.schemas.errors import GlobalTypedErrorView
from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.access.authentication_session import (
    AdminPrincipal,
    AdminSessionStorageError,
    MfaEnrollmentChallenge,
    PasswordLoginChallenge,
)

from tests.test_order_reopen_router import InMemoryOrderReopenRepository, _create_app, _default_facts


SAFE_CORRELATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$")
PRINCIPAL = AdminPrincipal(1, "admin_tester", "Admin Tester", "system_admin", is_root=True)


def _admin_app(
    repo: InMemoryOrderReopenRepository | None = None,
    *,
    authenticate: bool = True,
) -> FastAPI:
    app = _create_app(repo or InMemoryOrderReopenRepository(), authenticate=authenticate)
    app.include_router(admin_auth.router)
    return app


def _error(response):
    payload = response.json()
    assert set(payload) == {"detail"}
    assert set(payload["detail"]) == {"error"}
    error = payload["detail"]["error"]
    assert set(error) == {
        "category",
        "code",
        "message",
        "field_errors",
        "domain_blockers",
        "retryable",
        "correlation_id",
        "current_version",
    }
    return error


def _assert_no_sensitive_values(value, forbidden: tuple[str, ...]) -> None:
    rendered = repr(value)
    for secret in forbidden:
        assert secret not in rendered


def test_a_health_success_keeps_existing_base_response_shape():
    response = TestClient(production_app).get("/health")

    assert response.status_code == 200
    assert set(response.json()) == {"success", "message", "data", "error"}
    assert response.json()["data"]["status"] == "healthy"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"username": 7, "password": "password"},
        {"username": "admin", "password": None},
        {"username": "admin", "password": "password", "unexpected": "secret"},
    ],
)
def test_b_real_admin_challenge_validation_is_typed_and_redacted(body):
    response = TestClient(_admin_app()).post(
        "/api/v1/admin/auth/login/challenges",
        headers={"X-Correlation-ID": "validation-correlation"},
        json=body,
    )

    assert response.status_code == 422
    error = _error(response)
    assert error["category"] == "validation"
    assert response.headers["X-Correlation-ID"] == "validation-correlation"
    _assert_no_sensitive_values(error, ("secret",))
    assert all(set(item) == {"field", "code", "message"} for item in error["field_errors"])


def test_b_query_validation_uses_fixed_query_field_path_without_calling_application():
    app = _admin_app()
    app.include_router(anomaly_registry.router)
    query_called = False

    class QueryMustNotRun:
        def query_summaries(self, **_kwargs):
            nonlocal query_called
            query_called = True
            raise AssertionError("query application must not run for invalid query")

    app.dependency_overrides[get_anomaly_application] = lambda: QueryMustNotRun()
    response = TestClient(app).get(
        "/api/v1/anomalies?limit=0",
        headers={"X-Correlation-ID": "query-validation"},
    )

    assert response.status_code == 422
    error = _error(response)
    assert any(item["field"] == "query.limit" for item in error["field_errors"])
    assert not query_called


def test_b_path_validation_uses_fixed_path_field_path():
    response = TestClient(_admin_app()).post(
        "/api/v1/orders/" + ("x" * 51) + "/reopen/preview",
        headers={"X-Correlation-ID": "path-validation"},
    )

    assert response.status_code == 422
    error = _error(response)
    assert any(item["field"] == "path.case_no" for item in error["field_errors"])


def test_b_header_validation_uses_fixed_lowercase_header_path():
    response = TestClient(_admin_app()).post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "header-validation"},
        json={
            "expected_order_version": 4,
            "expected_client_finance_version": 2,
            "expected_payroll_version": 3,
            "preview_fingerprint": "0" * 64,
            "reason": "valid reason",
        },
    )

    assert response.status_code == 422
    error = _error(response)
    assert any(item["field"] == "header.idempotency-key" for item in error["field_errors"])


def test_b_null_body_is_rejected_without_echoing_input():
    response = TestClient(_admin_app()).post(
        "/api/v1/admin/auth/login/challenges",
        headers={"X-Correlation-ID": "null-body"},
        json=None,
    )

    assert response.status_code == 422
    error = _error(response)
    assert error["correlation_id"] == "null-body"


def test_c_valid_correlation_is_preserved_for_success_and_error():
    client = TestClient(_admin_app())
    success = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "kept.correlation:01"},
    )
    error = client.get(
        "/api/v1/route-does-not-exist",
        headers={"X-Correlation-ID": "kept.correlation:02"},
    )

    assert success.status_code == 200
    assert success.headers["X-Correlation-ID"] == "kept.correlation:01"
    assert error.status_code == 404
    assert error.headers["X-Correlation-ID"] == "kept.correlation:02"
    assert _error(error)["correlation_id"] == "kept.correlation:02"


def test_c_missing_correlation_is_generated_and_injected_into_required_header():
    client = TestClient(_admin_app())
    preview = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "preview-correlation"},
    )
    response = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"Idempotency-Key": "generated-correlation-key"},
        json={
            "expected_order_version": 4,
            "expected_client_finance_version": 2,
            "expected_payroll_version": 3,
            "preview_fingerprint": preview.json()["data"]["preview_fingerprint"],
            "reason": "missing correlation is allowed",
        },
    )

    assert response.status_code == 200
    generated = response.headers["X-Correlation-ID"]
    assert SAFE_CORRELATION.fullmatch(generated)
    assert generated != "order-reopen-preview"


@pytest.mark.parametrize("value", [" ", " leading", "trailing ", "bad/value", "x" * 192])
def test_c_invalid_correlation_is_rejected_without_reflection(value):
    response = TestClient(_admin_app()).get(
        "/api/v1/route-does-not-exist",
        headers={"X-Correlation-ID": value},
    )

    assert response.status_code == 422
    generated = response.headers["X-Correlation-ID"]
    assert SAFE_CORRELATION.fullmatch(generated)
    assert generated != value
    error = _error(response)
    assert error["code"] == "invalid_correlation_id"
    if value.strip():
        _assert_no_sensitive_values(error, (value,))


def test_c_duplicate_correlation_is_rejected_without_downstream_call_or_reflection():
    response = TestClient(_admin_app()).get(
        "/api/v1/route-does-not-exist",
        headers=[("X-Correlation-ID", "first-correlation"), ("X-Correlation-ID", "second-correlation")],
    )

    assert response.status_code == 422
    generated = response.headers["X-Correlation-ID"]
    assert SAFE_CORRELATION.fullmatch(generated)
    assert generated not in {"first-correlation", "second-correlation"}
    _assert_no_sensitive_values(response.json(), ("first-correlation", "second-correlation"))


def test_d_missing_and_expired_bearer_are_forbidden_typed_errors(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setattr("api.dependencies.admin_auth.get_admin_session", lambda _token: None)
    client = TestClient(_admin_app(None, authenticate=False))

    missing = client.post("/api/v1/orders/CASE-RO-001/reopen/preview")
    expired = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"Authorization": "Bearer expired-token"},
    )

    assert missing.status_code == 401
    assert expired.status_code == 401
    assert _error(missing)["category"] == "forbidden"
    assert _error(expired)["category"] == "forbidden"


def test_d_session_storage_failure_is_redacted_and_retryable(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")

    def unavailable(_token):
        raise AdminSessionStorageError("database-secret-token")

    monkeypatch.setattr("api.dependencies.admin_auth.get_admin_session", unavailable)
    response = TestClient(_admin_app(authenticate=False)).post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"Authorization": "Bearer valid-shaped-token"},
    )

    assert response.status_code == 503
    error = _error(response)
    assert error["code"] == "admin_session_storage_unavailable"
    assert error["retryable"] is True
    _assert_no_sensitive_values(error, ("database-secret-token",))


def test_d_forbidden_dependency_is_typed():
    app = _admin_app()

    def forbidden():
        raise HTTPException(status_code=403, detail="permission-secret")

    app.dependency_overrides[require_system_admin] = forbidden
    response = TestClient(app).post("/api/v1/orders/CASE-RO-001/reopen/preview")

    assert response.status_code == 403
    error = _error(response)
    assert error["category"] == "forbidden"
    _assert_no_sensitive_values(error, ("permission-secret",))


def test_e_real_admin_rate_limit_keeps_status_and_retryable(monkeypatch):
    def rate_limited(*_args, **_kwargs):
        from subsystems.access.authentication_session import AdminLoginRateLimitedError

        raise AdminLoginRateLimitedError()

    app = _admin_app()
    monkeypatch.setattr(admin_auth, "issue_password_login_challenge", rate_limited)
    response = TestClient(app).post(
        "/api/v1/admin/auth/login/challenges",
        headers={"X-Correlation-ID": "rate-limit-correlation"},
        json={"username": "admin", "password": "password"},
    )

    assert response.status_code == 429
    error = _error(response)
    assert error["code"] == "login_rate_limited"
    assert error["retryable"] is True


def test_f_existing_typed_route_error_is_rebased_without_double_wrap():
    repo = InMemoryOrderReopenRepository(
        facts=_default_facts(
            status=OrderLifecycleStatus.IN_SERVICE,
            cancellation_effective=False,
        )
    )
    response = TestClient(_admin_app(repo)).post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "request-correlation"},
    )

    assert response.status_code == 409
    error = _error(response)
    assert error["category"] == "domain_blocked"
    assert error["code"] == "order_reopen_requires_cancelled_order"
    assert error["correlation_id"] == "request-correlation"
    assert "error" not in response.json()["detail"]["error"]


def test_f_retry_after_is_preserved_on_typed_unavailable():
    repo = InMemoryOrderReopenRepository()
    repo.fail_with_mysql_code = 1205
    response = TestClient(_admin_app(repo)).post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "retry-correlation"},
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    error = _error(response)
    assert error["retryable"] is True
    assert error["correlation_id"] == "retry-correlation"


def test_g_mfa_legacy_detail_does_not_expose_provisioning_secret(monkeypatch):
    challenge = MfaEnrollmentChallenge(
        "challenge-id",
        "challenge-token-secret",
        "otpauth://totp/private-secret",
        datetime(2026, 8, 17, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(admin_auth, "authenticate_admin", lambda *_a, **_k: challenge)
    response = TestClient(_admin_app()).post(
        "/api/v1/admin/auth/login",
        headers={"X-Correlation-ID": "mfa-correlation"},
        json={"username": "admin", "password": "password", "totp_code": "123456"},
    )

    assert response.status_code == 403
    error = _error(response)
    assert error["code"] == "mfa_enrollment_required"
    _assert_no_sensitive_values(
        response.json(),
        ("challenge-token-secret", "otpauth://totp/private-secret", "provisioning_uri"),
    )


def test_g_mfa_enrollment_is_password_authenticated_success_data(monkeypatch):
    challenge = MfaEnrollmentChallenge(
        "challenge-id",
        "challenge-token-secret",
        "otpauth://totp/private-secret",
        datetime(2026, 8, 17, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        admin_auth, "issue_password_login_challenge", lambda *_a, **_k: challenge
    )

    response = TestClient(_admin_app()).post(
        "/api/v1/admin/auth/login/challenges",
        json={"username": "admin", "password": "password"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "detail" not in payload
    assert payload["data"] == {
        "challenge_type": "mfa_enrollment",
        "challenge_id": "challenge-id",
        "challenge_token": "challenge-token-secret",
        "expires_at": "2026-08-17T00:00:00Z",
        "provisioning_uri": "otpauth://totp/private-secret",
    }
    assert "access_token" not in payload["data"]


def test_g_unknown_data_browser_dict_is_status_redacted():
    app = _admin_app()
    app.include_router(data_browser_admin.router)
    response = TestClient(app).patch(
        "/api/v1/admin/data-browser/private_table/secret-row",
    )

    assert response.status_code == 410
    error = _error(response)
    assert error["code"] == "resource_retired"
    _assert_no_sensitive_values(
        response.json(),
        ("private_table", "secret-row", "replacement", "owning Domain"),
    )


def test_h_unknown_route_and_method_are_typed_with_headers():
    client = TestClient(_admin_app())
    missing = client.get(
        "/api/v1/route-does-not-exist",
        headers={"X-Correlation-ID": "not-found-correlation"},
    )
    method = client.get(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "method-correlation"},
    )

    assert missing.status_code == 404
    assert method.status_code == 405
    assert _error(missing)["code"] == "resource_not_found"
    assert _error(method)["code"] == "method_not_allowed"
    assert method.headers["X-Correlation-ID"] == "method-correlation"


def test_i_unexpected_exception_is_redacted_in_response_and_log(monkeypatch, caplog):
    async def explode(*_args, **_kwargs):
        raise RuntimeError("unexpected-secret-value")

    monkeypatch.setattr(admin_auth, "_authenticate", explode)
    client = TestClient(_admin_app(), raise_server_exceptions=False)
    with caplog.at_level("ERROR"):
        response = client.post(
            "/api/v1/admin/auth/login",
            headers={"X-Correlation-ID": "unexpected-correlation"},
            json={"username": "admin", "password": "password"},
        )

    assert response.status_code == 500
    error = _error(response)
    assert error["code"] == "internal_error"
    _assert_no_sensitive_values(response.json(), ("unexpected-secret-value",))
    assert "unexpected-secret-value" not in caplog.text


def test_i_response_validation_failure_is_redacted(monkeypatch):
    monkeypatch.setattr(admin_auth, "authenticate_admin", lambda *_a, **_k: ("token", datetime.now(timezone.utc), PRINCIPAL))
    monkeypatch.setattr(
        admin_auth,
        "_login_response",
        lambda *_a, **_k: {"data": {"invalid": "response-secret"}, "message": "x"},
    )
    response = TestClient(_admin_app(), raise_server_exceptions=False).post(
        "/api/v1/admin/auth/login",
        headers={"X-Correlation-ID": "response-validation"},
        json={"username": "admin", "password": "password"},
    )

    assert response.status_code == 500
    error = _error(response)
    assert error["code"] == "response_contract_mismatch"
    _assert_no_sensitive_values(response.json(), ("response-secret",))


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"category": "not-a-category", "code": "x", "message": "m", "field_errors": [], "domain_blockers": [], "retryable": False, "correlation_id": "c", "current_version": None},
        {"category": "validation", "code": "x", "message": "m", "field_errors": [], "domain_blockers": [], "retryable": 1, "correlation_id": "c", "current_version": None},
        {"category": "validation", "code": "x", "message": "m", "field_errors": [], "domain_blockers": [], "retryable": False, "correlation_id": "c", "current_version": None, "extra": "drift"},
    ],
)
def test_j_global_schema_rejects_missing_wrong_enum_wrong_primitive_and_extra(payload):
    with pytest.raises(ValidationError):
        GlobalTypedErrorView.model_validate(payload, strict=True)


def test_j_global_schema_requires_arrays_and_only_allows_nullable_current_version():
    payload = {
        "category": "validation",
        "code": "request_validation_error",
        "message": "invalid",
        "field_errors": [],
        "domain_blockers": [],
        "retryable": False,
        "correlation_id": "schema-correlation",
        "current_version": None,
    }
    valid = GlobalTypedErrorView.model_validate(payload)
    assert valid.current_version is None
    with pytest.raises(ValidationError):
        GlobalTypedErrorView.model_validate({**payload, "current_version": "1"}, strict=True)
    with pytest.raises(ValidationError):
        GlobalTypedErrorView.model_validate({key: value for key, value in payload.items() if key != "field_errors"}, strict=True)


def test_k_cors_exposes_only_approved_error_headers_without_wildcards():
    client = TestClient(production_app)
    preflight = client.options(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "authorization,x-correlation-id,x-preview-fingerprint,if-match,if-none-match"
            ),
        },
    )
    response = client.get(
        "/api/v1/route-does-not-exist",
        headers={
            "Origin": "http://localhost:8501",
            "X-Correlation-ID": "cors-correlation",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:8501"
    allowed_headers = preflight.headers["access-control-allow-headers"].lower()
    assert "*" not in allowed_headers
    for header in ("authorization", "x-correlation-id", "x-preview-fingerprint", "if-match", "if-none-match"):
        assert header in allowed_headers
    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == "http://localhost:8501"
    assert "*" not in response.headers.get("access-control-allow-methods", "")
    assert response.headers["access-control-expose-headers"] == "X-Correlation-ID, Retry-After, WWW-Authenticate"
