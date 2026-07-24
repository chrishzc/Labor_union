"""Authenticated LINE identity and rebind review management APIs."""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies.admin_auth import require_line_agent, require_line_manager
from api.schemas.base import BaseResponse
from api.schemas.line_reviews import LineReviewDecisionRequest
from line.worker import wake_worker
from services.admin_auth_service import AdminPrincipal
from services.line_review_service import (
    LineReviewDataConflictError,
    LineReviewNotFoundError,
    LineReviewStateConflictError,
    approve_line_review,
    get_line_review,
    get_line_review_summary,
    list_line_reviews,
    reject_line_review,
)


router = APIRouter(
    prefix="/api/v1/line/review-requests",
    tags=["LINE Reviews"],
    dependencies=[Depends(require_line_agent)],
)


def _raise_review_error(exc: Exception) -> NoReturn:
    if isinstance(exc, LineReviewNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (LineReviewStateConflictError, LineReviewDataConflictError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def _set_review_audit(request: Request, *, result: dict, reason: str) -> None:
    action = "approve" if result["status"] == "approved" else "reject"
    request.state.audit_action = f"line.review.{action}"
    request.state.audit_resource_type = "line_confirmation_request"
    request.state.audit_resource_id = str(result["request_id"])
    request.state.audit_details = {
        "request_type": result["request_type"],
        "reason": reason.strip(),
    }


@router.get("/summary", response_model=BaseResponse[dict])
def review_summary():
    return BaseResponse(data=get_line_review_summary())


@router.get("", response_model=BaseResponse[dict])
def review_list(
    request_type: str | None = None,
    status: str | None = "pending",
    search: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    try:
        result = list_line_reviews(
            request_type=request_type,
            status=status,
            search=search,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        _raise_review_error(exc)
    return BaseResponse(data=result)


@router.get("/{request_id}", response_model=BaseResponse[dict])
def review_detail(request_id: int):
    try:
        result = get_line_review(request_id)
    except LineReviewNotFoundError as exc:
        _raise_review_error(exc)
    return BaseResponse(data=result)


@router.post(
    "/{request_id}/approve",
    response_model=BaseResponse[dict],
    dependencies=[Depends(require_line_manager)],
)
def approve_review(
    request_id: int,
    payload: LineReviewDecisionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_manager),
):
    try:
        result = approve_line_review(
            request_id,
            admin_user_id=principal.id,
            reviewer_line_user_id=principal.linked_line_user_id,
            reason=payload.reason,
        )
    except (LineReviewNotFoundError, LineReviewStateConflictError, LineReviewDataConflictError, ValueError) as exc:
        _raise_review_error(exc)
    _set_review_audit(request, result=result, reason=payload.reason)
    wake_worker()
    return BaseResponse(data=result, message=result["message"])


@router.post(
    "/{request_id}/reject",
    response_model=BaseResponse[dict],
    dependencies=[Depends(require_line_manager)],
)
def reject_review(
    request_id: int,
    payload: LineReviewDecisionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_manager),
):
    try:
        result = reject_line_review(
            request_id,
            admin_user_id=principal.id,
            reviewer_line_user_id=principal.linked_line_user_id,
            reason=payload.reason,
        )
    except (LineReviewNotFoundError, LineReviewStateConflictError, LineReviewDataConflictError, ValueError) as exc:
        _raise_review_error(exc)
    _set_review_audit(request, result=result, reason=payload.reason)
    wake_worker()
    return BaseResponse(data=result, message=result["message"])
