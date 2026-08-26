"""
File: line_identity.py
Description: 提供 canonical LIFF flow、身分綁定、登記與 review 的 typed API。
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_identity_reader,
    require_line_identity_reviewer,
)
from api.dependencies.line_identity import (
    get_liff_token_verifier,
    get_line_identity_application,
    get_line_identity_review_application,
)
from api.dependencies.line_runtime import publish_line_wakeup_best_effort
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.line_identity import (
    AdminIdentityBindingApplyRequest,
    AdminIdentityBindingRequest,
    CanonicalLineReviewDecisionPreviewRequest,
    CanonicalLineReviewDecisionPreviewResponse,
    CanonicalLineReviewDecisionRequest,
    CanonicalLineReviewNumberedPageResponse,
    CanonicalLineReviewPageResponse,
    CanonicalLineReviewResponse,
    CanonicalLineReviewSummaryResponse,
    CustomerIdentityApplyRequest,
    CustomerIdentityRequest,
    LineIdentityApplyResponse,
    LineIdentityCandidateResponse,
    LineIdentityFlowOpenRequest,
    LineIdentityFlowOpenResponse,
    LineIdentityFlowValidationRequest,
    LineIdentityFlowValidationResponse,
    LineIdentityPreviewResponse,
    LineIdentityRuntimeConfigResponse,
    ProvisionalRegistrationRequest,
    ProvisionalRegistrationPreviewRequest,
    ProvisionalRegistrationPreviewResponse,
    ProvisionalRegistrationResponse,
    StaffIdentityApplyRequest,
    StaffIdentityRequest,
)
from domains.case_import.provisional_registration import (
    ProvisionalRegistrationDomainError,
    ProvisionalRegistrationIntent,
)
from domains.line.identities import LineIdentityFlowId, LineReviewRequestId, LineUserId
from domains.line.identity_flow import LineIdentityFlowPurpose
from domains.line.review import LineReviewDecision, LineReviewStatus, LineReviewType
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.identity_application import (
    LineIdentityApplication,
    LineIdentityAuthenticationError,
    LineIdentityConflictError,
    LineIdentityNotFoundError,
)
from subsystems.line.identity_contracts import (
    AdminCredentialProof,
    CustomerIdentityProof,
    StaffIdentityProof,
)
from subsystems.line.identity_review_application import (
    LineReviewDataConflictError,
    LineReviewNotFoundError,
)
from subsystems.line.review_contracts import (
    DecideLineReviewCommand,
    LineReviewListQuery,
    PreviewLineReviewDecisionCommand,
)
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflictError,
)
from infrastructure.mysql.provisional_registration_repository import (
    ProvisionalRegistrationStorageError,
)

public_router = APIRouter(prefix="/api/v1/line/identity", tags=["LINE Identity"])
review_router = APIRouter(
    prefix="/api/v1/line/identity/reviews",
    tags=["LINE Identity Reviews"],
)
page_router = APIRouter(tags=["LINE Identity"])
_IDENTITY_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "identity.html"
_REGISTRATION_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "register.html"
_STAFF_ORDERS_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "staff_order_search.html"
_STAFF_SCHEDULE_PAGE = Path(__file__).resolve().parents[2] / "line" / "static" / "staff_schedule.html"


@page_router.get("/line-identity/", include_in_schema=False)
@page_router.get("/line-identity")
def identity_page():
    return FileResponse(_IDENTITY_PAGE)


@page_router.get("/line-registration")
def registration_page():
    return FileResponse(_REGISTRATION_PAGE)


@page_router.get("/line-staff-orders")
def staff_orders_page():
    return FileResponse(_STAFF_ORDERS_PAGE)


@page_router.get("/line-staff-schedule")
def staff_schedule_page():
    return FileResponse(_STAFF_SCHEDULE_PAGE)


@public_router.get(
    "/runtime-config",
    response_model=BaseResponse[LineIdentityRuntimeConfigResponse],
)
def identity_runtime_config():
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id or liff_id == "your_liff_id_here":
        raise HTTPException(status_code=503, detail="LIFF 尚未完成設定")
    return BaseResponse(
        data=LineIdentityRuntimeConfigResponse(
            liff_id=liff_id,
            public_base_url=_safe_line_public_base_url(),
        )
    )


def _safe_line_public_base_url() -> str | None:
    value = (
        os.getenv("LINE_PUBLIC_BASE_URL", "").strip()
        or os.getenv("BASE_URL", "").strip()
    ).rstrip("/")
    if not value:
        return None
    parsed = urlsplit(value)
    is_loopback_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    if (
        (parsed.scheme != "https" and not is_loopback_http)
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return None
    return value


@public_router.post(
    "/flow/open",
    response_model=BaseResponse[LineIdentityFlowOpenResponse],
)
def open_identity_flow(payload: LineIdentityFlowOpenRequest):
    line_user_id = _verified_line_user_id(payload)
    purpose = LineIdentityFlowPurpose(payload.purpose)
    result = get_line_identity_application().open_flow(
        purpose,
        line_user_id,
        IdempotencyKey(payload.idempotency_key),
        _correlation_id("flow-open"),
    )
    return BaseResponse(
        data=LineIdentityFlowOpenResponse(
            flow_id=result.flow_id.value,
            purpose=result.purpose.value,
            expires_at=result.expires_at,
        )
    )


@public_router.post(
    "/flow/validate",
    response_model=BaseResponse[LineIdentityFlowValidationResponse],
)
def validate_identity_flow(payload: LineIdentityFlowValidationRequest):
    line_user_id = _verified_line_user_id(payload)
    snapshot = _translate_identity_errors(
        get_line_identity_application().validate_flow,
        LineIdentityFlowId(payload.flow_id),
        LineIdentityFlowPurpose(payload.purpose),
        line_user_id,
    )
    return BaseResponse(
        data=LineIdentityFlowValidationResponse(
            status="active",
            expires_at=snapshot.expires_at,
        )
    )


@public_router.post(
    "/customer/preview",
    response_model=BaseResponse[LineIdentityPreviewResponse],
)
def preview_customer(payload: CustomerIdentityRequest):
    line_user_id = _verified_line_user_id(payload)
    preview = _translate_identity_errors(
        get_line_identity_application().preview_customer,
        LineIdentityFlowId(payload.flow_id),
        line_user_id,
        CustomerIdentityProof(payload.name.strip(), payload.phone.strip()),
    )
    return BaseResponse(data=_preview_response(preview))


@public_router.post(
    "/customer/apply",
    response_model=BaseResponse[LineIdentityApplyResponse],
)
def apply_customer(payload: CustomerIdentityApplyRequest):
    line_user_id = _verified_line_user_id(payload)
    result = _translate_identity_errors(
        get_line_identity_application().apply_customer,
        LineIdentityFlowId(payload.flow_id),
        line_user_id,
        CustomerIdentityProof(payload.name.strip(), payload.phone.strip()),
        ExpectedVersion(payload.expected_version),
        PreviewFingerprint(payload.preview_fingerprint),
        _correlation_id("customer"),
    )
    publish_line_wakeup_best_effort()
    return BaseResponse(data=_apply_response(result, payload.preview_fingerprint))


@public_router.post(
    "/staff/preview",
    response_model=BaseResponse[LineIdentityPreviewResponse],
)
def preview_staff(payload: StaffIdentityRequest):
    line_user_id = _verified_line_user_id(payload)
    preview = _translate_identity_errors(
        get_line_identity_application().preview_staff,
        LineIdentityFlowId(payload.flow_id),
        line_user_id,
        StaffIdentityProof(payload.name.strip(), payload.identity_card.strip(), payload.birthday),
    )
    return BaseResponse(data=_preview_response(preview))


@public_router.post(
    "/staff/apply",
    response_model=BaseResponse[LineIdentityApplyResponse],
)
def apply_staff(payload: StaffIdentityApplyRequest):
    line_user_id = _verified_line_user_id(payload)
    result = _translate_identity_errors(
        get_line_identity_application().apply_staff,
        LineIdentityFlowId(payload.flow_id),
        line_user_id,
        StaffIdentityProof(payload.name.strip(), payload.identity_card.strip(), payload.birthday),
        ExpectedVersion(payload.expected_version),
        PreviewFingerprint(payload.preview_fingerprint),
        _correlation_id("staff"),
    )
    publish_line_wakeup_best_effort()
    return BaseResponse(data=_apply_response(result, payload.preview_fingerprint))


@public_router.post(
    "/admin/preview",
    response_model=BaseResponse[LineIdentityPreviewResponse],
)
def preview_admin(payload: AdminIdentityBindingRequest):
    line_user_id = _verified_line_user_id(payload)
    preview = _translate_identity_errors(
        get_line_identity_application().preview_admin,
        LineIdentityFlowId(payload.flow_id),
        line_user_id,
        AdminCredentialProof(payload.username.strip(), payload.password.get_secret_value()),
    )
    return BaseResponse(data=_preview_response(preview))


@public_router.post(
    "/admin/apply",
    response_model=BaseResponse[LineIdentityApplyResponse],
)
def apply_admin(payload: AdminIdentityBindingApplyRequest):
    line_user_id = _verified_line_user_id(payload)
    result = _translate_identity_errors(
        get_line_identity_application().apply_admin,
        LineIdentityFlowId(payload.flow_id),
        line_user_id,
        AdminCredentialProof(payload.username.strip(), payload.password.get_secret_value()),
        ExpectedVersion(payload.expected_version),
        PreviewFingerprint(payload.preview_fingerprint),
        _correlation_id("admin"),
    )
    publish_line_wakeup_best_effort()
    return BaseResponse(data=_apply_response(result, payload.preview_fingerprint))


@public_router.post(
    "/registration/preview",
    response_model=BaseResponse[ProvisionalRegistrationPreviewResponse],
)
def preview_provisional_registration(
    payload: ProvisionalRegistrationPreviewRequest,
    application: LineIdentityApplication = Depends(get_line_identity_application),
):
    line_user_id = _verified_line_user_id(payload)
    preview = _translate_identity_errors(
        application.preview_registration,
        _registration_intent(payload, line_user_id),
        line_user_id,
        LineIdentityFlowId(payload.flow_id) if payload.flow_id else None,
    )
    return BaseResponse(
        data=ProvisionalRegistrationPreviewResponse(
            status=preview.status,
            expected_binding_version=preview.expected_binding_version.value,
            payload_fingerprint=preview.payload_fingerprint.value,
            preview_fingerprint=preview.preview_fingerprint.value,
        )
    )


@public_router.post(
    "/registration/apply",
    response_model=BaseResponse[ProvisionalRegistrationResponse],
)
def apply_provisional_registration(
    payload: ProvisionalRegistrationRequest,
    application: LineIdentityApplication = Depends(get_line_identity_application),
):
    line_user_id = _verified_line_user_id(payload)
    receipt, binding = _apply_combined_registration(application, payload, line_user_id)
    identity_status = binding.status.value
    if receipt.worker_wakeup_required:
        publish_line_wakeup_best_effort()
    return BaseResponse(data=_registration_response(receipt, identity_status))


def _apply_combined_registration(application, payload, line_user_id):
    try:
        return application.apply_registration(
            _registration_intent(payload, line_user_id),
            line_user_id,
            LineIdentityFlowId(payload.flow_id) if payload.flow_id else None,
            ExpectedVersion(payload.expected_binding_version),
            PreviewFingerprint(payload.preview_fingerprint),
            _correlation_id("registration"),
        )
    except ProvisionalRegistrationConflictError as error:
        raise _registration_http_error(409, "registration_conflict", str(error)) from error
    except ProvisionalRegistrationDomainError as error:
        raise _registration_http_error(422, error.issue.value, str(error)) from error
    except ProvisionalRegistrationStorageError as error:
        raise _registration_http_error(503, str(error), "登記服務暫時無法使用") from error
    except (LineIdentityNotFoundError, LineIdentityConflictError) as error:
        raise _registration_http_error(409, "line_identity_conflict", str(error)) from error
    except RuntimeError as error:
        code = str(error)
        if code in {
            "customer_identity_binding_conflict",
            "line_identity_already_used_by_customer",
        }:
            raise _registration_http_error(
                409,
                code,
                "此客戶的 LINE 身分綁定已變更，請由管理端確認後再處理。",
            ) from error
        raise


def _registration_response(receipt, identity_status):
    return ProvisionalRegistrationResponse(
        registration_id=receipt.registration_id,
        client_id=receipt.client_id,
        beclass_record_id=receipt.beclass_record_id,
        client_name=receipt.client_name,
        replayed=receipt.replayed,
        identity_status=identity_status,
    )


@review_router.get(
    "",
    response_model=BaseResponse[CanonicalLineReviewPageResponse],
    dependencies=[Depends(require_line_identity_reader)],
)
def list_reviews(
    review_status: LineReviewStatus | None = LineReviewStatus.PENDING,
    review_type: LineReviewType | None = None,
    page_size: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=191),
):
    query = LineReviewListQuery(
        statuses=(review_status,) if review_status else (),
        review_types=(review_type,) if review_type else (),
        page_size=page_size,
        cursor=cursor,
    )
    page = get_line_identity_review_application().list(query)
    return BaseResponse(
        data=CanonicalLineReviewPageResponse(
            items=[_review_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )
    )


@review_router.get(
    "/numbered",
    response_model=BaseResponse[CanonicalLineReviewNumberedPageResponse],
    dependencies=[Depends(require_line_identity_reader)],
)
def list_reviews_numbered(
    review_status: LineReviewStatus | None = LineReviewStatus.PENDING,
    review_type: LineReviewType | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    query = LineReviewListQuery(
        statuses=(review_status,) if review_status else (),
        review_types=(review_type,) if review_type else (),
        page=page,
        page_size=page_size,
    )
    result = get_line_identity_review_application().list(query)
    return BaseResponse(
        data=CanonicalLineReviewNumberedPageResponse(
            items=[_review_response(item) for item in result.items],
            page=result.page or page,
            page_size=result.page_size or page_size,
            total=result.total or 0,
        )
    )


@review_router.get(
    "/summary",
    response_model=BaseResponse[CanonicalLineReviewSummaryResponse],
    dependencies=[Depends(require_line_identity_reader)],
)
def review_summary():
    stale_hours = int(os.getenv("LINE_REVIEW_STALE_HOURS", "24"))
    summary = get_line_identity_review_application().summary(stale_hours)
    return BaseResponse(
        data=CanonicalLineReviewSummaryResponse(
            pending_total=summary.pending_total,
            staff_pending=summary.staff_pending,
            rebind_pending=summary.rebind_pending,
            processed_today=summary.processed_today,
            stale_pending=summary.stale_pending,
            stale_hours=summary.stale_hours,
        )
    )


@review_router.get(
    "/{request_id}",
    response_model=BaseResponse[CanonicalLineReviewResponse],
    dependencies=[Depends(require_line_identity_reader)],
)
def review_detail(request_id: int):
    try:
        snapshot = get_line_identity_review_application().get(LineReviewRequestId(request_id))
    except LineReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return BaseResponse(data=_review_response(snapshot))


@review_router.post(
    "/{request_id}/{decision}/preview",
    response_model=BaseResponse[CanonicalLineReviewDecisionPreviewResponse],
)
def preview_review_decision(
    request_id: int,
    decision: LineReviewDecision,
    payload: CanonicalLineReviewDecisionPreviewRequest,
    principal: AdminPrincipal = Depends(require_line_identity_reviewer),
):
    command = PreviewLineReviewDecisionCommand(
        LineReviewRequestId(request_id),
        decision,
        ExpectedVersion(payload.expected_version),
        admin_actor_context(principal),
        payload.reason.strip(),
    )
    try:
        result = get_line_identity_review_application().preview(command)
    except LineReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise _review_http_conflict("line_review_version_conflict", str(error)) from error
    candidate = result.candidate
    snapshot = result.snapshot
    return BaseResponse(
        data=CanonicalLineReviewDecisionPreviewResponse(
            request_id=snapshot.request_id.value,
            decision=decision.value,
            before_status=candidate.before_status.value,
            after_status=candidate.after_status.value,
            expected_version=candidate.expected_version.value,
            resulting_version=candidate.resulting_version.value,
            subject_type=snapshot.subject_type.value if snapshot.subject_type else None,
            subject_reference=snapshot.subject_reference,
            line_user_id_masked=_mask_line_user_id(
                snapshot.line_user_id.value if snapshot.line_user_id else ""
            ),
            preview_fingerprint=candidate.fingerprint.value,
        )
    )


# Kept cohesive so HTTP conflict mapping and the mutation audit describe one command.
@review_router.post(
    "/{request_id}/{decision}/apply",
    response_model=BaseResponse[CanonicalLineReviewResponse],
)
def decide_review(
    request_id: int,
    decision: LineReviewDecision,
    payload: CanonicalLineReviewDecisionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_identity_reviewer),
):
    command = DecideLineReviewCommand(
        LineReviewRequestId(request_id),
        decision,
        ExpectedVersion(payload.expected_version),
        admin_actor_context(principal),
        payload.reason.strip(),
        PreviewFingerprint(payload.preview_fingerprint),
        IdempotencyKey(payload.idempotency_key),
        _correlation_id("review"),
    )
    try:
        result = get_line_identity_review_application().decide(command)
    except LineReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except LineReviewDataConflictError as error:
        raise _review_http_conflict(error.code, str(error)) from error
    except ValueError as error:
        raise _review_http_conflict("line_review_version_conflict", str(error)) from error
    except RuntimeError as error:
        raise _review_http_conflict("line_review_data_conflict", str(error)) from error
    request.state.audit_action = f"line.identity.review.{decision.value}"
    request.state.audit_resource_type = "line_review_request"
    request.state.audit_resource_id = str(request_id)
    publish_line_wakeup_best_effort()
    return BaseResponse(
        data=_review_response(
            result.snapshot,
            outcome=result.outcome.value,
            receipt_identity=(
                f"line-review:{result.snapshot.request_id.value}:"
                f"{result.snapshot.status.value}"
            ),
        )
    )


@review_router.post("/{request_id}/{decision}", include_in_schema=False)
def retired_direct_review_decision(
    request_id: int,
    decision: LineReviewDecision,
    principal: AdminPrincipal = Depends(require_line_identity_reviewer),
):
    del request_id, decision, principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "line_review_preview_required",
            "message": "此審核入口已退役，請先預覽再套用。",
            "retryable": False,
        },
    )


# Kept as one mapping so every public registration field has one auditable owner input.
def _registration_intent(payload, line_user_id):
    return ProvisionalRegistrationIntent(
        line_user_id=line_user_id.value,
        name=payload.name,
        phone=payload.phone,
        expected_date=payload.expected_date,
        service_days=payload.service_days,
        address=payload.address,
        gender=payload.gender,
        email=payload.email,
        birth_date=payload.birth_date,
        tel=payload.tel,
        ext=payload.ext,
        city=payload.city,
        zip_code=payload.zip_code,
        id_number=payload.id_number,
        liff_config_revision=payload.liff_config_revision,
        survey_details=payload.survey_details,
    )


def _registration_http_error(status_code, code, message):
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "retryable": status_code >= 500},
    )


def _review_http_conflict(code, message):
    return HTTPException(
        status_code=409,
        detail={"code": code, "message": message, "retryable": False},
    )


def _verified_line_user_id(payload) -> LineUserId:
    token = payload.line_id_token.strip()
    if token:
        try:
            verifier = get_liff_token_verifier()
        except ValueError as error:
            raise typed_http_error(
                503,
                "unavailable",
                "liff_verification_not_configured",
                "LINE 身分驗證服務尚未完成設定。",
                _correlation_id("liff-verification-config").value,
            ) from error
        try:
            return verifier.verify(token).line_user_id
        except InvalidLiffTokenError as error:
            raise typed_http_error(
                401,
                "forbidden",
                "liff_token_invalid",
                "LINE 登入狀態已失效或與此 LIFF 不一致，請重新登入 LINE。",
                _correlation_id("liff-token-invalid").value,
            ) from error
        except LiffVerificationUnavailableError as error:
            raise typed_http_error(
                503,
                "unavailable",
                "liff_verification_unavailable",
                "LINE 身分驗證服務暫時無法連線，請稍後再試。",
                _correlation_id("liff-verification-unavailable").value,
                retryable=True,
            ) from error
    if _development_identity_fallback_enabled():
        fallback = payload.development_line_user_id.strip()
        if fallback:
            return LineUserId(fallback)
    raise typed_http_error(
        401,
        "forbidden",
        "liff_token_required",
        "缺少有效的 LINE 登入狀態，請重新從 LINE 開啟此頁。",
        _correlation_id("liff-token-required").value,
    )


def _development_identity_fallback_enabled() -> bool:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    required = os.getenv("LIFF_REQUIRE_ID_TOKEN", "true").strip().lower()
    return app_env in {"development", "dev", "local", "test"} and required in {
        "0",
        "false",
        "no",
        "off",
    }


def _translate_identity_errors(call, *arguments):
    try:
        return call(*arguments)
    except LineIdentityNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except LineIdentityAuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except LineIdentityConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=410, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _preview_response(preview):
    candidate = preview.candidate
    candidate_response = None
    if candidate is not None:
        candidate_response = LineIdentityCandidateResponse(
            currently_bound=candidate.currently_bound_line_user_id is not None,
        )
    return LineIdentityPreviewResponse(
        status=preview.status.value,
        expected_version=preview.expected_version.value,
        preview_fingerprint=preview.preview_fingerprint.value,
        candidate=candidate_response,
    )


def _apply_response(result, preview_fingerprint):
    return LineIdentityApplyResponse(
        status=result.status.value,
        review_request_id=(result.review_request_id.value if result.review_request_id else None),
        receipt_identity=result.receipt_identity,
        preview_fingerprint=preview_fingerprint,
    )


def _review_response(snapshot, *, outcome=None, receipt_identity=None):
    return CanonicalLineReviewResponse(
        request_id=snapshot.request_id.value,
        review_type=snapshot.review_type.value,
        status=snapshot.status.value,
        version=snapshot.version.value,
        subject_type=snapshot.subject_type.value if snapshot.subject_type else None,
        subject_reference=snapshot.subject_reference,
        assigned_admin_id=snapshot.assigned_admin_id,
        due_at=snapshot.due_at,
        line_user_id_masked=_mask_line_user_id(snapshot.line_user_id.value),
        display_name=f"{snapshot.subject_type.value} #{snapshot.subject_reference}",
        decision_reason=snapshot.decision_reason,
        reviewed_by_actor_id=snapshot.reviewed_by_actor_id,
        reviewed_at=snapshot.reviewed_at,
        created_at=snapshot.created_at,
        outcome=outcome,
        receipt_identity=receipt_identity,
    )


def _mask_line_user_id(value: str) -> str:
    if len(value) <= 8:
        return value[:2] + "***"
    return value[:4] + "…" + value[-4:]


def _correlation_id(prefix: str) -> CorrelationId:
    return CorrelationId(f"line-identity:{prefix}:{uuid4()}")


__all__ = ["page_router", "public_router", "review_router"]
