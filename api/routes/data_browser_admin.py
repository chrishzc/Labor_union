"""
================================================================================
檔案名稱: api/routes/data_browser_admin.py
功能說明: 資料庫原始資料中繼權限查詢與單列微調稽核 API 路由 (DataBrowserAdminRouter)
================================================================================
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from api.dependencies.admin_auth import require_system_admin
from api.error_contracts import internal_query_error
from api.schemas.base import BaseResponse
from api.schemas.data_browser import (
    DataBrowserSourceCorrectionApplyRequest,
    DataBrowserSourceCorrectionPreviewRequest,
    DataBrowserTableResponse,
)
from infrastructure.mysql.admin_command_repository import AdminCommandRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.access import data_browser_maintenance
from subsystems.access import source_data_correction
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/admin/data-browser", tags=["Admin Data Browser"])

@router.get("/{table}", response_model=BaseResponse[DataBrowserTableResponse])
def get_data_browser_table(
    table: str = Path(..., description="資料表名稱"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """取得資料表動態主鍵、資料列、欄位清單與權限 SSOT"""
    try:
        data = data_browser_maintenance.get_data_browser_table_schema(table)
        return BaseResponse(data=data, message=f"成功取得資料表 {table} 中繼資料與權限 SSOT")
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as error:
        raise internal_query_error(
            "data_browser_query_internal_error",
            "資料表查詢失敗。",
            "data-browser-query",
        ) from error


def _http_status_for_data_browser_admin_error(error_message: str) -> int:
    if "不存在" in error_message:
        return 404
    return 422


@router.patch("/{table}/{row_id_str}", response_model=BaseResponse[bool])
def patch_data_browser_row(
    table: str = Path(..., description="資料表名稱"),
    row_id_str: str = Path(..., description="列識別碼 (支援整數 ID 與字串主鍵 case_no)"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    raise HTTPException(status_code=410, detail={"code": "data_browser_write_retired", "table": table, "row_id": row_id_str, "replacement": "Use the owning Domain typed Preview/Apply command."})


@router.post("/{table}/{row_id}/source-correction/preview", response_model=BaseResponse[dict])
def preview_source_correction(
    table: str,
    row_id: int,
    request: DataBrowserSourceCorrectionPreviewRequest,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    connection = get_connection()
    try:
        return BaseResponse(data=source_data_correction.preview(AdminCommandRepository(connection), table, row_id, request.updates))
    except ValueError as error:
        raise HTTPException(status_code=_http_status_for_data_browser_admin_error(str(error)), detail=str(error))
    finally:
        connection.close()


@router.post("/{table}/{row_id}/source-correction/apply", response_model=BaseResponse[dict])
def apply_source_correction(
    table: str,
    row_id: int,
    request: DataBrowserSourceCorrectionApplyRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    connection = get_connection()
    try:
        result = source_data_correction.apply(
            AdminCommandRepository(connection), table, row_id, request.updates,
            request.preview_fingerprint, idempotency_key, principal.username, request.reason,
        )
        return BaseResponse(data=result)
    except ValueError as error:
        connection.rollback()
        raise HTTPException(status_code=_http_status_for_data_browser_admin_error(str(error)), detail=str(error))
    finally:
        connection.close()
