"""
File: test_line_notification_rule_api.py
Description: 驗證通知規則透過既有版本化 LINE 設定 API 進行預覽與啟用。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import (
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from api.routes import line_configurations
from api.routes import line_notification_rules
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from subsystems.access.authentication_session import AdminPrincipal


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "admin", "管理員", "system_admin")


def _client(monkeypatch):
    app = FastAPI()
    app.include_router(line_configurations.router)
    app.dependency_overrides[require_line_configuration_reader] = _principal
    app.dependency_overrides[require_line_configuration_manager] = _principal
    return TestClient(app)


def _definition() -> dict[str, object]:
    return {
        "rules": [{
            "id": "baby_log_reminder",
            "event_code": "service_time_checkpoint",
            "recipient_selector": "assigned_caregiver",
            "template_id": "baby_log_reminder",
            "schedule": {"kind": "service_end"},
            "predicates": ["baby_log_missing"],
        }]
    }


def test_notification_rules_preview_is_a_typed_api(monkeypatch) -> None:
    class Application:
        def preview(self, kind, expected_revision, definition, actor):
            assert kind is LineConfigurationKind.NOTIFICATION_RULES
            assert expected_revision == LineConfigurationRevision(0)
            assert definition == _definition()
            return type("Candidate", (), {
                "kind": kind, "before_revision": expected_revision,
                "resulting_revision": LineConfigurationRevision(1),
                "definition_json": '{"rules":[]}', "fingerprint": type("F", (), {"value": "f" * 64})(),
            })()

    monkeypatch.setattr(line_configurations, "get_line_configuration_application", lambda: Application())
    response = _client(monkeypatch).post(
        "/api/v1/line/configurations/notification_rules/preview",
        json={"expected_revision": 0, "definition": _definition()},
    )
    assert response.status_code == 200
    assert response.json()["data"]["kind"] == "notification_rules"


def test_notification_rules_reject_unsafe_condition_before_api_enable() -> None:
    from domains.line.notification_rules import LineNotificationRuleError, validate_notification_rules
    import pytest

    unsafe = _definition()
    unsafe["rules"][0]["predicates"] = ["DELETE FROM line_delivery_tasks"]
    with pytest.raises(LineNotificationRuleError):
        validate_notification_rules(unsafe)


def test_delete_rule_creates_a_new_configuration_revision(monkeypatch) -> None:
    class Application:
        def delete(self, **command):
            assert command["rule_id"] == "baby_log_reminder"
            assert command["expected_revision"] == LineConfigurationRevision(4)
            return type("Result", (), {
                "revision": LineConfigurationRevision(5),
                "cancelled_intent_count": 2,
            })()

    application = Application()
    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_rule_administration",
        lambda: application,
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_manager] = _principal
    response = TestClient(app).request(
        "DELETE", "/api/v1/line/notification-rules/baby_log_reminder",
        json={"expected_revision": 4, "reason": "停止舊提醒", "idempotency_key": "delete-rule-1", "correlation_id": "delete-rule-1"},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "rule_id": "baby_log_reminder",
        "revision": 5,
        "cancelled_intent_count": 2,
    }


def test_dedicated_notification_rule_api_supports_get_preview_and_save(monkeypatch) -> None:
    calls = []

    class Application:
        def get(self, kind, _actor):
            assert kind is LineConfigurationKind.NOTIFICATION_RULES
            return LineConfigurationSnapshot(
                kind, LineConfigurationRevision(3), '{"rules":[]}'
            )

        def preview(self, kind, expected_revision, definition, _actor):
            calls.append(("preview", kind, expected_revision, definition))
            return type("Candidate", (), {
                "before_revision": expected_revision,
                "resulting_revision": LineConfigurationRevision(4),
                "fingerprint": type("F", (), {"value": "f" * 64})(),
            })()

        def apply(self, **command):
            calls.append(("apply", command))
            return type("Result", (), {
                "snapshot": LineConfigurationSnapshot(
                    LineConfigurationKind.NOTIFICATION_RULES,
                    LineConfigurationRevision(4),
                    '{"rules":[]}',
                )
            })()

    application = Application()
    monkeypatch.setattr(
        line_notification_rules,
        "get_line_configuration_application",
        lambda: application,
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_reader] = _principal
    app.dependency_overrides[require_line_configuration_manager] = _principal
    client = TestClient(app)

    assert client.get("/api/v1/line/notification-rules").json()["data"]["revision"] == 3
    preview = client.post(
        "/api/v1/line/notification-rules/preview",
        json={"expected_revision": 3, "definition": _definition()},
    )
    assert preview.status_code == 200
    saved = client.put(
        "/api/v1/line/notification-rules",
        json={
            "expected_revision": 3,
            "definition": _definition(),
            "reason": "啟用提醒",
            "idempotency_key": "notification-save-1",
            "correlation_id": "notification-save-1",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["revision"] == 4
    assert calls[0][0] == "preview"
    assert calls[1][0] == "apply"


def test_notification_timeline_api_returns_deidentified_evidence(monkeypatch) -> None:
    class Timeline:
        def list_case(self, case_no, _actor):
            assert case_no == "CASE-8"
            return ({
                "source_event_id": 9,
                "event_code": "service_time_checkpoint",
                "recipient_masked": "***1234",
                "intent_status": "cancelled",
            },)

    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_timeline_application",
        lambda: Timeline(),
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_reader] = _principal
    response = TestClient(app).get(
        "/api/v1/line/notification-rules/timeline/CASE-8"
    )

    assert response.status_code == 200
    assert response.json()["data"]["records"] == [{
        "source_event_id": 9,
        "event_code": "service_time_checkpoint",
        "recipient_masked": "***1234",
        "intent_status": "cancelled",
    }]


def test_manual_replay_api_requires_previewable_source_and_reason(monkeypatch) -> None:
    calls = []

    class Replay:
        def preview(self, source_event_id, _actor):
            calls.append(("preview", source_event_id))
            return {"source_event_id": source_event_id, "matching_rule_count": 1}

        def apply(self, source_event_id, _actor, reason, key, correlation):
            calls.append(("apply", source_event_id, reason, key.value, correlation.value))
            return 33

    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_manual_replay_application",
        lambda: Replay(),
    )
    app = FastAPI()
    app.include_router(line_notification_rules.router)
    app.dependency_overrides[require_line_configuration_manager] = _principal
    client = TestClient(app)

    preview = client.post("/api/v1/line/notification-rules/sources/12/manual-replay/preview")
    applied = client.post(
        "/api/v1/line/notification-rules/sources/12/manual-replay",
        json={"reason": "核准重送歷史通知", "idempotency_key": "manual-replay-12", "correlation_id": "manual-replay-12"},
    )

    assert preview.status_code == 200
    assert applied.status_code == 200
    assert applied.json()["data"]["replayed_source_event_id"] == 33
    assert calls == [
        ("preview", 12),
        ("apply", 12, "核准重送歷史通知", "manual-replay-12", "manual-replay-12"),
    ]
