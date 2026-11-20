"""Candidate information errors retain actionable reasons at the Global HTTP boundary."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_matching_sender, require_system_admin
from api.exception_handlers.typed_errors import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import candidate_contact_pool as routes
from api.routes import caregiver_segment_availability as availability_routes
from api.schemas.candidate_contact_pool import SendCandidateInformationRequest
from api.schemas.errors import GlobalTypedErrorResponseView
from domains.scheduling.matching_communication import CandidateMatchingError
from subsystems.access.authentication_session import AdminPrincipal
from pydantic import ValidationError


def test_only_resend_may_omit_the_preview_fingerprint():
    fields = {"actor": "operator-1", "event_key": "direct-send"}
    assert SendCandidateInformationRequest(**fields, resend=True).preview_fingerprint is None
    with pytest.raises(ValidationError, match="required for the initial send"):
        SendCandidateInformationRequest(**fields)


@pytest.mark.parametrize("operation", ["preview", "send"])
@pytest.mark.parametrize("code, category, text", [
    ("caregiver_has_no_line_delivery_identity", "domain_blocked", "尚未完成 LINE 綁定"),
    ("candidate_information_preview_stale", "conflict", "重新開啟寄送確認"),
    ("candidate_contact_order_not_negotiating", "domain_blocked", "已非洽談中"),
    ("candidate_contact_not_found", "domain_blocked", "可寄送的候選清單"),
    ("candidate_weekly_service_dates_not_ready", "domain_blocked", "確認並保存預計日期"),
    ("candidate_information_idempotency_conflict", "idempotency_mismatch", "確認原寄送結果"),
    ("candidate_information_package_already_queued", "conflict", "已有案件資訊投遞任務"),
    ("private provider exception must stay hidden", "conflict", "資料版本或目前狀態發生衝突"),
])
def test_information_errors_survive_global_boundary_without_exposing_unknown_details(monkeypatch, operation, code, category, text):
    def fail(*args, **kwargs):
        raise ValueError(code)

    monkeypatch.setattr(routes.workflow, "preview_information_package" if operation == "preview" else "send_information", fail)
    app = FastAPI()
    install_typed_error_handlers(app)
    app.add_middleware(CorrelationBoundaryMiddleware)
    app.include_router(routes.router)
    app.dependency_overrides[require_line_matching_sender] = lambda: AdminPrincipal(None, "operator-1", "Synthetic operator", "system_admin")
    client = TestClient(app)
    path = "/api/v1/orders/CASE-1/candidate-contact-pool/candidates/3/information"
    headers = {"X-Correlation-ID": "candidate-information-error-test"}
    if operation == "preview":
        response = client.get(path + "/package/preview", headers=headers)
    else:
        response = client.post(path, headers=headers, json={"actor": "operator-1", "event_key": "candidate-error-test", "preview_fingerprint": "a" * 64})
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


@pytest.mark.parametrize("operation", ["search", "add"])
@pytest.mark.parametrize(("code", "action"), [
    ("candidate_contact_order_not_negotiating", "重新讀取案件進度"),
    ("candidate_matching_assignment_present", "已有正式指派"),
    ("candidate_matching_data_needs_review", "資料待核對"),
    ("candidate_matching_service_started", "已有正式服務紀錄"),
    ("candidate_inquiry_dates_missing", "補存預計服務日期"),
    ("candidate_inquiry_dates_invalid", "保存正確日期"),
    ("candidate_inquiry_dates_too_long", "超過 60 天"),
    ("candidate_staff_not_active", "確認月嫂名冊"),
])
def test_matching_blockers_reach_candidate_workbench(monkeypatch, operation, code, action):
    def blocked(*args, **kwargs):
        raise CandidateMatchingError(code)

    app = FastAPI()
    install_typed_error_handlers(app)
    app.include_router(routes.router)
    app.include_router(availability_routes.router)
    principal = AdminPrincipal(None, "operator-1", "Synthetic operator", "system_admin")
    app.dependency_overrides[require_line_matching_sender] = lambda: principal
    app.dependency_overrides[require_system_admin] = lambda: principal
    if operation == "search":
        monkeypatch.setattr(availability_routes, "search_candidate_inquiry_availability", blocked)
        path = "availability/search"
        payload = {"as_of": "2026-11-20", "segment_drafts": []}
    else:
        monkeypatch.setattr(routes.workflow, "add_candidates", blocked)
        path = "candidates"
        payload = {
            "actor": "operator-1", "event_key": "candidate-error-test",
            "candidates": [{"staff_id": 7, "start_date": "2026-11-20", "end_date": "2026-11-21"}],
        }
    response = TestClient(app).post(f"/api/v1/orders/CASE-1/candidate-contact-pool/{path}", json=payload)
    assert response.status_code == 409
    error = GlobalTypedErrorResponseView.model_validate(response.json()).detail.error
    assert error.category == "conflict" and error.code == code and action in error.message
