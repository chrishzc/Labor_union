"""Typed Q/P/A endpoints for the union collection account."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from api.dependencies.admin_auth import require_admin
from api.dependencies.client_payment_destination import get_client_payment_destination_application
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.client_payment_destination import (
    PaymentDestinationApplyBody,
    PaymentDestinationPreviewBody,
    PaymentDestinationPreviewView,
    PaymentDestinationReceiptView,
    PaymentDestinationView,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.payment_destination_configuration import (
    PaymentDestinationApplyRequest,
    PaymentDestinationConfigurationApplication,
    PaymentDestinationConfigurationError,
)

router = APIRouter(prefix="/api/v1/client-finance/payment-destination", tags=["Client Finance"])
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]


def _view(current) -> PaymentDestinationView:
    return PaymentDestinationView(
        configured=current is not None,
        account_display=None if current is None else current.account_display,
        revision=0 if current is None else current.revision,
    )


@router.get("", response_model=BaseResponse[PaymentDestinationView])
def query_payment_destination(
    principal: AdminPrincipal = Depends(require_admin),
    application: PaymentDestinationConfigurationApplication = Depends(get_client_payment_destination_application),
):
    del principal
    try:
        return BaseResponse(data=_view(application.query()), message="Client payment destination")
    except Exception as exc:
        raise internal_query_error("client_payment_destination_query_failed", "收款帳戶設定讀取失敗。", "client-payment-destination-query") from exc


@router.post("/preview", response_model=BaseResponse[PaymentDestinationPreviewView])
def preview_payment_destination(
    body: PaymentDestinationPreviewBody,
    principal: AdminPrincipal = Depends(require_admin),
    application: PaymentDestinationConfigurationApplication = Depends(get_client_payment_destination_application),
):
    del principal
    try:
        preview = application.preview(body.account_display.strip(), body.expected_revision)
        return BaseResponse(data=PaymentDestinationPreviewView(current=_view(preview.current), candidate_account_display=preview.candidate_account_display, expected_revision=preview.expected_revision, preview_fingerprint=preview.preview_fingerprint.value), message="Client payment destination preview")
    except (ValueError, PaymentDestinationConfigurationError) as exc:
        raise typed_http_error(409 if getattr(exc, "code", "").endswith("stale") else 400, "conflict" if getattr(exc, "code", "").endswith("stale") else "validation", getattr(exc, "code", "client_payment_destination_invalid"), str(exc), "client-payment-destination-preview") from exc


@router.post("/apply", response_model=BaseResponse[PaymentDestinationReceiptView])
def apply_payment_destination(
    body: PaymentDestinationApplyBody,
    correlation_id: _CorrelationHeader,
    idempotency_key: _IdempotencyHeader,
    principal: AdminPrincipal = Depends(require_admin),
    application: PaymentDestinationConfigurationApplication = Depends(get_client_payment_destination_application),
):
    try:
        receipt = application.apply(PaymentDestinationApplyRequest(
            account_display=body.account_display.strip(), expected_revision=body.expected_revision,
            preview_fingerprint=PreviewFingerprint(body.preview_fingerprint), idempotency_key=IdempotencyKey(idempotency_key),
            correlation_id=CorrelationId(correlation_id), actor=ActorContext(principal.username), reason=body.reason.strip(),
        ))
        return BaseResponse(data=PaymentDestinationReceiptView(account_display=receipt.account_display, resulting_revision=receipt.resulting_revision, preview_fingerprint=receipt.preview_fingerprint.value), message="Client payment destination applied")
    except (ValueError, PaymentDestinationConfigurationError) as exc:
        code = getattr(exc, "code", "client_payment_destination_invalid")
        status = 409 if "stale" in code or "conflict" in code else 400
        raise typed_http_error(status, "conflict" if status == 409 else "validation", code, str(exc), "client-payment-destination-apply") from exc

