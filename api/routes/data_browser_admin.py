"""
File: data_browser_admin.py
Description: 提供 bounded 唯讀 Data Browser archive query，不提供原始資料表入口。
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from api.dependencies.admin_auth import require_system_admin
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.data_browser import DataBrowserPageView
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
    response_model=BaseResponse[DataBrowserPageView],
    responses=_ERROR_RESPONSES,
)
def get_data_browser_source(
    source_id: str = Path(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$"),
    limit: int = Query(25, ge=1, le=100),
    after: str | None = Query(None, min_length=1, max_length=191),
    query: str | None = Query(None, max_length=100),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Return a bounded server-canonical page for one canonical source."""
    del principal
    connection = get_connection()
    try:
        page = data_browser_maintenance.query_data_browser_source(
            DataBrowserQueryRepository(connection),
            source_id,
            limit=limit,
            after=after,
            query=query,
        )
        return BaseResponse(
            data=DataBrowserPageView.model_validate(page),
            message="成功取得資料來源",
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
