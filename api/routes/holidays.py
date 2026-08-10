from fastapi import APIRouter, Depends, Header, HTTPException, Path
from typing import List, Dict, Any
from datetime import date
from api.dependencies.admin_auth import require_system_admin
from api.error_contracts import internal_query_error
from infrastructure.mysql.admin_command_repository import AdminCommandRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.scheduling.holiday_query_cache import (
    invalidate_holiday_query_cache,
    query_holidays,
)
from subsystems.access.authentication_session import AdminPrincipal
from api.schemas.base import BaseResponse
from api.schemas.holidays import HolidayApplyRequest, HolidayPreviewRequest
from subsystems.scheduling import holiday_maintenance

router = APIRouter(prefix="/api/v1/holidays", tags=["Holidays 國定假日設定"])

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_holidays(
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """取得中華民國國定假日設定列表"""
    try:
        data = query_holidays()
        return BaseResponse(data=data, message="成功取得國定假日列表")
    except Exception as error:
        raise internal_query_error(
            "holiday_query_internal_error",
            "國定假日查詢失敗。",
            "holiday-query",
        ) from error

@router.post("/preview", response_model=BaseResponse[Dict[str, Any]])
def preview_holiday_change(
    req: HolidayPreviewRequest,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    connection = get_connection()
    try:
        result = holiday_maintenance.preview(AdminCommandRepository(connection), req.command())
        return BaseResponse(data=result, message="已產生國定假日變更預覽")
    except Exception as error:
        raise internal_query_error("holiday_preview_internal_error", "國定假日預覽失敗。", "holiday-preview") from error
    finally:
        connection.close()

@router.post("/apply", response_model=BaseResponse[Dict[str, Any]])
def apply_holiday_change(
    req: HolidayApplyRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    connection = get_connection()
    try:
        result = holiday_maintenance.apply(AdminCommandRepository(connection), req.command(), req.preview_fingerprint, idempotency_key, principal.username, req.reason)
        invalidate_holiday_query_cache()
        return BaseResponse(data=result, message="已套用國定假日變更")
    except ValueError as error:
        connection.rollback()
        code = str(error)
        raise HTTPException(status_code=409 if code in {"stale_preview", "idempotency_key_conflict"} else 404 if code == "holiday_not_found" else 422, detail={"code": code}) from error
    except Exception as error:
        connection.rollback()
        raise internal_query_error("holiday_apply_internal_error", "國定假日套用失敗。", "holiday-apply") from error
    finally:
        connection.close()
