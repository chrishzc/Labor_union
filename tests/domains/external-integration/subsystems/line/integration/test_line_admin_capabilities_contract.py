"""Focused contract checks for the typed LINE admin capability projection."""

import pytest
from pydantic import ValidationError

from api.routes import line_admin
from api.dependencies import line_runtime
from api.schemas.base import BaseResponse
from api.schemas.line_admin import (
    LineAdminCapabilitiesView,
    LineAdminHealthView,
    LineDatabaseHealthView,
    LineQueueCountsView,
    LineWorkerHealthView,
    LegacyLineTaskCountsView,
)
from subsystems.access.authentication_session import AdminPrincipal


def test_capabilities_route_returns_closed_typed_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONTRACT_INTEGRATION_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED", raising=False)

    response = line_admin.line_admin_capabilities(
        AdminPrincipal(7, "authenticated-user", "已驗證內部使用者", "system_admin")
    )

    assert isinstance(response.data, LineAdminCapabilitiesView)
    assert response.data.stage.isdigit()
    assert response.data.runtime_availability.contract_worker_enabled is False
    assert response.data.config_files.model_dump().keys() == {
        "message_templates",
        "message_schedules",
        "line_menus",
        "liff",
        "customer_service",
    }


def test_capabilities_projection_rejects_unknown_fields() -> None:
    response = line_admin.line_admin_capabilities(
        AdminPrincipal(7, "authenticated-user", "已驗證內部使用者", "system_admin")
    )
    payload = response.data.model_dump()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        LineAdminCapabilitiesView.model_validate(payload)


def test_health_route_uses_closed_typed_response_model() -> None:
    response_models = {
        route.path: route.response_model
        for route in line_admin.router.routes
        if getattr(route, "response_model", None) is not None
    }

    assert response_models["/api/v1/line/admin/health"] == BaseResponse[
        LineAdminHealthView
    ]
    assert response_models["/api/v1/line/admin/capabilities"] == BaseResponse[
        LineAdminCapabilitiesView
    ]


def test_health_projection_is_bounded_and_redacts_database_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        line_runtime,
        "get_connection",
        lambda: (_ for _ in ()).throw(RuntimeError("database-detail-must-not-leak")),
    )

    database = line_runtime.get_line_database_health()
    response = line_admin.line_admin_health(database)

    assert isinstance(response.data, LineAdminHealthView)
    assert response.data.status == "degraded"
    assert response.data.database.error_code == "line_database_unavailable"
    assert "database-detail-must-not-leak" not in response.data.model_dump_json()

    payload = response.data.model_dump()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        LineAdminHealthView.model_validate(payload)


def test_health_dependency_returns_typed_bounded_query_and_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        closed = False

        def close(self) -> None:
            self.closed = True

    class Repository:
        def __init__(self, connection: Connection) -> None:
            self.connection = connection

        def latest_heartbeat(self):
            return None

        def database_ready(self) -> bool:
            return True

        def legacy_task_counts(self) -> dict[str, int]:
            return {"pending": 2}

        def queue_counts(self) -> dict[str, int]:
            return {"inbox_pending": 1, "delivery_pending": 3}

    connection = Connection()
    monkeypatch.setattr(line_runtime, "get_connection", lambda: connection)
    monkeypatch.setattr(line_runtime, "MySqlLineRuntimeRepository", Repository)

    result = line_runtime.get_line_database_health()

    assert isinstance(result, LineDatabaseHealthView)
    assert result.ok is True
    assert result.line_task_counts.pending == 2
    assert result.queue_counts.inbox_pending == 1
    assert result.queue_counts.delivery_pending == 3
    assert result.worker.status == "missing"
    assert connection.closed is True


def test_health_route_does_not_own_sql_or_database_connections() -> None:
    source = line_admin.__file__
    route_text = open(source, encoding="utf-8").read()

    assert "get_connection" not in route_text
    assert "cursor.execute" not in route_text
    assert "MySqlLineRuntimeRepository" not in route_text
