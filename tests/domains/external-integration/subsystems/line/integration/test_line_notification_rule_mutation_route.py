"""
File: test_line_notification_rule_mutation_route.py
Description: 驗證通知規則 route 傳遞 mutation 欄位並輸出封閉 typed view。
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymysql.err import OperationalError

from api.dependencies.admin_auth import (
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from api.exception_handlers import install_typed_error_handlers
from api.routes import line_notification_rules
from domains.line.identities import LineConfigurationRevision
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.notification_rule_administration import LineNotificationRuleMutationError


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "admin", "管理員", "system_admin")


def _definition() -> dict[str, object]:
    return {"rules": [{
        "id": "deposit_notice",
        "event_code": "deposit_confirmed",
        "recipient_selector": "case_group",
        "template_id": "deposit_notice",
        "enabled": False,
        "schedule": {"kind": "immediate"},
        "frequency": {"kind": "once"},
        "predicates": [],
    }]}


def test_save_and_delete_forward_preview_fingerprint(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class Application:
        def save(self, **command):
            calls.append(("save", command))
            return type("Result", (), {
                "revision": LineConfigurationRevision(4),
                "preview_fingerprint": "f" * 64,
                "cancelled_intent_count": 2,
                "cancelled_task_count": 2,
            })()

        def delete(self, **command):
            calls.append(("delete", command))
            return type("Result", (), {
                "rule_id": "deposit_notice",
                "revision": LineConfigurationRevision(5),
                "preview_fingerprint": "e" * 64,
                "cancelled_intent_count": 1,
                "cancelled_task_count": 1,
            })()

    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_rule_administration",
        lambda: Application(),
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_manager] = _principal
    client = TestClient(app)

    saved = client.put("/api/v1/line/notification-rules", json={
        "expected_revision": 3,
        "preview_fingerprint": "f" * 64,
        "definition": _definition(),
        "reason": "停用通知",
        "idempotency_key": "notification-save-1",
        "correlation_id": "notification-save-1",
    })
    deleted = client.request(
        "DELETE",
        "/api/v1/line/notification-rules/deposit_notice",
        json={
            "expected_revision": 4,
            "preview_fingerprint": "e" * 64,
            "reason": "刪除通知",
            "idempotency_key": "notification-delete-1",
            "correlation_id": "notification-delete-1",
        },
    )

    assert saved.status_code == 200
    assert saved.json()["data"] == {
        "revision": 4,
        "preview_fingerprint": "f" * 64,
        "cancelled_intent_count": 2,
        "cancelled_task_count": 2,
    }
    assert deleted.status_code == 200
    assert calls[0][1]["preview_fingerprint"].value == "f" * 64
    assert calls[1][1]["preview_fingerprint"].value == "e" * 64


def test_query_and_manual_replay_routes_preserve_typed_payloads(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class ConfigurationApplication:
        def get(self, *_args):
            return type("Snapshot", (), {
                "revision": LineConfigurationRevision(7),
                "definition_json": json.dumps(_definition()),
            })()

    class TimelineApplication:
        def list_case(self, case_no, actor):
            calls.append(("timeline", (case_no, actor)))
            return ({
                "source_event_id": 8,
                "event_code": "service_time_checkpoint",
                "occurred_at_utc": "2026-08-29 08:00:00",
                "historical_silent": False,
                "rule_id": None,
                "decision_status": "suppressed",
                "reason_code": "rule_shadow_mode",
                "recipient_type": None,
                "recipient_identity": None,
                "occurrence_number": None,
                "intent_status": None,
                "scheduled_at_utc": None,
                "delivery_status": None,
                "delivery_task_id": None,
            },)

    class ReplayApplication:
        def preview(self, source_event_id, actor):
            calls.append(("preview", (source_event_id, actor)))
            return {
                "source_event_id": source_event_id,
                "event_code": "service_time_checkpoint",
                "historical_silent": True,
                "matching_rule_count": 2,
                "will_create_new_immutable_source": True,
            }

        def apply(self, source_event_id, actor, reason, idempotency_key, correlation_id):
            calls.append(("apply", (source_event_id, actor, reason, idempotency_key, correlation_id)))
            return 9

    monkeypatch.setattr(
        line_notification_rules,
        "get_line_configuration_application",
        lambda: ConfigurationApplication(),
    )
    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_timeline_application",
        lambda: TimelineApplication(),
    )
    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_manual_replay_application",
        lambda: ReplayApplication(),
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_reader] = _principal
    app.dependency_overrides[require_line_configuration_manager] = _principal
    client = TestClient(app)

    catalog = client.get("/api/v1/line/notification-rules")
    timeline = client.get("/api/v1/line/notification-rules/timeline/CASE-1")
    replay_preview = client.post(
        "/api/v1/line/notification-rules/sources/8/manual-replay/preview"
    )
    replay_apply = client.post(
        "/api/v1/line/notification-rules/sources/8/manual-replay",
        json={
            "reason": "重新建立通知來源",
            "idempotency_key": "notification-replay-1",
            "correlation_id": "notification-replay-1",
        },
    )

    assert catalog.status_code == 200
    assert catalog.json()["data"] == {
        "revision": 7,
        "definition": _definition(),
    }
    assert timeline.status_code == 200
    assert timeline.json()["data"]["case_no"] == "CASE-1"
    assert timeline.json()["data"]["records"][0]["source_event_id"] == 8
    assert replay_preview.status_code == 200
    assert replay_preview.json()["data"] == {
        "source_event_id": 8,
        "event_code": "service_time_checkpoint",
        "historical_silent": True,
        "matching_rule_count": 2,
        "will_create_new_immutable_source": True,
    }
    assert replay_apply.status_code == 200
    assert replay_apply.json()["data"] == {
        "source_event_id": 8,
        "replayed_source_event_id": 9,
    }
    assert [name for name, _value in calls] == ["timeline", "preview", "apply"]


def test_save_rejects_raw_definition_extra_field_before_application(monkeypatch) -> None:
    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_rule_administration",
        lambda: (_ for _ in ()).throw(AssertionError("application must not run")),
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_manager] = _principal
    definition = _definition()
    definition["rules"][0]["raw_sql"] = "SELECT 1"
    response = TestClient(app).put("/api/v1/line/notification-rules", json={
        "expected_revision": 3,
        "preview_fingerprint": "f" * 64,
        "definition": definition,
        "reason": "invalid",
        "idempotency_key": "notification-save-invalid",
        "correlation_id": "notification-save-invalid",
    })
    assert response.status_code == 422


def test_whitespace_only_mutation_text_returns_redacted_typed_validation_error() -> None:
    app = FastAPI()
    install_typed_error_handlers(app)
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_manager] = _principal
    response = TestClient(app).put("/api/v1/line/notification-rules", json={
        "expected_revision": 3,
        "preview_fingerprint": "f" * 64,
        "definition": _definition(),
        "reason": " \t\n",
        "idempotency_key": "notification-validation-1",
        "correlation_id": "notification-validation-1",
    })
    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["category"] == "validation"
    assert error["code"] == "request_validation_error"
    assert "input" not in response.text
    assert error["field_errors"]


def test_unknown_runtime_error_is_internal_not_conflict(monkeypatch) -> None:
    class Application:
        def save(self, **_command):
            raise RuntimeError("unexpected storage implementation failure")

    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_rule_administration",
        lambda: Application(),
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_manager] = _principal
    response = TestClient(app).put("/api/v1/line/notification-rules", json={
        "expected_revision": 3,
        "preview_fingerprint": "f" * 64,
        "definition": _definition(),
        "reason": "保存通知",
        "idempotency_key": "notification-runtime-1",
        "correlation_id": "notification-runtime-1",
    })
    assert response.status_code == 500
    assert response.json()["detail"]["error"]["category"] == "internal"


def test_storage_unavailable_is_retryable_503(monkeypatch) -> None:
    class Application:
        def save(self, **_command):
            raise OperationalError(2003, "database unavailable")

    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_rule_administration",
        lambda: Application(),
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_manager] = _principal
    response = TestClient(app).put("/api/v1/line/notification-rules", json={
        "expected_revision": 3,
        "preview_fingerprint": "f" * 64,
        "definition": _definition(),
        "reason": "保存通知",
        "idempotency_key": "notification-storage-1",
        "correlation_id": "notification-storage-1",
    })
    assert response.status_code == 503
    error = response.json()["detail"]["error"]
    assert error["category"] == "unavailable"
    assert error["retryable"] is True


def test_explicit_mutation_conflict_remains_409(monkeypatch) -> None:
    class Application:
        def save(self, **_command):
            raise LineNotificationRuleMutationError(
                "line_notification_rule_preview_mismatch",
                "preview is stale",
            )

    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_rule_administration",
        lambda: Application(),
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_manager] = _principal
    response = TestClient(app).put("/api/v1/line/notification-rules", json={
        "expected_revision": 3,
        "preview_fingerprint": "f" * 64,
        "definition": _definition(),
        "reason": "保存通知",
        "idempotency_key": "notification-conflict-1",
        "correlation_id": "notification-conflict-1",
    })
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["category"] == "conflict"
