"""
File: test_line_customer_service_first_release.py
Description: 驗證客服、Rich Menu、LIFF 與 durable LINE delivery 第一版 canonical 邊界。
"""

from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routes import line_identity
from api.routes import line_mobile_admin
from api.routes.customer_service import router as customer_service_router
from api.schemas.line_identity import LineIdentityFlowOpenRequest
from domains.customer_service.ticket import (
    CustomerServiceCategory,
    CustomerServiceStatus,
    CustomerServiceTransitionError,
    transition_ticket,
)
from domains.line.identities import LineUserId
from shared_kernel.migration_release import load_migration_release_manifest
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers


PROJECT_ROOT = Path(__file__).resolve().parents[6]


class DeliveryTasks:
    def __init__(self):
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)


class CustomerServiceRepository:
    def __init__(self):
        self.messages = []

    def create_or_append(self, command):
        self.messages.append(command)
        return SimpleNamespace(ticket_id=31)

    def latest_client_case(self, _line_user_id):
        return None


class Audit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


class ReplyProvider:
    def __init__(self):
        self.calls = []

    def reply(self, reply_token, message):
        self.calls.append((reply_token, message))
        raise AssertionError("service-help must not call LINE provider before commit")


def _inbox(event_id="event-1"):
    return SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value=event_id),
            payload_json=json.dumps({"replyToken": f"reply-{event_id}"}),
        )
    )


def _unit_of_work():
    return SimpleNamespace(
        delivery_tasks=DeliveryTasks(),
        customer_service=CustomerServiceRepository(),
        audit=Audit(),
    )


def test_customer_service_ticket_state_machine_rejects_backwards_transition():
    assert transition_ticket(CustomerServiceStatus.WAITING, CustomerServiceStatus.HANDLING) is CustomerServiceStatus.HANDLING
    assert transition_ticket(CustomerServiceStatus.RESOLVED, CustomerServiceStatus.HANDLING) is CustomerServiceStatus.HANDLING
    with pytest.raises(CustomerServiceTransitionError):
        transition_ticket(CustomerServiceStatus.HANDLING, CustomerServiceStatus.WAITING)


def test_service_help_menu_is_a_canonical_flex_delivery():
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 11, tzinfo=timezone.utc))

    handled = application.handle(_inbox(), unit_of_work, LineUserId("U123456789"), "服務說明")

    assert handled is True
    assert len(unit_of_work.delivery_tasks.requests) == 1
    request = unit_of_work.delivery_tasks.requests[0]
    assert request.message_kind.value == "flex"
    assert request.idempotency_key.value == "service-help:menu:event-1"
    assert "聯絡工會人員" not in request.payload_json
    assert "其他問題" in request.payload_json


def test_service_help_never_uses_reply_token_before_durable_delivery():
    unit_of_work = _unit_of_work()
    provider = ReplyProvider()
    assert "reply_provider" not in inspect.signature(LineServiceHelpApplication).parameters
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 11, tzinfo=timezone.utc))

    handled = application.handle(_inbox(), unit_of_work, LineUserId("U123456789"), "服務說明")

    assert handled is True
    assert provider.calls == []
    assert len(unit_of_work.delivery_tasks.requests) == 1
    request = unit_of_work.delivery_tasks.requests[0]
    assert request.message_kind.value == "flex"
    assert request.idempotency_key.value == "service-help:menu:event-1"


def test_contact_union_creates_ticket_audit_and_delivery_in_one_uow_boundary():
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 11, tzinfo=timezone.utc))

    handled = application.handle(_inbox("event-2"), unit_of_work, LineUserId("U123456789"), "聯絡工會人員")

    assert handled is True
    assert unit_of_work.customer_service.messages[0].category is CustomerServiceCategory.OTHER
    assert unit_of_work.customer_service.messages[0].event_key == "line-service-help:other:event-2"
    assert len(unit_of_work.audit.intents) == 1
    assert len(unit_of_work.delivery_tasks.requests) == 1


def test_service_help_accepts_rulebook_progress_alias_and_uses_approved_copy():
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 11, tzinfo=timezone.utc))

    handled = application.handle(_inbox("event-4"), unit_of_work, LineUserId("U123456789"), "訂單進度")

    assert handled is True
    assert "服務登記" in unit_of_work.delivery_tasks.requests[0].payload_json

    application.handle(_inbox("event-5"), unit_of_work, LineUserId("U123456789"), "收費與補助")

    assert "實際金額以工會確認結果為準" in unit_of_work.delivery_tasks.requests[1].payload_json


def test_service_registration_text_returns_the_non_expiring_liff_entrypoint(monkeypatch):
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-AbCdEf")
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 11, tzinfo=timezone.utc))

    handled = application.handle(_inbox("event-registration"), unit_of_work, LineUserId("U123456789"), "服務登記")

    assert handled is True
    payload = unit_of_work.delivery_tasks.requests[0].payload_json
    assert "https://liff.line.me/1234567890-AbCdEf?entry=registration" in payload
    assert "target=registration" not in payload


def test_unbound_progress_creates_a_canonical_customer_binding_flow():
    unit_of_work = _unit_of_work()
    unit_of_work.identity_flows = _IdentityFlows()
    application = LineServiceHelpApplication(
        lambda: datetime(2026, 8, 11, tzinfo=timezone.utc),
        lambda purpose, flow_id: f"https://example.test/{purpose}/{flow_id}",
    )

    handled = application.handle(_inbox("event-6"), unit_of_work, LineUserId("U123456789"), "查詢進度")

    assert handled is True
    assert unit_of_work.identity_flows.commands[0].idempotency_key.value == "service-help-binding:event-6"
    assert "https://example.test/customer_binding/flow-1" in unit_of_work.delivery_tasks.requests[0].payload_json


def test_webhook_handler_delegates_service_help_to_the_injected_owner_workflow():
    service_help = _RecordingServiceHelpApplication()
    handler = LineWebhookIdentityHandlers(
        lambda: datetime(2026, 8, 11, tzinfo=timezone.utc),
        lambda _purpose, _flow_id: "https://example.test/identity",
        service_help_application=service_help,
    )
    inbox = SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value="event-3"),
            occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            payload_json='{"message":{"type":"text","text":"服務說明"}}',
            source=SimpleNamespace(
                source_type=SimpleNamespace(value="user"),
                user_id=LineUserId("U123456789"),
            ),
        )
    )
    unit_of_work = SimpleNamespace(platform_users=SimpleNamespace(apply_friend_event=lambda _event: None))

    handler.handle_message(inbox, unit_of_work)

    assert service_help.calls == [("U123456789", "服務說明")]


class _RecordingServiceHelpApplication:
    def __init__(self):
        self.calls = []

    def handle(self, _inbox, _unit_of_work, line_user_id, text):
        self.calls.append((line_user_id.value, text))
        return True


class _IdentityFlows:
    def __init__(self):
        self.commands = []

    def open(self, command):
        self.commands.append(command)
        return SimpleNamespace(
            purpose=command.purpose,
            flow_id=SimpleNamespace(value="flow-1"),
        )


def test_first_release_schema_has_versioned_ticket_and_append_only_events():
    schema = (PROJECT_ROOT / "db/schema_parts/185_customer_service_runtime.sql").read_text(encoding="utf-8")
    assert "version BIGINT NOT NULL" in schema
    assert "customer_service_ticket_events" in schema
    assert "UNIQUE KEY uq_customer_service_event_key" in schema
    assert "active_marker" in schema


def test_stage11_migration_manifest_hashes_customer_service_artifacts():
    path = PROJECT_ROOT / "db/migration_releases/labor_union_2026_08_11_line_stage11_v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = [*manifest["artifacts"], manifest["descriptor_artifact"]]
    for artifact in artifacts:
        content = (PROJECT_ROOT / artifact["relative_path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]


def test_stage11_manifest_is_accepted_by_the_canonical_loader():
    path = (
        PROJECT_ROOT
        / "db/migration_releases/labor_union_2026_08_11_line_stage11_v1.json"
    )
    manifest = load_migration_release_manifest(path, PROJECT_ROOT)
    artifact_names = [item.artifact.name for item in manifest.schema_artifacts]
    assert artifact_names == ["185_customer_service_runtime.sql"]


def test_customer_context_uses_canonical_identity_binding_ssot():
    repository = (
        PROJECT_ROOT / "infrastructure/mysql/customer_service_repository.py"
    ).read_text(encoding="utf-8")
    assert "FROM line_identity_bindings b" in repository
    assert "WHERE c.line_user_id=%s" not in repository


def test_merge_menu_copy_uses_canonical_entry_and_verified_staff_liff_targets():
    menu = json.loads(
        (PROJECT_ROOT / "config/line_menu.json").read_text(encoding="utf-8")
    )
    identity = (PROJECT_ROOT / "line/static/identity.html").read_text(encoding="utf-8")
    staff_orders = (PROJECT_ROOT / "line/static/staff_order_search.html").read_text(encoding="utf-8")
    action_uris = {
        button["action"]["uri"]
        for menu_definition in menu["menus"]
        for button in menu_definition["buttons"]
        if button.get("action", {}).get("type") == "uri"
    }
    message_texts = {
        button["action"]["text"]
        for menu_definition in menu["menus"]
        for button in menu_definition["buttons"]
        if button.get("action", {}).get("type") == "message"
    }
    assert "?entry=registration" in action_uris
    assert "?target=registration" not in action_uris
    assert "服務說明" in message_texts
    assert "?target=staff_order_search" in action_uris
    assert "?target=staff_schedule" in action_uris
    assert "flow_id=${encodeURIComponent(flowId)}" in identity
    assert "development_line_user_id" not in staff_orders
    assert "userId" not in staff_orders


def test_staff_self_service_exposes_text_log_preview_apply_but_keeps_media_locked():
    schedule = (
        PROJECT_ROOT / "line/static/staff_schedule.html"
    ).read_text(encoding="utf-8")

    preview_route = "/api/v1/line/staff-self-service/leave-requests/preview"
    apply_route = "/api/v1/line/staff-self-service/leave-requests/apply"
    readback_route = "/api/v1/line/staff-self-service/leave-requests/${result.data.request_id}/query"
    assert preview_route in schedule
    assert apply_route in schedule
    assert readback_route in schedule
    assert schedule.index(preview_route) < schedule.index(apply_route) < schedule.index(readback_route)
    assert 'id="confirmLeave"' in schedule
    assert 'if (!leaveCandidate || !document.getElementById("confirmLeave").checked)' in schedule
    assert "preview_fingerprint" in schedule
    assert '"Idempotency-Key": candidate.idempotencyKey' in schedule
    assert f"fetch(`{readback_route}`, {{\n      method: \"POST\"" in schedule
    assert "body: JSON.stringify(identityPayload())" in schedule
    assert 'fetch("/api/v1/line/staff-self-service/leave-requests", {' not in schedule
    assert "/api/v1/line/staff-self-service/service-day-logs/preview" in schedule
    assert "/api/v1/line/staff-self-service/service-day-logs/apply" in schedule
    assert "/api/v1/line/staff-self-service/service-day-logs/${committed.log_id}/query" in schedule
    assert "/api/v1/line/staff-self-service/service-day-media" in schedule
    assert "受控檔案 staging" in schedule
    assert "LINE provider" not in schedule
    assert 'params.get("userId")' not in schedule
    assert 'searchParams.get("userId")' not in schedule
    assert 'development_line_user_id: ""' in schedule


def test_identity_flow_requires_and_forwards_client_idempotency_key(monkeypatch):
    recorded = {}

    class _IdentityApplication:
        def open_flow(self, purpose, line_user_id, idempotency_key, correlation_id):
            recorded.update(
                purpose=purpose.value,
                line_user_id=line_user_id.value,
                idempotency_key=idempotency_key.value,
                correlation_id=correlation_id.value,
            )
            return SimpleNamespace(
                flow_id=SimpleNamespace(value="flow-1"),
                purpose=purpose,
                expires_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )

    monkeypatch.setattr(
        line_identity,
        "_verified_line_user_id",
        lambda _payload: LineUserId("U123456789"),
    )
    monkeypatch.setattr(
        line_identity,
        "get_line_identity_application",
        lambda: _IdentityApplication(),
    )
    payload = LineIdentityFlowOpenRequest(
        purpose="staff_self_service",
        idempotency_key="staff-self-service:browser-session-1",
    )

    response = line_identity.open_identity_flow(payload)

    assert response.data.flow_id == "flow-1"
    assert recorded["idempotency_key"] == "staff-self-service:browser-session-1"
    with pytest.raises(ValidationError):
        LineIdentityFlowOpenRequest(purpose="staff_self_service")


def test_deferred_history_records_legacy_paths_that_must_not_return():
    history = (PROJECT_ROOT / "document/架構重整/03_追蹤清單與證據/LINE_merge功能未移植_history_20260811.md").read_text(encoding="utf-8")
    assert "query string `userId`" in history
    assert "人工 Preview／Apply" in history
    assert "直接 UPDATE clients" in history


def test_mobile_admin_actor_is_not_restricted_by_persisted_role():
    admin = SimpleNamespace(admin_user_id=7, role="line_viewer")

    actor = line_mobile_admin._actor_for_admin(admin)

    assert actor.actor_id == "admin:7"
    assert actor.permission_scope == ("line.identity.review",)
    assert "line_viewer" not in actor.permission_scope


def test_customer_service_preview_apply_routes_keep_legacy_patch_as_retired_guard():
    routes = {
        (route.path, method)
        for route in customer_service_router.routes
        for method in route.methods
    }

    assert ("/api/v1/customer-service/tickets/{ticket_id}", "PATCH") in routes
    assert (
        "/api/v1/customer-service/tickets/{ticket_id}/update/preview",
        "POST",
    ) in routes
    assert (
        "/api/v1/customer-service/tickets/{ticket_id}/update/apply",
        "POST",
    ) in routes
