"""Verified customer-facing LIFF order-change request endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from api.dependencies.admin_auth import require_persisted_admin, require_system_admin
from api.dependencies.client_profile import get_verified_client_identity
from api.dependencies.line_identity import get_liff_token_verifier
from api.dependencies.line_order_change import (
    get_customer_order_change_application,
    get_order_change_requests_application,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.line_order_change import (
    LegacyOrderChangeReferencePageView,
    LineOrderChangeApplyRequest,
    LineOrderChangeIdentityRequest,
    LineOrderChangeOrderListView,
    LineOrderChangePreviewRequest,
    LineOrderChangePreviewView,
    LineOrderChangeReceiptView,
    OrderChangeRequestCompletionBody,
    OrderChangeRequestPageView,
    OrderChangeRequestView,
)
from domains.orders.order_change_request import OrderChangeRequest
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_profile.contracts import ClientProfileBindingError
from subsystems.line.customer_order_change_application import CustomerOrderChangeApplication
from subsystems.line.customer_order_change_contracts import CustomerOrderChangeError
from subsystems.orders.order_change_requests import OrderChangeRequestsApplication


router = APIRouter(prefix="/api/v1/line/order-change", tags=["LINE Customer Order Change"])
page_router = APIRouter(tags=["LINE Customer Order Change Page"])
admin_router = APIRouter(
    prefix="/api/v1/orders/change-requests",
    tags=["Orders 訂單異動申請"],
    dependencies=[Depends(require_system_admin)],
)
_ADMIN_QUERY_ERRORS = {
    401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證。"},
}


@router.post("/query", response_model=BaseResponse[LineOrderChangeOrderListView])
def query_orders(
    payload: LineOrderChangeIdentityRequest,
    application: CustomerOrderChangeApplication = Depends(get_customer_order_change_application),
):
    try:
        identity, client_id = _identity(payload.line_id_token)
        items = application.query(identity, client_id)
        return BaseResponse(
            data={
                "items": [
                    {
                        "case_no": item.case_no,
                        "status": item.status,
                        "order_version": item.order_version,
                        "values": dict(item.values),
                    }
                    for item in items
                ]
            }
        )
    except _ROUTE_ERRORS as error:
        _raise_error(error, "line-order-change:query")


@router.post("/preview", response_model=BaseResponse[LineOrderChangePreviewView])
def preview_order_change(
    payload: LineOrderChangePreviewRequest,
    application: CustomerOrderChangeApplication = Depends(get_customer_order_change_application),
):
    try:
        identity, client_id = _identity(payload.line_id_token)
        preview = application.preview(
            identity,
            client_id,
            payload.case_no,
            payload.expected_order_version,
            payload.kind,
            payload.requested,
        )
        return BaseResponse(data=_preview_view(preview), message="異動預覽已建立；尚未修改訂單")
    except _ROUTE_ERRORS as error:
        _raise_error(error, "line-order-change:preview")


@router.post("/apply", include_in_schema=False)
def retired_order_change_ticket_apply():
    raise typed_http_error(
        410, "validation", "order_change_ticket_apply_retired",
        "請重新開啟「改訂單內容」表單後再送出。", "line-order-change:retired-apply",
    )


@router.post("/requests", response_model=BaseResponse[LineOrderChangeReceiptView])
def apply_order_change(
    payload: LineOrderChangeApplyRequest,
    application: CustomerOrderChangeApplication = Depends(get_customer_order_change_application),
):
    try:
        identity, client_id = _identity(payload.line_id_token)
        receipt = application.apply(
            identity,
            client_id,
            payload.case_no,
            payload.expected_order_version,
            payload.kind,
            payload.requested,
            PreviewFingerprint(payload.preview_fingerprint),
            IdempotencyKey(payload.idempotency_key),
        )
        return BaseResponse(
            data={
                "request_id": receipt.request_id,
                "request_status": receipt.request_status.value,
                "case_no": receipt.case_no,
                "kind": receipt.kind.value,
                "idempotency_key": receipt.idempotency_key,
                "replayed": receipt.replayed,
            },
            message="已取得訂單異動申請紀錄",
        )
    except _ROUTE_ERRORS as error:
        _raise_error(error, "line-order-change:apply")


@admin_router.get(
    "",
    response_model=BaseResponse[OrderChangeRequestPageView],
    responses=_ADMIN_QUERY_ERRORS,
)
def list_order_change_requests(
    case_no: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    before_id: Annotated[int | None, Query(gt=0)] = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    application: OrderChangeRequestsApplication = Depends(get_order_change_requests_application),
):
    page = application.list(case_no=case_no, before_id=before_id, page_size=page_size)
    return BaseResponse(data={
        "items": [_request_view(item) for item in page.items],
        "next_before_id": page.next_before_id,
    })


@admin_router.post("/{request_id}/complete", response_model=BaseResponse[OrderChangeRequestView])
def complete_order_change_request(
    request_id: Annotated[int, Path(gt=0)],
    payload: OrderChangeRequestCompletionBody,
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: OrderChangeRequestsApplication = Depends(get_order_change_requests_application),
):
    if principal.id is None:
        raise typed_http_error(403, "forbidden", "order_change_admin_session_required",
                               "請以本人帳號重新登入。", "orders:change-request")
    try:
        observed = application.complete(
            request_id, payload.expected_version, payload.result, principal.id, principal.username
        )
        return BaseResponse(data=_request_view(observed), message="訂單異動申請已結案")
    except (CustomerOrderChangeError, ValueError) as error:
        _raise_error(error, "orders:change-request")


@admin_router.get(
    "/legacy",
    response_model=BaseResponse[LegacyOrderChangeReferencePageView],
    responses=_ADMIN_QUERY_ERRORS,
)
def list_legacy_order_change_references(
    case_no: Annotated[str, Query(min_length=1, max_length=50)],
    before_id: Annotated[int | None, Query(gt=0)] = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    application: OrderChangeRequestsApplication = Depends(get_order_change_requests_application),
):
    items, next_before_id = application.legacy_references(case_no, before_id, page_size)
    return BaseResponse(data={"items": [asdict(item) for item in items], "next_before_id": next_before_id})


def _request_view(item: OrderChangeRequest) -> dict:
    completion = item.completion
    return {
        "request_id": item.request_id,
        "case_no": item.case_no,
        "kind": item.kind.value,
        "status": item.status.value,
        "version": item.version,
        "before": dict(item.before),
        "requested": dict(item.requested),
        "submitted_at": item.submitted_at,
        "completion": {
            "result": completion.result,
            "actor_name": completion.actor_name,
            "completed_at": completion.completed_at,
        } if completion is not None else None,
    }


def _identity(token: str) -> tuple[str, int]:
    return get_verified_client_identity(token, get_liff_token_verifier())


def _preview_view(preview):
    return {
        "case_no": preview.case_no,
        "status": preview.status,
        "order_version": preview.order_version,
        "kind": preview.kind.value,
        "before": dict(preview.before),
        "requested": dict(preview.requested),
        "impact_note": preview.impact_note,
        "preview_fingerprint": preview.preview_fingerprint.value,
    }


def _raise_error(error: Exception, correlation_id: str):
    if isinstance(error, LiffVerificationUnavailableError):
        raise typed_http_error(
            503,
            "unavailable",
            "liff_verification_unavailable",
            "LINE 身分驗證服務暫時無法連線，請稍後再試。",
            correlation_id,
            retryable=True,
        ) from error
    if isinstance(error, InvalidLiffTokenError):
        raise typed_http_error(
            401,
            "forbidden",
            "liff_token_invalid",
            "LINE 登入狀態已失效，請重新開啟此頁。",
            correlation_id,
        ) from error
    code = getattr(error, "code", str(error))
    if code.startswith("order_change_write_readback_"):
        raise internal_query_error(
            code, "暫時無法確認異動申請的結果，請稍後重試。", correlation_id
        ) from error
    status = (
        409
        if any(marker in code for marker in ("stale", "fingerprint", "idempotency", "replay", "already_completed"))
        else 404
        if "not_found" in code
        else 403
        if "binding" in code
        else 422
    )
    raise typed_http_error(
        status,
        "conflict" if status == 409 else "not_found" if status == 404 else "forbidden" if status == 403 else "validation",
        code,
        "訂單異動申請未完成，請重新載入後再試。",
        correlation_id,
    ) from error


_ROUTE_ERRORS = (
    CustomerOrderChangeError,
    ClientProfileBindingError,
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
    ValueError,
)


__all__ = ["admin_router", "page_router", "router"]
