"""
File: test_runtime_alert_preferences.py
Description: 驗證保留分類讀取、管理員通知與退役群組／固定分類的拒絕契約。
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies.admin_auth import require_line_alert_manager, require_line_monitor_reader
from api.routes import runtime_health as runtime_routes
from api.schemas.runtime_health import (
    AlertTargetPreferencesPayload,
    AlertTargetPreferencesRequest,
    AlertTargetPreferencesResponse,
)
from subsystems.line.runtime_alert_application import RuntimeLineAlertProjector, _category_enabled
from subsystems.line.runtime_alert_target_contracts import RuntimeAlertTargetError


def test_category_enabled_default_group_disables_system_health():
    group_target = {"id": 1, "target_type": "group", "group_id": "C123"}
    assert _category_enabled(group_target, "system_health") is False
    assert _category_enabled(group_target, "customer_service") is True
    assert _category_enabled(group_target, "dispatch_matching") is True
    assert _category_enabled(group_target, "staff_leave_urgent") is True
    assert _category_enabled(group_target, "contract_signing") is True


def test_category_enabled_default_admin_enables_system_health():
    admin_target = {"id": 2, "target_type": "admin_user", "linked_line_user_id": "U123"}
    assert _category_enabled(admin_target, "system_health") is True


def test_category_enabled_explicit_json_overrides_defaults():
    custom_target = {
        "id": 3,
        "target_type": "group",
        "preferences_json": '{"system_health": true, "customer_service": false}',
    }
    assert _category_enabled(custom_target, "system_health") is True
    assert _category_enabled(custom_target, "customer_service") is False


def test_projector_skips_retired_group_without_delivery():
    repo = MagicMock()
    delivery_tasks = MagicMock()
    now = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)

    # Group target with system_health = False (default)
    target = {
        "id": 10,
        "target_type": "group",
        "group_id": "C-test-group",
        "minimum_status": "warning",
        "resulting_status": "critical",
        "check_name": "worker",
        "message": "heartbeat fail",
        "occurred_at_utc": now,
        "preferences_json": '{"system_health": false}',
    }
    repo.pending_alert_targets.return_value = (target,)

    projector = RuntimeLineAlertProjector(lambda: now)
    queued = projector.project(100, repo, delivery_tasks)

    assert queued == 0
    delivery_tasks.enqueue.assert_not_called()
    repo.append_alert_intent.assert_called_once_with(
        100, 10, None, "skipped", "group", "", "line_alert_group_retired"
    )


def test_projector_enqueues_when_system_health_enabled():
    repo = MagicMock()
    delivery_tasks = MagicMock()
    task_result = MagicMock()
    task_result.task_id.value = 888
    delivery_tasks.enqueue.return_value = task_result
    now = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)

    # Current notifications go to a bound administrator's personal LINE.
    target = {
        "id": 11,
        "target_type": "admin_user",
        "linked_line_user_id": "U-test-admin",
        "minimum_status": "warning",
        "resulting_status": "critical",
        "check_name": "worker",
        "message": "heartbeat fail",
        "occurred_at_utc": now,
        "preferences_json": '{"system_health": true}',
    }
    repo.pending_alert_targets.return_value = (target,)

    projector = RuntimeLineAlertProjector(lambda: now)
    queued = projector.project(101, repo, delivery_tasks)

    assert queued == 1
    delivery_tasks.enqueue.assert_called_once()
    repo.append_alert_intent.assert_called_once_with(
        101, 11, 888, "queued", "user", "U-test-admin"
    )


def test_preferences_schema_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AlertTargetPreferencesPayload(
            customer_service=True,
            dispatch_matching=True,
            staff_leave_urgent=True,
            system_health=False,
            contract_signing=True,
            unknown_category=True,
        )


def test_preferences_routes_read_fixed_rules_and_reject_patch(monkeypatch):
    test_app = FastAPI()
    test_app.include_router(runtime_routes.router)
    test_app.dependency_overrides[require_line_monitor_reader] = lambda: object()
    test_app.dependency_overrides[require_line_alert_manager] = lambda: object()

    stored_prefs = {
        "customer_service": True,
        "dispatch_matching": True,
        "staff_leave_urgent": True,
        "system_health": False,
        "contract_signing": True,
    }

    mock_app = MagicMock()
    mock_app.get_target_preferences.return_value = stored_prefs

    mock_app.save_target_preferences.side_effect = RuntimeAlertTargetError(
        "conflict", "line_alert_preferences_fixed", "通知分類使用固定規則，無法個別修改"
    )
    monkeypatch.setattr(runtime_routes, "_app", lambda: mock_app)

    client = TestClient(test_app)

    # GET
    res_get = client.get("/api/v1/runtime/line-alert-targets/10/preferences")
    assert res_get.status_code == 200
    assert res_get.json()["data"] == {
        "target_id": 10,
        "preferences": {
            "customer_service": True,
            "dispatch_matching": True,
            "staff_leave_urgent": True,
            "system_health": False,
            "contract_signing": True,
        },
    }

    # PATCH
    res_patch = client.patch(
        "/api/v1/runtime/line-alert-targets/10/preferences",
        json={
            "preferences": {
                "customer_service": True,
                "dispatch_matching": False,
                "staff_leave_urgent": True,
                "system_health": True,
                "contract_signing": True,
            }
        },
    )
    assert res_patch.status_code == 409
    assert res_patch.json()["detail"]["error"]["code"] == "line_alert_preferences_fixed"
    assert client.get("/api/v1/runtime/line-alert-targets/10/preferences").json() == res_get.json()
