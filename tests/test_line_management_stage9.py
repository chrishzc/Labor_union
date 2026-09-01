"""
File: test_line_management_stage9.py
Description: 驗證 Stage 9 薄 UI、能力、傳輸與架構邊界。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.schemas.line_admin import LineAdminHealthView
from subsystems.access.authentication_session import AdminPrincipal
from ui.api_clients.knowledge_retrieval_api_client import KnowledgeRetrievalApiClient
from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.api_clients.runtime_health_api_client import RuntimeHealthApiClient
from ui.components import line_ui_support
from ui.components.knowledge_management import _allowed_action
from ui.components.line_order_group_manager import _group_rows
from ui.components.line_runtime_manager import _details_summary
from ui.components.line_task_manager import _delivery_query_filters


ROOT = Path(__file__).resolve().parents[1]


class _Transport:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request(self, method, path, **kwargs):
        call = {"method": method, "path": path, **kwargs}
        self.calls.append(call)
        if path == "/api/v1/runtime/health-status":
            return []
        return call


class _Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""
        self.content = b""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._payload


def test_effective_capabilities_are_equal_for_enabled_internal_users() -> None:
    viewer = AdminPrincipal(1, "viewer", "Viewer", "line_viewer")
    manager = AdminPrincipal(2, "manager", "Manager", "line_manager")

    assert viewer.effective_capabilities() == manager.effective_capabilities()
    assert "line.monitor.read" in viewer.effective_capabilities()
    assert "knowledge.read" in viewer.effective_capabilities()
    assert "line.audit.read" in viewer.effective_capabilities()
    assert "contract.evidence.manage" in viewer.effective_capabilities()


def test_domain_clients_use_bounded_api_routes_and_forward_operation_headers() -> None:
    transport = _Transport()
    knowledge = KnowledgeRetrievalApiClient(transport)
    runtime = RuntimeHealthApiClient(transport)

    knowledge.transition(
        "session",
        7,
        "publish",
        {"expected_version": 2, "reason": "approved"},
        headers={"Idempotency-Key": "idem-2", "X-Correlation-ID": "corr-2"},
    )
    runtime.health_status("session")

    assert transport.calls[0]["path"] == "/api/v1/knowledge/items/7/publish"
    assert transport.calls[0]["extra_headers"]["X-Correlation-ID"] == "corr-2"
    assert transport.calls[1]["path"] == "/api/v1/runtime/health-status"


def test_line_task_client_forwards_stable_operation_identity(monkeypatch) -> None:
    captured = {}

    def request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return _Response(200, {"data": {"task_id": 9}})

    monkeypatch.setattr("ui.api_clients.line_api_client.requests.request", request)

    result = LineAdminApiClient().line_task_action(
        "session-token",
        9,
        "retry",
        reason="人工重試",
        idempotency_key="idem-task",
        correlation_id="corr-task",
    )

    assert result == {"task_id": 9}
    assert captured["headers"]["Authorization"] == "Bearer session-token"
    assert captured["json"]["idempotency_key"] == "idem-task"
    assert captured["json"]["correlation_id"] == "corr-task"


def test_line_task_query_uses_only_safe_source_filters() -> None:
    rich_menu = _delivery_query_filters("sent", "rich_menu_link", False, 3)
    onboarding = _delivery_query_filters(None, "general_push", True, 2)

    assert rich_menu == {
        "status": "sent",
        "source_type": "rich_menu_link",
        "page": 3,
        "page_size": 25,
    }
    assert onboarding == {
        "status": None,
        "source_type": "follow_schedule",
        "page": 2,
        "page_size": 25,
    }
    assert "user_id" not in rich_menu
    assert "task_type" not in rich_menu
    assert "onboarding_only" not in onboarding


def test_line_health_client_returns_a_typed_projection(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.api_clients.line_api_client.requests.request",
        lambda *args, **kwargs: _Response(
            200,
            {
                "data": {
                    "status": "degraded",
                    "database": {
                        "ok": False,
                        "line_task_counts": {},
                        "queue_counts": {},
                        "worker": {"status": "unknown", "running": False},
                        "error_code": "line_database_unavailable",
                    },
                    "worker": {"status": "unknown", "running": False},
                    "line_credentials": {
                        "channel_secret": False,
                        "channel_access_token": False,
                        "liff_id": False,
                    },
                }
            },
        ),
    )

    result = LineAdminApiClient().health("session-token")

    assert isinstance(result, LineAdminHealthView)
    assert result.database.error_code == "line_database_unavailable"


def test_line_health_client_fails_closed_on_schema_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.api_clients.line_api_client.requests.request",
        lambda *args, **kwargs: _Response(
            200,
            {"data": {"status": "healthy", "unexpected": True}},
        ),
    )

    with pytest.raises(LineAdminApiError) as captured:
        LineAdminApiClient().health("session-token")

    assert captured.value.category == "schema"
    assert captured.value.code == "line_admin_health_response_invalid"


def test_rich_menu_client_reads_and_writes_canonical_configuration(monkeypatch) -> None:
    calls = []

    def request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        definition = {"version": 2, "menus": []}
        if url.endswith("/api/v1/line/rich-menus/draft") and method == "GET":
            return _Response(
                200,
                {
                    "data": {
                        "kind": "rich_menus",
                        "revision": 4,
                        "definition": definition,
                    }
                },
            )
        if url.endswith("/api/v1/line/rich-menus/draft/preview"):
            return _Response(
                200,
                {
                    "data": {
                        "before_revision": 4,
                        "resulting_revision": 5,
                        "normalized_definition": definition,
                        "preview_fingerprint": "a" * 64,
                    }
                },
            )
        if url.endswith("/api/v1/line/rich-menus/draft") and method == "PUT":
            return _Response(
                200,
                {
                    "data": {
                        "receipt": {
                            "outcome": "created",
                            "committed_revision": 5,
                            "receipt_reference": "line-rich-menu-draft:5",
                        },
                        "readback": {
                            "kind": "rich_menus",
                            "revision": 5,
                            "definition": definition,
                        },
                    }
                },
            )
        return _Response(
            200,
            {"data": {"revision": 4, "definition": definition}},
        )

    monkeypatch.setattr("ui.api_clients.line_api_client.requests.request", request)
    client = LineAdminApiClient()

    state = client.line_menu_state("session-token")
    preview = client.preview_line_menu_draft(
        "session-token",
        state["config"],
        revision=state["revision"],
    )
    client.update_line_menus(
        "session-token",
        state["config"],
        revision=state["revision"],
        preview_fingerprint=preview["preview_fingerprint"],
        reason="儲存 Rich Menu",
        idempotency_key="idem-rich-menu",
        correlation_id="corr-rich-menu",
    )

    assert state == {"revision": 4, "config": {"version": 2, "menus": []}}
    assert calls[0]["url"].endswith("/api/v1/line/rich-menus/draft")
    assert calls[1]["url"].endswith("/api/v1/line/rich-menus/draft/preview")
    assert calls[1]["json"]["expected_revision"] == 4
    assert calls[2]["url"].endswith("/api/v1/line/rich-menus/draft")
    assert calls[2]["json"]["expected_revision"] == 4
    assert calls[2]["json"]["preview_fingerprint"] == "a" * 64
    assert calls[2]["json"]["idempotency_key"] == "idem-rich-menu"


@pytest.mark.parametrize(
    ("status_code", "category", "message"),
    [
        (401, "unauthorized", "登入已失效"),
        (403, "forbidden", "沒有執行此操作的權限"),
        (409, "conflict", "資料已更新"),
        (503, "unavailable", "暫時無法使用"),
    ],
)
def test_line_transport_preserves_typed_error_semantics(
    monkeypatch,
    status_code: int,
    category: str,
    message: str,
) -> None:
    monkeypatch.setattr(
        "ui.api_clients.line_api_client.requests.request",
        lambda *args, **kwargs: _Response(
            status_code,
            {"detail": {"code": "backend_code", "correlation_id": "corr-9"}},
        ),
    )

    with pytest.raises(LineAdminApiError) as captured:
        LineAdminApiClient().request("GET", "/api/v1/test", token="session")

    assert captured.value.status_code == status_code
    assert captured.value.category == category
    assert captured.value.code == "backend_code"
    assert captured.value.correlation_id == "corr-9"
    assert message in str(captured.value)


def test_line_transport_displays_typed_conflict_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.api_clients.line_api_client.requests.request",
        lambda *args, **kwargs: _Response(
            409,
            {
                "detail": {
                    "code": "staff_identity_binding_conflict",
                    "message": "月嫂目前綁定的 LINE 已變更，請重新確認後再審核。",
                }
            },
        ),
    )

    with pytest.raises(LineAdminApiError) as captured:
        LineAdminApiClient().request("GET", "/api/v1/test", token="session")

    assert captured.value.code == "staff_identity_binding_conflict"
    assert "月嫂目前綁定" in str(captured.value)


def test_operation_identity_is_stable_until_payload_changes_or_completes(monkeypatch) -> None:
    session_state: dict = {}
    monkeypatch.setattr(line_ui_support.st, "session_state", session_state)

    first = line_ui_support.operation_headers("publish", {"version": 1})
    replay = line_ui_support.operation_headers("publish", {"version": 1})
    changed = line_ui_support.operation_headers("publish", {"version": 2})
    line_ui_support.complete_operation("publish")
    next_operation = line_ui_support.operation_headers("publish", {"version": 2})

    assert first == replay
    assert changed != first
    assert next_operation != changed


def test_line_management_ui_has_no_database_or_domain_bypass() -> None:
    paths = [ROOT / "ui/pages/07_line_management.py"]
    paths.extend((ROOT / "ui/components").glob("line_*.py"))
    paths.extend(
        [
            ROOT / "ui/components/knowledge_management.py",
        ]
    )
    forbidden = (
        "mysql.connector",
        "get_connection",
        "infrastructure.mysql",
        "repository",
        "domains.",
        "SELECT ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert not any(token in source for token in forbidden), path


def test_component_read_models_hide_sensitive_transport_values() -> None:
    groups = _group_rows(
        [{"case_no": "CASE-7", "status": "active", "group_id": "C-secret", "version": 2}]
    )

    assert "group_id" not in groups[0]
    assert "C-secret" not in groups[0].values()


def test_component_actions_follow_effective_capabilities() -> None:
    viewer = {"effective_capabilities": ["knowledge.read"]}
    manager = {
        "effective_capabilities": ["knowledge.manage", "knowledge.publish"]
    }

    assert _allowed_action("draft", viewer) is None
    assert _allowed_action("draft", manager) == ("review", "完成審核")
    assert _allowed_action("reviewed", manager) == ("publish", "發布內容")
    assert _allowed_action("published", manager) == ("retire", "停用內容")


def test_runtime_detail_summary_is_bounded() -> None:
    summary = _details_summary({str(index): index for index in range(8)})

    assert summary.count("=") == 4


def test_stage9_management_routes_are_registered(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("REACT_ADMIN_CURRENT_ARTIFACT_DIR", "")
    monkeypatch.setenv("REACT_ADMIN_PREVIOUS_ARTIFACT_DIR", "")
    monkeypatch.setenv("REACT_ADMIN_ACTIVE_SELECTOR", "")
    from api.main import app

    paths = app.openapi()["paths"]

    assert "get" in paths["/api/v1/admin/audits"]
    assert "post" in paths["/api/v1/knowledge/items/{item_id}/retire"]
    assert "post" in paths["/api/v1/knowledge/jobs/{job_id}/retry"]
    assert "get" in paths["/api/v1/knowledge/questions/{request_id}"]
    assert "get" in paths["/api/v1/runtime/line-alert-targets/admin-candidates"]
