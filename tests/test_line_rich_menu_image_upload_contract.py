"""驗證 Rich Menu 圖片上傳只公開封閉的 metadata receipt。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from api.routes import line_rich_menus
from api.schemas.line_rich_menus import (
    RichMenuImageUploadResponse,
    RichMenuImageUploadResult,
)


def _request() -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/line/rich-menus/staff/images",
            "headers": [],
            "query_string": b"",
        }
    )
    request.state.admin_principal = SimpleNamespace(id=17)
    return request


def _asset() -> dict[str, object]:
    return {
        "id": 41,
        "original_filename": "menu.png",
        "mime_type": "image/jpeg",
        "file_size": 1234,
        "sha256": "a" * 64,
        "width": 2500,
        "height": 843,
        "created_at": datetime(2026, 8, 29, tzinfo=UTC),
    }


def test_upload_route_declares_closed_typed_response() -> None:
    route = next(
        route
        for route in line_rich_menus.router.routes
        if route.path.endswith("/{menu_id}/images")
    )

    assert route.response_model is RichMenuImageUploadResponse


def test_upload_route_maps_storage_metadata_without_provider_call(monkeypatch) -> None:
    calls: list[bytes] = []

    monkeypatch.setattr(
        line_rich_menus,
        "_menu",
        lambda _menu_id: SimpleNamespace(size=SimpleNamespace(width=2500, height=843)),
    )

    def store(content: bytes, **kwargs):
        calls.append(content)
        assert kwargs["menu_id"] == "staff"
        return _asset()

    monkeypatch.setattr(line_rich_menus, "store_uploaded_rich_menu_image", store)

    response = asyncio.run(
        line_rich_menus.upload_rich_menu_image(
            "staff",
            _request(),
            UploadFile(file=BytesIO(b"image-bytes"), filename="menu.png"),
        )
    )

    assert response.model_dump(mode="json") == {
        "success": True,
        "message": "Rich Menu 圖片已安全保存",
        "data": {
            "id": 41,
            "original_filename": "menu.png",
            "mime_type": "image/jpeg",
            "file_size": 1234,
            "sha256": "a" * 64,
            "width": 2500,
            "height": 843,
            "created_at": "2026-08-29T00:00:00Z",
        },
        "error": None,
    }
    assert calls == [b"image-bytes"]


def test_upload_result_rejects_unknown_public_fields() -> None:
    payload = _asset() | {"storage_key": "internal/path.jpg"}

    with pytest.raises(ValidationError):
        RichMenuImageUploadResult.model_validate(payload)
