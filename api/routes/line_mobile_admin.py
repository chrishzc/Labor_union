"""LINE 綁定工會人員的 LIFF 手機管理端點。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.dependencies.line_identity import get_liff_token_verifier, get_line_identity_review_application
from api.dependencies.line_runtime import publish_line_wakeup_best_effort
from api.schemas.base import BaseResponse
from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus, CustomerServiceTransitionError
from domains.line.identities import LineReviewRequestId
from domains.line.review import LineReviewDecision, LineReviewStatus, LineReviewType
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError, LiffVerificationUnavailableError
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.customer_service.application import (
    CustomerServiceApplication,
    CustomerServiceTicketNotFoundError,
    CustomerServiceVersionConflictError,
)
from subsystems.customer_service.contracts import CustomerServiceListQuery, ReplyCustomerServiceTicket
from subsystems.line.capabilities import LineCapability
from subsystems.line.identity_review_application import LineReviewDataConflictError, LineReviewNotFoundError
from subsystems.line.review_contracts import DecideLineReviewCommand, LineReviewListQuery


router = APIRouter(prefix="/api/v1/line/mobile-admin", tags=["LINE Mobile Admin"])
page_router = APIRouter(tags=["LINE Mobile Admin"])
_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "mobile_admin.html"


class _LiffAuthRequest(BaseModel):
    line_id_token: str = Field(min_length=1, max_length=4096)


class _CustomerServiceListRequest(_LiffAuthRequest):
    status: CustomerServiceStatus | None = CustomerServiceStatus.WAITING
    category: CustomerServiceCategory | None = None
    search: str | None = Field(default=None, max_length=191)


class _CustomerServiceReplyRequest(_LiffAuthRequest):
    reply_text: str = Field(min_length=1, max_length=2000)
    resolve: bool = False
    internal_note: str | None = Field(default=None, max_length=4000)
    expected_version: int = Field(ge=0)
    idempotency_key: str | None = Field(default=None, max_length=191)


class _ReviewListRequest(_LiffAuthRequest):
    review_status: LineReviewStatus | None = LineReviewStatus.PENDING
    review_type: LineReviewType | None = LineReviewType.STAFF_VERIFICATION


class _ReviewDecisionRequest(_LiffAuthRequest):
    decision: LineReviewDecision
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str | None = Field(default=None, max_length=191)


@page_router.get("/line-mobile-admin", include_in_schema=False)
def mobile_admin_page():
    return FileResponse(_PAGE)


@router.post("/profile", response_model=BaseResponse[dict])
def profile(payload: _LiffAuthRequest):
    admin = _linked_admin(payload.line_id_token)
    return BaseResponse(data=_admin_view(admin))


@router.post("/customer-service/summary", response_model=BaseResponse[dict])
def customer_service_summary(payload: _LiffAuthRequest):
    actor = _mobile_admin_actor(payload.line_id_token)
    return BaseResponse(data={**CustomerServiceApplication(open_line_unit_of_work).summary(), "actor": actor.actor_id})


@router.post("/customer-service/tickets", response_model=BaseResponse[dict])
def customer_service_tickets(payload: _CustomerServiceListRequest):
    _mobile_admin_actor(payload.line_id_token)
    page = CustomerServiceApplication(open_line_unit_of_work).list(
        CustomerServiceListQuery(payload.status, payload.category, payload.search, 1, 50)
    )
    return BaseResponse(data=page)


@router.post("/customer-service/tickets/{ticket_id}", response_model=BaseResponse[dict])
def customer_service_detail(ticket_id: int, payload: _LiffAuthRequest):
    _mobile_admin_actor(payload.line_id_token)
    try:
        detail = CustomerServiceApplication(open_line_unit_of_work).detail(ticket_id)
    except CustomerServiceTicketNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return BaseResponse(data=detail)


@router.post("/customer-service/tickets/{ticket_id}/reply", response_model=BaseResponse[dict])
def customer_service_reply(ticket_id: int, payload: _CustomerServiceReplyRequest):
    admin = _linked_admin(payload.line_id_token)
    actor = _actor_for_admin(admin)
    command = ReplyCustomerServiceTicket(
        ticket_id,
        payload.reply_text,
        payload.resolve,
        payload.internal_note,
        ExpectedVersion(payload.expected_version),
        actor.actor_id,
        admin.admin_user_id,
        IdempotencyKey(payload.idempotency_key or f"mobile-cs-reply:{uuid4()}"),
        CorrelationId(f"mobile-customer-service:{uuid4()}"),
    )
    try:
        detail = CustomerServiceApplication(open_line_unit_of_work).reply(command)
    except CustomerServiceTicketNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (CustomerServiceVersionConflictError, CustomerServiceTransitionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    publish_line_wakeup_best_effort()
    return BaseResponse(data=detail, message="已記錄回覆並排入 LINE 傳送")


@router.post("/identity-reviews", response_model=BaseResponse[dict])
def identity_reviews(payload: _ReviewListRequest):
    _mobile_admin_actor(payload.line_id_token)
    page = get_line_identity_review_application().list(
        LineReviewListQuery(
            statuses=(payload.review_status,) if payload.review_status else (),
            review_types=(payload.review_type,) if payload.review_type else (),
            page_size=50,
        )
    )
    return BaseResponse(data={"items": [_review_view(item) for item in page.items], "next_cursor": page.next_cursor})


@router.post("/identity-reviews/{request_id}/decision", response_model=BaseResponse[dict])
def identity_review_decision(request_id: int, payload: _ReviewDecisionRequest):
    actor = _mobile_admin_actor(payload.line_id_token)
    command = DecideLineReviewCommand(
        LineReviewRequestId(request_id),
        payload.decision,
        ExpectedVersion(payload.expected_version),
        actor,
        payload.reason,
        IdempotencyKey(payload.idempotency_key or f"mobile-review:{request_id}:{uuid4()}"),
        CorrelationId(f"mobile-line-review:{uuid4()}"),
    )
    try:
        result = get_line_identity_review_application().decide(command)
    except LineReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (LineReviewDataConflictError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    publish_line_wakeup_best_effort()
    return BaseResponse(data=_review_view(result.snapshot), message="審核結果已保存")


def _mobile_admin_actor(line_id_token: str) -> ActorContext:
    return _actor_for_admin(_linked_admin(line_id_token))


def _actor_for_admin(admin) -> ActorContext:
    # The approved Access policy treats every enabled internal user alike.
    # Identity review requires this scope inside its owning application.
    return ActorContext(f"admin:{admin.admin_user_id}", (LineCapability.IDENTITY_REVIEW.value,))


def _linked_admin(line_id_token: str):
    try:
        line_user_id = get_liff_token_verifier().verify(line_id_token).line_user_id
    except InvalidLiffTokenError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except LiffVerificationUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    with open_line_unit_of_work() as unit_of_work:
        admin = unit_of_work.admins.get_linked_admin(line_user_id)
    if admin is None:
        raise HTTPException(status_code=403, detail="此 LINE 尚未綁定工會人員身分")
    return admin


def _admin_view(admin) -> dict:
    return {
        "admin_user_id": admin.admin_user_id,
        "display_name": admin.display_name,
        "role": admin.role,
    }


def _review_view(snapshot) -> dict:
    return {
        "request_id": snapshot.request_id.value,
        "review_type": snapshot.review_type.value,
        "status": snapshot.status.value,
        "version": snapshot.version.value,
        "subject_type": snapshot.subject_type.value if snapshot.subject_type else None,
        "subject_reference": snapshot.subject_reference,
        "line_user_id_masked": _mask(snapshot.line_user_id.value if snapshot.line_user_id else ""),
        "display_name": f"{snapshot.subject_type.value} #{snapshot.subject_reference}" if snapshot.subject_type else "未指定",
        "decision_reason": snapshot.decision_reason,
        "reviewed_by_actor_id": snapshot.reviewed_by_actor_id,
        "reviewed_at": snapshot.reviewed_at,
        "created_at": snapshot.created_at,
    }


def _mask(value: str) -> str:
    return value[:4] + "…" + value[-4:] if len(value) > 8 else value


__all__ = ["router", "page_router"]
