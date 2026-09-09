"""Verified customer-facing LIFF order-change request endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from api.dependencies.client_profile import get_verified_client_identity
from api.dependencies.line_identity import get_liff_token_verifier
from api.dependencies.line_order_change import get_customer_order_change_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.line_order_change import (
    LineOrderChangeApplyRequest,
    LineOrderChangeIdentityRequest,
    LineOrderChangeOrderListView,
    LineOrderChangePreviewRequest,
    LineOrderChangePreviewView,
    LineOrderChangeReceiptView,
)
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.client_profile.contracts import ClientProfileBindingError
from subsystems.line.customer_order_change_application import CustomerOrderChangeApplication
from subsystems.line.customer_order_change_contracts import CustomerOrderChangeError


router = APIRouter(prefix="/api/v1/line/order-change", tags=["LINE Customer Order Change"])
page_router = APIRouter(tags=["LINE Customer Order Change Page"])
_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "order_update.html"
_NO_CACHE_HEADERS = {"Cache-Control": "no-store"}


@page_router.get("/line-order-update")
def order_update_page():
    return FileResponse(_PAGE, headers=_NO_CACHE_HEADERS)


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


@router.post("/apply", response_model=BaseResponse[LineOrderChangeReceiptView])
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
                "ticket_id": receipt.ticket_id,
                "ticket_status": receipt.ticket_status,
                "case_no": receipt.case_no,
                "kind": receipt.kind.value,
                "idempotency_key": receipt.idempotency_key,
                "replayed": receipt.replayed,
            },
            message="訂單異動申請已送出，等待工會確認；正式訂單尚未修改",
        )
    except _ROUTE_ERRORS as error:
        _raise_error(error, "line-order-change:apply")


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
    status = (
        409
        if any(marker in code for marker in ("stale", "fingerprint", "idempotency", "replay"))
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


__all__ = ["page_router", "router"]
