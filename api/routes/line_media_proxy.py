"""NAS public routes preserve wire contracts without opening local file workflows."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Service Day Logs"])

_RETIRED_PROXY_DETAIL = {
    "code": "service_day_media_retired",
    "message": "月嫂照片與寶寶日誌網頁上傳已退役，請維持於 LINE 案件群組相簿新增。",
}


@router.post("/service-day-logs", status_code=410)
def retired_direct_service_day_log():
    raise HTTPException(410, detail=_RETIRED_PROXY_DETAIL)


@router.post("/service-day-media", status_code=410)
async def upload(*args, **kwargs):
    raise HTTPException(410, detail=_RETIRED_PROXY_DETAIL)


@router.post("/service-day-media/settings", status_code=410)
async def settings(*args, **kwargs):
    raise HTTPException(410, detail=_RETIRED_PROXY_DETAIL)


@router.post("/service-day-logs/preview", status_code=410)
async def preview(*args, **kwargs):
    raise HTTPException(410, detail=_RETIRED_PROXY_DETAIL)


@router.post("/service-day-logs/apply", status_code=410)
async def apply(*args, **kwargs):
    raise HTTPException(410, detail=_RETIRED_PROXY_DETAIL)


@router.post("/service-day-logs/options", status_code=410)
async def log_options(*args, **kwargs):
    raise HTTPException(410, detail=_RETIRED_PROXY_DETAIL)


@router.post("/service-day-logs/{log_id}/query", status_code=410)
async def query(*args, **kwargs):
    raise HTTPException(410, detail=_RETIRED_PROXY_DETAIL)


@router.post("/service-day-logs/{log_id}/photos/{file_id}/download", status_code=410)
async def download(*args, **kwargs):
    raise HTTPException(410, detail=_RETIRED_PROXY_DETAIL)


__all__ = [
    "router",
    "retired_direct_service_day_log",
    "upload",
    "settings",
    "preview",
    "apply",
    "log_options",
    "query",
    "download",
]
