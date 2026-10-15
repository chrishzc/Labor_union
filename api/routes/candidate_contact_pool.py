"""File: candidate_contact_pool.py
Description: 提供候選聯繫池 API 路由與 typed schema 邊界。
"""

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies.admin_auth import (
    require_line_matching_override,
    require_line_matching_reader,
    require_line_matching_sender,
)
from api.dependencies.service_date_confirmation import get_service_date_confirmation_workflow
from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationWorkflow
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalErrorCategory, GlobalTypedErrorView
from api.schemas.candidate_contact_pool import (
    AddCandidatesRequest,
    CandidateInformationPreviewView,
    CandidateWeeklyServicePreviewView,
    CandidateWeeklyServiceDatesPreviewRequest,
    AddCandidatesResult,
    CandidateContactPoolView,
    CandidateWillingnessRequest,
    CandidateWillingnessResult,
    ManualCandidateInformationApplyRequest,
    ManualCandidateInformationPreview,
    ManualCandidateInformationPreviewRequest,
    ManualCandidateInformationReceipt,
    SendCandidateInformationRequest,
    SendCandidateInformationResult,
    CaseInformationPreviewView,
    CaseWeeklyServicePreviewView,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling import candidate_contact_pool_workflow as workflow
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.segmented_availability_repository import MySqlSegmentedAvailabilityFactsRepository


workflow.get_connection = get_connection
workflow.segmented_facts_port = MySqlSegmentedAvailabilityFactsRepository(get_connection)

router = APIRouter(prefix="/api/v1", tags=["Matches Candidate Contact Pool"])


def _require_actor(principal: AdminPrincipal, actor: str) -> None:
    if str(principal.username or "").strip() != actor.strip():
        raise HTTPException(status_code=403, detail="actor does not match authenticated principal")


def _information_error(error: ValueError) -> HTTPException:
    # Translate only known sending failures; the Global boundary sanitizes unknown errors.
    messages = {
        "caregiver_has_no_line_delivery_identity": (
            GlobalErrorCategory.DOMAIN_BLOCKED,
            "月嫂尚未完成 LINE 綁定，無法寄送資訊。請先完成月嫂的 LINE 綁定後，再重新寄送。",
        ),
        "candidate_information_preview_stale": (
            GlobalErrorCategory.CONFLICT,
            "訂單內容或月嫂的 LINE 綁定資料已更新。請取消本次寄送，重新開啟寄送確認後再寄送。",
        ),
        "candidate_contact_order_not_negotiating": (
            GlobalErrorCategory.DOMAIN_BLOCKED,
            "本案目前已非洽談中，不能再寄送候選詢問資訊。請重新讀取案件進度。",
        ),
        "candidate_contact_not_found": (
            GlobalErrorCategory.DOMAIN_BLOCKED,
            "這位月嫂已不在本案可寄送的候選清單。請重新讀取候選清單後再操作。",
        ),
        "candidate_weekly_service_dates_not_ready": (
            GlobalErrorCategory.DOMAIN_BLOCKED,
            "每週服務日期尚未保存，或日期與約定服務天數不符。請先確認並保存預計日期後再寄送。",
        ),
        "candidate_information_idempotency_conflict": (
            GlobalErrorCategory.IDEMPOTENCY_MISMATCH,
            "本次寄送與原寄送操作不一致。請先確認原寄送結果，避免重複寄送。",
        ),
    }
    code = str(error)
    if code not in messages:
        return HTTPException(status_code=409, detail=code)
    category, message = messages[code]
    view = GlobalTypedErrorView(
        category=category, code=code, message=message, field_errors=[],
        domain_blockers=[code] if category == GlobalErrorCategory.DOMAIN_BLOCKED else [],
        retryable=False, correlation_id="", current_version=None,
    )
    return HTTPException(status_code=409, detail={"error": view.model_dump(mode="json")})


@router.get("/orders/{case_no}/candidate-contact-pool/information/preview", response_model=BaseResponse[CaseInformationPreviewView])
def preview_case_information(case_no: str, info_type: int, principal: AdminPrincipal = Depends(require_line_matching_reader)):
    del principal
    try:
        return BaseResponse(data=CaseInformationPreviewView.model_validate(workflow.preview_case_information(case_no, info_type)), message="已讀取訂單共用資訊")
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/orders/{case_no}/candidate-contact-pool/weekly-service/preview", response_model=BaseResponse[CaseWeeklyServicePreviewView])
def preview_case_weekly_service(case_no: str, principal: AdminPrincipal = Depends(require_line_matching_reader)):
    del principal
    try:
        return BaseResponse(data=CaseWeeklyServicePreviewView.model_validate(workflow.preview_case_weekly_service(case_no)), message="已讀取共用每週服務說明")
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/orders/{case_no}/candidate-contact-pool/weekly-service/preview", response_model=BaseResponse[CaseWeeklyServicePreviewView])
def preview_case_weekly_dates(case_no: str, req: CandidateWeeklyServiceDatesPreviewRequest,
                             principal: AdminPrincipal = Depends(require_line_matching_reader),
                             dates_workflow: ServiceDateConfirmationWorkflow = Depends(get_service_date_confirmation_workflow)):
    del principal
    try:
        proposed = dates_workflow.preview(case_no, tuple(req.service_dates))
        return BaseResponse(data=CaseWeeklyServicePreviewView.model_validate(workflow.preview_case_weekly_service(case_no, proposed.candidate.service_dates)), message="已試算共用每週服務說明，尚未保存")
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/orders/{case_no}/candidate-contact-pool",
    response_model=BaseResponse[CandidateContactPoolView],
)
def query_candidate_contact_pool(case_no: str, principal: AdminPrincipal = Depends(require_line_matching_reader)):
    del principal
    return BaseResponse(
        data=CandidateContactPoolView.model_validate(workflow.query_pool(case_no)),
        message="成功讀取候選聯繫池",
    )


@router.post(
    "/orders/{case_no}/candidate-contact-pool/candidates",
    response_model=BaseResponse[AddCandidatesResult],
)
def add_candidate_contact_pool_entries(case_no: str, req: AddCandidatesRequest, principal: AdminPrincipal = Depends(require_line_matching_sender)):
    _require_actor(principal, req.actor)
    try:
        result = workflow.add_candidates(
            case_no,
            [item.model_dump(mode="json") for item in req.candidates],
            req.actor,
            req.event_key,
        )
        return BaseResponse(
            data=AddCandidatesResult.model_validate(result),
            message="候選月嫂已加入聯繫池",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information/preview",
    response_model=BaseResponse[CandidateInformationPreviewView],
)
def preview_candidate_information(case_no: str, candidate_id: int, info_type: int,
                                  principal: AdminPrincipal = Depends(require_line_matching_sender)):
    del principal
    try:
        return BaseResponse(data=CandidateInformationPreviewView.model_validate(
            workflow.preview_information(case_no, candidate_id, info_type)), message="已讀取寄送內容")
    except ValueError as error:
        raise _information_error(error) from error


@router.get(
    "/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/weekly-service/preview",
    response_model=BaseResponse[CandidateWeeklyServicePreviewView],
)
def preview_candidate_weekly_service(
    case_no: str,
    candidate_id: int,
    principal: AdminPrincipal = Depends(require_line_matching_reader),
):
    del principal
    try:
        return BaseResponse(
            data=CandidateWeeklyServicePreviewView.model_validate(
                workflow.preview_weekly_service(case_no, candidate_id)
            ),
            message="已讀取每周服務中說明",
        )
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/weekly-service/preview",
    response_model=BaseResponse[CandidateWeeklyServicePreviewView],
)
def preview_candidate_weekly_dates(
    case_no: str, candidate_id: int, req: CandidateWeeklyServiceDatesPreviewRequest,
    principal: AdminPrincipal = Depends(require_line_matching_reader),
    dates_workflow: ServiceDateConfirmationWorkflow = Depends(get_service_date_confirmation_workflow),
):
    del principal
    try:
        proposed = dates_workflow.preview(case_no, tuple(req.service_dates))
        return BaseResponse(
            data=CandidateWeeklyServicePreviewView.model_validate(
                workflow.preview_weekly_service(case_no, candidate_id, proposed.candidate.service_dates)
            ), message="已試算每週服務時間，尚未保存日期",
        )
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information",
    response_model=BaseResponse[SendCandidateInformationResult],
)
def send_candidate_information(case_no: str, candidate_id: int, req: SendCandidateInformationRequest, principal: AdminPrincipal = Depends(require_line_matching_sender)):
    _require_actor(principal, req.actor)
    try:
        result = workflow.send_information(
            case_no, candidate_id, req.info_type, req.actor, req.event_key, req.preview_fingerprint
        )
        return BaseResponse(
            data=SendCandidateInformationResult.model_validate(result),
            message=f"候選月嫂的訂單資訊-{req.info_type} 已建立可靠發送任務",
        )
    except ValueError as error:
        raise _information_error(error) from error


@router.post(
    "/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information/manual-confirmation/preview",
    response_model=BaseResponse[ManualCandidateInformationPreview],
)
def preview_manual_candidate_information_confirmation(
    case_no: str,
    candidate_id: int,
    req: ManualCandidateInformationPreviewRequest,
    principal: AdminPrincipal = Depends(require_line_matching_override),
):
    _require_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=ManualCandidateInformationPreview.model_validate(
                workflow.preview_manual_information_confirmation(
                    case_no,
                    candidate_id,
                    req.info_type,
                    req.confirmation_method,
                    req.reason,
                    req.actor,
                )
            ),
            message="已預覽候選月嫂資訊人工確認",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information/manual-confirmation",
    response_model=BaseResponse[ManualCandidateInformationReceipt],
)
def apply_manual_candidate_information_confirmation(
    case_no: str,
    candidate_id: int,
    req: ManualCandidateInformationApplyRequest,
    principal: AdminPrincipal = Depends(require_line_matching_override),
):
    _require_actor(principal, req.actor)
    try:
        return BaseResponse(
            data=ManualCandidateInformationReceipt.model_validate(
                workflow.apply_manual_information_confirmation(
                    case_no,
                    candidate_id,
                    req.info_type,
                    req.confirmation_method,
                    req.reason,
                    req.actor,
                    req.expected_version,
                    req.preview_fingerprint,
                    req.event_key,
                )
            ),
            message="候選月嫂資訊人工確認已留存",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put(
    "/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/willingness",
    response_model=BaseResponse[CandidateWillingnessResult],
)
def record_candidate_willingness(case_no: str, candidate_id: int, req: CandidateWillingnessRequest, principal: AdminPrincipal = Depends(require_line_matching_override)):
    _require_actor(principal, req.actor)
    try:
        result = workflow.record_willingness(
            case_no,
            candidate_id,
            req.willingness,
            req.reason,
            req.actor,
            req.event_key,
        )
        return BaseResponse(
            data=CandidateWillingnessResult.model_validate(result),
            message="候選月嫂意願已更新",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
