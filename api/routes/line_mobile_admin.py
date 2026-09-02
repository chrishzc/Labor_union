"""
File: line_mobile_admin.py
Description: 提供已綁定工會人員的 LIFF 客服、排班與身分審核 Preview／Apply 端點。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import (
    admin_actor_context,
    has_required_capability,
    require_persisted_admin,
)
from api.dependencies.line_identity import (
    get_liff_token_verifier,
    get_line_identity_management_application,
    get_line_identity_review_application,
)
from api.dependencies.line_runtime import publish_line_wakeup_best_effort
from api.dependencies.assignment_plan import (
    AssignmentPlanApplication,
    get_assignment_plan_application,
)
from api.error_contracts import typed_http_error
from api.routes.assignment_plan import (
    AssignmentPlanSegmentInput,
    _call_endpoint as _call_assignment_plan_endpoint,
    _materialize,
    _preview_assignment,
    _query_payload,
)
from api.routes.customer_service import _call_update_endpoint
from api.schemas.assignment_plan import (
    AssignmentPlanQueryView,
    AssignmentPlanReceiptView,
    AssignmentPlanSegmentView,
)
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
    CanonicalLineReviewNumberedPageResponse,
    CanonicalLineReviewResponse,
)
from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus
from domains.line.identities import LineReviewRequestId, LineUserId
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from domains.line.review import LineReviewDecision, LineReviewStatus, LineReviewType
from domains.scheduling.assignment_plan import AssignmentPlanIntent
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError, LiffVerificationUnavailableError
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
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
from subsystems.line.identity_management_application import LineIdentityManagementApplication
from subsystems.line.identity_management_contracts import LineIdentityCurrentFactReadbackStatus
from subsystems.line.review_contracts import (
    DecideLineReviewCommand,
    LineReviewListQuery,
    PreviewLineReviewDecisionCommand,
)
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanApplyRequest,
    AssignmentPlanPreviewRequest,
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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    review_status: LineReviewStatus | None = LineReviewStatus.PENDING
    review_type: LineReviewType | None = LineReviewType.STAFF_VERIFICATION
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=100)


class _ReviewDecisionPreviewRequest(_LiffAuthRequest):
    decision: LineReviewDecision
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class _ReviewDecisionRequest(_ReviewDecisionPreviewRequest):
    idempotency_key: str | None = Field(default=None, max_length=191)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class _SchedulingReviewQueryRequest(_LiffAuthRequest):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    case_no: str = Field(min_length=1, max_length=50)


class _SchedulingReviewPreviewRequest(_LiffAuthRequest):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    case_no: str = Field(min_length=1, max_length=50)
    segments: list[AssignmentPlanSegmentInput] = Field(min_length=1, max_length=4)


class _SchedulingReviewApplyRequest(_SchedulingReviewPreviewRequest):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    expected_client_finance_version: int = Field(ge=0)
    expected_payroll_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    reason: str = Field(min_length=1, max_length=500)


class _SchedulingReviewApplyView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    receipt: AssignmentPlanReceiptView
    readback: AssignmentPlanQueryView


class _SchedulingReviewPreviewView(BaseModel):
    """Closed mobile projection of the Scheduling preview contract."""

    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    cancelled_assignment_ids: list[int]
    assignments: list[AssignmentPlanSegmentView]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class _MobileAdminProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    admin_user_id: int = Field(gt=0)
    display_name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)


@page_router.get("/line-mobile-admin", include_in_schema=False)
def mobile_admin_page():
    return FileResponse(_PAGE, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


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


@router.post("/identity-reviews", response_model=BaseResponse[CanonicalLineReviewNumberedPageResponse])
def identity_reviews(payload: _ReviewListRequest):
    _mobile_admin_actor(payload.line_id_token)
    page = get_line_identity_review_application().list(
        LineReviewListQuery(
            statuses=(payload.review_status,) if payload.review_status else (),
            review_types=(payload.review_type,) if payload.review_type else (),
            page_size=payload.page_size,
            page=payload.page,
        )
    )
    if page.page != payload.page or page.page_size != payload.page_size or page.total is None:
        raise RuntimeError("line_review_numbered_page_contract_invalid")
    return BaseResponse(
        data=CanonicalLineReviewNumberedPageResponse(
            items=[_review_view(item) for item in page.items],
            page=page.page,
            page_size=page.page_size,
            total=page.total,
        )
    )


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


@router.post(
    "/scheduling-review/query",
    response_model=BaseResponse[AssignmentPlanQueryView],
)
def scheduling_review_query(
    payload: _SchedulingReviewQueryRequest,
    application: AssignmentPlanApplication = Depends(get_assignment_plan_application),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    identity_management: LineIdentityManagementApplication = Depends(get_line_identity_management_application),
):
    _scheduling_mobile_actor(payload.line_id_token, principal, identity_management)
    correlation = CorrelationId(f"mobile-scheduling-review-query:{payload.case_no}")
    return _call_assignment_plan_endpoint(
        lambda: AssignmentPlanQueryView.model_validate(
            _query_payload(application.query(payload.case_no))
        ),
        "成功取得目前正式排班",
        correlation,
    )


@router.post(
    "/scheduling-review/preview",
    response_model=BaseResponse[_SchedulingReviewPreviewView],
)
def scheduling_review_preview(
    payload: _SchedulingReviewPreviewRequest,
    application: AssignmentPlanApplication = Depends(get_assignment_plan_application),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    identity_management: LineIdentityManagementApplication = Depends(get_line_identity_management_application),
):
    _scheduling_mobile_actor(payload.line_id_token, principal, identity_management)
    correlation = CorrelationId(f"mobile-scheduling-review-preview:{uuid4()}")
    request = AssignmentPlanPreviewRequest(
        payload.case_no,
        AssignmentPlanIntent(tuple(segment.to_domain() for segment in payload.segments)),
        correlation,
    )
    return _call_assignment_plan_endpoint(
        lambda: _SchedulingReviewPreviewView.model_validate(
            _scheduling_review_preview_payload(application.preview(request))
        ),
        "成功產生正式排班預覽",
        correlation,
    )


@router.post(
    "/scheduling-review/apply",
    response_model=BaseResponse[_SchedulingReviewApplyView],
)
def scheduling_review_apply(
    payload: _SchedulingReviewApplyRequest,
    application: AssignmentPlanApplication = Depends(get_assignment_plan_application),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    identity_management: LineIdentityManagementApplication = Depends(get_line_identity_management_application),
):
    actor = _scheduling_mobile_actor(payload.line_id_token, principal, identity_management)
    correlation = CorrelationId(f"mobile-scheduling-review-apply:{uuid4()}")
    request = AssignmentPlanApplyRequest(
        payload.case_no,
        AssignmentPlanIntent(tuple(segment.to_domain() for segment in payload.segments)),
        ExpectedVersion(payload.expected_order_version),
        ExpectedVersion(payload.expected_scheduling_version),
        ExpectedVersion(payload.expected_client_finance_version),
        ExpectedVersion(payload.expected_payroll_version),
        PreviewFingerprint(payload.preview_fingerprint),
        IdempotencyKey(payload.idempotency_key),
        actor,
        payload.reason,
        correlation,
    )
    return _call_assignment_plan_endpoint(
        lambda: _apply_scheduling_review(application, request),
        "正式排班已保存，並已重新讀回目前根事實",
        correlation,
    )


def _apply_scheduling_review(application, request):
    receipt = application.apply(request)
    readback = application.query(request.case_no)
    return _SchedulingReviewApplyView(
        receipt=AssignmentPlanReceiptView.model_validate(_materialize(receipt)),
        readback=AssignmentPlanQueryView.model_validate(_query_payload(readback)),
    )


def _scheduling_review_preview_payload(preview) -> dict:
    """Expose only the Scheduling projection needed to confirm an edit."""

    scheduling = preview.candidate.scheduling
    return {
        "case_no": scheduling.case_no,
        "order_version": preview.order_version,
        "scheduling_version": preview.scheduling_version,
        "scheduling_generation": scheduling.generation_number,
        "client_finance_version": preview.client_finance_version,
        "payroll_version": preview.payroll_version,
        "cancelled_assignment_ids": scheduling.cancelled_assignment_ids,
        "assignments": [_preview_assignment(item) for item in scheduling.assignments],
        "preview_fingerprint": preview.fingerprint.value,
    }


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


def _scheduling_mobile_actor(
    line_id_token: str,
    principal: AdminPrincipal,
    identity_management: LineIdentityManagementApplication,
) -> ActorContext:
    """Require both the persisted human Session and current role-scoped LINE fact."""

    if principal.id is None or not has_required_capability(principal, "line.review.decide"):
        raise typed_http_error(
            403,
            "forbidden",
            "scheduling_review_capability_required",
            "排班審核需要已登入且具備審核能力的內部使用者 Session。",
            "line-mobile-admin:scheduling-capability",
        )
    line_user_id = _verified_line_user_id(line_id_token)
    try:
        fact = identity_management.current_fact(line_user_id)
    except LookupError as error:
        raise typed_http_error(
            403,
            "forbidden",
            "line_admin_binding_not_found",
            "此 LINE 尚未綁定目前有效的工會人員身分。",
            "line-mobile-admin:role-scoped-binding",
        ) from error
    admin_bindings = tuple(
        binding
        for binding in fact.root_bindings
        if binding.subject_type is LineBindingSubjectType.ADMIN
    )
    if (
        fact.root_status is not LineIdentityBindingStatus.BOUND
        or fact.readback_status is not LineIdentityCurrentFactReadbackStatus.COMPLETE
        or len(admin_bindings) != 1
        or admin_bindings[0].subject_reference != str(principal.id)
    ):
        raise typed_http_error(
            403,
            "forbidden",
            "line_admin_binding_not_current",
            "LINE 工會人員身分已變更，請重新確認後再操作。",
            "line-mobile-admin:role-scoped-binding",
        )
    return admin_actor_context(principal)


def _mobile_admin_actor(line_id_token: str) -> ActorContext:
    return _actor_for_admin(_linked_admin(line_id_token))


def _verified_line_user_id(line_id_token: str) -> LineUserId:
    try:
        return get_liff_token_verifier().verify(line_id_token).line_user_id
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
