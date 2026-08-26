"""
File: test_line_configuration_public_query_route.py
Description: 驗證 LINE Configuration safe GET、Rich Menu successor guard 與其他種類相容性。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies.admin_auth import (
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import line_configurations
from api.schemas.line_configurations import LineConfigurationSafePublicView
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from shared_kernel.fingerprints import PreviewFingerprint
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
    app.dependency_overrides[require_line_configuration_manager] = _principal
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    return TestClient(app)


class _Application:
    def __init__(self, safe_result: object) -> None:
        self.safe_result = safe_result
        self.safe_calls: list[tuple[object, object]] = []
        self.get_calls: list[LineConfigurationKind] = []
        self.preview_calls: list[LineConfigurationKind] = []
        self.apply_calls: list[LineConfigurationKind] = []

    def get_safe(self, query: object, actor: object) -> object:
        self.safe_calls.append((query, actor))
        if isinstance(self.safe_result, Exception):
            raise self.safe_result
        return self.safe_result

    def get(self, kind: LineConfigurationKind, _actor: object) -> LineConfigurationSnapshot:
        self.get_calls.append(kind)
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

    def preview(
        self,
        kind: LineConfigurationKind,
        expected_revision: LineConfigurationRevision,
        definition: dict[str, object],
        _actor: object,
    ) -> object:
        self.preview_calls.append(kind)
        return SimpleNamespace(
            kind=kind,
            before_revision=expected_revision,
            resulting_revision=LineConfigurationRevision(expected_revision.value + 1),
            definition_json=json.dumps(
                definition,
                sort_keys=True,
                separators=(",", ":"),
            ),
            fingerprint=PreviewFingerprint("a" * 64),
        )

    def apply(self, **command: object) -> object:
        kind = command["kind"]
        expected_revision = command["expected_revision"]
        definition = command["definition"]
        assert isinstance(kind, LineConfigurationKind)
        assert isinstance(expected_revision, LineConfigurationRevision)
        assert isinstance(definition, dict)
        self.apply_calls.append(kind)
        return SimpleNamespace(
            snapshot=LineConfigurationSnapshot(
                kind,
                LineConfigurationRevision(expected_revision.value + 1),
                json.dumps(definition, sort_keys=True, separators=(",", ":")),
            )
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


def test_generic_rich_menu_query_preview_and_apply_point_to_dedicated_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application(
        LineConfigurationSafeResult(
            LineConfigurationKind.RICH_MENUS,
            9,
            LineConfigurationSafeState.CONFIGURED,
        )
    )
    client = _client(monkeypatch, application)
    responses = (
        client.get("/api/v1/line/configurations/rich_menus"),
        client.post(
            "/api/v1/line/configurations/rich_menus/preview",
            json={"expected_revision": 9, "definition": {"menus": []}},
        ),
        client.put(
            "/api/v1/line/configurations/rich_menus",
            json={
                "expected_revision": 9,
                "definition": {"menus": []},
                "reason": "更新 Rich Menu 草稿",
                "idempotency_key": "rich-menu-draft:9",
                "correlation_id": "rich-menu-draft-9",
            },
        ),
    )

    for response in responses:
        assert response.status_code == 410
        assert response.json()["detail"]["error"]["code"] == (
            "line_rich_menu_generic_configuration_retired"
        )
        assert "/api/v1/line/rich-menus/draft" in response.text
    assert application.get_calls == []
    assert application.preview_calls == []
    assert application.apply_calls == []


def test_other_configuration_kinds_keep_generic_query_preview_and_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application(
        LineConfigurationSafeResult(
            LineConfigurationKind.LIFF,
            9,
            LineConfigurationSafeState.CONFIGURED,
        )
    )
    client = _client(monkeypatch, application)

    queried = client.get("/api/v1/line/configurations/liff")
    previewed = client.post(
        "/api/v1/line/configurations/liff/preview",
        json={"expected_revision": 9, "definition": {"pages": []}},
    )
    applied = client.put(
        "/api/v1/line/configurations/liff",
        json={
            "expected_revision": 9,
            "definition": {"pages": []},
            "reason": "更新 LIFF 設定",
            "idempotency_key": "liff-config:9",
            "correlation_id": "liff-config-9",
        },
    )

    assert queried.status_code == 200
    assert previewed.status_code == 200
    assert previewed.json()["data"]["resulting_revision"] == 10
    assert applied.status_code == 200
    assert applied.json()["data"]["revision"] == 10
    assert application.get_calls == [LineConfigurationKind.LIFF]
    assert application.preview_calls == [LineConfigurationKind.LIFF]
    assert application.apply_calls == [LineConfigurationKind.LIFF]
