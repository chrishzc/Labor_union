"""
File: historical_order_review_remediation.py
Description: 提供歷史訂單 review 更正的 authenticated Query、Preview 與 Apply 邊界。
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Path as ApiPath, UploadFile
from pymysql.err import IntegrityError, OperationalError

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_historical_order_review_remediator,
)
from api.dependencies.historical_order_review_remediation import (
    HistoricalOrderReviewRemediationApplication,
    get_historical_order_review_remediation_application,
)
from api.schemas.base import BaseResponse
from api.schemas.historical_order_review_remediation import (
    HistoricalReviewRemediationApplyBody,
    HistoricalReviewRemediationPreviewView,
    HistoricalReviewRemediationQueryView,
    HistoricalReviewRemediationReceiptView,
)
from domains.orders.historical_review_remediation import conflict_for_issue
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_review_remediation_workflow import (
    ApplyHistoricalReviewRemediation,
    HistoricalReviewRemediationWorkflowError,
)


router = APIRouter(prefix="/api/v1/orders/historical-review-remediations", tags=["Orders"])
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]


@router.get("/{review_identity}", response_model=BaseResponse[HistoricalReviewRemediationQueryView])
def query_historical_review_remediation(
    review_identity: str = ApiPath(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalOrderReviewRemediationApplication = Depends(get_historical_order_review_remediation_application),
):
    correlation = CorrelationId(f"historical-order-remediation-query:{review_identity}")
    del principal
    return _call(lambda: _query_payload(application.query(review_identity, correlation)), "成功載入歷史訂單更正資料", correlation)


@router.post("/preview", response_model=BaseResponse[HistoricalReviewRemediationPreviewView])
def preview_historical_review_remediation(
    review_identity: Annotated[str, Form(min_length=1, max_length=191)],
    expected_review_version: Annotated[int, Form(ge=0)],
    expected_remediation_version: Annotated[int, Form(ge=0)],
    reason: Annotated[str, Form(min_length=1, max_length=500)],
    evidence: Annotated[list[str], Form(min_length=1, max_length=20)],
    workbook: UploadFile = File(...),
    correlation_id: _CorrelationHeader = "historical-order-remediation-preview",
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalOrderReviewRemediationApplication = Depends(get_historical_order_review_remediation_application),
):
    correlation = CorrelationId(correlation_id)
    normalized_evidence = tuple(
        sorted(set(item.strip() for item in evidence if item.strip()))
    )
    path = _save_workbook(workbook)
    try:
        return _call(
            lambda: _preview_payload(
                application.preview(
                    review_identity.strip(),
                    path,
                    ExpectedVersion(expected_review_version),
                    ExpectedVersion(expected_remediation_version),
                    admin_actor_context(principal),
                    reason.strip(),
                    normalized_evidence,
                    correlation,
                )
            ),
            "成功產生歷史訂單更正 Preview",
            correlation,
        )
    finally:
        path.unlink(missing_ok=True)


@router.post("/apply", response_model=BaseResponse[HistoricalReviewRemediationReceiptView])
def apply_historical_review_remediation(
    review_identity: Annotated[str, Form(min_length=1, max_length=191)],
    expected_review_version: Annotated[int, Form(ge=0)],
    expected_remediation_version: Annotated[int, Form(ge=0)],
    preview_fingerprint: Annotated[str, Form(pattern=r"^[0-9a-f]{64}$")],
    reason: Annotated[str, Form(min_length=1, max_length=500)],
    evidence: Annotated[list[str], Form(min_length=1, max_length=20)],
    workbook: UploadFile = File(...),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalOrderReviewRemediationApplication = Depends(get_historical_order_review_remediation_application),
):
    path = _save_workbook(workbook)
    try:
        body = HistoricalReviewRemediationApplyBody(
            review_identity=review_identity,
            expected_review_version=expected_review_version,
            expected_remediation_version=expected_remediation_version,
            preview_fingerprint=preview_fingerprint,
            reason=reason,
            evidence=evidence,
        )
        correlation = CorrelationId(correlation_id)
        command = ApplyHistoricalReviewRemediation(
            body.review_identity.strip(),
            str(path),
            ExpectedVersion(body.expected_review_version),
            ExpectedVersion(body.expected_remediation_version),
            PreviewFingerprint(body.preview_fingerprint),
            IdempotencyKey(idempotency_key),
            admin_actor_context(principal),
            body.reason.strip(),
            tuple(sorted(set(item.strip() for item in body.evidence if item.strip()))),
            correlation,
        )
        return _call(
            lambda: _apply_payload(application, command),
            "成功提交歷史訂單人工更正",
            correlation,
        )
    finally:
        path.unlink(missing_ok=True)


def _save_workbook(workbook: UploadFile) -> Path:
    filename = (workbook.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="historical_order_correction_workbook_must_be_xlsx")
    with tempfile.NamedTemporaryFile(prefix="historical-order-remediation-", suffix=".xlsx", delete=False) as target:
        written = 0
        while chunk := workbook.file.read(1024 * 1024):
            written += len(chunk)
            if written > _MAXIMUM_WORKBOOK_BYTES:
                target.close()
                Path(target.name).unlink(missing_ok=True)
                raise HTTPException(status_code=422, detail="historical_order_correction_workbook_too_large")
            target.write(chunk)
        if written == 0:
            target.close()
            Path(target.name).unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail="historical_order_correction_workbook_empty",
            )
        return Path(target.name)


def _query_payload(query):
    context = query.context
    return {
        "review_identity": context.review_identity,
        "masked_case_identity": context.masked_case_identity,
        "issues": [_conflict_payload(conflict) for conflict in context.conflicts],
        "review_version": context.review_version,
        "remediation_version": context.remediation_version,
        "workbook_contract": {
            "contract_key": "orders.historical-review-correction",
            "contract_version": 1,
            "required_columns": ["case_no", "client_name", "status"],
            "single_row_only": True,
            "file_extension": "xlsx",
        },
        "reason_required": True,
        "evidence_required": True,
        "completion_condition": "更正來源合法採納，或由具體 successor review 接手原問題。",
        "prior_alert_active": context.prior_alert_active,
    }


def _preview_payload(preview):
    candidate = preview.candidate
    return {
        "prior_review_identity": candidate.prior_review_identity,
        "source_content_digest": candidate.source.workbook_digest,
        "outcome": candidate.disposition.value,
        "remaining_issues": [
            _conflict_payload(conflict_for_issue(code))
            for code in candidate.blockers
        ],
        "preview_fingerprint": preview.fingerprint.value,
        "review_version": preview.expected_review_version.value,
        "remediation_version": preview.expected_remediation_version.value,
    }


def _apply_payload(application, command):
    receipt = application.apply(command)
    prior = application.query(receipt.prior_review_identity, command.correlation_id).context
    successor = None
    if receipt.successor_review_identity is not None:
        successor_context = application.query(
            receipt.successor_review_identity, command.correlation_id
        ).context
        successor = {
            "review_identity": successor_context.review_identity,
            "masked_case_identity": successor_context.masked_case_identity,
            "issues": [
                _conflict_payload(conflict)
                for conflict in successor_context.conflicts
            ],
        }
    return {
        "prior_review_identity": receipt.prior_review_identity,
        "disposition": receipt.disposition,
        "receipt": {
            "remediation_receipt_identity": receipt.remediation_receipt_identity,
            "disposition": receipt.disposition,
            "source_content_digest": receipt.source_content_digest,
            "preview_fingerprint": receipt.preview_fingerprint.value,
            "resulting_remediation_version": receipt.resulting_remediation_version,
        },
        "prior_alert_active": prior.prior_alert_active,
        "successor": successor,
        "replayed": receipt.replayed,
        "readback": {
            "prior_review_identity": prior.review_identity,
            "prior_alert_active": prior.prior_alert_active,
            "remaining_issues": (
                [
                    _conflict_payload(conflict)
                    for conflict in prior.conflicts
                ]
                if prior.prior_alert_active
                else []
            ),
            "review_version": prior.review_version,
            "remediation_version": prior.remediation_version,
        },
    }


def _conflict_payload(conflict):
    return {
        "issue_code": conflict.issue_code,
        "field_path": conflict.field_path,
        "field_label": conflict.field_label,
        "masked_source_value": conflict.masked_source_value,
        "masked_current_value": conflict.masked_current_value,
        "rule": conflict.rule,
        "allowed_values": list(conflict.allowed_values),
        "process_blocker": conflict.process_blocker,
    }


def _call(operation, message, correlation):
    try:
        return BaseResponse(data=operation(), message=message)
    except HistoricalReviewRemediationWorkflowError as error:
        raise _typed_http_error(error.error) from error
    except OperationalError as error:
        retryable = int(error.args[0]) in {1205, 1213} if error.args else False
        typed = TypedError(ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL, "historical_order_remediation_unavailable" if retryable else "historical_order_remediation_failed", "歷史訂單更正暫時無法完成。" if retryable else "歷史訂單更正失敗。", correlation, retryable=retryable)
        raise _http_error(503 if retryable else 500, typed) from error
    except IntegrityError as error:
        typed = TypedError(
            ErrorCategory.CONFLICT,
            "historical_order_remediation_integrity_conflict",
            "歷史訂單更正與目前資料衝突，請重新查詢與 Preview。",
            correlation,
        )
        raise _http_error(409, typed) from error
    except (TypeError, ValueError) as error:
        typed = TypedError(ErrorCategory.VALIDATION, str(error) or "historical_order_remediation_invalid", "歷史訂單更正資料未通過驗證。", correlation)
        raise _http_error(422, typed) from error


def _typed_http_error(error):
    status = {ErrorCategory.VALIDATION: 422, ErrorCategory.FORBIDDEN: 403, ErrorCategory.NOT_FOUND: 404, ErrorCategory.DOMAIN_BLOCKED: 409, ErrorCategory.CONFLICT: 409, ErrorCategory.IDEMPOTENCY_MISMATCH: 409, ErrorCategory.UNAVAILABLE: 503, ErrorCategory.INTERNAL: 500}[error.category]
    return _http_error(status, error)


def _http_error(status, error):
    return HTTPException(status_code=status, detail={"error": {"category": error.category.value, "code": error.code, "message": error.message, "field_errors": [], "domain_blockers": list(error.domain_blockers), "retryable": error.retryable, "correlation_id": error.correlation_id.value, "current_version": None if error.current_version is None else error.current_version.value}})


__all__ = ["router"]
