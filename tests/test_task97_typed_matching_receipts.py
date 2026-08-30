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
            },
        ),
    ),
)
def test_matching_receipts_reject_unowned_extra_fields(model, payload):
    assert model.model_validate(payload).model_dump(mode="json") == payload

    with pytest.raises(ValidationError):
        model.model_validate({**payload, "raw_database_row": {"secret": "leak"}})
