"""
File: test_runtime_alert_target_admin_contract.py
Description: 驗證 runtime health／alert target API 的封閉欄位與去敏契約。
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies.admin_auth import require_line_monitor_reader
from api.main import app
from api.routes import runtime_health as runtime_routes
from api.schemas.runtime_health import (
    AlertAdminTargetRequest,
    AlertTargetEnabledRequest,
    AlertTargetMutationResponse,
    AlertTargetViewResponse,
    ResetLineAlertGroupRequest,
)


def test_public_target_view_has_no_raw_identity_fields():
    view = AlertTargetViewResponse(
        target_id=3,
        target_kind="group",
        display_label="LINE 群組告警對象 #3",
        state="active",
        minimum_status="warning",
        current_version="opaque-token",
        updated_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    payload = view.model_dump()
    assert "group_id" not in payload
    assert "admin_user_id" not in payload
    assert "display_name" not in payload


def test_runtime_health_routes_filter_uncontracted_details(monkeypatch):
    @dataclass(frozen=True)
    class Record:
        check_name: str
        component: str
        status: str
        raw_status: str
        message: str
        response_ms: int | None
        consecutive_failures: int
        consecutive_successes: int
        checked_at: datetime
        status_changed_at: datetime
        details: dict[str, object]

    now = datetime(2026, 8, 21, tzinfo=timezone.utc)
    record = Record(
        "line-worker",
        "LINE Worker",
        "healthy",
        "ok",
        "運作正常",
        5,
        0,
        3,
        now,
        now,
        {"group_id": "C-secret", "access_token": "secret"},
    )
    monkeypatch.setattr(runtime_routes, "_query", lambda *_args: (record,))
    test_app = FastAPI()
    test_app.include_router(runtime_routes.router)
    test_app.dependency_overrides[require_line_monitor_reader] = lambda: object()

    response = TestClient(test_app).get("/api/v1/runtime/health-status")

    assert response.status_code == 200
    assert response.json() == [
        {
            "check_name": "line-worker",
            "component": "LINE Worker",
            "status": "healthy",
            "raw_status": "ok",
            "message": "運作正常",
            "response_ms": 5,
            "consecutive_failures": 0,
            "consecutive_successes": 3,
            "checked_at": "2026-08-21T00:00:00Z",
            "status_changed_at": "2026-08-21T00:00:00Z",
        }
    ]


def test_reset_request_requires_all_command_identity_fields():
    request = ResetLineAlertGroupRequest(
        expected_version="opaque-token",
        reason="群組輪替",
        idempotency_key="reset-1",
        correlation_id="corr-1",
    )
    assert request.idempotency_key == "reset-1"


def test_mutation_response_is_closed_typed_shape():
    receipt = AlertTargetMutationResponse(
        receipt_id="receipt:abc",
        command_family="line_alert_target",
        operation="group_reset",
        target_id=3,
        previous_state="active",
        resulting_state="disabled",
        current_version="opaque-token-2",
        replayed=False,
        correlation_id="corr-1",
        committed_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    assert receipt.target_id == 3
    assert "group_id" not in receipt.model_dump()


def test_target_openapi_uses_exact_closed_enum_sets_and_rejects_unknown_values():
    schemas = app.openapi()["components"]["schemas"]
    view_properties = schemas["AlertTargetViewResponse"]["properties"]
    mutation_properties = schemas["AlertTargetMutationResponse"]["properties"]

    assert set(view_properties["target_kind"]["enum"]) == {"group", "admin_user"}
    assert set(view_properties["state"]["enum"]) == {"active", "disabled"}
    assert set(view_properties["minimum_status"]["enum"]) == {"warning", "critical"}
    assert mutation_properties["command_family"]["const"] == "line_alert_target"
    assert set(mutation_properties["operation"]["enum"]) == {
        "group_reset", "enable", "disable", "admin_target_add"
    }
    assert set(mutation_properties["previous_state"]["enum"]) == {"active", "disabled"}
    assert set(mutation_properties["resulting_state"]["enum"]) == {"active", "disabled"}

    view_payload = {
        "target_id": 3,
        "target_kind": "group",
        "display_label": "LINE 群組告警對象 #3",
        "state": "active",
        "minimum_status": "warning",
        "current_version": "opaque-token",
        "updated_at": datetime(2026, 8, 21, tzinfo=timezone.utc),
    }
    mutation_payload = {
        "receipt_id": "receipt:abc",
        "command_family": "line_alert_target",
        "operation": "group_reset",
        "target_id": 3,
        "previous_state": "active",
        "resulting_state": "disabled",
        "current_version": "opaque-token-2",
        "replayed": False,
        "correlation_id": "corr-1",
        "committed_at": datetime(2026, 8, 21, tzinfo=timezone.utc),
    }
    for model, payload, field, value in (
        (AlertTargetViewResponse, view_payload, "target_kind", "unknown"),
        (AlertTargetViewResponse, view_payload, "state", "unknown"),
        (AlertTargetViewResponse, view_payload, "minimum_status", "unknown"),
        (AlertTargetMutationResponse, mutation_payload, "command_family", "unknown"),
        (AlertTargetMutationResponse, mutation_payload, "operation", "unknown"),
        (AlertTargetMutationResponse, mutation_payload, "previous_state", "unknown"),
        (AlertTargetMutationResponse, mutation_payload, "resulting_state", "unknown"),
    ):
        with pytest.raises(ValidationError):
            model(**{**payload, field: value})


def test_admin_add_requires_client_command_identity():
    with pytest.raises(ValidationError):
        AlertAdminTargetRequest(admin_user_id=7, minimum_status="warning", reason="新增告警")


@pytest.mark.parametrize(
    "model, payload",
    [
        (
            AlertAdminTargetRequest,
            {
                "admin_user_id": 7,
                "minimum_status": "warning",
                "reason": "新增告警",
                "idempotency_key": "add-1",
                "correlation_id": "corr-1",
                "group_id": "must-not-cross-contract",
            },
        ),
        (
            ResetLineAlertGroupRequest,
            {
                "expected_version": "opaque-token",
                "reason": "群組輪替",
                "idempotency_key": "reset-1",
                "correlation_id": "corr-1",
                "group_id": "must-not-cross-contract",
            },
        ),
        (
            AlertTargetEnabledRequest,
            {
                "expected_version": "opaque-token",
                "enabled": False,
                "reason": "停用告警",
                "idempotency_key": "disable-1",
                "correlation_id": "corr-1",
                "group_id": "must-not-cross-contract",
            },
        ),
        (
            AlertTargetMutationResponse,
            {
                "receipt_id": "receipt:abc",
                "command_family": "line_alert_target",
                "operation": "group_reset",
                "target_id": 3,
                "previous_state": "active",
                "resulting_state": "disabled",
                "current_version": "opaque-token-2",
                "replayed": False,
                "correlation_id": "corr-1",
                "committed_at": datetime(2026, 8, 21, tzinfo=timezone.utc),
                "group_id": "must-not-cross-contract",
            },
        ),
    ],
)
def test_mutation_requests_reject_unknown_or_identity_fields(model, payload):
    with pytest.raises(ValidationError):
        model(**payload)


def test_admin_add_reason_is_required_and_whitespace_is_not_a_command():
    with pytest.raises(ValidationError):
        AlertAdminTargetRequest(
            admin_user_id=7,
            minimum_status="warning",
            idempotency_key="add-1",
            correlation_id="corr-1",
        )
    with pytest.raises(ValidationError):
        AlertAdminTargetRequest(
            admin_user_id=7,
            minimum_status="warning",
            reason="   ",
            idempotency_key="add-1",
            correlation_id="corr-1",
        )
