"""
File: staff_availability.py
Description: 提供 Staff Availability authenticated Query、Preview、Apply 與 Global typed error 邊界。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import admin_actor_context, require_admin
from api.dependencies.staff_availability import (
    StaffAvailabilityApplication,
    get_staff_availability_application,
)
from api.schemas.base import BaseResponse
from api.schemas.staff_availability import (
    StaffAvailabilityApplyBody,
    StaffAvailabilityIntentBody,
    StaffAvailabilityPreviewView,
    StaffAvailabilityReceiptView,
    StaffUnavailabilityBlockView,
)
from domains.scheduling.staff_availability import (
    StaffAvailabilityDomainError,
    StaffAvailabilityErrorCode,
    StaffAvailabilityIntent,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.staff_availability_workflow import (
    StaffAvailabilityApplyRequest,
    StaffAvailabilityPreviewRequest,
    StaffAvailabilityQuery,
)

router = APIRouter(
    prefix="/api/v1/scheduling/staff",
    tags=["Scheduling Staff Availability"],
)
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_SCHEMA_NOT_READY_MYSQL_CODES = frozenset({1054, 1146})


@router.get(
    "/{staff_id}/availability-blocks",
    response_model=BaseResponse[list[StaffUnavailabilityBlockView]],
)
def query_staff_availability_blocks(
    staff_id: int = Path(..., gt=0),
    range_start: date = Query(...),
    range_end: date = Query(...),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffAvailabilityApplication = Depends(
        get_staff_availability_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id or uuid4().hex)
    return _call(
        lambda: BaseResponse(
            data=[_block_payload(item) for item in application.query(StaffAvailabilityQuery(staff_id, range_start, range_end))],
            message="成功取得月嫂不可服務期間",
        ),
        correlation,
    )


@router.post(
    "/{staff_id}/availability-blocks/preview",
    response_model=BaseResponse[StaffAvailabilityPreviewView],
)
def preview_staff_availability_change(
    body: StaffAvailabilityIntentBody,
    staff_id: int = Path(..., gt=0),
    correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffAvailabilityApplication = Depends(
        get_staff_availability_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id or uuid4().hex)
    return _call(
        lambda: BaseResponse(
            data=_preview_payload(
                application.preview(
                    StaffAvailabilityPreviewRequest(_intent(staff_id, body))
                )
            ),
            message="成功產生月嫂不可服務期間預覽",
        ),
        correlation,
    )


@router.post(
    "/{staff_id}/availability-blocks/apply",
    response_model=BaseResponse[StaffAvailabilityReceiptView],
)
def apply_staff_availability_change(
    body: StaffAvailabilityApplyBody,
    staff_id: int = Path(..., gt=0),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffAvailabilityApplication = Depends(
        get_staff_availability_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _apply_response(
            application,
            staff_id,
            body,
            idempotency_key,
            principal,
            correlation,
        ),
        correlation,
    )


def _apply_response(application, staff_id, body, idempotency_key, principal, correlation):
    request = _apply_request(
        staff_id,
        body,
        idempotency_key,
        principal,
        correlation,
    )
    return BaseResponse(
        data=_receipt_payload(application.apply(request)),
        message="成功套用月嫂不可服務期間異動",
    )


def _apply_request(staff_id, body, idempotency_key, principal, correlation):
    return StaffAvailabilityApplyRequest(
        _intent(staff_id, body),
        ExpectedVersion(body.expected_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        admin_actor_context(principal),
        correlation,
    )


def _intent(staff_id, body):
    return StaffAvailabilityIntent(
        body.action,
        staff_id,
        body.reason.strip(),
        body.start_date,
        body.end_date,
        body.block_id,
        body.resume_date,
    )


def _preview_payload(preview):
    candidate = preview.candidate
    return {
        "staff_id": preview.staff_id,
        "action": preview.action,
        "source_version": preview.source_version,
        "target_block": _block_payload(preview.target_block) if preview.target_block else None,
        "candidate_kind": candidate.kind if candidate else None,
        "candidate_start_date": candidate.start_date if candidate else None,
        "candidate_end_date": candidate.end_date if candidate else None,
        "blockers": list(preview.blockers),
        "can_apply": preview.can_apply,
        "preview_fingerprint": preview.preview_fingerprint.value,
    }


def _receipt_payload(receipt):
    return {
        "staff_id": receipt.staff_id,
        "action": receipt.action,
        "block": _block_payload(receipt.block),
        "aggregate_version": receipt.aggregate_version,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "idempotency_key": receipt.idempotency_key.value,
    }


def _block_payload(block):
    return {
        "block_id": block.block_id,
        "staff_id": block.staff_id,
        "kind": block.kind,
        "start_date": block.start_date,
        "end_date": block.end_date,
        "status": block.status,
        "reason": block.reason,
    }


def _call(operation, correlation):
    try:
        return operation()
    except StaffAvailabilityDomainError as error:
        _raise_domain_error(error, correlation)
    except (OperationalError, ProgrammingError) as error:
        _raise_mysql_error(error, correlation)
    except (TypeError, ValueError) as error:
        _raise_validation_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        raise _http_error(
            500,
            TypedError(
                ErrorCategory.INTERNAL,
                "staff_availability_internal_error",
                "月嫂不可服務期間處理失敗。",
                correlation,
            ),
        ) from error


def _raise_domain_error(error, correlation):
    not_found = error.code in {
        StaffAvailabilityErrorCode.STAFF_NOT_FOUND,
        StaffAvailabilityErrorCode.BLOCK_NOT_FOUND,
    }
    validation = error.code is StaffAvailabilityErrorCode.INVALID_INTENT
    idempotency_mismatch = error.code is StaffAvailabilityErrorCode.IDEMPOTENCY_CONFLICT
    category = (
        ErrorCategory.NOT_FOUND
        if not_found
        else ErrorCategory.VALIDATION
        if validation
        else ErrorCategory.IDEMPOTENCY_MISMATCH
        if idempotency_mismatch
        else ErrorCategory.CONFLICT
    )
    typed = TypedError(
        category,
        error.code.value,
        "月嫂不可服務期間異動未通過。",
        correlation,
        domain_blockers=tuple(sorted(set(error.blockers))),
        current_version=_current_version(error.blockers),
    )
    raise _http_error(404 if not_found else 422 if validation else 409, typed)


def _raise_validation_error(error, correlation):
    typed = TypedError(
        ErrorCategory.VALIDATION,
        StaffAvailabilityErrorCode.INVALID_INTENT.value,
        "月嫂不可服務期間輸入無效。",
        correlation,
    )
    raise _http_error(422, typed) from error


def _raise_mysql_error(error, correlation):
    mysql_code = _mysql_error_code(error)
    schema_not_ready = mysql_code in _SCHEMA_NOT_READY_MYSQL_CODES
    retryable = mysql_code in _RETRYABLE_MYSQL_CODES
    if schema_not_ready:
        code = "staff_availability_schema_not_ready"
    elif retryable:
        code = "staff_availability_temporarily_unavailable"
    else:
        code = "staff_availability_database_error"
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if schema_not_ready or retryable else ErrorCategory.INTERNAL,
        code,
        "月嫂不可服務期間資料庫暫時無法使用。",
        correlation,
        retryable=retryable,
    )
    raise _http_error(503 if schema_not_ready or retryable else 500, typed) from error


def _mysql_error_code(error) -> int:
    if not error.args:
        return 0
    try:
        return int(error.args[0])
    except (TypeError, ValueError):
        return 0


def _http_error(status_code, error):
    return HTTPException(
        status_code=status_code,
        detail={"error": _typed_error_payload(error)},
    )


def _typed_error_payload(error):
    return {
        "category": error.category.value,
        "code": error.code,
        "message": error.message,
        "correlation_id": error.correlation_id.value,
        "field_errors": [
            {"field": item.field, "code": item.code, "message": item.message}
            for item in error.field_errors
        ],
        "domain_blockers": list(error.domain_blockers),
        "retryable": error.retryable,
        "current_version": error.current_version.value if error.current_version else None,
    }


def _current_version(blockers):
    for blocker in blockers:
        prefix = "current_version:"
        if blocker.startswith(prefix):
            value = blocker[len(prefix) :]
            if value.isdigit():
                return ExpectedVersion(int(value))
    return None


__all__ = ["router"]
