"""驗證 Rich Menu 圖片上傳只公開封閉的 metadata receipt。"""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import Request
from PIL import Image
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from api.routes import line_rich_menus
from api.schemas.line_rich_menus import (
    RichMenuImageUploadResponse,
    RichMenuImageUploadResult,
)
from infrastructure.file.storage_layout import CLIENT_PASSBOOK_DIRECTORY, MEDIA_DIRECTORY
from subsystems.line import media_archive


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


def test_new_local_menu_upload_reads_from_04_and_legacy_asset_still_reads(tmp_path, monkeypatch):
    root = tmp_path / "shared"
    root.mkdir()
    legacy_root = tmp_path / "legacy"
    old_key = "rich_menus/staff/old.jpg"
    old_path = legacy_root / old_key
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"old menu")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(root))
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(legacy_root))
    assets = {1: {"storage_key": old_key, "sha256": sha256(b"old menu").hexdigest()}}

    def insert(_sql, parameters):
        assets[2] = {"id": 2, "storage_key": parameters[2], "sha256": parameters[5]}

    cursor = SimpleNamespace(execute=insert, lastrowid=2)
    connection = SimpleNamespace(cursor=lambda: nullcontext(cursor), close=lambda: None)
    monkeypatch.setattr(media_archive, "get_media_asset", lambda asset_id, **_: assets[asset_id])
    source = BytesIO()
    Image.new("RGB", (2500, 843), "white").save(source, format="PNG")

    asset = media_archive.store_uploaded_rich_menu_image(
        source.getvalue(), menu_id="staff", original_filename="menu.png",
        expected_width=2500, expected_height=843, created_by_admin_user_id=17,
        connection_factory=lambda: connection,
        unit_of_work_factory=lambda _: nullcontext(SimpleNamespace(commit=lambda: None)),
    )

    assert asset["storage_key"].startswith("rich_menus/uploads/v1/staff/")
    archive_file = root / MEDIA_DIRECTORY / asset["storage_key"]
    assert media_archive.read_media_asset(2)[1] == archive_file.read_bytes()
    assert media_archive.read_media_asset(1)[1] == old_path.read_bytes() == b"old menu"
    assert not (root / CLIENT_PASSBOOK_DIRECTORY).exists()
