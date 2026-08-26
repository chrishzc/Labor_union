"""
File: test_line_media_asset_query_route.py
Description: 驗證 Rich Menu media list/detail 的認證、嚴格回應與安全錯誤。
"""

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_configuration_reader
from api.routes import line_media_assets
from domains.line.media_asset import RichMenuMediaAsset
from subsystems.line.media_asset_contracts import RichMenuMediaAssetPage


def _asset(*, deleted: bool = False) -> RichMenuMediaAsset:
    return RichMenuMediaAsset(
        asset_id=11,
        menu_definition_id="staff_menu",
        original_filename="staff.png",
        mime_type="image/png",
        file_size=2048,
        sha256="a" * 64,
        width=2500,
        height=1686,
        created_at=datetime(2026, 8, 26, 1, 2, tzinfo=timezone.utc),
        deleted_at=(
            datetime(2026, 8, 26, 2, 2, tzinfo=timezone.utc) if deleted else None
        ),
    )


class _Repository:
    def list(self, query):
        assert (query.menu_definition_id, query.page, query.page_size) == (
            "staff_menu",
            2,
            25,
        )
        return RichMenuMediaAssetPage((_asset(),), 2, 25, 26, 2)

    def get(self, query):
        assert (query.menu_definition_id, query.asset_id) == ("staff_menu", 11)
        return _asset(deleted=True)


def _client(repository=None, auth_dependency=None) -> TestClient:
    app = FastAPI()
    app.include_router(line_media_assets.router)
    app.dependency_overrides[
        line_media_assets.get_line_rich_menu_media_asset_query_repository
    ] = lambda: repository or _Repository()
    app.dependency_overrides[require_line_configuration_reader] = (
        auth_dependency or (lambda: object())
    )
    return TestClient(app)


def test_list_returns_typed_numbered_metadata_without_storage_fields() -> None:
    response = _client().get(
        "/api/v1/line/media-assets/rich-menu",
        params={"menu_definition_id": "staff_menu", "page": 2, "page_size": 25},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["total"] == 26
    assert payload["data"]["total_pages"] == 2
    item = payload["data"]["items"][0]
    assert item["selectable"] is True
    assert len(item["asset_version"]) == 64
    assert "storage_provider" not in item
    assert "storage_key" not in item
    assert "created_by" not in item


def test_detail_returns_deleted_metadata_with_business_reason() -> None:
    response = _client().get(
        "/api/v1/line/media-assets/rich-menu/11",
        params={"menu_definition_id": "staff_menu"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["selectable"] is False
    assert "已刪除" in response.json()["data"]["business_reason"]


def test_route_requires_authenticated_admin_reader() -> None:
    def denied():
        raise HTTPException(status_code=401, detail="session required")

    response = _client(auth_dependency=denied).get(
        "/api/v1/line/media-assets/rich-menu",
        params={"menu_definition_id": "staff_menu"},
    )

    assert response.status_code == 401


def test_owner_scoped_missing_detail_is_404() -> None:
    class MissingRepository(_Repository):
        def get(self, query):
            return None

    response = _client(MissingRepository()).get(
        "/api/v1/line/media-assets/rich-menu/11",
        params={"menu_definition_id": "staff_menu"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == (
        "line_rich_menu_media_asset_not_found"
    )


def test_invalid_persisted_projection_fails_closed_without_raw_error() -> None:
    class InvalidRepository(_Repository):
        def list(self, query):
            raise ValueError("raw storage key must not leak")

    response = _client(InvalidRepository()).get(
        "/api/v1/line/media-assets/rich-menu",
        params={"menu_definition_id": "staff_menu", "page": 2, "page_size": 25},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == (
        "line_rich_menu_media_asset_query_unavailable"
    )
    assert "raw storage key" not in response.text
