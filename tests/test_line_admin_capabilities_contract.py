"""Focused contract checks for the typed LINE admin capability projection."""

import pytest
from pydantic import ValidationError

from api.routes import line_admin
from api.schemas.base import BaseResponse
from api.schemas.line_admin import LineAdminCapabilitiesView
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


def test_health_route_keeps_opaque_response_model() -> None:
    response_models = {
        route.path: route.response_model
        for route in line_admin.router.routes
        if getattr(route, "response_model", None) is not None
    }

    assert response_models["/api/v1/line/admin/health"] == BaseResponse[dict]
    assert response_models["/api/v1/line/admin/capabilities"] == BaseResponse[
        LineAdminCapabilitiesView
    ]
