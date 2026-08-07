from fastapi import APIRouter, HTTPException, Path, Query
from typing import List, Dict, Any
from infrastructure.mysql import mysql_adapter as db_service
from api.error_contracts import internal_query_error
from api.schemas.base import BaseResponse

router = APIRouter(prefix="/api/v1/staff", tags=["Staff 服務人員/月嫂名冊"])

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_staff():
    """取得全量服務人員/月嫂名冊資料表"""
    try:
        data = db_service.get_table_data("staff")
        return BaseResponse(data=data, message="成功取得服務人員列表")
    except Exception as error:
        raise internal_query_error(
            "staff_query_internal_error",
            "服務人員名冊查詢失敗。",
            "staff-query",
        ) from error
