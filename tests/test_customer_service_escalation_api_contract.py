"""
File: test_customer_service_escalation_api_contract.py
Description: 驗證客服 escalation 路由的 OpenAPI typed contract 與 closed schema。
"""

from datetime import datetime, timezone

import pytest
from fastapi.routing import APIRoute

from api.dependencies.admin_auth import require_customer_service_handler, require_customer_service_reader
from api.routes import customer_service
from api.schemas.customer_service import (
    HumanEscalationClaimRequest,
    HumanEscalationClaimApplyRequest,
    HumanEscalationCreateRequest,
    HumanEscalationCreateApplyRequest,
    HumanEscalationHandlingRequest,
    HumanEscalationHandlingApplyRequest,
    HumanEscalationResolveRequest,
    HumanEscalationResolveApplyRequest,
)
from domains.customer_service.escalation import (
    AlertStatus,
    AutomationHoldState,
    EscalationWorkflowStatus,
    TriggerCode,
)
from domains.customer_service.ticket import CustomerServiceCategory
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.customer_service.escalation_contracts import HumanEscalationReceipt, HumanEscalationView


def test_escalation_openapi_contract_is_mounted_and_typed() -> None:
    from api.main import app

    openapi = app.openapi()
    expected = {
        "/api/v1/customer-service/escalations": (
            "post",
            "HumanEscalationCreateApplyRequest",
            "BaseResponse_HumanEscalationReceiptResponse_",
        ),
        "/api/v1/customer-service/escalations/preview": (
            "post",
            "HumanEscalationCreateRequest",
            "BaseResponse_HumanEscalationPreviewResponse_",
        ),
        "/api/v1/customer-service/escalations/{escalation_id}": (
            "get",
            None,
            "BaseResponse_HumanEscalationViewResponse_",
        ),
        "/api/v1/customer-service/escalations/{escalation_id}/claim": (
            "post",
            "HumanEscalationClaimApplyRequest",
            "BaseResponse_HumanEscalationReceiptResponse_",
        ),
        "/api/v1/customer-service/escalations/{escalation_id}/claim/preview": (
            "post",
            "HumanEscalationClaimRequest",
            "BaseResponse_HumanEscalationPreviewResponse_",
        ),
        "/api/v1/customer-service/escalations/{escalation_id}/handling": (
            "post",
            "HumanEscalationHandlingApplyRequest",
            "BaseResponse_HumanEscalationReceiptResponse_",
        ),
        "/api/v1/customer-service/escalations/{escalation_id}/handling/preview": (
            "post",
            "HumanEscalationHandlingRequest",
            "BaseResponse_HumanEscalationPreviewResponse_",
        ),
        "/api/v1/customer-service/escalations/{escalation_id}/resolve": (
            "post",
            "HumanEscalationResolveApplyRequest",
            "BaseResponse_HumanEscalationReceiptResponse_",
        ),
        "/api/v1/customer-service/escalations/{escalation_id}/resolve/preview": (
            "post",
            "HumanEscalationResolveRequest",
            "BaseResponse_HumanEscalationPreviewResponse_",
        ),
    }
    operation_ids = []
    schemas = openapi["components"]["schemas"]

    for path, (method, request_model, response_model) in expected.items():
        operation = openapi["paths"][path][method]
        operation_ids.append(operation["operationId"])
        if request_model is not None:
            body = operation["requestBody"]
            assert body["required"] is True
            assert body["content"]["application/json"]["schema"] == {
                "$ref": f"#/components/schemas/{request_model}"
            }
            assert schemas[request_model]["additionalProperties"] is False
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{response_model}"
        }

    assert len(operation_ids) == len(set(operation_ids))


def test_escalation_routes_require_role_specific_dependencies() -> None:
    expected = {
        ("POST", "/api/v1/customer-service/escalations"): require_customer_service_handler,
        ("GET", "/api/v1/customer-service/escalations/{escalation_id}"): require_customer_service_reader,
        ("POST", "/api/v1/customer-service/escalations/{escalation_id}/claim"): require_customer_service_handler,
        ("POST", "/api/v1/customer-service/escalations/preview"): require_customer_service_handler,
        ("POST", "/api/v1/customer-service/escalations/{escalation_id}/claim/preview"): require_customer_service_handler,
        ("POST", "/api/v1/customer-service/escalations/{escalation_id}/handling"): require_customer_service_handler,
        ("POST", "/api/v1/customer-service/escalations/{escalation_id}/handling/preview"): require_customer_service_handler,
        ("POST", "/api/v1/customer-service/escalations/{escalation_id}/resolve"): require_customer_service_handler,
        ("POST", "/api/v1/customer-service/escalations/{escalation_id}/resolve/preview"): require_customer_service_handler,
    }

    for (method, path), dependency in expected.items():
        matches = [
            route
            for route in customer_service.escalation_router.routes
            if isinstance(route, APIRoute) and route.path == path and method in route.methods
        ]
        assert len(matches) == 1, f"expected exactly one {method} {path} route"
        dependency_calls = {item.call for item in matches[0].dependant.dependencies}
        assert dependency in dependency_calls


def _principal() -> AdminPrincipal:
    return AdminPrincipal(
        id=7,
        username="operator",
        display_name="Operator",
        role="system_admin",
        is_root=True,
    )


def test_escalation_commands_are_closed_and_require_identity() -> None:
    claim = HumanEscalationClaimRequest(
        expected_escalation_version=0,
        idempotency_key="m4-claim-1",
        correlation_id="m4-correlation-1",
    )
    assert claim.expected_escalation_version == 0
    with pytest.raises(ValueError):
        HumanEscalationClaimRequest(
            expected_escalation_version=0,
            idempotency_key="m4-claim-1",
            correlation_id="m4-correlation-1",
            line_user_id="U-raw",
        )
    with pytest.raises(ValueError):
        HumanEscalationResolveRequest(
            expected_escalation_version=0,
            expected_ticket_version=0,
            resolution_code="done",
            resolution_evidence_digest="not-a-digest",
            idempotency_key="m4-resolve-1",
            correlation_id="m4-correlation-1",
        )
    create = HumanEscalationCreateRequest(
        source_event_identity="line-event:m4",
        source_kind="line_inbox",
        source_fingerprint="a" * 64,
        trigger_code="complaint",
        trigger_policy_version="complaint.v1",
        ticket_category="other",
        masked_context={
            "summary_code": "complaint_explicit",
            "policy_version": "complaint.v1",
            "category": "other",
            "redaction_version": "m4-mask.v1",
        },
        hold_scope="line:conversation:m4",
        idempotency_key="m4-create-1",
        correlation_id="m4-correlation-1",
    )
    assert create.masked_context["summary_code"] == "complaint_explicit"
    with pytest.raises(ValueError):
        HumanEscalationCreateApplyRequest(
            source_event_identity="line-event:m4",
            source_kind="line_inbox",
            source_fingerprint="a" * 64,
            trigger_code="complaint",
            trigger_policy_version="complaint.v1",
            ticket_category="other",
            masked_context={"raw_message": "不要穿透"},
            hold_scope="line:conversation:m4",
            idempotency_key="m4-create-2",
            correlation_id="m4-correlation-2",
            preview_fingerprint="b" * 64,
        )


def test_escalation_route_uses_typed_receipt_projection(monkeypatch) -> None:
    committed_at = datetime(2026, 8, 21, tzinfo=timezone.utc)
    receipt = HumanEscalationReceipt(
        "receipt:m4",
        "customer_service_human_escalation",
        "claim",
        11,
        "ticket:21",
        EscalationWorkflowStatus.CLAIMED,
        AutomationHoldState.ACTIVE,
        "version:m4",
        False,
        "m4-correlation-1",
        committed_at,
    )

    class FakeApplication:
        def claim(self, command):
            assert command.escalation_id == 11
            assert command.actor.actor_id == "admin:7"
            return receipt

    monkeypatch.setattr(customer_service, "_escalation_application", lambda: FakeApplication())
    response = customer_service.claim_escalation(
        11,
        HumanEscalationClaimApplyRequest(
            expected_escalation_version=0,
            idempotency_key="m4-claim-1",
            correlation_id="m4-correlation-1",
            preview_fingerprint="b" * 64,
        ),
        _principal(),
    )
    assert response.data is not None
    assert response.data.resulting_workflow_status == "claimed"
    assert response.data.resulting_hold_state == "active"


def test_escalation_view_projection_is_masked() -> None:
    view = HumanEscalationView(
        11,
        "ticket:21",
        CustomerServiceCategory.OTHER,
        "high",
        TriggerCode.COMPLAINT,
        EscalationWorkflowStatus.OPEN,
        0,
        AutomationHoldState.ACTIVE,
        "opaque",
        {
            "summary_code": "complaint_explicit",
            "policy_version": "complaint.v1",
            "category": "other",
            "redaction_version": "m4-mask.v1",
        },
        AlertStatus.PENDING,
        "version:m4",
        datetime(2026, 8, 21, tzinfo=timezone.utc),
        datetime(2026, 8, 21, tzinfo=timezone.utc),
        ("claim",),
    )
    projected = customer_service._escalation_view_response(view)
    assert set(projected.masked_context) == {
        "summary_code",
        "policy_version",
        "category",
        "redaction_version",
    }
    assert "ticket:21" == projected.ticket_ref
