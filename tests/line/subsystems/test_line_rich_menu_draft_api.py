"""
File: test_line_rich_menu_draft_api.py
Description: 驗證 Rich Menu 專用草稿 API 的 strict Query、Preview、Apply 與 readback。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies.admin_auth import (
    require_line_configuration_manager,
    require_line_viewer,
)
from api.routes import line_rich_menus
from api.schemas.line_rich_menu_drafts import RichMenuDraftApplyRequest
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationResult,
    LineConfigurationCommandOutcome,
    LineRichMenuDraftPublicationLock,
    LineRichMenuDraftPublicationState,
    LineRichMenuDraftQueryResult,
)


def _principal() -> AdminPrincipal:
    return AdminPrincipal(7, "rich-menu-admin", "選單管理員", "system_admin")


def _definition(text: str = "聯絡工會") -> dict[str, object]:
    return {
        "version": 2,
        "menus": [
            {
                "id": "customer_menu",
                "name": "客戶選單",
                "audience_role": "customer",
                "chat_bar_text": "服務選單",
                "set_as_default": True,
                "buttons": [
                    {
                        "id": "contact",
                        "label": "聯絡工會",
                        "bounds": {"x": 0, "y": 0, "width": 2500, "height": 843},
                        "action": {"type": "message", "text": text},
                    }
                ],
            }
        ],
    }


def _client(monkeypatch, application) -> TestClient:
    app = FastAPI()
    app.include_router(line_rich_menus.router)
    app.dependency_overrides[require_line_viewer] = _principal
    app.dependency_overrides[require_line_configuration_manager] = _principal
    monkeypatch.setattr(
        line_rich_menus,
        "get_line_configuration_application",
        lambda: application,
    )
    return TestClient(app)


def _query_result(snapshot, state=LineRichMenuDraftPublicationState.EDITABLE):
    return LineRichMenuDraftQueryResult(
        snapshot,
        (
            LineRichMenuDraftPublicationLock(
                "customer_menu",
                snapshot.revision,
                state,
            ),
        ),
    )


def test_draft_query_returns_action_only_through_manager_contract(monkeypatch) -> None:
    class Application:
        def get_rich_menu_draft_query(self, actor):
            assert actor.actor_id == "admin:7"
            return _query_result(LineConfigurationSnapshot(
                LineConfigurationKind.RICH_MENUS,
                LineConfigurationRevision(4),
                canonical_line_payload_json(_definition()),
            ), LineRichMenuDraftPublicationState.PROCESSING)

    response = _client(monkeypatch, Application()).get("/api/v1/line/rich-menus/draft")

    assert response.status_code == 200
    assert response.json()["data"]["revision"] == 4
    assert response.json()["data"]["publication_locks"] == [
        {
            "menu_definition_id": "customer_menu",
            "configuration_revision": 4,
            "state": "processing",
            "readonly_reason": "此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。",
        }
    ]
    assert response.json()["data"]["definition"]["menus"][0]["buttons"][0]["action"] == {
        "type": "message",
        "text": "聯絡工會",
        "uri": None,
        "uri_source": "literal",
        "data": None,
        "rich_menu_alias_id": None,
    }


def test_draft_preview_and_apply_return_normalized_readback(monkeypatch) -> None:
    definition = _definition("實際候選訊息")
    normalized_json = canonical_line_payload_json(_definition("實際候選訊息"))
    fingerprint = PreviewFingerprint("a" * 64)

    class Application:
        def __init__(self):
            self.snapshot = LineConfigurationSnapshot(
                LineConfigurationKind.RICH_MENUS,
                LineConfigurationRevision(5),
                normalized_json,
            )

        def preview_rich_menu_draft(self, expected_revision, received, actor):
            assert expected_revision == LineConfigurationRevision(4)
            assert received == definition
            return type(
                "Candidate",
                (),
                {
                    "before_revision": LineConfigurationRevision(4),
                    "resulting_revision": LineConfigurationRevision(5),
                    "definition_json": normalized_json,
                    "fingerprint": fingerprint,
                },
            )()

        def apply_rich_menu_draft(self, **command):
            assert command["preview_fingerprint"] == fingerprint
            assert command["expected_revision"] == LineConfigurationRevision(4)
            return ApplyLineConfigurationResult(
                LineConfigurationCommandOutcome.CREATED,
                self.snapshot,
            )

        def get_rich_menu_draft_query(self, actor):
            return _query_result(self.snapshot)

    client = _client(monkeypatch, Application())
    preview = client.post(
        "/api/v1/line/rich-menus/draft/preview",
        json={"expected_revision": 4, "definition": definition},
    )
    apply = client.put(
        "/api/v1/line/rich-menus/draft",
        json={
            "expected_revision": 4,
            "definition": definition,
            "preview_fingerprint": "a" * 64,
            "reason": "調整客服候選訊息",
            "idempotency_key": "rich-menu-draft-api-4",
            "correlation_id": "rich-menu-draft-api-correlation-4",
        },
    )

    assert preview.status_code == 200
    assert preview.json()["data"]["resulting_revision"] == 5
    assert apply.status_code == 200
    assert apply.json()["data"]["receipt"] == {
        "outcome": "created",
        "committed_revision": 5,
        "receipt_reference": "line-rich-menu-draft:5",
    }
    assert apply.json()["data"]["readback"]["definition"]["menus"][0]["buttons"][0]["action"]["text"] == "實際候選訊息"
    assert apply.json()["data"]["readback"]["publication_locks"][0]["state"] == "editable"


def test_apply_request_is_closed_and_requires_preview_fingerprint() -> None:
    payload = {
        "expected_revision": 4,
        "definition": _definition(),
        "reason": "調整選單",
        "idempotency_key": "rich-menu-draft-api-4",
        "correlation_id": "rich-menu-draft-api-correlation-4",
    }
    with pytest.raises(ValidationError):
        RichMenuDraftApplyRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        RichMenuDraftApplyRequest.model_validate(
            {**payload, "preview_fingerprint": "b" * 64, "provider_payload": "secret"}
        )


@pytest.mark.parametrize(
    "code",
    [
        "line_rich_menu_media_asset_missing",
        "line_rich_menu_media_asset_owner_conflict",
        "line_rich_menu_media_asset_deleted",
        "line_rich_menu_media_asset_digest_conflict",
        "line_rich_menu_media_asset_version_conflict",
        "line_rich_menu_media_asset_size_conflict",
    ],
)
def test_draft_media_conflicts_return_typed_business_reason(monkeypatch, code) -> None:
    class Application:
        def preview_rich_menu_draft(self, *_args):
            raise RuntimeError(code)

    response = _client(monkeypatch, Application()).post(
        "/api/v1/line/rich-menus/draft/preview",
        json={"expected_revision": 4, "definition": _definition()},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == code
    assert "重新選擇" in response.json()["detail"]["error"]["message"]


def test_draft_routes_use_typed_response_models() -> None:
    response_models = {
        (tuple(sorted(route.methods or ())), route.path): route.response_model
        for route in line_rich_menus.router.routes
        if route.path in {
            "/api/v1/line/rich-menus/draft",
            "/api/v1/line/rich-menus/draft/preview",
        }
    }
    assert all(model is not None for model in response_models.values())
    assert len(response_models) == 3
