"""Candidate information errors retain actionable reasons at the Global HTTP boundary."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_matching_sender
from api.exception_handlers.typed_errors import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import candidate_contact_pool as routes
from api.schemas.errors import GlobalTypedErrorResponseView
from subsystems.access.authentication_session import AdminPrincipal


@pytest.mark.parametrize("operation", ["preview", "send"])
@pytest.mark.parametrize("code, category, text", [
    ("caregiver_has_no_line_delivery_identity", "domain_blocked", "尚未完成 LINE 綁定"),
    ("candidate_information_preview_stale", "conflict", "重新開啟寄送確認"),
    ("candidate_contact_order_not_negotiating", "domain_blocked", "已非洽談中"),
    ("candidate_contact_not_found", "domain_blocked", "可寄送的候選清單"),
    ("candidate_weekly_service_dates_not_ready", "domain_blocked", "確認並保存預計日期"),
    ("candidate_information_idempotency_conflict", "idempotency_mismatch", "確認原寄送結果"),
    ("private provider exception must stay hidden", "conflict", "資料版本或目前狀態發生衝突"),
])
def test_information_errors_survive_global_boundary_without_exposing_unknown_details(monkeypatch, operation, code, category, text):
    def fail(*args, **kwargs):
        raise ValueError(code)

    monkeypatch.setattr(routes.workflow, "preview_information" if operation == "preview" else "send_information", fail)
    app = FastAPI()
    install_typed_error_handlers(app)
    app.add_middleware(CorrelationBoundaryMiddleware)
    app.include_router(routes.router)
    app.dependency_overrides[require_line_matching_sender] = lambda: AdminPrincipal(None, "operator-1", "Synthetic operator", "system_admin")
    client = TestClient(app)
    path = "/api/v1/orders/CASE-1/candidate-contact-pool/candidates/3/information"
    headers = {"X-Correlation-ID": "candidate-information-error-test"}
    if operation == "preview":
        response = client.get(path + "/preview", params={"info_type": 1}, headers=headers)
    else:
        response = client.post(path, headers=headers, json={"info_type": 1, "actor": "operator-1", "event_key": "candidate-error-test", "preview_fingerprint": "a" * 64})
    assert response.status_code == 409
    error = GlobalTypedErrorResponseView.model_validate(response.json()).detail.error
    assert error.category == category and text in error.message
    assert error.retryable is False
    assert error.correlation_id == response.headers["X-Correlation-ID"] == headers["X-Correlation-ID"]
    if code.startswith("private"):
        assert error.code == "conflict"
        assert code not in response.text
    else:
        assert error.code == code
