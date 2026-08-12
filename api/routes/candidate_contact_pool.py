"""Candidate-contact pool endpoints."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_matching_override,
    require_line_matching_reader,
    require_line_matching_sender,
)
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling import candidate_contact_pool_workflow as workflow

router = APIRouter(prefix="/api/v1", tags=["Matches Candidate Contact Pool"])


class _EventIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=100)
    event_key: str = Field(min_length=1, max_length=100)


class CandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_id: int = Field(gt=0)
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)


class AddCandidatesRequest(_EventIdentity):
    candidates: list[CandidateInput] = Field(min_length=1, max_length=50)


class SendCandidateInformationRequest(_EventIdentity):
    info_type: Literal[1, 2]


class CandidateWillingnessRequest(_EventIdentity):
    willingness: Literal["willing", "unwilling"]
    reason: str = Field(default="", max_length=500)


def _require_actor(principal: AdminPrincipal, actor: str) -> None:
    if str(principal.username or "").strip() != actor.strip():
        raise HTTPException(status_code=403, detail="actor does not match authenticated principal")


@router.get("/orders/{case_no}/candidate-contact-pool", response_model=BaseResponse[dict])
def query_candidate_contact_pool(case_no: str, principal: AdminPrincipal = Depends(require_line_matching_reader)):
    del principal
    return BaseResponse(data=workflow.query_pool(case_no), message="成功讀取候選聯繫池")


@router.post("/orders/{case_no}/candidate-contact-pool/candidates", response_model=BaseResponse[dict])
def add_candidate_contact_pool_entries(case_no: str, req: AddCandidatesRequest, principal: AdminPrincipal = Depends(require_line_matching_sender)):
    _require_actor(principal, req.actor)
    try:
        return BaseResponse(data=workflow.add_candidates(case_no, [item.model_dump() for item in req.candidates], req.actor, req.event_key), message="候選月嫂已加入聯繫池")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information", response_model=BaseResponse[dict])
def send_candidate_information(case_no: str, candidate_id: int, req: SendCandidateInformationRequest, principal: AdminPrincipal = Depends(require_line_matching_sender)):
    _require_actor(principal, req.actor)
    try:
        return BaseResponse(data=workflow.send_information(case_no, candidate_id, req.info_type, req.actor, req.event_key), message=f"候選月嫂的訂單資訊-{req.info_type} 已建立可靠發送任務")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/willingness", response_model=BaseResponse[dict])
def record_candidate_willingness(case_no: str, candidate_id: int, req: CandidateWillingnessRequest, principal: AdminPrincipal = Depends(require_line_matching_override)):
    _require_actor(principal, req.actor)
    try:
        return BaseResponse(data=workflow.record_willingness(case_no, candidate_id, req.willingness, req.reason, req.actor, req.event_key), message="候選月嫂意願已更新")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
