"""Authenticated BeClass import review Query, Preview, and Apply."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.beclass_import_review import (
    BeClassImportReviewApplication,
    get_beclass_import_review_application,
)
from api.schemas.base import BaseResponse
from api.schemas.beclass_import_review import (
    BeClassImportReviewApplyBody,
    BeClassImportReviewIntentBody,
    BeClassImportReviewPreviewView,
    BeClassImportReviewQueryView,
    BeClassImportReviewReceiptView,
)
from domains.case_import.beclass_import_review import (
    BeClassImportReviewIntent,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.case_import.beclass_import_review_workflow import (
    ApplyBeClassImportReview,
    BeClassImportReviewWorkflowError,
)

router = APIRouter(
    prefix="/api/v1/beclass-import-reviews",
    tags=["Case Import"],
)
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


@router.get(
    "/{review_identity}",
    response_model=BaseResponse[BeClassImportReviewQueryView],
)
def query_beclass_import_review(
    review_identity: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: BeClassImportReviewApplication = Depends(
        get_beclass_import_review_application
    ),
):
    del principal
    correlation = CorrelationId(f"beclass-review-query:{review_identity}")
    return _call(
        lambda: _query_payload(application.query(review_identity, correlation)),
        "成功載入 BeClass 匯入待修正資料",
        correlation,
    )


@router.post(
    "/preview",
    response_model=BaseResponse[BeClassImportReviewPreviewView],
)
def preview_beclass_import_review(
    body: BeClassImportReviewIntentBody,
    correlation_id: _CorrelationHeader = "beclass-review-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: BeClassImportReviewApplication = Depends(
        get_beclass_import_review_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_intent(body), correlation)
        ),
        "成功產生 BeClass 匯入修正 Preview",
        correlation,
    )


@router.post(
    "/apply",
    response_model=BaseResponse[BeClassImportReviewReceiptView],
)
def apply_beclass_import_review(
    body: BeClassImportReviewApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: BeClassImportReviewApplication = Depends(
        get_beclass_import_review_application
    ),
):
    correlation = CorrelationId(correlation_id)
    command = ApplyBeClassImportReview(
        _intent(body),
        ExpectedVersion(body.expected_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        correlation,
    )
    return _call(
        lambda: _materialize(application.apply(command)),
        "成功修正 BeClass 匯入資料並寫入正式資料",
        correlation,
    )


def _intent(body):
    return BeClassImportReviewIntent(
        body.review_identity.strip(),
        dict(body.corrected_fields),
        tuple(sorted(set(item.strip() for item in body.resolved_issue_codes))),
    )


def _query_payload(query):
    facts = query.facts
    return {
        "review_identity": facts.root.review_identity,
        "source_kind": facts.root.source_kind.value,
        "source_payload": dict(facts.root.source_payload),
        "issue_codes": list(facts.root.issue_codes),
        "review_version": facts.review_version,
        "status": facts.status.value,
        "effective_payload": dict(facts.effective_payload),
    }


def _preview_payload(preview):
    return {
        "candidate": {
            "review_identity": preview.candidate.review_identity,
            "source_kind": preview.candidate.source_kind.value,
            "resulting_version": preview.candidate.resulting_version,
            "corrected_payload": dict(preview.candidate.corrected_payload),
            "resolved_issue_codes": list(
                preview.candidate.resolved_issue_codes
            ),
            "candidate_fingerprint": preview.candidate.fingerprint.value,
        },
        "expected_version": preview.expected_version.value,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except BeClassImportReviewWorkflowError as error:
        raise _typed_http_error(error.error) from error
    except OperationalError as error:
        raise _mysql_http_error(error, correlation) from error
    except (TypeError, ValueError) as error:
        raise _validation_http_error(error, correlation) from error
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_http_error(correlation) from error


def _typed_http_error(error):
    status = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.UNAVAILABLE: 503,
        ErrorCategory.INTERNAL: 500,
    }[error.category]
    headers = {"Retry-After": "1"} if error.retryable else None
    return _http_error(status, error, headers)


def _mysql_http_error(error, correlation):
    mysql_code = int(error.args[0]) if error.args else 0
    retryable = mysql_code in {1205, 1213}
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
        "downstream_unavailable" if retryable else "transaction_failed",
        "BeClass 匯入修正暫時無法完成。" if retryable else "BeClass 匯入修正失敗。",
        correlation,
        retryable=retryable,
    )
    return _http_error(503 if retryable else 500, typed)


def _validation_http_error(error, correlation):
    code = str(error) or "invalid_beclass_import_review_request"
    typed = TypedError(
        ErrorCategory.VALIDATION,
        code,
        "BeClass 匯入修正資料未通過驗證。",
        correlation,
    )
    return _http_error(422, typed)


def _internal_http_error(correlation):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "beclass_import_review_internal_error",
            "BeClass 匯入修正處理失敗。",
            correlation,
        ),
    )


def _http_error(status, error, headers=None):
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error)},
        headers=headers,
    )


def _materialize(value):
    if isinstance(
        value,
        (CorrelationId, ExpectedVersion, IdempotencyKey, PreviewFingerprint),
    ):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _materialize(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


__all__ = ["router"]
