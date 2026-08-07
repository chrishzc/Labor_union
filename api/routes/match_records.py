"""
================================================================================
檔案名稱: api/routes/match_records.py
功能說明: 案件與月嫂媒合紀錄 API 路由 (MatchRecordRouter)
================================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from typing import Dict, Any, List
from api.schemas.base import BaseResponse
from api.error_contracts import internal_query_error
from api.schemas.matches import MatchCreateRequest
from api.dependencies.admin_auth import require_system_admin
from subsystems.scheduling import match_record_query
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/orders", tags=["Match Records 媒合紀錄"])

@router.get("/{case_no}/matches", response_model=BaseResponse[List[Dict[str, Any]]])
def get_order_matches(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """查詢案件之全量媒合紀錄"""
    del principal
    try:
        data = match_record_query.get_order_match_records(case_no)
        return BaseResponse(data=data, message="成功取得案件媒合紀錄")
    except Exception as error:
        raise internal_query_error(
            "legacy_match_history_query_internal_error",
            "媒合歷史查詢失敗。",
            "legacy-match-history-query",
        ) from error

@router.post("/{case_no}/matches", response_model=BaseResponse[Dict[str, Any]])
def create_or_get_match_record(
    req: MatchCreateRequest,
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; new matching history is matching-plan owned."""
    del req, principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_match_record_writer_retired",
            "case_no": case_no,
            "replacement": "Matching Plan create/contact-state endpoints",
        },
    )
