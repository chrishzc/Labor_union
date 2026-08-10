"""Stage 9 thin-UI, capability, transport, and architecture boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from subsystems.access.integration_capabilities import integration_capabilities_for_role
from subsystems.line.capabilities import line_capabilities_for_role
from ui.api_clients.knowledge_retrieval_api_client import KnowledgeRetrievalApiClient
from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.api_clients.runtime_health_api_client import RuntimeHealthApiClient
from ui.components import line_ui_support
from ui.components.knowledge_management import _allowed_action
from ui.components.line_order_group_manager import _group_rows
from ui.components.line_runtime_manager import _details_summary


ROOT = Path(__file__).resolve().parents[1]


class _Transport:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request(self, method, path, **kwargs):
        call = {"method": method, "path": path, **kwargs}
        self.calls.append(call)
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


def test_effective_capabilities_keep_viewer_and_manager_scopes_distinct() -> None:
    viewer = set(line_capabilities_for_role("line_viewer")) | set(
        integration_capabilities_for_role("line_viewer")
    )
    manager = set(line_capabilities_for_role("line_manager")) | set(
        integration_capabilities_for_role("line_manager")
    )

    assert "line.monitor.read" in viewer
    assert "knowledge.read" in viewer
    assert "line.audit.read" not in viewer
    assert "line.audit.read" in manager
    assert "contract.evidence.manage" in manager


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

    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
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
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
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


def test_stage9_management_routes_are_registered() -> None:
    from api.main import app

    paths = app.openapi()["paths"]

    assert "get" in paths["/api/v1/admin/audits"]
    assert "post" in paths["/api/v1/knowledge/items/{item_id}/retire"]
    assert "post" in paths["/api/v1/knowledge/jobs/{job_id}/retry"]
    assert "get" in paths["/api/v1/knowledge/questions/{request_id}"]
    assert "get" in paths["/api/v1/runtime/line-alert-targets/admin-candidates"]
