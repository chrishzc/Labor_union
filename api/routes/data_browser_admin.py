"""
================================================================================
檔案名稱: api/routes/data_browser_admin.py
功能說明: 資料庫原始資料中繼權限查詢與單列微調稽核 API 路由 (DataBrowserAdminRouter)
================================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from api.dependencies.admin_auth import require_system_admin
from api.error_contracts import internal_query_error
from api.schemas.base import BaseResponse
from api.schemas.data_browser import DataBrowserPatchRequest, DataBrowserTableResponse
from subsystems.access import data_browser_maintenance
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
    req: DataBrowserPatchRequest,
    table: str = Path(..., description="資料表名稱"),
    row_id_str: str = Path(..., description="列識別碼 (支援整數 ID 與字串主鍵 case_no)"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """更新單列微調資料，支援動態主鍵型別，並寫入異動稽核紀錄"""
    try:
        success = data_browser_maintenance.patch_data_browser_table_row(
            table_name=table,
            row_id=row_id_str,
            updates=req.updates,
            operator_id=principal.username,
            operator_role=principal.role,
        )
        return BaseResponse(data=success, message=f"成功更新資料表 {table} 之資料列 {row_id_str}")
    except ValueError as ve:
        status_code = _http_status_for_data_browser_admin_error(str(ve))
        raise HTTPException(status_code=status_code, detail=str(ve))
    except Exception as error:
        raise internal_query_error(
            "data_browser_patch_internal_error",
            "資料列更新失敗。",
            "data-browser-patch",
        ) from error
