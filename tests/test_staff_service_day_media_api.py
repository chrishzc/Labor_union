"""File: test_staff_service_day_media_api.py
Description: 驗證月嫂餐食照片 API 僅接受已驗證身分、真實圖片位元組與受控 media reference。"""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from api.routes import staff_service_day_media
from domains.line.identities import LineUserId


class Upload:
    def __init__(self, content: bytes, content_type: str) -> None:
        self._content = content
        self.content_type = content_type

    async def read(self, _limit: int) -> bytes:
        return self._content


def test_upload_meal_photo_persists_verified_staff_media(monkeypatch) -> None:
    recorded = {}

    class MediaMetadata:
        def get(self, _media_id):
            return None

        def register(self, metadata, reference, key):
            recorded.update(metadata=metadata, reference=reference, key=key)

    @contextmanager
    def line_uow():
        yield SimpleNamespace(
            customer_service=SimpleNamespace(
                staff_subject=lambda user_id: {"staff_id": 8} if user_id == "U-caregiver" else None
            ),
            media_metadata=MediaMetadata(),
            commit=lambda: recorded.setdefault("committed", True),
        )

    class Store:
        def __init__(self, _root):
            pass

        def put(self, metadata, content):
            assert metadata.source.user_id == LineUserId("U-caregiver")
            assert content.startswith(b"\x89PNG")
            return "user_upload/aa/photo.png"

    monkeypatch.setattr(staff_service_day_media, "open_line_unit_of_work", line_uow)
    monkeypatch.setattr(staff_service_day_media, "_verified_line_user_id", lambda _payload: LineUserId("U-caregiver"))
    monkeypatch.setattr(staff_service_day_media, "FileSystemLineMediaObjectStore", Store)

    response = asyncio.run(
        staff_service_day_media.upload_service_day_meal_photo(
            Upload(b"\x89PNG\r\n\x1a\nphoto", "image/png"),
            "flow", "token", "", "meal-photo-1",
        )
    )

    assert response.data["outcome"] == "created"
    assert response.data["media_id"].startswith("liff-upload:")
    assert recorded["metadata"].content_type == "image/png"
    assert recorded["reference"] == "user_upload/aa/photo.png"
    assert recorded["committed"] is True


def test_upload_meal_photo_rejects_declared_type_that_does_not_match_bytes(monkeypatch) -> None:
    monkeypatch.setattr(staff_service_day_media, "_verified_line_user_id", lambda _payload: LineUserId("U-caregiver"))

    try:
        asyncio.run(
            staff_service_day_media.upload_service_day_meal_photo(
                Upload(b"not-an-image", "image/jpeg"),
                "flow", "token", "", "meal-photo-invalid",
            )
        )
    except staff_service_day_media.HTTPException as error:
        assert error.status_code == 422
        assert error.detail["code"] == "service_day_meal_photo_content_type_invalid"
    else:
        raise AssertionError("expected invalid meal photo to be rejected")
