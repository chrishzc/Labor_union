"""
File: data_browser_admin.py
Description: 提供 legacy table 管理與六來源 masked Data Browser query。
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from api.dependencies.admin_auth import require_system_admin
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.data_browser import (
    DataBrowserTableResponse,
    DataBrowserMaskedPageView,
)
from infrastructure.mysql import mysql_adapter as db_service
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.data_browser_query_repository import (
    DataBrowserQueryRepository,
    DataBrowserSourceNotFound,
)
from subsystems.access import data_browser_maintenance
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/admin/data-browser", tags=["Admin Data Browser"])
_ERROR_RESPONSES = {
    401: {"model": GlobalTypedErrorResponseView},
    403: {"model": GlobalTypedErrorResponseView},
    404: {"model": GlobalTypedErrorResponseView},
    422: {"model": GlobalTypedErrorResponseView},
    500: {"model": GlobalTypedErrorResponseView},
}


@router.get(
    "/sources/{source_id}",
    response_model=BaseResponse[DataBrowserMaskedPageView],
    responses=_ERROR_RESPONSES,
)
def get_masked_data_browser_source(
    source_id: str = Path(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$"),
    limit: int = Query(25, ge=1, le=100),
    after: str | None = Query(None, min_length=1, max_length=191),
    query: str | None = Query(None, max_length=100),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Return a bounded server-masked page for one canonical source."""
    del principal
    connection = get_connection()
    try:
        page = data_browser_maintenance.query_masked_data_browser_source(
            DataBrowserQueryRepository(connection),
            source_id,
            limit=limit,
            after=after,
            query=query,
        )
        return BaseResponse(
            data=DataBrowserMaskedPageView.model_validate(page),
            message="成功取得去敏資料來源",
        )
    except DataBrowserSourceNotFound as error:
        raise typed_http_error(
            404,
            "not_found",
            "source_not_found",
            "找不到核准的資料來源。",
            f"data-browser-source:{source_id}",
        ) from error
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            str(error) or "data_browser_query_invalid",
            "資料瀏覽查詢參數或資料未通過驗證。",
            f"data-browser-source:{source_id}",
        ) from error
    except HTTPException:
        raise
    except Exception as error:
        raise internal_query_error(
            "data_browser_query_internal_error",
            "資料來源查詢失敗。",
            f"data-browser-source:{source_id}",
        ) from error
    finally:
        connection.close()

@router.get("/{table}", response_model=BaseResponse[DataBrowserTableResponse])
def get_data_browser_table(
    table: str = Path(..., description="資料表名稱"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """取得資料表動態主鍵、資料列、欄位清單與權限 SSOT"""
    try:
        data = data_browser_maintenance.get_data_browser_table_schema(
            table,
            data_reader=db_service.get_table_data,
            columns_reader=db_service.get_table_columns,
            primary_keys=db_service.TABLE_PRIMARY_KEYS,
        )
        return BaseResponse(data=data, message=f"成功取得資料表 {table} 中繼資料與權限 SSOT")
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as error:
        raise internal_query_error(
            "data_browser_query_internal_error",
            "資料表查詢失敗。",
            "data-browser-query",
        ) from error


@router.patch("/{table}/{row_id_str}", response_model=BaseResponse[bool])
def patch_data_browser_row(
    table: str = Path(..., description="資料表名稱"),
    row_id_str: str = Path(..., description="列識別碼 (支援整數 ID 與字串主鍵 case_no)"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    raise HTTPException(status_code=410, detail={"code": "data_browser_write_retired", "table": table, "row_id": row_id_str, "replacement": "Use the owning Domain typed Preview/Apply command."})


@router.post("/{table}/{row_id}/source-correction/preview")
def preview_source_correction(
    table: str,
    row_id: int,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "data_browser_write_retired",
            "table": table,
            "row_id": row_id,
            "replacement": "Use the owning Domain typed Preview/Apply command.",
        },
    )


@router.post("/{table}/{row_id}/source-correction/apply")
def apply_source_correction(
    table: str,
    row_id: int,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "data_browser_write_retired",
            "table": table,
            "row_id": row_id,
            "replacement": "Use the owning Domain typed Preview/Apply command.",
        },
    )
