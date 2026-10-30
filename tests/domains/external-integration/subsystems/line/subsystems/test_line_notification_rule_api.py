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
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationResult,
    LineConfigurationCommandOutcome,
)


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "admin", "管理員", "system_admin")


def _copy_client(monkeypatch):
    import json
    from domains.line.canonical_payload import canonical_line_payload_json
    from domains.line.configuration import LineConfigurationRevisionConflict
    from subsystems.line.configuration_store import read_raw_config
    class Application:
        revision = 7
        from pathlib import Path
        definitions = {LineConfigurationKind.NOTIFICATION_RULES: json.loads(Path("config/notification_rules.json").read_text(encoding="utf-8")), LineConfigurationKind.MESSAGE_TEMPLATES: read_raw_config("message_templates")}
        def get(self, kind, actor):
            return LineConfigurationSnapshot(kind, LineConfigurationRevision(self.revision), canonical_line_payload_json(self.definitions[kind]))
        def apply(self, **command):
            if command["expected_revision"].value != self.revision:
                raise LineConfigurationRevisionConflict("stale")
            self.definitions[command["kind"]] = json.loads(canonical_line_payload_json(command["definition"]))
            self.revision += 1
            return ApplyLineConfigurationResult(LineConfigurationCommandOutcome.CREATED, self.get(command["kind"], command["actor"]))
    application = Application()
    monkeypatch.setattr(line_notification_rules, "get_line_configuration_application", lambda: application)
    web = FastAPI()
    web.include_router(line_notification_rules.router)
    web.dependency_overrides[require_line_configuration_reader] = _principal
    web.dependency_overrides[require_line_configuration_manager] = _principal
    return TestClient(web), application


def test_retired_explanation_templates_cannot_be_read_or_edited_even_if_saved(monkeypatch):
    client, application = _copy_client(monkeypatch)
    templates = application.definitions[LineConfigurationKind.MESSAGE_TEMPLATES]['templates']
    for key in ('service-flow', 'service-payment'):
        saved_template = {'id': 'LINE-COPY-' + key, 'name': key, 'message_type': 'text',
            'enabled': True, 'content': '舊說明內容', 'variables': []}
        templates.append(saved_template)
        endpoint = f'/api/v1/line/notification-rules/{key}/message-template'
        assert client.get(endpoint).status_code == 404
        assert client.put(endpoint, json={'content': '不得覆寫', 'expected_revision': 7}).status_code == 404
        assert saved_template['content'] == '舊說明內容'
    assert application.revision == 7
    for key in ('service-profile-update', 'service-order-update'):
        assert client.get(f'/api/v1/line/notification-rules/{key}/message-template').status_code == 200


def test_every_current_catalog_entry_can_read_and_save_its_editable_content(monkeypatch):
    from subsystems.line.message_preview import LineMessagePreviewApplication
    client, application = _copy_client(monkeypatch)
    catalog = LineMessagePreviewApplication._catalog(application.definitions[LineConfigurationKind.MESSAGE_TEMPLATES], application.definitions[LineConfigurationKind.NOTIFICATION_RULES])
    for entry in catalog:
        if entry.id == "welcome":
            continue
        response = client.get(f"/api/v1/line/notification-rules/{entry.id}/message-template")
        if entry.id == 'card-candidate-information-3':
            assert response.status_code == 404  # System-generated picture has no editable copy.
            continue
        assert response.status_code == 200, (entry.id, response.text)
        view = response.json()["data"]
        assert view["content"]
        if entry.format == "flex":
            assert view["fields"], entry.id
        saved = client.put(f"/api/v1/line/notification-rules/{entry.id}/message-template", json={"content": view["content"], "expected_revision": view["revision"]})
        assert saved.status_code == 200, (entry.id, saved.text)
        assert saved.json()["data"]["content"] == view["content"]


def test_fixed_copy_and_card_labels_save_with_revision_and_reject_action_fields(monkeypatch):
    import json
    from subsystems.line.message_copy_catalog import render_copy_payload
    from subsystems.line.order_group_application import group_invitation_payload
    client, application = _copy_client(monkeypatch)
    base = "/api/v1/line/notification-rules/"
    text = client.get(base + "service-contact/message-template").json()["data"]
    saved = client.put(base + "service-contact/message-template", json={"content": "已收到，請留下問題內容。", "expected_revision": text["revision"]})
    assert saved.status_code == 200
    assert client.get(base + "service-contact/message-template").json()["data"]["content"] == "已收到，請留下問題內容。"
    stale = client.put(base + "service-contact/message-template", json={"content": "舊版修改", "expected_revision": text["revision"]})
    assert stale.status_code == 409
    assert "line_message_template_revision_conflict" in stale.text
    view = client.get(base + "group-invitation-customer/message-template").json()["data"]
    content = json.loads(view["content"])
    button = next(field for field in view["fields"] if field["label"] == "按鈕名稱")
    content[button["id"]] = "進入案件群組"
    response = client.put(base + "group-invitation-customer/message-template", json={"content": json.dumps(content, ensure_ascii=False), "expected_revision": view["revision"]})
    assert response.status_code == 200
    payload = group_invitation_payload("CASE-1", "媽媽", "https://line.me/original")
    result = render_copy_payload(application.definitions[LineConfigurationKind.MESSAGE_TEMPLATES], "group-invitation-customer", payload, {"case_no": "CASE-1"})
    action = result["contents"]["footer"]["contents"][0]["action"]
    assert action == {"type": "uri", "label": "進入案件群組", "uri": "https://line.me/original"}
    content["contents/footer/contents/0/action/uri"] = "https://invalid.local"
    rejected = client.put(base + "group-invitation-customer/message-template", json={"content": json.dumps(content, ensure_ascii=False), "expected_revision": application.revision})
    assert rejected.status_code == 422
    assert application.revision == response.json()["data"]["revision"]


def test_existing_flex_template_edits_text_without_replacing_dynamic_actions(monkeypatch):
    import json
    from copy import deepcopy
    from subsystems.line.message_copy import copy_fields
    client, application = _copy_client(monkeypatch)
    definition = application.definitions[LineConfigurationKind.MESSAGE_TEMPLATES]
    template = next(t for t in definition["templates"] if t["id"] == "LINE-ORDER-SERVICE-START-DAY-CARD-V1")
    before = deepcopy(template["content"])
    rule = next(r for r in application.definitions[LineConfigurationKind.NOTIFICATION_RULES]["rules"] if r["template_id"] == template["id"])
    path = f'/api/v1/line/notification-rules/{rule["id"]}/message-template'
    view = client.get(path).json()["data"]
    values = json.loads(view["content"])
    assert 'response_token' not in view['variables']
    body = next(f for f in view['fields'] if f['kind'] == 'body')
    title = next(f for f in view['fields'] if f['kind'] == 'title')
    invalid = {**values, body['id']: '不允許顯示 action-only 的 {response_token}'}
    assert client.put(path, json={'content': json.dumps(invalid), 'expected_revision': view['revision']}).status_code == 422
    assert application.revision == view['revision']
    values[body['id']] = '第一段說明：{case_no}\n\n另外加入的服務提醒。'
    values[title['id']] = '新的服務狀況詢問標題'
    button = next(f for f in view["fields"] if f["label"] == "按鈕名稱")
    values[button["id"]] = "需要協助處理"
    assert client.put(path, json={"content": json.dumps(values, ensure_ascii=False), "expected_revision": view["revision"]}).status_code == 200
    after = next(t for t in application.definitions[LineConfigurationKind.MESSAGE_TEMPLATES]["templates"] if t["id"] == template["id"])["content"]
    def actions(node):
        if isinstance(node, dict):
            if "action" in node:
                yield {k: v for k, v in node["action"].items() if k != "label"}
            for value in node.values():
                yield from actions(value)
        elif isinstance(node, list):
            for value in node:
                yield from actions(value)
    assert list(actions(before)) == list(actions(after))
    assert any(f["content"] == "需要協助處理" for f in copy_fields(after))
    assert any(f['content'] == '第一段說明：{case_no}\n\n另外加入的服務提醒。' for f in copy_fields(after))
    assert after['contents']['body']['contents'][0]['text'] == '新的服務狀況詢問標題'
    # Read back after inserting a previously absent title, then save again.
    current = client.get(path).json()['data']
    assert client.put(path, json={'content': current['content'], 'expected_revision': current['revision']}).status_code == 200


def test_customer_and_caregiver_card_bodies_are_stored_independently_across_flows(monkeypatch):
    import json
    from dataclasses import asdict
    from subsystems.line.message_preview import LineMessagePreviewApplication
    from infrastructure.line.table_image_renderer import render_table_image
    from api.dependencies.admin_auth import admin_actor_context
    client, application = _copy_client(monkeypatch)
    root = '/api/v1/line/notification-rules/'
    messages = {'card-customer-confirmation': '客戶：請確認推薦方案。\n\n確認後由工會協助簽約。',
        'card-candidate-information-1': '月嫂：請確認薪資與檔期。\n\n若有問題請先聯繫工會。',
        'card-candidate-information-2': '月嫂：請核對照護與餐食需求。'}
    for key, text in messages.items():
        view = client.get(root + key + '/message-template').json()['data']
        values = json.loads(view['content'])
        field = next(field for field in view['fields'] if field['kind'] == 'body')
        values[field['id']] = text
        response = client.put(root + key + '/message-template', json={'content': json.dumps(values, ensure_ascii=False), 'expected_revision': view['revision']})
        assert response.status_code == 200, response.text
    preview = LineMessagePreviewApplication(application, lambda: None, render_table_image)
    for key, text in messages.items():
        view = client.get(root + key + '/message-template').json()['data']
        field = next(field for field in view['fields'] if field['kind'] == 'body')
        assert json.loads(view['content'])[field['id']] == text
        result = preview.render(key, None, None, None, admin_actor_context(_principal()), sample=True)
        visible = json.dumps(asdict(result), ensure_ascii=False)
        assert text.split('\n')[0] in visible
        assert all(other.split('\n')[0] not in visible for other in messages.values() if other != text)


def test_previous_audience_specific_success_ids_update_the_corresponding_current_role(monkeypatch):
    client, _ = _copy_client(monkeypatch)
    root = "/api/v1/line/notification-rules/"
    for previous, current, text in (("template-bind_success_new_order", "identity-bound-customer", "客戶請查看服務進度。"), ("template-staff_switch_success", "identity-bound-staff", "月嫂請確認可服務時段。")):
        view = client.get(root + previous + "/message-template").json()["data"]
        saved = client.put(root + previous + "/message-template", json={"content": text, "expected_revision": view["revision"]})
        assert saved.status_code == 200
        assert client.get(root + current + "/message-template").json()["data"]["content"] == text
    assert client.get(root + "identity-bound-customer/message-template").json()["data"]["content"] == "客戶請查看服務進度。"
    assert "工會人員" in client.get(root + "identity-bound-admin/message-template").json()["data"]["content"]


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
                "rule_id": "baby_log_reminder",
                "revision": LineConfigurationRevision(5),
                "preview_fingerprint": PreviewFingerprint("e" * 64),
                "cancelled_intent_count": 2,
                "cancelled_task_count": 2,
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
        json={"expected_revision": 4, "preview_fingerprint": "e" * 64, "reason": "停止舊提醒", "idempotency_key": "delete-rule-1", "correlation_id": "delete-rule-1"},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "rule_id": "baby_log_reminder",
        "revision": 5,
        "preview_fingerprint": "e" * 64,
        "cancelled_intent_count": 2,
        "cancelled_task_count": 2,
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
                "definition_json": '{"rules":[]}',
                "fingerprint": type("F", (), {"value": "f" * 64})(),
            })()

    class Administration:
        def save(self, **command):
            calls.append(("save", command))
            return type("Result", (), {
                "revision": LineConfigurationRevision(4),
                "preview_fingerprint": PreviewFingerprint("f" * 64),
                "cancelled_intent_count": 0,
                "cancelled_task_count": 0,
            })()

    application = Application()
    monkeypatch.setattr(
        line_notification_rules,
        "get_line_configuration_application",
        lambda: application,
    )
    monkeypatch.setattr(
        line_notification_rules,
        "get_line_notification_rule_administration",
        lambda: Administration(),
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
            "preview_fingerprint": "f" * 64,
            "definition": _definition(),
            "reason": "啟用提醒",
            "idempotency_key": "notification-save-1",
            "correlation_id": "notification-save-1",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["revision"] == 4
    assert calls[0][0] == "preview"
    assert calls[1][0] == "save"


def test_notification_rule_message_template_can_be_queried_and_updated(monkeypatch) -> None:
    from domains.line.canonical_payload import canonical_line_payload_json

    rules = {
        "rules": [{
            "id": "deposit_notice",
            "event_code": "deposit_confirmed",
            "recipient_selector": "client",
            "template_id": "deposit_template",
            "enabled": True,
            "schedule": {"kind": "immediate"},
            "frequency": {"kind": "once"},
            "predicates": [],
        }]
    }
    templates = {
        "version": 1,
        "templates": [{
            "id": "deposit_template",
            "name": "訂金確認通知",
            "category": "push",
            "message_type": "text",
            "enabled": True,
            "content": "案件 {case_no} 已確認訂金。",
            "variables": [{"name": "case_no", "required": True}],
            "usage": ["push"],
        }],
    }
    applied = []

    class Application:
        template_revision = 7

        def get(self, kind, _actor):
            definition = rules if kind is LineConfigurationKind.NOTIFICATION_RULES else templates
            revision = 3 if kind is LineConfigurationKind.NOTIFICATION_RULES else self.template_revision
            return LineConfigurationSnapshot(
                kind,
                LineConfigurationRevision(revision),
                canonical_line_payload_json(definition),
            )

        def apply(self, **command):
            assert command["kind"] is LineConfigurationKind.MESSAGE_TEMPLATES
            assert command["expected_revision"] == LineConfigurationRevision(7)
            applied.append(command["definition"])
            self.template_revision = 8
            return ApplyLineConfigurationResult(
                outcome=LineConfigurationCommandOutcome.CREATED,
                snapshot=LineConfigurationSnapshot(
                    LineConfigurationKind.MESSAGE_TEMPLATES,
                    LineConfigurationRevision(8),
                    canonical_line_payload_json(command["definition"]),
                ),
            )

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

    queried = client.get(
        "/api/v1/line/notification-rules/deposit_notice/message-template"
    )
    assert queried.status_code == 200
    assert queried.json()["data"] == {
        "rule_id": "deposit_notice",
        "template_id": "deposit_template",
        "name": "訂金確認通知",
        "content": "案件 {case_no} 已確認訂金。",
        "revision": 7,
        "variables": ["case_no"],
        "sample_preview": "案件 〔case_no〕 已確認訂金。",
        "fields": [],
    }

    updated = client.put(
        "/api/v1/line/notification-rules/deposit_notice/message-template",
        json={
            "content": "案件 {case_no} 的訂金已完成確認。",
            "expected_revision": 7,
            "reason": "調整通知文案",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["content"] == "案件 {case_no} 的訂金已完成確認。"
    assert updated.json()["data"]["revision"] == 8
    assert applied[0]["templates"][0]["content"] == "案件 {case_no} 的訂金已完成確認。"


def test_notification_timeline_api_returns_deidentified_evidence(monkeypatch) -> None:
    record = {
        "source_event_id": 9,
        "event_code": "service_time_checkpoint",
        "occurred_at_utc": "2026-08-08T02:30:00Z",
        "historical_silent": False,
        "rule_id": "baby_log_reminder",
        "decision_status": "matched",
        "reason_code": None,
        "recipient_type": "assigned_caregiver",
        "recipient_identity": "***1234",
        "occurrence_number": 1,
        "intent_status": "cancelled",
        "scheduled_at_utc": "2026-08-08T03:00:00Z",
        "delivery_status": "cancelled",
        "delivery_task_id": 44,
    }

    class Timeline:
        def list_case(self, case_no, _actor):
            assert case_no == "CASE-8"
            return (record,)

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
    assert response.json()["data"]["records"] == [record]


def test_manual_replay_api_requires_previewable_source_and_reason(monkeypatch) -> None:
    calls = []

    class Replay:
        def preview(self, source_event_id, _actor):
            calls.append(("preview", source_event_id))
            return {
                "source_event_id": source_event_id,
                "event_code": "service_time_checkpoint",
                "historical_silent": False,
                "matching_rule_count": 1,
                "will_create_new_immutable_source": True,
            }

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


def test_service_guide_alias_reads_and_saves_one_canonical_setting_without_rewriting_legacy(monkeypatch):
    import json
    client, application = _copy_client(monkeypatch)
    legacy = {'id': 'LINE-COPY-service-other', 'name': '舊導覽', 'message_type': 'text',
              'enabled': True, 'content': '{}', 'variables': []}
    application.definitions[LineConfigurationKind.MESSAGE_TEMPLATES]['templates'].append(legacy)
    base = '/api/v1/line/notification-rules/'
    original = client.get(base + 'service-menu/message-template').json()['data']
    alias = client.get(base + 'service-other/message-template').json()['data']
    assert alias['template_id'] == original['template_id'] == 'LINE-COPY-service-menu'
    assert alias['content'] == original['content']
    content = json.loads(alias['content'])
    content[next(iter(content))] = '合併後的服務導覽'
    changed = json.dumps(content, ensure_ascii=False)
    saved = client.put(base + 'service-other/message-template', json={'content': changed, 'expected_revision': 7})
    assert saved.status_code == 200, saved.text
    assert json.loads(client.get(base + 'service-menu/message-template').json()['data']['content']) == content
    persisted = application.definitions[LineConfigurationKind.MESSAGE_TEMPLATES]['templates']
    assert next(row for row in persisted if row['id'] == legacy['id']) == legacy


def test_unused_standalone_template_editors_are_closed_but_saved_settings_and_active_rules_remain(monkeypatch):
    from copy import deepcopy
    client, application = _copy_client(monkeypatch)
    before = deepcopy(application.definitions)
    unused = ('staff_switch_fail','staff_menu_not_set','esc_success','esc_fail','bind_link_msg',
              'register_success','bind_success_existing','bind_confirm_rebind','bind_fail_no_data',
              'client_rebind_approved','staff_verification_requested')
    for key in unused:
        endpoint = f'/api/v1/line/notification-rules/template-{key}/message-template'
        assert client.get(endpoint).status_code == 404
        assert client.put(endpoint, json={'content':'不得覆寫', 'expected_revision':7}).status_code == 404
    assert application.definitions == before and application.revision == 7
    rules = application.definitions[LineConfigurationKind.NOTIFICATION_RULES]['rules']
    active = next(rule for rule in rules if rule['id'] == 'LINE-SECOND-PAYMENT-DUE-V1')
    rules.append({**active, 'id':'still-active-notification', 'template_id':'register_success'})
    assert client.get('/api/v1/line/notification-rules/still-active-notification/message-template').status_code == 200
    for key in ('template-client_rebind_rejected','template-staff_verification_rejected','identity-pending',
                'identity-bound-customer','identity-bound-staff','identity-bound-admin','service-profile-update','service-order-update'):
        assert client.get(f'/api/v1/line/notification-rules/{key}/message-template').status_code == 200


def test_legacy_order_menu_copy_is_projected_to_liff_without_mutating_saved_definition(monkeypatch):
    import json
    from copy import deepcopy
    from subsystems.line.message_copy_catalog import effective_copy_definition
    from subsystems.line.message_copy import copy_template_id
    monkeypatch.setenv('LINE_LIFF_ID', '1234567890-order')
    definition = {'version':1, 'templates':[{'id':copy_template_id('order-update-menu'), 'name':'舊訂單異動導覽',
        'message_type':'text', 'enabled':True, 'variables':[], 'content':json.dumps({
            'contents/body/contents/0/action/label':'修改服務地址',
            'contents/body/contents/4/action/label':'其他訂單內容'})}]}
    before = deepcopy(definition)
    projected = effective_copy_definition(definition)
    view = next(row for row in projected['templates'] if row['id'] == copy_template_id('order-update-menu'))
    assert '開啟訂單異動表單' in view['content'] and '修改服務天數' not in view['content']
    assert 'contents/body/contents/4/action/label' not in json.loads(view['content'])
    assert definition == before


def test_fixed_feedback_and_liff_admin_alert_editors_are_closed_without_deleting_saved_settings(monkeypatch):
    from copy import deepcopy
    client, application = _copy_client(monkeypatch)
    keys = ('group-bound','group-invitations-queued','group-error-invitation-url','group-format-invite',
            'group-error-admin','group-error-order','group-error-unbound','group-error-identity',
            'group-error-cancelled','group-error-unpaid','group-error-occupied','group-format-empty',
            'group-format-case','group-format-url','group-format-spacing','group-format-split',
            'group-format-invalid-case','group-format-invalid-url','runtime-system-health')
    saved = application.definitions[LineConfigurationKind.MESSAGE_TEMPLATES]['templates']
    for key in keys:
        saved.append({'id':'LINE-COPY-'+key,'name':key,'message_type':'text','enabled':True,'content':'歷史固定提示','variables':[]})
    before = deepcopy(application.definitions)
    ids = (*keys,'LU96-M4-SAFE-ALERT-RULE-V1','LU96-M4-COMPLAINT-HIGH-RULE-V1')
    for key in ids:
        endpoint=f'/api/v1/line/notification-rules/{key}/message-template'
        assert client.get(endpoint).status_code == 404
        assert client.put(endpoint,json={'content':'不應儲存','expected_revision':7}).status_code == 404
    assert application.revision == 7 and application.definitions == before
    for key in ('group-invitation-customer','group-invitation-staff','service-profile-update','service-order-update'):
        assert client.get(f'/api/v1/line/notification-rules/{key}/message-template').status_code == 200
