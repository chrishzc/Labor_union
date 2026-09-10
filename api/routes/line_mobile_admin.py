"""
File: line_mobile_admin.py
Description: 提供已綁定工會人員的 LIFF 客服、排班與身分審核 Preview／Apply 端點。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pymysql.err import OperationalError
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.anomaly_registry import get_current_issue_query_application
from api.dependencies.admin_auth import (
    admin_actor_context,
    has_required_capability,
)
from api.dependencies.client_profile import get_client_profile_application
from api.dependencies.line_identity import (
    get_liff_token_verifier,
    get_line_identity_review_application,
)
from api.dependencies.staff_leave_intake import get_staff_leave_intake_application
from api.dependencies.line_runtime import publish_line_wakeup_best_effort
from api.dependencies.operations_reports import get_weekly_operations_report_query
from api.dependencies.order_summary import (
    OrderSummaryApplication,
    get_order_summary_application,
)
from api.dependencies.assignment_plan import (
    AssignmentPlanApplication,
    get_assignment_plan_application,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.routes.assignment_plan import (
    AssignmentPlanSegmentInput,
    _call_endpoint as _call_assignment_plan_endpoint,
    _materialize,
    _preview_assignment,
    _query_payload,
)
from api.routes.customer_service import _call_update_endpoint
from api.routes import client_profile as client_profile_routes
from api.routes import staff_leave_management as staff_leave_management_routes
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
from api.schemas.client_profile import (
    ClientProfileApprovalApplyRequest,
    ClientProfileApprovalPreviewRequest,
    ClientProfileApprovalReceiptView,
    ClientProfilePreviewView,
    ClientProfileRejectPreviewRequest,
    ClientProfileRejectRequest,
    ClientProfileRequestPageView,
    ClientProfileRequestView,
)
from api.schemas.line_identity import (
    CanonicalLineReviewDecisionPreviewResponse,
    CanonicalLineReviewNumberedPageResponse,
    CanonicalLineReviewResponse,
)
from api.schemas.staff_leave_management import (
    StaffLeaveInboxItemView,
    StaffLeaveReviewReceiptView,
    StaffLeaveStatus,
)
from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus
from domains.line.identities import LineReviewRequestId, LineUserId
from domains.line.review import LineReviewDecision, LineReviewStatus, LineReviewType
from domains.orders.lifecycle import OrderLifecycleScope
from domains.scheduling.assignment_plan import AssignmentPlanIntent
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError, LiffVerificationUnavailableError
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.segmented_availability_repository import (
    MySqlSegmentedAvailabilityFactsRepository,
    SegmentedAvailabilityFactsPort,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.current_issue_query import (
    CurrentIssueListRequest,
    CurrentIssueQueryApplication,
)
from subsystems.customer_service.application import (
    CustomerServiceApplication,
    CustomerServiceTicketNotFoundError,
)
from subsystems.customer_service.contracts import (
    ApplyCustomerServiceTicketReply,
    CustomerServiceListQuery,
    PreviewCustomerServiceTicketReply,
)
from subsystems.client_profile.application import ClientProfileApplication
from subsystems.line.capabilities import LineCapability
from subsystems.line.identity_review_application import LineReviewDataConflictError, LineReviewNotFoundError
from subsystems.line.review_contracts import (
    DecideLineReviewCommand,
    LineReviewListQuery,
    PreviewLineReviewDecisionCommand,
)
from subsystems.orders.summary_query import (
    OrderSummaryContractError,
    OrderSummaryQueryRequest,
)
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanApplyRequest,
    AssignmentPlanPreviewRequest,
)
from subsystems.scheduling.staff_leave_intake_workflow import StaffLeaveIntakeApplication
from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery


router = APIRouter(prefix="/api/v1/line/mobile-admin", tags=["LINE Mobile Admin"])
page_router = APIRouter(tags=["LINE Mobile Admin"])
_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "mobile_admin.html"


class _LiffAuthRequest(BaseModel):
    line_id_token: str = Field(min_length=1, max_length=4096)


class _MobileClientProfileListRequest(_LiffAuthRequest):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    status: str | None = "pending"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class _MobileClientProfileApprovalPreviewRequest(ClientProfileApprovalPreviewRequest):
    line_id_token: str = Field(min_length=1, max_length=4096)


class _MobileClientProfileApprovalApplyRequest(ClientProfileApprovalApplyRequest):
    line_id_token: str = Field(min_length=1, max_length=4096)


class _MobileClientProfileRejectPreviewRequest(ClientProfileRejectPreviewRequest):
    line_id_token: str = Field(min_length=1, max_length=4096)


class _MobileClientProfileRejectRequest(ClientProfileRejectRequest):
    line_id_token: str = Field(min_length=1, max_length=4096)


class _MobileStaffLeaveListRequest(_LiffAuthRequest):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    status: StaffLeaveStatus = "pending"
    limit: int = Field(default=50, ge=1, le=100)


class _MobileStaffLeaveReviewRequest(_LiffAuthRequest):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    action: Literal["accept", "reject", "cancel"]
    reason: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=191)


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
    review_type: LineReviewType | None = None
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


class _SchedulingReviewOptionsRequest(_LiffAuthRequest):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    case_no: str | None = Field(default=None, min_length=1, max_length=50)
    after_case_no: str | None = Field(default=None, min_length=1, max_length=50)
    page_size: int = Field(default=200, ge=1, le=200)


class _SchedulingCaseOptionView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str
    order_status: str


class _SchedulingStaffOptionView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    staff_id: int = Field(gt=0)
    staff_name: str = Field(min_length=1)


class _SchedulingReviewOptionsView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_options: list[_SchedulingCaseOptionView]
    next_cursor: str | None = None
    selected_case_no: str | None = None
    staff_options: list[_SchedulingStaffOptionView]
    service_dates: list[date]


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


class _MobileCurrentAnomalyListRequest(_LiffAuthRequest):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    cursor: str | None = Field(default=None, min_length=1, max_length=2048)


class _MobileCurrentAnomalySummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    issue_key: str = Field(pattern=r"^ci_[0-9a-f]{64}$")
    definition_code: Literal["LINE-006"]
    severity: Literal["warning", "blocking"]
    blocking: bool
    episode_started_at: datetime
    last_verified_at: datetime


class _MobileCurrentAnomalyPageView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[_MobileCurrentAnomalySummaryView] = Field(max_length=50)
    next_cursor: str | None = Field(default=None, max_length=2048)


class _MobileOperationsCountsView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    application_count: int = Field(ge=0)
    general_eligible_count: int = Field(ge=0)
    subsidized_eligible_count: int = Field(ge=0)
    rejection_unpartitioned_count: int = Field(ge=0)
    order_established_count: int = Field(ge=0)
    incomplete_count: int = Field(ge=0)


class _MobileOperationsSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    start_date: date
    end_date: date
    generated_at: datetime
    summary: _MobileOperationsCountsView


@page_router.get("/line-mobile-admin", include_in_schema=False)
def mobile_admin_page():
    return FileResponse(_PAGE, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@router.post("/profile", response_model=BaseResponse[_MobileAdminProfileView])
def profile(
    payload: _LiffAuthRequest,
):
    principal, _ = _mobile_admin_context(payload.line_id_token)
    return BaseResponse(data=_admin_view(principal))


@router.post(
    "/client-profile/requests",
    response_model=BaseResponse[ClientProfileRequestPageView],
)
def mobile_client_profile_requests(
    payload: _MobileClientProfileListRequest,
    application: ClientProfileApplication = Depends(get_client_profile_application),
):
    principal, _ = _mobile_admin_context(
        payload.line_id_token,
        LineCapability.CUSTOMER_SERVICE_READ,
    )
    return client_profile_routes.list_requests(
        status=payload.status,
        page=payload.page,
        page_size=payload.page_size,
        _=principal,
        application=application,
    )


@router.post(
    "/client-profile/requests/{request_id}/approve/preview",
    response_model=BaseResponse[ClientProfilePreviewView],
)
def mobile_client_profile_approval_preview(
    request_id: int,
    payload: _MobileClientProfileApprovalPreviewRequest,
    application: ClientProfileApplication = Depends(get_client_profile_application),
):
    principal, _ = _mobile_admin_context(
        payload.line_id_token,
        LineCapability.CUSTOMER_SERVICE_HANDLE,
    )
    return client_profile_routes.preview_approval(
        request_id,
        ClientProfileApprovalPreviewRequest.model_validate(
            payload.model_dump(exclude={"line_id_token"})
        ),
        principal,
        application,
    )


@router.post(
    "/client-profile/requests/{request_id}/approve/apply",
    response_model=BaseResponse[ClientProfileApprovalReceiptView],
)
def mobile_client_profile_approval_apply(
    request_id: int,
    payload: _MobileClientProfileApprovalApplyRequest,
    application: ClientProfileApplication = Depends(get_client_profile_application),
):
    principal, _ = _mobile_admin_context(
        payload.line_id_token,
        LineCapability.CUSTOMER_SERVICE_HANDLE,
    )
    return client_profile_routes.apply_approval(
        request_id,
        ClientProfileApprovalApplyRequest.model_validate(
            payload.model_dump(exclude={"line_id_token"})
        ),
        principal,
        application,
    )


@router.post(
    "/client-profile/requests/{request_id}/reject/preview",
    response_model=BaseResponse[ClientProfilePreviewView],
)
def mobile_client_profile_rejection_preview(
    request_id: int,
    payload: _MobileClientProfileRejectPreviewRequest,
    application: ClientProfileApplication = Depends(get_client_profile_application),
):
    principal, _ = _mobile_admin_context(
        payload.line_id_token,
        LineCapability.CUSTOMER_SERVICE_HANDLE,
    )
    return client_profile_routes.preview_rejection(
        request_id,
        ClientProfileRejectPreviewRequest.model_validate(
            payload.model_dump(exclude={"line_id_token"})
        ),
        principal,
        application,
    )


@router.post(
    "/client-profile/requests/{request_id}/reject",
    response_model=BaseResponse[ClientProfileRequestView],
)
def mobile_client_profile_rejection_apply(
    request_id: int,
    payload: _MobileClientProfileRejectRequest,
    application: ClientProfileApplication = Depends(get_client_profile_application),
):
    principal, _ = _mobile_admin_context(
        payload.line_id_token,
        LineCapability.CUSTOMER_SERVICE_HANDLE,
    )
    return client_profile_routes.reject_request(
        request_id,
        ClientProfileRejectRequest.model_validate(
            payload.model_dump(exclude={"line_id_token"})
        ),
        principal,
        application,
    )


@router.post(
    "/staff-leave-requests",
    response_model=BaseResponse[list[StaffLeaveInboxItemView]],
)
def mobile_staff_leave_requests(payload: _MobileStaffLeaveListRequest):
    principal, _ = _mobile_admin_context(
        payload.line_id_token,
        LineCapability.REVIEW_READ,
    )
    return staff_leave_management_routes.list_staff_leave_requests(
        status=payload.status,
        limit=payload.limit,
        principal=principal,
    )


@router.post(
    "/staff-leave-requests/{request_id}/review",
    response_model=BaseResponse[StaffLeaveReviewReceiptView],
)
def mobile_staff_leave_review(
    request_id: int,
    payload: _MobileStaffLeaveReviewRequest,
    application: StaffLeaveIntakeApplication = Depends(get_staff_leave_intake_application),
):
    principal, _ = _mobile_admin_context(
        payload.line_id_token,
        LineCapability.REVIEW_DECIDE,
    )
    return staff_leave_management_routes.review_staff_leave_request(
        request_id,
        staff_leave_management_routes.ReviewBody(
            expected_version=payload.expected_version,
            action=payload.action,
            reason=payload.reason,
        ),
        payload.idempotency_key,
        principal,
        application,
    )


@router.post(
    "/current-anomalies",
    response_model=BaseResponse[_MobileCurrentAnomalyPageView],
)
def current_anomalies(
    payload: _MobileCurrentAnomalyListRequest,
    application: CurrentIssueQueryApplication = Depends(
        get_current_issue_query_application
    ),
):
    _mobile_admin_context(payload.line_id_token, LineCapability.MONITOR_READ)
    try:
        page = application.query(
            CurrentIssueListRequest(
                definition_code="LINE-006",
                limit=50,
                cursor=payload.cursor,
            )
        )
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "mobile_current_anomaly_query_invalid",
            "目前異常清單的查詢條件已失效，請重新整理。",
            "line-mobile-admin:current-anomalies",
        ) from error
    except OperationalError as error:
        raise typed_http_error(
            503,
            "unavailable",
            "mobile_current_anomaly_query_unavailable",
            "目前異常清單暫時無法查詢。",
            "line-mobile-admin:current-anomalies",
            retryable=True,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "mobile_current_anomaly_query_internal_error",
            "目前異常清單查詢失敗。",
            "line-mobile-admin:current-anomalies",
        ) from error
    return BaseResponse(
        data={
            "items": [
                {
                    "issue_key": item.issue_key,
                    "definition_code": item.definition_code,
                    "severity": item.severity,
                    "blocking": item.blocking,
                    "episode_started_at": item.episode_started_at,
                    "last_verified_at": item.last_verified_at,
                }
                for item in page.items
                if item.definition_code == "LINE-006"
            ],
            "next_cursor": page.next_cursor,
        },
        message="成功取得目前通知異常",
    )


@router.post(
    "/operations-summary",
    response_model=BaseResponse[_MobileOperationsSummaryView],
)
def operations_summary(
    payload: _LiffAuthRequest,
    query: WeeklyOperationsReportQuery = Depends(get_weekly_operations_report_query),
):
    _mobile_admin_context(payload.line_id_token)
    start_date, end_date = _current_business_week(SystemBusinessClock().today())
    try:
        report = query.query(start_date, end_date)
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "mobile_operations_summary_range_invalid",
            "本週營運摘要的期間無效。",
            "line-mobile-admin:operations-summary",
        ) from error
    except OperationalError as error:
        raise typed_http_error(
            503,
            "unavailable",
            "mobile_operations_summary_unavailable",
            "營運摘要暫時無法查詢。",
            "line-mobile-admin:operations-summary",
            retryable=True,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "mobile_operations_summary_internal_error",
            "營運摘要查詢失敗。",
            "line-mobile-admin:operations-summary",
        ) from error
    return BaseResponse(
        data={
            "start_date": report.start_date,
            "end_date": report.end_date,
            "generated_at": report.generated_at,
            "summary": {
                "application_count": report.summary.application_count,
                "general_eligible_count": report.summary.general_eligible_count,
                "subsidized_eligible_count": report.summary.subsidized_eligible_count,
                "rejection_unpartitioned_count": report.summary.rejection_unpartitioned_count,
                "order_established_count": report.summary.order_established_count,
                "incomplete_count": report.summary.incomplete_count,
            },
        },
        message="成功取得本週營運摘要",
    )


@router.post("/customer-service/summary", response_model=BaseResponse[CustomerServiceSummaryView])
def customer_service_summary(
    payload: _LiffAuthRequest,
):
    _mobile_admin_context(payload.line_id_token, LineCapability.CUSTOMER_SERVICE_READ)
    return BaseResponse(data=CustomerServiceApplication(open_line_unit_of_work).summary())


@router.post("/customer-service/tickets", response_model=BaseResponse[CustomerServicePageView])
def customer_service_tickets(
    payload: _CustomerServiceListRequest,
):
    _mobile_admin_context(payload.line_id_token, LineCapability.CUSTOMER_SERVICE_READ)
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
def customer_service_detail(
    ticket_id: int,
    payload: _LiffAuthRequest,
):
    _mobile_admin_context(payload.line_id_token, LineCapability.CUSTOMER_SERVICE_READ)
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
    _mobile_admin_context(payload.line_id_token, LineCapability.CUSTOMER_SERVICE_HANDLE)
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
    principal, actor = _mobile_admin_context(
        payload.line_id_token,
        LineCapability.CUSTOMER_SERVICE_HANDLE,
    )
    identity = CorrelationId(f"mobile-customer-service-reply-apply:{uuid4()}")
    command = ApplyCustomerServiceTicketReply(
        ticket_id,
        payload.reply_text,
        payload.resolve,
        payload.internal_note,
        ExpectedVersion(payload.expected_version),
        PreviewFingerprint(payload.preview_fingerprint),
        actor.actor_id,
        principal.id,
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
def identity_reviews(
    payload: _ReviewListRequest,
):
    _mobile_admin_context(payload.line_id_token, LineCapability.REVIEW_READ)
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
    _, actor = _mobile_admin_context(payload.line_id_token, LineCapability.REVIEW_DECIDE)
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
            "line_user_id": _mask(snapshot.line_user_id.value if snapshot.line_user_id else ""),
            "preview_fingerprint": candidate.fingerprint.value,
        }
    )


@router.post(
    "/identity-reviews/{request_id}/decision/apply",
    response_model=BaseResponse[CanonicalLineReviewResponse],
)
def identity_review_decision(
    request_id: int,
    payload: _ReviewDecisionRequest,
):
    _, actor = _mobile_admin_context(payload.line_id_token, LineCapability.REVIEW_DECIDE)
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


def _get_scheduling_review_options_facts() -> SegmentedAvailabilityFactsPort:
    return MySqlSegmentedAvailabilityFactsRepository(get_connection)


@router.post(
    "/scheduling-review/options",
    response_model=BaseResponse[_SchedulingReviewOptionsView],
)
def scheduling_review_options(
    payload: _SchedulingReviewOptionsRequest,
    orders: OrderSummaryApplication = Depends(get_order_summary_application),
    facts: SegmentedAvailabilityFactsPort = Depends(
        _get_scheduling_review_options_facts
    ),
):
    """Return bounded owner-backed options for the mobile Scheduling form."""

    _scheduling_mobile_actor(payload.line_id_token)
    try:
        page = orders.query(
            OrderSummaryQueryRequest(
                payload.page_size,
                payload.after_case_no,
                lifecycle_scope=OrderLifecycleScope.UNFINISHED,
            )
        )
        staff_options: list[_SchedulingStaffOptionView] = []
        service_dates: list[date] = []
        if payload.case_no is not None:
            selected = facts.load_case_facts(payload.case_no)
            order = selected.get("order")
            if order is None:
                raise typed_http_error(
                    404,
                    "not_found",
                    "mobile_scheduling_case_not_found",
                    "找不到所選排班案件。",
                    "line-mobile-admin:scheduling-options",
                )
            if "staff_rows" not in selected:
                raise typed_http_error(
                    409,
                    "conflict",
                    "mobile_scheduling_case_not_selectable",
                    "所選案件目前不在可調整排班狀態。",
                    "line-mobile-admin:scheduling-options",
                )
            staff_options = [
                _SchedulingStaffOptionView(
                    staff_id=int(item["id"]),
                    staff_name=str(item.get("name") or f"月嫂 {item['id']}"),
                )
                for item in selected["staff_rows"]
            ]
            service_dates = [
                item["service_date"] for item in selected["confirmed_service_dates"]
            ]
            if not service_dates:
                raise typed_http_error(
                    409,
                    "conflict",
                    "official_service_dates_incomplete",
                    "所選案件尚未建立正式服務日期，無法提供排班選項。",
                    "line-mobile-admin:scheduling-options",
                )
        return BaseResponse(
            data=_SchedulingReviewOptionsView(
                case_options=[
                    _SchedulingCaseOptionView(
                        case_no=item.case_no,
                        order_status=item.order_status,
                    )
                    for item in page.items
                ],
                next_cursor=page.next_cursor,
                selected_case_no=payload.case_no,
                staff_options=staff_options,
                service_dates=service_dates,
            ),
            message="成功取得排班下拉選項",
        )
    except HTTPException:
        raise
    except OrderSummaryContractError as error:
        raise typed_http_error(
            409,
            "conflict",
            "mobile_scheduling_options_projection_invalid",
            "排班選項的案件資料不一致，請稍後再試。",
            "line-mobile-admin:scheduling-options",
        ) from error
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "mobile_scheduling_options_invalid",
            "排班選項查詢條件不正確。",
            "line-mobile-admin:scheduling-options",
        ) from error
    except OperationalError as error:
        raise typed_http_error(
            503,
            "unavailable",
            "mobile_scheduling_options_unavailable",
            "排班選項暫時無法查詢。",
            "line-mobile-admin:scheduling-options",
            retryable=True,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "mobile_scheduling_options_internal_error",
            "排班選項查詢失敗。",
            "line-mobile-admin:scheduling-options",
        ) from error


@router.post(
    "/scheduling-review/query",
    response_model=BaseResponse[AssignmentPlanQueryView],
)
def scheduling_review_query(
    payload: _SchedulingReviewQueryRequest,
    application: AssignmentPlanApplication = Depends(get_assignment_plan_application),
):
    _scheduling_mobile_actor(payload.line_id_token)
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
):
    _scheduling_mobile_actor(payload.line_id_token)
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
):
    actor = _scheduling_mobile_actor(payload.line_id_token)
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
) -> ActorContext:
    """Resolve one current LINE-bound admin with Scheduling review capability."""

    _, actor = _mobile_admin_context(line_id_token, LineCapability.REVIEW_DECIDE)
    return actor


def _mobile_admin_context(
    line_id_token: str,
    required_capability: LineCapability | None = None,
) -> tuple[AdminPrincipal, ActorContext]:
    """Resolve an enabled Admin owner exclusively from a verified current LINE binding."""

    line_user_id = _verified_line_user_id(line_id_token)
    with open_line_unit_of_work() as unit_of_work:
        linked_admin = unit_of_work.admins.get_linked_admin(line_user_id)
    if linked_admin is None:
        raise typed_http_error(
            403,
            "forbidden",
            "line_admin_binding_not_current",
            "此 LINE 尚未綁定目前有效的工會人員身分。",
            "line-mobile-admin:role-scoped-binding",
        )
    principal = AdminPrincipal(
        linked_admin.admin_user_id,
        f"admin:{linked_admin.admin_user_id}",
        linked_admin.display_name,
        linked_admin.role,
        linked_line_user_id=line_user_id.value,
    )
    if required_capability is not None and not has_required_capability(
        principal,
        required_capability.value,
    ):
        raise typed_http_error(
            403,
            "forbidden",
            "mobile_admin_capability_required",
            "此工會人員身分沒有執行目前操作的權限。",
            "line-mobile-admin:capability",
        )
    return principal, admin_actor_context(principal)


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


def _admin_view(principal: AdminPrincipal) -> dict:
    return {
        "admin_user_id": principal.id,
        "display_name": principal.display_name,
        "role": principal.role,
    }


def _current_business_week(today: date) -> tuple[date, date]:
    return today - timedelta(days=today.weekday()), today


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
        "line_user_id": _mask(snapshot.line_user_id.value if snapshot.line_user_id else ""),
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
