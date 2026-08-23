"""
================================================================================
檔案名稱: api/routes/matches.py
功能說明: 訂單媒合 API，管理月嫂推薦、意願回覆、訂單資訊通知、履歷傳送與定案指派
================================================================================
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Literal
from subsystems.scheduling.matching_plan_workflow import create_matching_plan_version
from subsystems.scheduling.matching_communication_workflow import (
    cancel_matching_plan,
    get_active_matching_plan_state,
)
from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_matching_override,
    require_line_matching_reader,
    require_line_matching_sender,
    require_system_admin,
)
from api.schemas.base import BaseResponse
from api.error_contracts import internal_query_error
from api.schemas.matches import MatchReplyRequest, MatchAssignRequest
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.matching_recommendation_application import (
    query_matching_recommendations,
)
from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingNotificationKind,
    MatchingPlanReference,
)
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling.matching_notification_application import (
    MatchingNotificationApplication,
)
from subsystems.scheduling.matching_notification_contracts import (
    RecordManualMatchingResponseCommand,
    RequestCaregiverInformationCommand,
    RequestCustomerProfilesCommand,
)

router = APIRouter(prefix="/api/v1", tags=["Matches 案件配對與 LINE 訊息推播"])
matching_notifications = MatchingNotificationApplication(
    open_line_unit_of_work,
    lambda: datetime.now(timezone.utc),
)


class MatchingPlanEventIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(..., min_length=1, max_length=100)
    actor: str = Field(..., min_length=1, max_length=100)


class MatchingPlanInformationRequest(MatchingPlanEventIdentity):
    info_type: Literal[1, 2]
    expected_version: int = Field(..., ge=0)


class MatchingPlanWillingnessRequest(MatchingPlanEventIdentity):
    willingness: Literal["willing", "unwilling"]
    expected_version: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1, max_length=500)


class MatchingPlanResumeRequest(MatchingPlanEventIdentity):
    note: str = Field(..., min_length=1, max_length=1000)
    expected_version: int = Field(..., ge=0)


class MatchingPlanCustomerDecisionRequest(MatchingPlanEventIdentity):
    decision: Literal["accepted", "declined", "contact_requested"]
    expected_version: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1, max_length=500)


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
    principal: AdminPrincipal = Depends(require_line_matching_reader),
):
    try:
        state = matching_notifications.get_contact_state(
            admin_actor_context(principal),
            case_no,
            plan_id,
        )
        return BaseResponse(
            data=_contact_state_data(state),
            message="成功讀取配對聯繫與意願狀態",
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/orders/{case_no}/matching-plans/active",
    response_model=BaseResponse[Dict[str, Any]],
)
def get_active_matching_plan_state_route(
    case_no: str,
    principal: AdminPrincipal = Depends(require_line_matching_reader),
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
    principal: AdminPrincipal = Depends(require_line_matching_sender),
):
    _require_matching_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=_notification_data(
                matching_notifications.request_caregiver_information(
                    RequestCaregiverInformationCommand(
                        MatchingPlanReference(case_no, plan_id, req.expected_version),
                        segment_id,
                        MatchingNotificationKind(f"caregiver_info_{req.info_type}"),
                        admin_actor_context(principal),
                        ExpectedVersion(req.expected_version),
                        IdempotencyKey(req.event_key),
                        CorrelationId(f"matching-api:{req.event_key}"),
                    )
                )
            ),
            message=f"訂單資訊-{req.info_type} 已建立可靠發送任務",
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put(
    "/orders/{case_no}/matching-plans/{plan_id}/customer-decision",
    response_model=BaseResponse[Dict[str, Any]],
)
def record_matching_customer_decision_route(
    req: MatchingPlanCustomerDecisionRequest,
    case_no: str,
    plan_id: int,
    principal: AdminPrincipal = Depends(require_line_matching_override),
):
    _require_matching_actor(principal, req.actor)
    try:
        result = matching_notifications.record_manual_response(
            RecordManualMatchingResponseCommand(
                MatchingPlanReference(case_no, plan_id, req.expected_version),
                None,
                None,
                CustomerMatchingDecision(req.decision),
                req.reason,
                admin_actor_context(principal),
                ExpectedVersion(req.expected_version),
                IdempotencyKey(req.event_key),
                CorrelationId(f"matching-api:{req.event_key}"),
            )
        )
        return BaseResponse(data=_response_data(result), message="成功補登客戶配對決策")
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
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
    principal: AdminPrincipal = Depends(require_line_matching_override),
):
    _require_matching_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=_response_data(
                matching_notifications.record_manual_response(
                    RecordManualMatchingResponseCommand(
                        MatchingPlanReference(case_no, plan_id, req.expected_version),
                        segment_id,
                        CaregiverWillingness(req.willingness),
                        None,
                        req.reason,
                        admin_actor_context(principal),
                        ExpectedVersion(req.expected_version),
                        IdempotencyKey(req.event_key),
                        CorrelationId(f"matching-api:{req.event_key}"),
                    )
                )
            ),
            message="成功更新月嫂意願",
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/orders/{case_no}/matching-plans/{plan_id}/resumes",
    response_model=BaseResponse[Dict[str, Any]],
)
def send_matching_plan_resumes_route(
    req: MatchingPlanResumeRequest,
    case_no: str,
    plan_id: int,
    principal: AdminPrincipal = Depends(require_line_matching_sender),
):
    _require_matching_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=_notification_data(
                matching_notifications.request_customer_profiles(
                    RequestCustomerProfilesCommand(
                        MatchingPlanReference(case_no, plan_id, req.expected_version),
                        req.note,
                        admin_actor_context(principal),
                        ExpectedVersion(req.expected_version),
                        IdempotencyKey(req.event_key),
                        CorrelationId(f"matching-api:{req.event_key}"),
                    )
                )
            ),
            message="已建立客戶月嫂小卡與確認按鈕的可靠發送任務",
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
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
    case_no: str = Query(..., min_length=1, max_length=50, description="案件編號"),
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


def _contact_state_data(state) -> dict[str, Any]:
    return {
        "plan": {
            "id": state.plan.plan_id,
            "case_no": state.plan.case_no,
            "communication_version": state.plan.version,
            "status": state.plan_status,
            "is_active": 1 if state.plan_is_active else None,
        },
        "segments": [_segment_state_data(segment) for segment in state.segments],
        "all_willing": state.all_willing,
        "customer_decision": state.customer_decision.value,
        "customer_profiles_status": (
            state.customer_profiles_status.value
            if state.customer_profiles_status else None
        ),
    }


def _segment_state_data(segment) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "segment_order": segment.segment_order,
        "staff_id": segment.staff_id,
        "staff_name": segment.staff_name,
        "assigned_start_date": segment.assigned_start_date,
        "assigned_end_date": segment.assigned_end_date,
        "willingness": segment.willingness.value,
        "info_1_status": (
            segment.information_1_status.value if segment.information_1_status else None
        ),
        "info_2_status": (
            segment.information_2_status.value if segment.information_2_status else None
        ),
    }


def _notification_data(result) -> dict[str, Any]:
    return {
        "intent_id": result.intent_id,
        "line_delivery_task_id": (
            result.line_delivery_task_id.value
            if result.line_delivery_task_id else None
        ),
        "delivery_status": result.projection_status.value,
        "notification_kind": result.notification_kind.value,
    }


def _response_data(result) -> dict[str, Any]:
    return {
        "event_id": result.event_id,
        "communication_version": result.plan.version,
        "source": result.source.value,
        "willingness": (
            result.caregiver_willingness.value
            if result.caregiver_willingness else None
        ),
        "customer_decision": (
            result.customer_decision.value if result.customer_decision else None
        ),
    }


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
