"""Bounded Client profile applicant and reviewer endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies.client_profile import get_client_profile_application, get_verified_client_identity
from api.dependencies.admin_auth import require_customer_service_handler, require_customer_service_reader
from api.dependencies.line_identity import get_liff_token_verifier
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.client_profile import (
    ClientProfileApprovalApplyRequest,
    ClientProfileApprovalPreviewRequest,
    ClientProfileApprovalReceiptView,
    ClientProfileChangeApplyRequest,
    ClientProfileChangeRequest,
    ClientProfileApplicantReceiptView,
    ClientProfilePreviewView,
    ClientProfileQueryRequest,
    ClientProfileRequestPageView,
    ClientProfileRequestView,
    ClientProfileView,
    ClientProfileRejectPreviewRequest,
    ClientProfileRejectRequest,
)
from domains.clients.profile import ClientProfileValidationError
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError, LiffVerificationUnavailableError
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_profile.application import ClientProfileApplication
from subsystems.client_profile.contracts import ClientProfileError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


router = APIRouter(prefix="/api/v1/line/client-profile", tags=["LINE Client Profile"])
review_router = APIRouter(prefix="/api/v1/client-profile/requests", tags=["Client Profile Review"])


@router.post("/query", response_model=BaseResponse[ClientProfileView])
def query_applicant(payload: ClientProfileQueryRequest, application: ClientProfileApplication = Depends(get_client_profile_application)):
    try:
        applicant, client_id = _identity(payload.line_id_token)
        return BaseResponse(data=_view(application.query_applicant(applicant, client_id)))
    except (ClientProfileError, InvalidLiffTokenError, LiffVerificationUnavailableError) as error:
        _raise_error(error, "client-profile:query")


@router.post("/preview", response_model=BaseResponse[ClientProfilePreviewView])
def preview_applicant(payload: ClientProfileChangeRequest, application: ClientProfileApplication = Depends(get_client_profile_application)):
    try:
        preview = application.preview_applicant(
            *_identity(payload.line_id_token), payload.changes, ExpectedVersion(payload.expected_version)
        )
        return BaseResponse(data=_preview_view(preview), message="資料異動 Preview 已建立；尚未送出")
    except (ClientProfileError, ClientProfileValidationError, InvalidLiffTokenError, LiffVerificationUnavailableError) as error:
        _raise_error(error, "client-profile:preview")


@router.post("/apply", response_model=BaseResponse[ClientProfileApplicantReceiptView])
def apply_applicant(payload: ClientProfileChangeApplyRequest, application: ClientProfileApplication = Depends(get_client_profile_application)):
    try:
        receipt = application.apply_applicant(
            *_identity(payload.line_id_token), payload.changes, ExpectedVersion(payload.expected_version),
            payload.reason, PreviewFingerprint(payload.preview_fingerprint), IdempotencyKey(payload.idempotency_key),
            CorrelationId(payload.correlation_id),
        )
        return BaseResponse(data=_applicant_receipt_view(receipt), message="資料異動申請已送出，等待工會審核")
    except (ClientProfileError, ClientProfileValidationError, InvalidLiffTokenError, LiffVerificationUnavailableError) as error:
        _raise_error(error, "client-profile:apply")


@review_router.get("", response_model=BaseResponse[ClientProfileRequestPageView])
def list_requests(
    status: str | None = Query(default="pending"), page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
    _: AdminPrincipal = Depends(require_customer_service_reader), application: ClientProfileApplication = Depends(get_client_profile_application),
):
    try:
        items, total = application.list_requests(status=status, page=page, page_size=page_size)
        return BaseResponse(data={"items": [_request_view(item) for item in items], "total": total, "page": page, "page_size": page_size})
    except ClientProfileError as error:
        _raise_error(error, "client-profile:review:list")


@review_router.get("/{request_id}", response_model=BaseResponse[ClientProfileRequestView])
def query_request(request_id: int, _: AdminPrincipal = Depends(require_customer_service_reader), application: ClientProfileApplication = Depends(get_client_profile_application)):
    try:
        return BaseResponse(data=_request_view(application.query_request(request_id)))
    except ClientProfileError as error:
        _raise_error(error, f"client-profile:review:{request_id}")


@review_router.post("/{request_id}/approve/preview", response_model=BaseResponse[ClientProfilePreviewView])
def preview_approval(request_id: int, payload: ClientProfileApprovalPreviewRequest, __: AdminPrincipal = Depends(require_customer_service_handler), application: ClientProfileApplication = Depends(get_client_profile_application)):
    try:
        return BaseResponse(data=_preview_view(application.preview_approval(request_id, ExpectedVersion(payload.expected_request_version))), message="核准 Preview 已建立；尚未套用")
    except ClientProfileError as error:
        _raise_error(error, f"client-profile:approve-preview:{request_id}")


@review_router.post("/{request_id}/approve/apply", response_model=BaseResponse[ClientProfileApprovalReceiptView])
def apply_approval(request_id: int, payload: ClientProfileApprovalApplyRequest, principal: AdminPrincipal = Depends(require_customer_service_handler), application: ClientProfileApplication = Depends(get_client_profile_application)):
    try:
        actor = ActorContext(f"admin:{principal.id}" if principal.id is not None else "system:local_bypass", tuple(sorted(principal.effective_capabilities())))
        receipt = application.apply_approval(
            request_id, actor, payload.reason, ExpectedVersion(payload.expected_request_version),
            ExpectedVersion(payload.expected_profile_version), PreviewFingerprint(payload.preview_fingerprint),
            IdempotencyKey(payload.idempotency_key), CorrelationId(payload.correlation_id),
        )
        return BaseResponse(data=_approval_receipt_view(receipt), message="客戶資料已核准套用並完成讀回")
    except ClientProfileError as error:
        _raise_error(error, f"client-profile:approve-apply:{request_id}")


@review_router.post("/{request_id}/reject/preview", response_model=BaseResponse[ClientProfilePreviewView])
def preview_rejection(request_id: int, payload: ClientProfileRejectPreviewRequest, __: AdminPrincipal = Depends(require_customer_service_handler), application: ClientProfileApplication = Depends(get_client_profile_application)):
    try:
        preview = application.preview_rejection(request_id, ExpectedVersion(payload.expected_request_version), payload.reason)
        return BaseResponse(data=_preview_view(preview), message="退回 Preview 已建立；尚未套用")
    except ClientProfileError as error:
        _raise_error(error, f"client-profile:reject-preview:{request_id}")


@review_router.post("/{request_id}/reject", response_model=BaseResponse[ClientProfileRequestView])
def reject_request(request_id: int, payload: ClientProfileRejectRequest, principal: AdminPrincipal = Depends(require_customer_service_handler), application: ClientProfileApplication = Depends(get_client_profile_application)):
    try:
        actor = ActorContext(f"admin:{principal.id}" if principal.id is not None else "system:local_bypass", tuple(sorted(principal.effective_capabilities())))
        result = application.reject_request(
            request_id, actor, payload.reason, ExpectedVersion(payload.expected_request_version),
            PreviewFingerprint(payload.preview_fingerprint), IdempotencyKey(payload.idempotency_key), CorrelationId(payload.correlation_id),
        )
        return BaseResponse(data=_request_view(result), message="資料異動申請已退回；客戶資料未修改")
    except ClientProfileError as error:
        _raise_error(error, f"client-profile:reject:{request_id}")


def _identity(token: str):
    try:
        return get_verified_client_identity(token, get_liff_token_verifier())
    except InvalidLiffTokenError as error:
        raise error
    except LiffVerificationUnavailableError as error:
        raise error


def _view(view):
    return {"client_id": view.client_id, "version": view.version, "values": dict(view.values)}


def _preview_view(view):
    return {"client_id": view.client_id, "current_version": view.current_version, "before": dict(view.before), "requested": dict(view.requested), "preview_fingerprint": view.preview_fingerprint.value, "blockers": list(view.blockers), "apply_ready": view.apply_ready}


def _request_view(view):
    return {"request_id": view.request_id, "client_id": view.client_id, "status": view.status, "request_version": view.request_version, "profile_version": view.profile_version, "before": dict(view.before), "requested": dict(view.requested), "reason": view.reason}


def _applicant_receipt_view(receipt):
    return {"request": _request_view(receipt.request), "preview_fingerprint": receipt.preview_fingerprint.value, "idempotency_key": receipt.idempotency_key, "replayed": receipt.replayed, "readback": _view(receipt.readback)}


def _approval_receipt_view(receipt):
    return {"request": _request_view(receipt.request), "preview_fingerprint": receipt.preview_fingerprint.value, "idempotency_key": receipt.idempotency_key, "replayed": receipt.replayed, "readback": _view(receipt.readback)}


def _raise_error(error: Exception, correlation_id: str):
    if isinstance(error, LiffVerificationUnavailableError):
        raise typed_http_error(503, "unavailable", "liff_verification_unavailable", "LINE 身分驗證服務暫時無法連線，請稍後再試。", correlation_id, retryable=True) from error
    if isinstance(error, InvalidLiffTokenError):
        raise typed_http_error(401, "forbidden", "liff_token_invalid", "LINE 登入狀態已失效，請重新開啟此頁。", correlation_id) from error
    code = getattr(error, "code", str(error))
    status = 409 if "stale" in code or "conflict" in code or "fingerprint" in code or "idempotency" in code else 403 if "binding" in code else 404 if "not_found" in code else 422 if isinstance(error, ClientProfileValidationError) else 500
    raise typed_http_error(status, "validation" if status == 422 else "conflict" if status == 409 else "forbidden" if status == 403 else "not_found" if status == 404 else "internal", code, "資料異動操作未完成，請重新查詢後再試。", correlation_id) from error


__all__ = ["router", "review_router"]
