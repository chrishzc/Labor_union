"""Verified caregiver-facing LIFF endpoints for candidate-pool responses."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from api.dependencies.line_identity import get_liff_token_verifier
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.line_candidate_contact import (
    CandidateContactFormView,
    CandidateContactIdentityRequest,
    CandidateContactSubmitRequest,
    CandidateContactSubmitView,
    CandidateContactCustomerFormView,
    CandidateContactCustomerQueryRequest,
    CandidateContactCustomerSubmitRequest,
    CandidateContactCustomerSubmitView,
)
from domains.scheduling.candidate_contact_response import parse_candidate_response
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
)
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import IdempotencyKey
from subsystems.line.candidate_contact_response_application import (
    CandidateContactResponseApplication,
    CandidateContactResponseError,
)


router = APIRouter(prefix="/api/v1/line/candidate-contact", tags=["LINE Candidate Contact"])
page_router = APIRouter(tags=["LINE Candidate Contact Page"])
_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "candidate_contact.html"
_CUSTOMER_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "candidate_contact_customer.html"
_NO_CACHE_HEADERS = {"Cache-Control": "no-store"}


def _application() -> CandidateContactResponseApplication:
    return CandidateContactResponseApplication(get_connection)


@page_router.get("/line-candidate-contact")
def candidate_contact_page():
    return FileResponse(_PAGE, headers=_NO_CACHE_HEADERS)


@page_router.get("/line-candidate-contact-customer")
def candidate_contact_customer_page():
    return FileResponse(_CUSTOMER_PAGE, headers=_NO_CACHE_HEADERS)


@router.post("/query", response_model=BaseResponse[CandidateContactFormView])
def query_candidate_contact(payload: CandidateContactIdentityRequest):
    try:
        identity = get_liff_token_verifier().verify(payload.line_id_token)
        return BaseResponse(
            data=CandidateContactFormView.model_validate(
                _application().query(payload.interaction_reference, identity.line_user_id)
            )
        )
    except _ROUTE_ERRORS as error:
        _raise_error(error, "line-candidate-contact:query")


@router.post("/submit", response_model=BaseResponse[CandidateContactSubmitView])
def submit_candidate_contact(payload: CandidateContactSubmitRequest):
    try:
        identity = get_liff_token_verifier().verify(payload.line_id_token)
        response = parse_candidate_response(
            no_interest=payload.no_interest,
            issues=[item.model_dump(mode="json") for item in payload.issues],
        )
        result = _application().submit(
            payload.interaction_reference,
            identity.line_user_id,
            response,
            IdempotencyKey(payload.idempotency_key),
        )
        return BaseResponse(
            data=CandidateContactSubmitView.model_validate(result),
            message=(
                "已記錄回應；需要確認的資訊會由助理直接聯絡客戶。"
                if result["customer_message_queued"]
                else "已記錄回應。"
            ),
        )
    except _ROUTE_ERRORS as error:
        _raise_error(error, "line-candidate-contact:submit")


@router.post("/customer/query", response_model=BaseResponse[CandidateContactCustomerFormView])
def query_candidate_contact_customer(payload: CandidateContactCustomerQueryRequest):
    try:
        identity = get_liff_token_verifier().verify(payload.line_id_token)
        return BaseResponse(
            data=CandidateContactCustomerFormView.model_validate(
                _application().query_customer(payload.interaction_reference, identity.line_user_id)
            )
        )
    except _ROUTE_ERRORS as error:
        _raise_error(error, "line-candidate-contact-customer:query")


@router.post("/customer/submit", response_model=BaseResponse[CandidateContactCustomerSubmitView])
def submit_candidate_contact_customer(payload: CandidateContactCustomerSubmitRequest):
    try:
        identity = get_liff_token_verifier().verify(payload.line_id_token)
        result = _application().submit_customer_answer(
            payload.interaction_reference,
            identity.line_user_id,
            payload.answer,
            payload.decision,
            IdempotencyKey(payload.idempotency_key),
        )
        return BaseResponse(
            data=CandidateContactCustomerSubmitView.model_validate(
                result
            ),
            message=(
                "回答已直接轉交提出問題的月嫂。"
                if result["caregiver_message_queued"]
                else "已記錄是否可調整，並交由工會人員接續處理。"
            ),
        )
    except _ROUTE_ERRORS as error:
        _raise_error(error, "line-candidate-contact-customer:submit")


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
    code = str(error)
    status = (
        410
        if any(marker in code for marker in ("expired", "closed", "resolved"))
        else 403
        if "recipient" in code
        else 404
        if "not_found" in code
        else 422
    )
    raise typed_http_error(
        status,
        "expired" if status == 410 else "forbidden" if status == 403 else "not_found" if status == 404 else "validation",
        code,
        (
            "此案件客戶尚未綁定 LINE，問題目前無法傳送；請先由客戶完成 LINE 身分綁定。"
            if code == "candidate_contact_customer_unavailable"
            else "回應未送出，請重新從案件卡片開啟表單。"
        ),
        correlation_id,
    ) from error


_ROUTE_ERRORS = (
    CandidateContactResponseError,
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
    ValueError,
)


__all__ = ["page_router", "router"]
