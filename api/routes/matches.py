"""
================================================================================
檔案名稱: api/routes/matches.py
功能說明: 訂單媒合 API，管理月嫂推薦、意願回覆、訂單資訊通知、履歷傳送與定案指派
================================================================================
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Literal
from subsystems.scheduling.matching_plan_workflow import create_matching_plan_version
from subsystems.scheduling.matching_communication_workflow import (
    cancel_matching_plan,
    get_active_matching_plan_state,
    get_matching_plan_contact_state,
    record_matching_plan_willingness,
    send_matching_plan_information,
    send_matching_plan_resumes,
)
from api.dependencies.admin_auth import require_system_admin
from api.schemas.base import BaseResponse
from api.error_contracts import internal_query_error
from api.schemas.matches import MatchReplyRequest, MatchAssignRequest
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.matching_recommendation_application import (
    query_matching_recommendations,
)

router = APIRouter(prefix="/api/v1", tags=["Matches 案件配對與 LINE 訊息推播"])


class MatchingPlanEventIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(..., min_length=1, max_length=100)
    actor: str = Field(..., min_length=1, max_length=100)


class MatchingPlanInformationRequest(MatchingPlanEventIdentity):
    info_type: Literal[1, 2]


class MatchingPlanWillingnessRequest(MatchingPlanEventIdentity):
    willingness: Literal["pending", "willing", "unwilling"]


class MatchingPlanResumeRequest(MatchingPlanEventIdentity):
    note: str = Field(..., min_length=1, max_length=1000)


class MatchingPlanCancellationRequest(MatchingPlanEventIdentity):
    reason: str = Field(..., min_length=1, max_length=255)


def _require_matching_actor(principal: AdminPrincipal, actor: str) -> None:
    if str(principal.username or "").strip() != actor.strip():
        raise HTTPException(status_code=403, detail="actor does not match authenticated principal")


@router.get(
    "/orders/{case_no}/matching-plans/{plan_id}/contact-state",
    response_model=BaseResponse[Dict[str, Any]],
)
def get_matching_plan_contact_state_route(
    case_no: str,
    plan_id: int,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    try:
        return BaseResponse(
            data=get_matching_plan_contact_state(case_no, plan_id),
            message="成功讀取配對聯繫與意願狀態",
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/orders/{case_no}/matching-plans/active",
    response_model=BaseResponse[Dict[str, Any]],
)
def get_active_matching_plan_state_route(
    case_no: str,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    try:
        return BaseResponse(
            data=get_active_matching_plan_state(case_no),
            message="成功讀取目前有效配對方案",
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/information",
    response_model=BaseResponse[Dict[str, Any]],
)
def send_matching_plan_information_route(
    req: MatchingPlanInformationRequest,
    case_no: str,
    plan_id: int,
    segment_id: int,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    _require_matching_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=send_matching_plan_information(
                case_no, plan_id, segment_id, req.info_type, req.event_key, req.actor
            ),
            message=f"訂單資訊-{req.info_type} 已建立可靠發送任務",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put(
    "/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/willingness",
    response_model=BaseResponse[Dict[str, Any]],
)
def record_matching_plan_willingness_route(
    req: MatchingPlanWillingnessRequest,
    case_no: str,
    plan_id: int,
    segment_id: int,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    _require_matching_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=record_matching_plan_willingness(
                case_no,
                plan_id,
                segment_id,
                req.willingness,
                req.event_key,
                req.actor,
            ),
            message="成功更新月嫂意願",
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/orders/{case_no}/matching-plans/{plan_id}/resumes",
    response_model=BaseResponse[Dict[str, Any]],
)
def send_matching_plan_resumes_route(
    req: MatchingPlanResumeRequest,
    case_no: str,
    plan_id: int,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    _require_matching_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=send_matching_plan_resumes(
                case_no, plan_id, req.note, req.event_key, req.actor
            ),
            message="已逐位建立履歷與備註的可靠發送任務",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/orders/{case_no}/matching-plans/{plan_id}/cancel",
    response_model=BaseResponse[Dict[str, Any]],
)
def cancel_matching_plan_route(
    req: MatchingPlanCancellationRequest,
    case_no: str,
    plan_id: int,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    _require_matching_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=cancel_matching_plan(
                case_no, plan_id, req.event_key, req.actor, req.reason
            ),
            message="已取消目前配對組合並保留歷史",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/orders/{case_no}/matching-plans",
    response_model=BaseResponse[Dict[str, Any]],
)
def create_matching_plan_version_route(
    case_no: str = Path(..., description="案件編號"),
    segments: List[Dict[str, Any]] = Body(...),
    created_by: str = Body(...),
    as_of: str = Body(...),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """建立或冪等取得正式多月嫂配對計畫版本。"""
    _require_matching_actor(principal, created_by)
    try:
        result = create_matching_plan_version(
            case_no=case_no,
            segments=segments,
            created_by=str(principal.username or "").strip(),
            as_of=as_of,
        )
        return BaseResponse(data=result, message="成功建立多月嫂配對計畫版本")
    except ValueError as error:
        message = str(error)
        if message == "case not found":
            status_code = 404
        elif message in {
            "case is not in negotiation stage",
            "case is not editable while an accepted plan exists",
            "case has an active availability lock",
        }:
            status_code = 409
        else:
            status_code = 422
        raise HTTPException(status_code=status_code, detail=message) from error
    except Exception:
        raise HTTPException(status_code=500, detail="建立多月嫂配對計畫版本失敗")


@router.get("/matches/recommend-staff", response_model=BaseResponse[list[dict]])


def recommend_staff(
    case_no: str,
    filter_region: bool = True,
    filter_schedule: bool = True,
    filter_babies: bool = True,
    filter_time: bool = True,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """智慧粗篩比對月嫂推薦引擎 API (比對 clients.city/address 與檔期 7 天預留備用期)"""
    del principal
    try:
        data = query_matching_recommendations(
            case_no=case_no,
            filter_region=filter_region,
            filter_schedule=filter_schedule,
            filter_babies=filter_babies,
            filter_time=filter_time
        )
        return BaseResponse(data=data, message="成功計算月嫂智慧粗篩推薦名單")
    except Exception as error:
        raise internal_query_error(
            "matching_recommendation_query_internal_error",
            "月嫂推薦名單查詢失敗。",
            "matching-recommendation-query",
        ) from error

@router.post("/matches/{match_id}/send-info-1", response_model=BaseResponse[Dict[str, Any]])
def send_info_1(
    match_id: int = Path(..., description="配對紀錄 ID"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; reliable information delivery is matching-plan owned."""
    del principal
    _raise_legacy_matching_gone(match_id)

@router.post("/matches/{match_id}/send-info-2", response_model=BaseResponse[Dict[str, Any]])
def send_info_2(
    match_id: int = Path(..., description="配對紀錄 ID"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; reliable information delivery is matching-plan owned."""
    del principal
    _raise_legacy_matching_gone(match_id)

@router.put("/matches/{match_id}/reply", response_model=BaseResponse[bool])
def reply_matching_inquiry(
    req: MatchReplyRequest,
    match_id: int = Path(..., description="配對紀錄 ID"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; willingness is matching-plan-segment owned."""
    del req, principal
    _raise_legacy_matching_gone(match_id)

@router.post("/matches/{match_id}/send-resume", response_model=BaseResponse[bool])
def send_resume_to_client(
    match_id: int = Path(..., description="配對紀錄 ID"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; reliable resume delivery is matching-plan owned."""
    del principal
    _raise_legacy_matching_gone(match_id)


@router.post("/orders/{case_no}/send-resume", response_model=BaseResponse[Dict[str, Any]])
def send_resume_for_case(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; anomaly recovery must navigate to the matching plan."""
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_case_resume_writer_retired",
            "case_no": case_no,
            "replacement": "Matching Plan resumes endpoint",
        },
    )


def _raise_legacy_matching_gone(match_id):
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_matching_writer_retired",
            "match_id": match_id,
            "replacement": "Matching Plan communication endpoints",
        },
    )

@router.post("/orders/{case_no}/assign-staff", response_model=BaseResponse[bool])
def assign_staff_to_order(
    req: MatchAssignRequest,
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; formal staffing requires Assignment Plan Preview and Apply."""
    del req, principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_single_staff_assignment_endpoint_retired",
            "case_no": case_no,
            "replacement": "Assignment Plan Query/Preview/Apply",
        },
    )
