"""File: staff_service_day_logs.py
Description: [RETIRED] 月嫂寶寶日誌入口，依 2026-11-10 裁決退役並回傳 410 GONE；日誌維持於 LINE 群組相簿新增。"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Service Day Logs"])

_RETIRED_DETAIL = {
    "code": "service_day_log_retired",
    "message": "月嫂寶寶日誌網頁填寫與上傳已退役，請維持於 LINE 案件群組相簿新增。",
}


@router.post("/service-day-logs", status_code=410)
def retired_direct_service_day_log():
    raise HTTPException(status_code=410, detail=_RETIRED_DETAIL)


@router.post("/service-day-logs/preview", status_code=410)
def preview_service_day_log(*args, **kwargs):
    raise HTTPException(status_code=410, detail=_RETIRED_DETAIL)


@router.post("/service-day-logs/apply", status_code=410)
def apply_service_day_log(*args, **kwargs):
    raise HTTPException(status_code=410, detail=_RETIRED_DETAIL)


@router.post("/service-day-logs/options", status_code=410)
def service_day_log_options(*args, **kwargs):
    raise HTTPException(status_code=410, detail=_RETIRED_DETAIL)


@router.post("/service-day-logs/{log_id}/query", status_code=410)
def query_service_day_log(*args, **kwargs):
    raise HTTPException(status_code=410, detail=_RETIRED_DETAIL)


__all__ = [
    "router",
    "retired_direct_service_day_log",
    "preview_service_day_log",
    "apply_service_day_log",
    "service_day_log_options",
    "query_service_day_log",
]
