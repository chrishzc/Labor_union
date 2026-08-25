"""File: candidate_contact_pool.py
Description: 提供候選聯繫池 API 路由與 typed schema 邊界。
"""

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies.admin_auth import (
    require_line_matching_override,
    require_line_matching_reader,
    require_line_matching_sender,
)
from api.schemas.base import BaseResponse
from api.schemas.candidate_contact_pool import (
    AddCandidatesRequest,
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
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling import candidate_contact_pool_workflow as workflow

router = APIRouter(prefix="/api/v1", tags=["Matches Candidate Contact Pool"])


def _require_actor(principal: AdminPrincipal, actor: str) -> None:
    if str(principal.username or "").strip() != actor.strip():
        raise HTTPException(status_code=403, detail="actor does not match authenticated principal")


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


@router.post(
    "/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information",
    response_model=BaseResponse[SendCandidateInformationResult],
)
def send_candidate_information(case_no: str, candidate_id: int, req: SendCandidateInformationRequest, principal: AdminPrincipal = Depends(require_line_matching_sender)):
    _require_actor(principal, req.actor)
    try:
        result = workflow.send_information(
            case_no, candidate_id, req.info_type, req.actor, req.event_key
        )
        return BaseResponse(
            data=SendCandidateInformationResult.model_validate(result),
            message=f"候選月嫂的訂單資訊-{req.info_type} 已建立可靠發送任務",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


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
