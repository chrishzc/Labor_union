"""
File: test_line_configuration_public_query_route.py
Description: 驗證 LINE Configuration safe GET 的封閉回應、typed errors、auth alias 與 legacy 相容性。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies.admin_auth import require_line_configuration_reader
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import line_configurations
from api.schemas.line_configurations import LineConfigurationSafePublicView
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_contracts import (
    LineConfigurationQueryContractError,
    LineConfigurationQueryUnavailableError,
    LineConfigurationSafeResult,
    LineConfigurationSafeState,
)


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "configuration-admin", "設定管理員", "operator")


def _client(monkeypatch: pytest.MonkeyPatch, application: object) -> TestClient:
    monkeypatch.setattr(
        line_configurations,
        "get_line_configuration_application",
        lambda: application,
    )
    app = FastAPI()
    app.include_router(line_configurations.router)
    app.dependency_overrides[require_line_configuration_reader] = _principal
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    return TestClient(app)


class _Application:
    def __init__(self, safe_result: object) -> None:
        self.safe_result = safe_result
        self.safe_calls: list[tuple[object, object]] = []

    def get_safe(self, query: object, actor: object) -> object:
        self.safe_calls.append((query, actor))
        if isinstance(self.safe_result, Exception):
            raise self.safe_result
        return self.safe_result

    def get(self, kind: LineConfigurationKind, _actor: object) -> LineConfigurationSnapshot:
        return LineConfigurationSnapshot(
            kind,
            LineConfigurationRevision(9),
            json.dumps(
                {
                    "menus": [],
                    "uri": "https://legacy.invalid/menu",
                    "provider_id": "legacy-provider-secret",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )


def test_safe_route_returns_exact_closed_redacted_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application(
        LineConfigurationSafeResult(
            LineConfigurationKind.RICH_MENUS,
            9,
            LineConfigurationSafeState.CONFIGURED,
        )
    )

    response = _client(monkeypatch, application).get(
        "/api/v1/line/configurations/rich_menus/safe",
        headers={"X-Correlation-ID": "configuration-safe-route"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Success",
        "data": {
            "kind": "rich_menus",
            "revision": 9,
            "state": "configured",
        },
        "error": None,
    }
    rendered = json.dumps(response.json()["data"], sort_keys=True)
    assert "legacy.invalid" not in rendered
    assert "provider-secret" not in rendered
    assert len(application.safe_calls) == 1


def test_safe_public_view_rejects_extra_or_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        LineConfigurationSafePublicView.model_validate(
            {
                "kind": "rich_menus",
                "revision": 1,
                "state": "configured",
                "definition": {"uri": "https://secret.invalid"},
            }
        )


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_retryable"),
    [
        (
            LineConfigurationQueryContractError(),
            "line_configuration_query_contract_invalid",
            False,
        ),
        (
            LineConfigurationQueryUnavailableError(),
            "line_configuration_query_unavailable",
            True,
        ),
    ],
)
def test_safe_route_returns_redacted_global_typed_error(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    response = _client(monkeypatch, _Application(failure)).get(
        "/api/v1/line/configurations/rich_menus/safe",
        headers={"X-Correlation-ID": "configuration-safe-failure"},
    )

    assert response.status_code == 503
    error = response.json()["detail"]["error"]
    assert error == {
        "category": "unavailable",
        "code": expected_code,
        "message": "LINE 設定查詢結果無法安全提供。",
        "field_errors": [],
        "domain_blockers": [],
        "retryable": expected_retryable,
        "correlation_id": "configuration-safe-failure",
        "current_version": None,
    }
    assert "secret" not in json.dumps(error, ensure_ascii=False).lower()


def test_safe_route_rejects_unknown_kind_with_global_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(
        monkeypatch,
        _Application(
            LineConfigurationSafeResult(
                LineConfigurationKind.RICH_MENUS,
                0,
                LineConfigurationSafeState.EMPTY,
            )
        ),
    ).get(
        "/api/v1/line/configurations/unknown_kind/safe",
        headers={"X-Correlation-ID": "configuration-safe-unknown"},
    )

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["category"] == "validation"
    assert error["correlation_id"] == "configuration-safe-unknown"


def test_legacy_full_definition_get_remains_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application(
        LineConfigurationSafeResult(
            LineConfigurationKind.RICH_MENUS,
            9,
            LineConfigurationSafeState.CONFIGURED,
        )
    )
    response = _client(monkeypatch, application).get(
        "/api/v1/line/configurations/rich_menus"
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "kind": "rich_menus",
        "revision": 9,
        "definition": {
            "menus": [],
            "provider_id": "legacy-provider-secret",
            "uri": "https://legacy.invalid/menu",
        },
    }
