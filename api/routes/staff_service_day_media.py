"""
File: staff_service_day_media.py
Description: [RETIRED] 提供月嫂上傳寶寶／餐食照片的 LIFF API，依 2026-11-10 裁決退役並回傳 410 GONE；照片維持於 LINE 群組相簿新增。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Service Day Logs"])

_RETIRED_MEDIA_DETAIL = {
    "code": "service_day_media_retired",
    "message": "服務日寶寶與餐食照片網頁上傳已退役，請維持於 LINE 案件群組相簿新增。",
}


@router.post("/service-day-media/settings", status_code=410)
def service_day_media_settings(*args, **kwargs):
    raise HTTPException(status_code=410, detail=_RETIRED_MEDIA_DETAIL)


@router.post("/service-day-media", status_code=410)
async def upload_service_day_meal_photo(*args, **kwargs):
    raise HTTPException(status_code=410, detail=_RETIRED_MEDIA_DETAIL)


@router.post("/service-day-logs/{log_id}/photos/{file_id}/download", status_code=410)
async def download_service_day_photo(*args, **kwargs):
    raise HTTPException(status_code=410, detail=_RETIRED_MEDIA_DETAIL)


__all__ = [
    "router",
    "service_day_media_settings",
    "upload_service_day_meal_photo",
    "download_service_day_photo",
]
