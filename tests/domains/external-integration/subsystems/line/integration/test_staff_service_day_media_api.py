"""驗證月嫂服務日照片上傳 API 依 2026-11-10 裁決退役並回傳 410 GONE。"""

import asyncio
import pytest
from fastapi import HTTPException

from api.routes import staff_service_day_media


def test_service_day_media_endpoints_are_retired() -> None:
    with pytest.raises(HTTPException) as captured:
        staff_service_day_media.service_day_media_settings()
    assert captured.value.status_code == 410
    assert captured.value.detail["code"] == "service_day_media_retired"

    with pytest.raises(HTTPException) as captured:
        asyncio.run(staff_service_day_media.upload_service_day_meal_photo())
    assert captured.value.status_code == 410
    assert captured.value.detail["code"] == "service_day_media_retired"

    with pytest.raises(HTTPException) as captured:
        asyncio.run(staff_service_day_media.download_service_day_photo())
    assert captured.value.status_code == 410
    assert captured.value.detail["code"] == "service_day_media_retired"
