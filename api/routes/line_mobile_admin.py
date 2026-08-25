"""
File: line_mobile_admin.py
Description: 提供已綁定工會人員的 LIFF 客服回覆與身分審核 Preview／Apply 端點。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.line_identity import get_liff_token_verifier, get_line_identity_review_application
from api.dependencies.line_runtime import publish_line_wakeup_best_effort
from api.error_contracts import typed_http_error
from api.routes.customer_service import _call_update_endpoint
from api.schemas.base import BaseResponse
from api.schemas.customer_service import (
    CustomerServiceDetailView,
    CustomerServicePageView,
    CustomerServiceReplyApplyView,
    CustomerServiceReplyPreviewView,
    CustomerServiceSummaryView,
)
from api.schemas.line_identity import (
    CanonicalLineReviewDecisionPreviewResponse,
    CanonicalLineReviewPageResponse,
    CanonicalLineReviewResponse,
)
from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus
from domains.line.identities import LineReviewRequestId
from domains.line.review import LineReviewDecision, LineReviewStatus, LineReviewType
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError, LiffVerificationUnavailableError
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.customer_service.application import (
    CustomerServiceApplication,
    CustomerServiceTicketNotFoundError,
)
from subsystems.customer_service.contracts import (
    ApplyCustomerServiceTicketReply,
    CustomerServiceListQuery,
    PreviewCustomerServiceTicketReply,
)
from subsystems.line.capabilities import LineCapability
from subsystems.line.identity_review_application import LineReviewDataConflictError, LineReviewNotFoundError
from subsystems.line.review_contracts import (
    DecideLineReviewCommand,
    LineReviewListQuery,
    PreviewLineReviewDecisionCommand,
)


router = APIRouter(prefix="/api/v1/line/mobile-admin", tags=["LINE Mobile Admin"])
page_router = APIRouter(tags=["LINE Mobile Admin"])
_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "mobile_admin.html"


class _LiffAuthRequest(BaseModel):
    line_id_token: str = Field(min_length=1, max_length=4096)


class _CustomerServiceListRequest(_LiffAuthRequest):
    status: CustomerServiceStatus | None = CustomerServiceStatus.WAITING
    category: CustomerServiceCategory | None = None
    search: str | None = Field(default=None, max_length=191)
    page: int = Field(default=1, ge=1, le=100)


class _CustomerServiceReplyPreviewRequest(_LiffAuthRequest):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    reply_text: str = Field(min_length=1, max_length=2000)
    resolve: bool
    internal_note: str | None = Field(max_length=4000)
    expected_version: int = Field(ge=0)


class _CustomerServiceReplyApplyRequest(_CustomerServiceReplyPreviewRequest):
    idempotency_key: str = Field(min_length=1, max_length=191)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class _ReviewListRequest(_LiffAuthRequest):
    review_status: LineReviewStatus | None = LineReviewStatus.PENDING
    review_type: LineReviewType | None = LineReviewType.STAFF_VERIFICATION
    cursor: str | None = Field(default=None, min_length=1, max_length=191)


class _ReviewDecisionPreviewRequest(_LiffAuthRequest):
    decision: LineReviewDecision
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class _ReviewDecisionRequest(_ReviewDecisionPreviewRequest):
    idempotency_key: str | None = Field(default=None, max_length=191)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class _MobileAdminProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    admin_user_id: int = Field(gt=0)
    display_name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)


@page_router.get("/line-mobile-admin", include_in_schema=False)
def mobile_admin_page():
    return FileResponse(_PAGE)


@router.post("/profile", response_model=BaseResponse[_MobileAdminProfileView])
def profile(payload: _LiffAuthRequest):
    admin = _linked_admin(payload.line_id_token)
    return BaseResponse(data=_admin_view(admin))


@router.post("/customer-service/summary", response_model=BaseResponse[CustomerServiceSummaryView])
def customer_service_summary(payload: _LiffAuthRequest):
    _mobile_admin_actor(payload.line_id_token)
    return BaseResponse(data=CustomerServiceApplication(open_line_unit_of_work).summary())


@router.post("/customer-service/tickets", response_model=BaseResponse[CustomerServicePageView])
def customer_service_tickets(payload: _CustomerServiceListRequest):
    _mobile_admin_actor(payload.line_id_token)
    page = CustomerServiceApplication(open_line_unit_of_work).list(
        CustomerServiceListQuery(
            status=payload.status,
            category=payload.category,
            search=payload.search,
            page=payload.page,
            page_size=50,
        )
    )
    return BaseResponse(data=page)


@router.post("/customer-service/tickets/{ticket_id}", response_model=BaseResponse[CustomerServiceDetailView])
def customer_service_detail(ticket_id: int, payload: _LiffAuthRequest):
    _mobile_admin_actor(payload.line_id_token)
    try:
        detail = CustomerServiceApplication(open_line_unit_of_work).detail(ticket_id)
    except CustomerServiceTicketNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return BaseResponse(data=detail)


@router.post(
    "/customer-service/tickets/{ticket_id}/reply/preview",
    response_model=BaseResponse[CustomerServiceReplyPreviewView],
)
def customer_service_reply_preview(
    ticket_id: int,
    payload: _CustomerServiceReplyPreviewRequest,
):
    _mobile_admin_actor(payload.line_id_token)
    identity = CorrelationId(f"mobile-customer-service-reply-preview:{uuid4()}")
    command = PreviewCustomerServiceTicketReply(
        ticket_id,
        payload.reply_text,
        payload.resolve,
        payload.internal_note,
        ExpectedVersion(payload.expected_version),
        identity,
    )
    preview = _call_update_endpoint(
        CustomerServiceApplication(open_line_unit_of_work).preview_reply,
        command,
        correlation_id=identity,
        error_scope="reply",
    )
    return BaseResponse(
        data=CustomerServiceReplyPreviewView(
            ticket_id=preview.ticket_id,
            before_status=preview.before_status,
            after_status=preview.after_status,
            current_version=preview.current_version,
            expected_version=preview.expected_version,
            reply_character_count=preview.reply_character_count,
            will_enqueue_delivery=preview.will_enqueue_delivery,
            preview_fingerprint=preview.preview_fingerprint.value,
            apply_ready=preview.apply_ready,
        ),
        message="客服回覆 Preview 已建立；尚未寫入或排入傳送",
    )


@router.post(
    "/customer-service/tickets/{ticket_id}/reply/apply",
    response_model=BaseResponse[CustomerServiceReplyApplyView],
)
def customer_service_reply_apply(
    ticket_id: int,
    payload: _CustomerServiceReplyApplyRequest,
):
    admin = _linked_admin(payload.line_id_token)
    actor = _actor_for_admin(admin)
    identity = CorrelationId(f"mobile-customer-service-reply-apply:{uuid4()}")
    command = ApplyCustomerServiceTicketReply(
        ticket_id,
        payload.reply_text,
        payload.resolve,
        payload.internal_note,
        ExpectedVersion(payload.expected_version),
        PreviewFingerprint(payload.preview_fingerprint),
        actor.actor_id,
        admin.admin_user_id,
        IdempotencyKey(payload.idempotency_key),
        identity,
    )
    result = _call_update_endpoint(
        CustomerServiceApplication(open_line_unit_of_work).apply_reply,
        command,
        correlation_id=identity,
        error_scope="reply",
    )
    publish_line_wakeup_best_effort()
    return BaseResponse(
        data=CustomerServiceReplyApplyView(
            ticket_id=result.ticket_id,
            resulting_status=result.resulting_status,
            resulting_version=result.resulting_version,
            preview_fingerprint=result.preview_fingerprint.value,
            delivery_enqueued=result.delivery_enqueued,
            delivery_delivered=result.delivery_delivered,
            replayed=result.replayed,
            readback=result.readback,
        ),
        message="客服回覆已保存；LINE delivery 已排入佇列，尚未送達",
    )


@router.post("/customer-service/tickets/{ticket_id}/reply", include_in_schema=False)
def retired_customer_service_reply(ticket_id: int):
    del ticket_id
    raise HTTPException(
        status_code=410,
        detail={
            "code": "customer_service_reply_preview_required",
            "message": "此回覆入口已退役，請先預覽再套用。",
            "retryable": False,
        },
    )


@router.post("/identity-reviews", response_model=BaseResponse[CanonicalLineReviewPageResponse])
def identity_reviews(payload: _ReviewListRequest):
    _mobile_admin_actor(payload.line_id_token)
    page = get_line_identity_review_application().list(
        LineReviewListQuery(
            statuses=(payload.review_status,) if payload.review_status else (),
            review_types=(payload.review_type,) if payload.review_type else (),
            page_size=50,
            cursor=payload.cursor,
        )
    )
    return BaseResponse(data={"items": [_review_view(item) for item in page.items], "next_cursor": page.next_cursor})


@router.post(
    "/identity-reviews/{request_id}/decision/preview",
    response_model=BaseResponse[CanonicalLineReviewDecisionPreviewResponse],
)
def identity_review_decision_preview(
    request_id: int,
    payload: _ReviewDecisionPreviewRequest,
):
    actor = _mobile_admin_actor(payload.line_id_token)
    command = PreviewLineReviewDecisionCommand(
        LineReviewRequestId(request_id),
        payload.decision,
        ExpectedVersion(payload.expected_version),
        actor,
        payload.reason,
    )
    try:
        result = get_line_identity_review_application().preview(command)
    except LineReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    candidate = result.candidate
    snapshot = result.snapshot
    return BaseResponse(
        data={
            "request_id": snapshot.request_id.value,
            "decision": payload.decision.value,
            "before_status": candidate.before_status.value,
            "after_status": candidate.after_status.value,
            "expected_version": candidate.expected_version.value,
            "resulting_version": candidate.resulting_version.value,
            "subject_type": snapshot.subject_type.value if snapshot.subject_type else None,
            "subject_reference": snapshot.subject_reference,
            "line_user_id_masked": _mask(snapshot.line_user_id.value if snapshot.line_user_id else ""),
            "preview_fingerprint": candidate.fingerprint.value,
        }
    )


@router.post(
    "/identity-reviews/{request_id}/decision/apply",
    response_model=BaseResponse[CanonicalLineReviewResponse],
)
def identity_review_decision(request_id: int, payload: _ReviewDecisionRequest):
    actor = _mobile_admin_actor(payload.line_id_token)
    command = DecideLineReviewCommand(
        LineReviewRequestId(request_id),
        payload.decision,
        ExpectedVersion(payload.expected_version),
        actor,
        payload.reason,
        PreviewFingerprint(payload.preview_fingerprint),
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
    return BaseResponse(
        data=_review_view(
            result.snapshot,
            outcome=result.outcome.value,
            receipt_identity=(
                f"line-review:{result.snapshot.request_id.value}:"
                f"{result.snapshot.status.value}"
            ),
        ),
        message="審核結果已保存；通知已排入可靠佇列，尚未證明送達",
    )


@router.post("/identity-reviews/{request_id}/decision", include_in_schema=False)
def retired_mobile_identity_review_decision(
    request_id: int,
    payload: _ReviewDecisionPreviewRequest,
):
    del request_id, payload
    raise HTTPException(
        status_code=410,
        detail={
            "code": "line_review_preview_required",
            "message": "此審核入口已退役，請先預覽再套用。",
            "retryable": False,
        },
    )


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
        raise typed_http_error(
            401,
            "forbidden",
            "liff_token_invalid",
            "LINE 登入狀態已失效或與此 LIFF 不一致，請重新登入 LINE。",
            "line-mobile-admin:liff-token-invalid",
        ) from error
    except LiffVerificationUnavailableError as error:
        raise typed_http_error(
            503,
            "unavailable",
            "liff_verification_unavailable",
            "LINE 身分驗證服務暫時無法連線，請稍後再試。",
            "line-mobile-admin:liff-verification-unavailable",
            retryable=True,
        ) from error
    with open_line_unit_of_work() as unit_of_work:
        admin = unit_of_work.admins.get_linked_admin(line_user_id)
    if admin is None:
        raise typed_http_error(
            403,
            "forbidden",
            "line_admin_binding_not_found",
            "此 LINE 尚未綁定工會人員身分。",
            "line-mobile-admin:binding",
        )
    return admin


def _admin_view(admin) -> dict:
    return {
        "admin_user_id": admin.admin_user_id,
        "display_name": admin.display_name,
        "role": admin.role,
    }


def _review_view(snapshot, *, outcome=None, receipt_identity=None) -> dict:
    return {
        "request_id": snapshot.request_id.value,
        "review_type": snapshot.review_type.value,
        "status": snapshot.status.value,
        "version": snapshot.version.value,
        "subject_type": snapshot.subject_type.value if snapshot.subject_type else None,
        "subject_reference": snapshot.subject_reference,
        "assigned_admin_id": None,
        "due_at": None,
        "line_user_id_masked": _mask(snapshot.line_user_id.value if snapshot.line_user_id else ""),
        "display_name": f"{snapshot.subject_type.value} #{snapshot.subject_reference}" if snapshot.subject_type else "未指定",
        "decision_reason": snapshot.decision_reason,
        "reviewed_by_actor_id": snapshot.reviewed_by_actor_id,
        "reviewed_at": snapshot.reviewed_at,
        "created_at": snapshot.created_at,
        "outcome": outcome,
        "receipt_identity": receipt_identity,
    }


def _mask(value: str) -> str:
    return value[:4] + "…" + value[-4:] if len(value) > 8 else value


__all__ = ["router", "page_router"]
