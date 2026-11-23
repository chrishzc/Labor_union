from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from api.routes.matches import router
from api.schemas.base import BaseResponse
from api.schemas.matches import (
    ManualMatchingProfilesPreviewView,
    ManualMatchingProfilesReceiptView,
    MatchingCaregiverWillingnessReceiptView,
    MatchingCustomerDecisionReceiptView,
    MatchingNotificationReceiptView,
    MatchingPlanCancellationReceiptView,
    MatchingPlanReceiptView,
)


def _response_model(path: str, method: str):
    for route in router.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == path
            and method in route.methods
        ):
            return route.response_model
    raise AssertionError(f"route not found: {method} {path}")


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    (
        (
            "POST",
            "/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/information",
            BaseResponse[MatchingNotificationReceiptView],
        ),
        (
            "PUT",
            "/api/v1/orders/{case_no}/matching-plans/{plan_id}/customer-decision",
            BaseResponse[MatchingCustomerDecisionReceiptView],
        ),
        (
            "PUT",
            "/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/willingness",
            BaseResponse[MatchingCaregiverWillingnessReceiptView],
        ),
        (
            "POST",
            "/api/v1/orders/{case_no}/matching-plans/{plan_id}/resumes",
            BaseResponse[MatchingNotificationReceiptView],
        ),
        (
            "POST",
            "/api/v1/orders/{case_no}/matching-plans/{plan_id}/resumes/manual-confirmation/preview",
            BaseResponse[ManualMatchingProfilesPreviewView],
        ),
        (
            "POST",
            "/api/v1/orders/{case_no}/matching-plans/{plan_id}/resumes/manual-confirmation",
            BaseResponse[ManualMatchingProfilesReceiptView],
        ),
        (
            "POST",
            "/api/v1/orders/{case_no}/matching-plans/{plan_id}/cancel",
            BaseResponse[MatchingPlanCancellationReceiptView],
        ),
        (
            "POST",
            "/api/v1/orders/{case_no}/matching-plans",
            BaseResponse[MatchingPlanReceiptView],
        ),
        (
            "GET",
            "/api/v1/orders/{case_no}/matching-plans/receipts/{event_key}",
            BaseResponse[MatchingPlanReceiptView],
        ),
    ),
)
def test_matching_plan_mutations_publish_closed_receipts(method, path, expected):
    assert _response_model(path, method) == expected


@pytest.mark.parametrize(
    ("model", "payload"),
    (
        (
            MatchingNotificationReceiptView,
            {
                "intent_id": 1,
                "line_delivery_task_id": None,
                "delivery_status": "pending",
                "notification_kind": "caregiver_info_1",
            },
        ),
        (
            MatchingCustomerDecisionReceiptView,
                {
                    "event_id": 2,
                    "case_no": "115000297",
                    "plan_id": 6,
                    "segment_id": None,
                    "event_key": "manual-customer-decision-97",
                    "communication_version": 3,
                    "source": "admin",
                    "willingness": None,
                    "customer_decision": "accepted",
                },
        ),
        (
            MatchingCaregiverWillingnessReceiptView,
                {
                    "event_id": 4,
                    "case_no": "115000297",
                    "plan_id": 6,
                    "segment_id": 8,
                    "event_key": "manual-caregiver-willingness-97",
                    "communication_version": 5,
                    "source": "admin",
                    "willingness": "willing",
                    "customer_decision": None,
                },
        ),
        (
            ManualMatchingProfilesPreviewView,
            {
                "case_no": "CASE-97",
                "plan_id": 6,
                "expected_version": 7,
                "segment_ids": [8],
                "confirmation_method": "phone",
                "reason": "operator confirmed delivery",
                "preview_fingerprint": "a" * 64,
                "apply_allowed": True,
            },
        ),
        (
            ManualMatchingProfilesReceiptView,
            {
                "case_no": "CASE-97",
                "plan_id": 6,
                "communication_version": 8,
                "event_ids": [9],
                "confirmation_method": "phone",
                "preview_fingerprint": "b" * 64,
                "replayed": False,
            },
        ),
        (
            MatchingPlanCancellationReceiptView,
            {"status": "cancelled", "event_id": 10},
        ),
        (
            MatchingPlanReceiptView,
            {
                "plan_id": 11,
                "case_no": "CASE-97",
                "version": 1,
                "status": "proposed",
                "result": "created",
                "segments": [
                    {
                        "segment_order": 1,
                        "staff_id": 12,
                        "assigned_start_date": "2026-09-01",
                        "assigned_end_date": "2026-09-28",
                    }
                ],
                "actor": "operator",
                "as_of": "2026-09-11",
                "event_key": "matching-plan:CASE-97:create",
                "command_fingerprint": "a" * 64,
                "replayed": False,
            },
        ),
    ),
)
def test_matching_receipts_reject_unowned_extra_fields(model, payload):
    assert model.model_validate(payload).model_dump(mode="json") == payload

    with pytest.raises(ValidationError):
        model.model_validate({**payload, "raw_database_row": {"secret": "leak"}})


@pytest.mark.parametrize("reason,code", [
    ("current confirmed service dates are required", "confirmed_service_dates_required"),
    ("current confirmed service dates mismatch", "confirmed_service_dates_mismatch"),
    ("invalid current confirmed service dates", "confirmed_service_dates_mismatch"),
    ("current confirmed service dates do not match plan segments", "confirmed_service_dates_mismatch"),
])
def test_customer_decision_date_blockers_remain_typed(monkeypatch, reason, code):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.exception_handlers.typed_errors import (
        CorrelationBoundaryMiddleware,
        install_typed_error_handlers,
    )
    from api.routes import matches as routes
    from subsystems.access.authentication_session import AdminPrincipal

    def reject(_command):
        raise ValueError(reason)

    monkeypatch.setattr(routes.matching_notifications, "record_manual_response", reject)
    app = FastAPI()
    app.include_router(routes.router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[routes.require_line_matching_override] = lambda: AdminPrincipal(
        1, "operator", "Test operator", "system_admin",
    )
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/orders/CASE-1/matching-plans/8/customer-decision",
            json={"decision": "accepted", "expected_version": 2, "reason": "",
                  "actor": "operator", "event_key": "manual-decision-date-error"},
        )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "domain_blocked"
    assert error["code"] == code
    assert error["domain_blockers"] == [code]
    assert "本次客戶決定未保存" in error["message"]
    assert error["retryable"] is False
