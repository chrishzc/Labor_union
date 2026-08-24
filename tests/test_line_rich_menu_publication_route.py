"""
File: test_line_rich_menu_publication_route.py
Description: 驗證 Rich Menu publish-preview route 的零寫入、決定性回應與 typed failure。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import (
    require_line_configuration_reader,
    require_line_menu_publisher,
    require_line_viewer,
)
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import line_rich_menus
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision, LineRichMenuPublicationId
from domains.line.rich_menu import (
    LineRichMenuPublicationSnapshot,
    LineRichMenuPublicationStatus,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line import rich_menu_publication_workflow
from subsystems.line.rich_menu_application import LineRichMenuNotFoundError
from subsystems.line.ports import LineRichMenuPublicationPage, LineRichMenuPublicationStep


class _Cursor:
    def __init__(self) -> None:
        self.lastrowid = 41
        self.executions: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def execute(self, query: str, _parameters: tuple[object, ...]) -> None:
        self.executions.append(query)


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.commit_count = 0
        self.close_count = 0

    def cursor(self, *_args: object) -> _Cursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commit_count += 1

    def close(self) -> None:
        self.close_count += 1


class _ConfigurationApplication:
    def get(self, kind: LineConfigurationKind, _actor: object) -> LineConfigurationSnapshot:
        assert kind is LineConfigurationKind.RICH_MENUS
        return LineConfigurationSnapshot(kind, LineConfigurationRevision(7), "{}")


class _RichMenuApplication:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.preview_count = 0

    def preview(self, command: object, _actor: object) -> dict[str, object]:
        self.preview_count += 1
        if self.failure is not None:
            raise self.failure
        assert getattr(command, "menu_definition_id") == "default_menu"
        assert getattr(command, "configuration_revision") == LineConfigurationRevision(7)
        return {
            "menu_definition": {"id": "default_menu", "enabled": True},
            "provider_definition": {"size": {"width": 2500, "height": 843}},
        }


class _PublicationApplication(_RichMenuApplication):
    def __init__(self) -> None:
        super().__init__()
        self.page_count = 0
        self.page_offsets: list[int] = []
        self.page_queries: list[object] = []
        self.retry_commands: list[object] = []
        self.get_count = 0
        self.item = LineRichMenuPublicationSnapshot(
            LineRichMenuPublicationId(19),
            "default_menu",
            LineConfigurationRevision(7),
            LineRichMenuPublicationStatus.PUBLISHING,
        )

    def list_page(self, query: object, *, offset: int, actor: object):
        self.page_count += 1
        self.page_offsets.append(offset)
        self.page_queries.append(query)
        return LineRichMenuPublicationPage(
            items=(self.item,),
            total=243,
            offset=offset,
            page_size=getattr(query, "page_size"),
        )

    def get(self, _publication_id: object, _actor: object):
        self.get_count += 1
        return self.item

    def retry(self, command: object):
        self.retry_commands.append(command)
        return self.item


def _client(
    monkeypatch,
    connection: _Connection,
    rich_menu_application: _RichMenuApplication,
) -> tuple[TestClient, list[Request]]:
    principal = AdminPrincipal(17, "menu-admin", "選單管理員", "operator")
    requests: list[Request] = []

    def authorize(request: Request) -> AdminPrincipal:
        request.state.admin_principal = principal
        requests.append(request)
        return principal

    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "_current_menu_snapshot",
        lambda _menu_id: (SimpleNamespace(id="default_menu"), "7", "a" * 64),
    )
    monkeypatch.setattr(
        rich_menu_publication_workflow,
        "get_connection",
        lambda: connection,
    )
    monkeypatch.setattr(
        line_rich_menus,
        "get_line_configuration_application",
        lambda: _ConfigurationApplication(),
    )
    monkeypatch.setattr(
        line_rich_menus,
        "get_line_rich_menu_application",
        lambda: rich_menu_application,
    )
    monkeypatch.setattr(
        line_rich_menus,
        "get_publication_step_receipts",
        lambda _publication_id, _actor: (),
    )
    monkeypatch.setattr(
        line_rich_menus,
        "list_publication_page",
        lambda query, *, offset, actor: rich_menu_application.list_page(
            query,
            offset=offset,
            actor=actor,
        ),
    )
    monkeypatch.setattr(
        line_rich_menus,
        "get_line_wakeup_publisher",
        lambda: (_ for _ in ()).throw(AssertionError("preview must not wake a worker")),
    )
    app = FastAPI()
    app.include_router(line_rich_menus.router)
    app.dependency_overrides[require_line_viewer] = authorize
    app.dependency_overrides[require_line_configuration_reader] = authorize
    app.dependency_overrides[require_line_menu_publisher] = authorize
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    return TestClient(app), requests


def test_publish_preview_route_is_deterministic_and_zero_write(monkeypatch) -> None:
    connection = _Connection()
    rich_menu_application = _RichMenuApplication()
    client, requests = _client(monkeypatch, connection, rich_menu_application)

    first = client.post(
        "/api/v1/line/rich-menus/default_menu/publish-preview",
        headers={"X-Correlation-ID": "rich-menu-preview-first"},
    )
    replay = client.post(
        "/api/v1/line/rich-menus/default_menu/publish-preview",
        headers={"X-Correlation-ID": "rich-menu-preview-replay"},
    )

    assert first.status_code == 200
    assert first.json() == replay.json()
    assert set(first.json()["data"]) == {
        "preview_id",
        "config_revision",
        "config_fingerprint",
    }
    assert first.json()["data"]["preview_id"] > 0
    assert connection.cursor_instance.executions == []
    assert connection.commit_count == 0
    assert rich_menu_application.preview_count == 2
    assert not any(hasattr(request.state, "audit_action") for request in requests)


def test_publish_preview_rejects_overlong_menu_id_before_application(monkeypatch) -> None:
    connection = _Connection()
    rich_menu_application = _RichMenuApplication()
    client, _requests = _client(monkeypatch, connection, rich_menu_application)

    response = client.post(
        f"/api/v1/line/rich-menus/{'m' * 192}/publish-preview",
        headers={"X-Correlation-ID": "rich-menu-preview-invalid"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["category"] == "validation"
    assert rich_menu_application.preview_count == 0
    assert connection.commit_count == 0


def test_publish_route_uses_stateless_apply_and_wakes_after_queue(monkeypatch) -> None:
    connection = _Connection()
    application = _RichMenuApplication()
    client, requests = _client(monkeypatch, connection, application)
    queued = LineRichMenuPublicationSnapshot(
        LineRichMenuPublicationId(41),
        "default_menu",
        LineConfigurationRevision(7),
        LineRichMenuPublicationStatus.QUEUED,
    )
    calls: list[object] = []
    wakeups: list[bool] = []
    monkeypatch.setattr(
        line_rich_menus,
        "validate_publication_preview",
        lambda menu_id, preview_id, previewed_by_admin_user_id: {
            "preview_id": preview_id,
            "config_revision": "7",
            "config_fingerprint": "a" * 64,
        },
    )
    monkeypatch.setattr(
        line_rich_menus,
        "queue_publication",
        lambda command, *, reason: calls.append((command, reason)) or queued,
    )
    monkeypatch.setattr(
        line_rich_menus,
        "get_line_wakeup_publisher",
        lambda: SimpleNamespace(publish=lambda: wakeups.append(True)),
    )

    response = client.post(
        "/api/v1/line/rich-menus/default_menu/publish",
        json={
            "preview_id": 7,
            "reason": "核准發布",
            "idempotency_key": "rich-menu-publish:7",
            "correlation_id": "rich-menu-publish-correlation",
        },
        headers={"X-Correlation-ID": "rich-menu-publish-route"},
    )

    assert response.status_code == 202
    assert response.json()["data"]["id"] == 41
    assert len(calls) == 1
    command, reason = calls[0]
    assert reason == "核准發布"
    assert command.idempotency_key.value == "rich-menu-publish:7"
    assert command.correlation_id.value == "rich-menu-publish-correlation"
    assert len(wakeups) == 1
    assert not hasattr(requests[-1].state, "audit_action")


def test_publish_and_retry_require_client_command_metadata(monkeypatch) -> None:
    connection = _Connection()
    application = _PublicationApplication()
    client, _requests = _client(monkeypatch, connection, application)

    publish = client.post(
        "/api/v1/line/rich-menus/default_menu/publish",
        json={"preview_id": 7},
        headers={"X-Correlation-ID": "rich-menu-publish-missing-metadata"},
    )
    retry = client.post(
        "/api/v1/line/rich-menus/publications/19/retry",
        json={"reason": " ", "idempotency_key": "", "correlation_id": ""},
        headers={"X-Correlation-ID": "rich-menu-retry-blank-metadata"},
    )

    assert publish.status_code == 422
    assert retry.status_code == 422
    assert application.page_count == 0


def test_retry_uses_exact_client_metadata_and_typed_projection(monkeypatch) -> None:
    connection = _Connection()
    application = _PublicationApplication()
    client, _requests = _client(monkeypatch, connection, application)
    wakeups: list[bool] = []
    monkeypatch.setattr(
        line_rich_menus,
        "get_line_wakeup_publisher",
        lambda: SimpleNamespace(publish=lambda: wakeups.append(True)),
    )

    response = client.post(
        "/api/v1/line/rich-menus/publications/19/retry",
        json={
            "reason": "人工確認後重試",
            "idempotency_key": "rich-menu-retry:19",
            "correlation_id": "rich-menu-retry-correlation",
        },
        headers={"X-Correlation-ID": "rich-menu-retry-route"},
    )

    assert response.status_code == 200
    assert set(response.json()["data"]) == {
        "id",
        "menu_definition_id",
        "configuration_revision",
        "status",
    }
    command = application.retry_commands[0]
    assert command.reason == "人工確認後重試"
    assert command.idempotency_key.value == "rich-menu-retry:19"
    assert command.correlation_id.value == "rich-menu-retry-correlation"
    assert command.actor.actor_id == "admin:17"
    assert wakeups == [True]


def test_publish_request_forbids_unknown_fields_before_apply(monkeypatch) -> None:
    connection = _Connection()
    application = _RichMenuApplication()
    client, _requests = _client(monkeypatch, connection, application)

    response = client.post(
        "/api/v1/line/rich-menus/default_menu/publish",
        json={"preview_id": 7, "provider_payload": "secret"},
        headers={"X-Correlation-ID": "rich-menu-publish-extra"},
    )

    assert response.status_code == 422
    assert "secret" not in json.dumps(response.json(), ensure_ascii=False)


def test_publish_preview_not_found_is_typed_and_redacted(monkeypatch) -> None:
    connection = _Connection()
    rich_menu_application = _RichMenuApplication(
        failure=LineRichMenuNotFoundError("provider-secret-menu")
    )
    client, _requests = _client(monkeypatch, connection, rich_menu_application)

    response = client.post(
        "/api/v1/line/rich-menus/default_menu/publish-preview",
        headers={"X-Correlation-ID": "rich-menu-preview-not-found"},
    )

    assert response.status_code == 404
    error = response.json()["detail"]["error"]
    assert error["code"] == "rich_menu_preview_not_found"
    assert error["correlation_id"] == "rich-menu-preview-not-found"
    assert "provider-secret-menu" not in json.dumps(error, ensure_ascii=False)
    assert connection.commit_count == 0


def test_publish_preview_identifies_missing_liff_readiness_without_disclosing_configuration(monkeypatch) -> None:
    connection = _Connection()
    rich_menu_application = _RichMenuApplication(
        failure=ValueError("LINE_LIFF_ID is required for LIFF Rich Menu actions")
    )
    client, _requests = _client(monkeypatch, connection, rich_menu_application)

    response = client.post(
        "/api/v1/line/rich-menus/default_menu/publish-preview",
        headers={"X-Correlation-ID": "rich-menu-preview-liff-readiness"},
    )

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "rich_menu_preview_invalid"
    assert error["message"] == "LIFF 設定尚未完成；目前不能建立發布預覽。"
    assert "LINE_LIFF_ID" not in response.text
    assert connection.commit_count == 0


def test_publication_list_and_detail_are_closed_redacted_projections(monkeypatch) -> None:
    connection = _Connection()
    application = _PublicationApplication()
    client, _requests = _client(monkeypatch, connection, application)
    monkeypatch.setattr(
        line_rich_menus,
        "get_publication_step_receipts",
        lambda _publication_id, _actor: (
            SimpleNamespace(
                step=LineRichMenuPublicationStep.UPLOAD,
                acknowledged_at=datetime(2026, 8, 20, tzinfo=UTC),
                provider_menu_id="provider-secret-menu",
                payload_fingerprint="f" * 64,
                idempotency_key="secret-key",
            ),
        ),
    )

    listed = client.get(
        "/api/v1/line/rich-menus/publications",
        params={"menu_id": "default_menu", "page": 1, "page_size": 100},
        headers={"X-Correlation-ID": "rich-menu-query-list"},
    )
    detailed = client.get(
        "/api/v1/line/rich-menus/publications/19",
        headers={"X-Correlation-ID": "rich-menu-query-detail"},
    )

    assert listed.status_code == 200
    assert detailed.status_code == 200
    assert set(listed.json()["data"]) == {
        "items",
        "page",
        "page_size",
        "total",
        "total_pages",
    }
    assert set(listed.json()["data"]["items"][0]) == {
        "id",
        "menu_definition_id",
        "configuration_revision",
        "status",
        "step_receipts",
    }
    assert detailed.json()["data"]["step_receipts"] == [
        {
            "step": "upload",
            "acknowledged_at": "2026-08-20T00:00:00Z",
        }
    ]
    serialized = json.dumps(detailed.json(), ensure_ascii=False)
    for forbidden in (
        "provider_menu_id",
        "provider-secret",
        "error_message",
        "correlation_id",
        "idempotency_key",
        "fingerprint",
    ):
        assert forbidden not in serialized
    assert listed.json()["data"]["total"] == 243
    assert listed.json()["data"]["total_pages"] == 3
    assert application.page_count == 1
    assert application.page_offsets == [0]
    assert application.page_queries[0].menu_definition_id == "default_menu"
    assert application.get_count == 1
    assert connection.commit_count == 0


def test_publication_query_rejects_unknown_status_before_application(monkeypatch) -> None:
    connection = _Connection()
    application = _PublicationApplication()
    client, _requests = _client(monkeypatch, connection, application)

    response = client.get(
        "/api/v1/line/rich-menus/publications",
        params={"status": "provider-secret-status"},
        headers={"X-Correlation-ID": "rich-menu-query-invalid"},
    )

    assert response.status_code == 422
    assert application.page_count == 0
    assert "provider-secret-status" not in json.dumps(
        response.json(), ensure_ascii=False
    )


def test_publication_query_contract_failure_is_typed_503_non_retryable(monkeypatch) -> None:
    connection = _Connection()

    class _BrokenPublicationApplication(_PublicationApplication):
        def list_page(self, query: object, *, offset: int, actor: object):
            raise ValueError("provider-secret-row-shape")

        def get(self, _publication_id: object, _actor: object):
            raise ValueError("provider-secret-row-shape")

    client, _requests = _client(monkeypatch, connection, _BrokenPublicationApplication())

    listed = client.get(
        "/api/v1/line/rich-menus/publications",
        headers={"X-Correlation-ID": "rich-menu-query-contract-list"},
    )
    detailed = client.get(
        "/api/v1/line/rich-menus/publications/19",
        headers={"X-Correlation-ID": "rich-menu-query-contract-detail"},
    )

    for response in (listed, detailed):
        assert response.status_code == 503
        assert response.json()["detail"]["error"]["code"] == "rich_menu_publication_query_unavailable"
        assert response.json()["detail"]["error"]["retryable"] is False
        assert "provider-secret-row-shape" not in response.text


def test_publication_detail_not_found_is_declared_in_openapi(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(line_rich_menus.router)
    responses = app.openapi()["paths"][
        "/api/v1/line/rich-menus/publications/{publication_id}"
    ]["get"]["responses"]

    assert {"401", "403", "404", "422", "503"} <= set(responses)
    assert responses["404"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/GlobalTypedErrorResponseView"
    )
