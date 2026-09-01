"""
File: customer_service.py
Description: 暴露客服唯讀、結案與回覆 Preview／Apply，以及退役 direct mutation 的認證 HTTP 入口。
"""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pymysql.err import OperationalError

from api.dependencies.admin_auth import admin_actor_context, require_customer_service_handler, require_customer_service_reader
from api.dependencies.line_runtime import publish_line_wakeup_best_effort
from api.schemas.base import BaseResponse
from api.schemas.customer_service import (
    CustomerServiceDetailView,
    CustomerServicePageView,
    CustomerServiceReplyApplyRequest,
    CustomerServiceReplyApplyView,
    CustomerServiceReplyPreviewRequest,
    CustomerServiceReplyPreviewView,
    CustomerServiceSummaryView,
    CustomerServiceUpdateApplyRequest,
    CustomerServiceUpdateApplyView,
    CustomerServiceUpdatePreviewRequest,
    CustomerServiceUpdatePreviewView,
    HumanEscalationClaimRequest,
    HumanEscalationClaimApplyRequest,
    HumanEscalationCreateRequest,
    HumanEscalationCreateApplyRequest,
    HumanEscalationHandlingRequest,
    HumanEscalationHandlingApplyRequest,
    HumanEscalationPreviewResponse,
    HumanEscalationReceiptResponse,
    HumanEscalationResolveRequest,
    HumanEscalationResolveApplyRequest,
    HumanEscalationViewResponse,
)
from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus, CustomerServiceTransitionError
from domains.customer_service.escalation import TriggerCode
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.customer_service.application import (
    CustomerServiceApplication,
    CustomerServiceIdempotencyMismatchError,
    CustomerServicePreviewFingerprintConflictError,
    CustomerServiceTicketNotFoundError,
    CustomerServiceVersionConflictError,
)
from subsystems.customer_service.escalation_application import HumanEscalationApplication
from subsystems.customer_service.escalation_contracts import (
    ClaimHumanEscalation,
    CreateHumanEscalation,
    HumanEscalationError,
    ResolveHumanEscalation,
    StartHumanEscalationHandling,
)
from subsystems.customer_service.contracts import (
    ApplyCustomerServiceTicketReply,
    ApplyCustomerServiceTicketUpdate,
    CustomerServiceListQuery,
    PreviewCustomerServiceTicketReply,
    PreviewCustomerServiceTicketUpdate,
)


router = APIRouter(prefix="/api/v1/customer-service/tickets", tags=["Customer Service"])
escalation_router = APIRouter(prefix="/api/v1/customer-service/escalations", tags=["Customer Service Escalations"])


def _application():
    return CustomerServiceApplication(open_line_unit_of_work)


def _escalation_application():
    return HumanEscalationApplication(open_line_unit_of_work)


@escalation_router.post("", response_model=BaseResponse[HumanEscalationReceiptResponse])
def create_escalation(
    payload: HumanEscalationCreateApplyRequest,
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    command = CreateHumanEscalation(
        payload.source_event_identity,
        payload.source_kind,
        payload.source_fingerprint,
        TriggerCode(payload.trigger_code),
        payload.trigger_policy_version,
        CustomerServiceCategory(payload.ticket_category),
        payload.masked_context,
        payload.hold_scope,
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
        admin_actor_context(principal),
        PreviewFingerprint(payload.preview_fingerprint),
    )
    try:
        receipt = _escalation_application().create(command)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, payload.correlation_id) from error
    return BaseResponse(data=_escalation_receipt_response(receipt))


@escalation_router.post("/preview", response_model=BaseResponse[HumanEscalationPreviewResponse])
def preview_create_escalation(
    payload: HumanEscalationCreateRequest,
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    command = CreateHumanEscalation(
        payload.source_event_identity,
        payload.source_kind,
        payload.source_fingerprint,
        TriggerCode(payload.trigger_code),
        payload.trigger_policy_version,
        CustomerServiceCategory(payload.ticket_category),
        payload.masked_context,
        payload.hold_scope,
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
        admin_actor_context(principal),
    )
    try:
        preview = _escalation_application().preview(command)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, payload.correlation_id) from error
    return BaseResponse(data=_escalation_preview_response(preview), message="人工客服升級 Preview 已建立；尚未寫入")


@escalation_router.get("/{escalation_id}", response_model=BaseResponse[HumanEscalationViewResponse])
def escalation_detail(escalation_id: int, _: AdminPrincipal = Depends(require_customer_service_reader)):
    try:
        view = _escalation_application().query(escalation_id)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, f"customer-service:escalation:query:{escalation_id}") from error
    return BaseResponse(data=_escalation_view_response(view))


@escalation_router.post("/{escalation_id}/claim", response_model=BaseResponse[HumanEscalationReceiptResponse])
def claim_escalation(
    escalation_id: int,
    payload: HumanEscalationClaimApplyRequest,
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    command = ClaimHumanEscalation(
        escalation_id,
        payload.expected_escalation_version,
        admin_actor_context(principal),
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
        PreviewFingerprint(payload.preview_fingerprint),
    )
    try:
        receipt = _escalation_application().claim(command)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, payload.correlation_id) from error
    return BaseResponse(data=_escalation_receipt_response(receipt))


@escalation_router.post("/{escalation_id}/claim/preview", response_model=BaseResponse[HumanEscalationPreviewResponse])
def preview_claim_escalation(
    escalation_id: int,
    payload: HumanEscalationClaimRequest,
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    command = ClaimHumanEscalation(
        escalation_id,
        payload.expected_escalation_version,
        admin_actor_context(principal),
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
    )
    try:
        preview = _escalation_application().preview(command)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, payload.correlation_id) from error
    return BaseResponse(data=_escalation_preview_response(preview), message="人工客服接手 Preview 已建立；尚未寫入")


@escalation_router.post("/{escalation_id}/handling", response_model=BaseResponse[HumanEscalationReceiptResponse])
def start_escalation_handling(
    escalation_id: int,
    payload: HumanEscalationHandlingApplyRequest,
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    command = StartHumanEscalationHandling(
        escalation_id,
        payload.expected_escalation_version,
        payload.expected_ticket_version,
        admin_actor_context(principal),
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
        PreviewFingerprint(payload.preview_fingerprint),
    )
    try:
        receipt = _escalation_application().start_handling(command)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, payload.correlation_id) from error
    return BaseResponse(data=_escalation_receipt_response(receipt))


@escalation_router.post("/{escalation_id}/handling/preview", response_model=BaseResponse[HumanEscalationPreviewResponse])
def preview_start_escalation_handling(
    escalation_id: int,
    payload: HumanEscalationHandlingRequest,
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    command = StartHumanEscalationHandling(
        escalation_id,
        payload.expected_escalation_version,
        payload.expected_ticket_version,
        admin_actor_context(principal),
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
    )
    try:
        preview = _escalation_application().preview(command)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, payload.correlation_id) from error
    return BaseResponse(data=_escalation_preview_response(preview), message="人工客服開始處理 Preview 已建立；尚未寫入")


@escalation_router.post("/{escalation_id}/resolve", response_model=BaseResponse[HumanEscalationReceiptResponse])
def resolve_escalation(
    escalation_id: int,
    payload: HumanEscalationResolveApplyRequest,
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    command = ResolveHumanEscalation(
        escalation_id,
        payload.expected_escalation_version,
        payload.expected_ticket_version,
        payload.resolution_code,
        payload.resolution_evidence_digest,
        admin_actor_context(principal),
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
        PreviewFingerprint(payload.preview_fingerprint),
    )
    try:
        receipt = _escalation_application().resolve(command)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, payload.correlation_id) from error
    return BaseResponse(data=_escalation_receipt_response(receipt))


@escalation_router.post("/{escalation_id}/resolve/preview", response_model=BaseResponse[HumanEscalationPreviewResponse])
def preview_resolve_escalation(
    escalation_id: int,
    payload: HumanEscalationResolveRequest,
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    command = ResolveHumanEscalation(
        escalation_id,
        payload.expected_escalation_version,
        payload.expected_ticket_version,
        payload.resolution_code,
        payload.resolution_evidence_digest,
        admin_actor_context(principal),
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
    )
    try:
        preview = _escalation_application().preview(command)
    except HumanEscalationError as error:
        raise _human_escalation_http_error(error, payload.correlation_id) from error
    return BaseResponse(data=_escalation_preview_response(preview), message="人工客服解除暫停 Preview 已建立；尚未寫入")


@router.get("/summary", response_model=BaseResponse[CustomerServiceSummaryView])
def summary(_: AdminPrincipal = Depends(require_customer_service_reader)):
    return BaseResponse(data=_application().summary())


@router.get("", response_model=BaseResponse[CustomerServicePageView])
def list_tickets(
    status: CustomerServiceStatus | None = CustomerServiceStatus.WAITING,
    category: CustomerServiceCategory | None = None, search: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    _: AdminPrincipal = Depends(require_customer_service_reader),
):
    return BaseResponse(data=_application().list(CustomerServiceListQuery(status, category, search, page, page_size)))


@router.get("/{ticket_id}", response_model=BaseResponse[CustomerServiceDetailView])
def detail(ticket_id: int, _: AdminPrincipal = Depends(require_customer_service_reader)):
    return BaseResponse(data=_call(_application().detail, ticket_id))


@router.post(
    "/{ticket_id}/update/preview",
    response_model=BaseResponse[CustomerServiceUpdatePreviewView],
)
def preview_update(
    ticket_id: int,
    payload: CustomerServiceUpdatePreviewRequest,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ],
    _: AdminPrincipal = Depends(require_customer_service_handler),
):
    identity = CorrelationId(correlation_id)
    command = PreviewCustomerServiceTicketUpdate(
        ticket_id,
        CustomerServiceStatus(payload.status),
        payload.internal_note,
        ExpectedVersion(payload.expected_version),
        identity,
    )
    preview = _call_update_endpoint(
        _application().preview_update,
        command,
        correlation_id=identity,
    )
    return BaseResponse(
        data=CustomerServiceUpdatePreviewView(
            ticket_id=preview.ticket_id,
            before_status=preview.before_status,
            after_status=preview.after_status,
            current_version=preview.current_version,
            expected_version=preview.expected_version,
            blockers=list(preview.blockers),
            preview_fingerprint=preview.preview_fingerprint.value,
            apply_ready=preview.apply_ready,
        ),
        message="客服結案 Preview 已建立",
    )


@router.post(
    "/{ticket_id}/update/apply",
    response_model=BaseResponse[CustomerServiceUpdateApplyView],
)
def apply_update(
    ticket_id: int,
    payload: CustomerServiceUpdateApplyRequest,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ],
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ],
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    identity = CorrelationId(correlation_id)
    command = ApplyCustomerServiceTicketUpdate(
        ticket_id,
        CustomerServiceStatus(payload.status),
        payload.internal_note,
        ExpectedVersion(payload.expected_version),
        PreviewFingerprint(payload.preview_fingerprint),
        admin_actor_context(principal).actor_id,
        IdempotencyKey(idempotency_key),
        identity,
    )
    result = _call_update_endpoint(
        _application().apply_update,
        command,
        correlation_id=identity,
    )
    _audit_request(request, "update.apply", ticket_id)
    return BaseResponse(
        data=CustomerServiceUpdateApplyView(
            ticket_id=result.ticket_id,
            resulting_status=result.resulting_status,
            resulting_version=result.resulting_version,
            preview_fingerprint=result.preview_fingerprint.value,
            replayed=result.replayed,
            readback=result.readback,
        ),
        message="客服管理操作已完成",
    )


@router.patch("/{ticket_id}", include_in_schema=False)
def retired_update(ticket_id: int, request: Request):
    del ticket_id, request
    raise HTTPException(
        status_code=410,
        detail={
            "code": "customer_service_update_preview_required",
            "message": "此客服更新入口已退役，請先預覽再套用。",
            "retryable": False,
        },
    )


@router.post(
    "/{ticket_id}/reply/preview",
    response_model=BaseResponse[CustomerServiceReplyPreviewView],
)
def preview_reply(
    ticket_id: int,
    payload: CustomerServiceReplyPreviewRequest,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ],
    _: AdminPrincipal = Depends(require_customer_service_handler),
):
    identity = CorrelationId(correlation_id)
    command = PreviewCustomerServiceTicketReply(
        ticket_id,
        payload.reply_text,
        payload.resolve,
        payload.internal_note,
        ExpectedVersion(payload.expected_version),
        identity,
    )
    preview = _call_update_endpoint(
        _application().preview_reply,
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
    "/{ticket_id}/reply/apply",
    response_model=BaseResponse[CustomerServiceReplyApplyView],
)
def apply_reply(
    ticket_id: int,
    payload: CustomerServiceReplyApplyRequest,
    request: Request,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ],
    principal: AdminPrincipal = Depends(require_customer_service_handler),
):
    identity = CorrelationId(correlation_id)
    command = ApplyCustomerServiceTicketReply(
        ticket_id,
        payload.reply_text,
        payload.resolve,
        payload.internal_note,
        ExpectedVersion(payload.expected_version),
        PreviewFingerprint(payload.preview_fingerprint),
        admin_actor_context(principal).actor_id,
        principal.id,
        IdempotencyKey(payload.idempotency_key),
        identity,
    )
    result = _call_update_endpoint(
        _application().apply_reply,
        command,
        correlation_id=identity,
        error_scope="reply",
    )
    _audit_request(request, "reply.apply", ticket_id)
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


@router.post("/{ticket_id}/reply", include_in_schema=False)
def retired_reply(ticket_id: int, request: Request):
    del ticket_id, request
    raise HTTPException(
        status_code=410,
        detail={
            "code": "customer_service_reply_preview_required",
            "message": "此回覆入口已退役，請先預覽再套用。",
            "retryable": False,
        },
    )


def _call(operation, *arguments):
    try:
        return operation(*arguments)
    except CustomerServiceTicketNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "customer_service_ticket_not_found", "message": str(error)}) from error
    except (CustomerServiceVersionConflictError, CustomerServiceTransitionError) as error:
        raise HTTPException(status_code=409, detail={"code": "customer_service_ticket_version_conflict", "message": str(error)}) from error


def _call_update_endpoint(
    operation,
    *arguments,
    correlation_id: CorrelationId,
    error_scope: str = "update",
):
    try:
        return operation(*arguments)
    except CustomerServiceTicketNotFoundError as error:
        raise _typed_http_error(
            404,
            TypedError(
                ErrorCategory.NOT_FOUND,
                "customer_service_ticket_not_found",
                "找不到指定的客服需求。",
                correlation_id,
            ),
        ) from error
    except CustomerServiceIdempotencyMismatchError as error:
        raise _typed_http_error(
            409,
            TypedError(
                ErrorCategory.IDEMPOTENCY_MISMATCH,
                f"customer_service_{error_scope}_idempotency_mismatch",
                "相同冪等鍵已被不同內容使用。",
                correlation_id,
            ),
        ) from error
    except CustomerServicePreviewFingerprintConflictError as error:
        raise _typed_http_error(
            409,
            TypedError(
                ErrorCategory.CONFLICT,
                f"customer_service_{error_scope}_preview_conflict",
                (
                    "客服回覆 Preview 已過期，請重新查詢並預覽。"
                    if error_scope == "reply"
                    else "客服結案 Preview 已過期，請重新查詢並預覽。"
                ),
                correlation_id,
            ),
        ) from error
    except CustomerServiceVersionConflictError as error:
        raise _typed_http_error(
            409,
            TypedError(
                ErrorCategory.CONFLICT,
                "customer_service_ticket_version_conflict",
                "客服需求版本已更新，請重新查詢。",
                correlation_id,
            ),
        ) from error
    except CustomerServiceTransitionError as error:
        raise _typed_http_error(
            409,
            TypedError(
                ErrorCategory.DOMAIN_BLOCKED,
                "customer_service_transition_invalid",
                "目前狀態不允許這項客服操作。",
                correlation_id,
                domain_blockers=("customer_service_transition_invalid",),
            ),
        ) from error
    except OperationalError as error:
        mysql_code = int(error.args[0]) if error.args else 0
        retryable = mysql_code in {1205, 1213}
        category = ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL
        status_code = 503 if retryable else 500
        raise _typed_http_error(
            status_code,
            TypedError(
                category,
                (
                    f"customer_service_{error_scope}_temporarily_unavailable"
                    if retryable
                    else f"customer_service_{error_scope}_database_error"
                ),
                (
                    "客服操作暫時無法完成，可使用相同冪等鍵重試。"
                    if retryable
                    else "客服操作發生資料庫錯誤。"
                ),
                correlation_id,
                retryable=retryable,
            ),
        ) from error
    except Exception as error:
        raise _typed_http_error(
            500,
            TypedError(
                ErrorCategory.INTERNAL,
                f"customer_service_{error_scope}_internal_error",
                "客服操作發生未預期錯誤。",
                correlation_id,
            ),
        ) from error


def _typed_http_error(status_code: int, error: TypedError) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "category": error.category.value,
                "code": error.code,
                "message": error.message,
                "field_errors": [
                    {
                        "field": item.field,
                        "code": item.code,
                        "message": item.message,
                    }
                    for item in error.field_errors
                ],
                "domain_blockers": list(error.domain_blockers),
                "retryable": error.retryable,
                "correlation_id": error.correlation_id.value,
                "current_version": (
                    None
                    if error.current_version is None
                    else error.current_version.value
                ),
            }
        },
        headers={"Retry-After": "1"} if error.retryable else None,
    )


def _human_escalation_http_error(error: HumanEscalationError, correlation_id: str) -> HTTPException:
    category = {
        "validation": ErrorCategory.VALIDATION,
        "not_found": ErrorCategory.NOT_FOUND,
        "conflict": ErrorCategory.CONFLICT,
        "idempotency_mismatch": ErrorCategory.IDEMPOTENCY_MISMATCH,
        "domain_blocked": ErrorCategory.DOMAIN_BLOCKED,
        "unavailable": ErrorCategory.UNAVAILABLE,
        "internal": ErrorCategory.INTERNAL,
    }.get(error.category, ErrorCategory.INTERNAL)
    status_code = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.UNAVAILABLE: 503,
    }.get(category, 500)
    return _typed_http_error(
        status_code,
        TypedError(category, error.code, "客服人工接手操作未完成。", CorrelationId(correlation_id), retryable=error.retryable),
    )


def _escalation_receipt_response(receipt) -> HumanEscalationReceiptResponse:
    return HumanEscalationReceiptResponse(
        receipt_id=receipt.receipt_id,
        command_family=receipt.command_family,
        operation=receipt.operation,
        escalation_id=receipt.escalation_id,
        ticket_ref=receipt.ticket_ref,
        resulting_workflow_status=receipt.resulting_workflow_status.value,
        resulting_hold_state=receipt.resulting_hold_state.value,
        current_version=receipt.current_version,
        replayed=receipt.replayed,
        correlation_id=receipt.correlation_id,
        committed_at=receipt.committed_at,
    )


def _escalation_preview_response(preview) -> HumanEscalationPreviewResponse:
    return HumanEscalationPreviewResponse(
        operation=preview.operation,
        escalation_id=preview.escalation_id,
        before_workflow_status=preview.before_workflow_status,
        resulting_workflow_status=preview.resulting_workflow_status.value,
        before_hold_state=preview.before_hold_state,
        resulting_hold_state=preview.resulting_hold_state.value,
        current_escalation_version=preview.current_escalation_version,
        current_ticket_version=preview.current_ticket_version,
        preview_fingerprint=preview.preview_fingerprint.value,
        apply_ready=preview.apply_ready,
    )


def _escalation_view_response(view) -> HumanEscalationViewResponse:
    return HumanEscalationViewResponse(
        escalation_id=view.escalation_id,
        ticket_ref=view.ticket_ref,
        category=view.category.value,
        urgency=view.urgency,
        trigger_code=view.trigger_code.value,
        workflow_status=view.workflow_status.value,
        workflow_version=view.workflow_version,
        automation_hold=view.automation_hold.value,
        hold_scope_label=view.hold_scope_label,
        masked_context=dict(view.masked_context),
        alert_status=view.alert_status.value,
        current_version=view.current_version,
        created_at=view.created_at,
        updated_at=view.updated_at,
        available_actions=list(view.available_actions),
        delivery_task_ref=view.delivery_task_ref,
        delivery_outcome_ref=view.delivery_outcome_ref,
        trigger_identity=view.trigger_identity,
        attempt_window=(
            None
            if view.attempt_window is None
            else {
                "attempt_count": view.attempt_window.attempt_count,
                "maximum_attempts": view.attempt_window.maximum_attempts,
                "generation": view.attempt_window.generation,
            }
        ),
        owner_selector=view.owner_selector,
    )


def _correlation(operation):
    return CorrelationId(f"customer-service:{operation}:{uuid4()}")


def _audit_request(request, operation, ticket_id):
    request.state.audit_action = f"customer_service.ticket.{operation}"
    request.state.audit_resource_type = "customer_service_ticket"
    request.state.audit_resource_id = str(ticket_id)


__all__ = ["escalation_router", "router"]
