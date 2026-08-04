"""Authenticated endpoints for Payroll rebuild and monthly aggregation."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Path, status

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.payroll_rebuild import (
    PayrollRebuildApplication,
    get_payroll_rebuild_application,
)
from api.schemas.base import BaseResponse
from api.schemas.jobs import JobAcceptedResponse
from api.dependencies.jobs import get_job_repository
from infrastructure.mysql.background_job_repository import (
    BackgroundJobRepository,
    JobIdempotencyConflict,
)
from api.schemas.payroll_rebuild import (
    PayrollRebuildApplyBody,
    PayrollRebuildPreviewView,
    PayrollRebuildReceiptView,
    StaffMonthlyPayrollSummaryView,
)
from infrastructure.mysql.payroll_rebuild_repository import (
    PayrollRebuildRepositoryUnavailable,
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
from subsystems.payroll.rebuild_workflow import (
    PayrollRebuildError,
    PayrollRebuildRequest,
)

router = APIRouter(prefix="/api/v1/payroll-rebuild", tags=["Payroll"])
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


# Kept cohesive because authenticated actor and command headers form the audit.
@router.post(
    "/cases/{case_no}/preview",
    response_model=BaseResponse[PayrollRebuildPreviewView],
)
def preview_payroll_rebuild(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: PayrollRebuildApplication = Depends(
        get_payroll_rebuild_application
    ),
):
    del principal
    correlation_id = CorrelationId(f"payroll-rebuild-preview:{case_no}")
    return _call(
        lambda: _preview_payload(case_no, application.preview(case_no)),
        "成功產生 Payroll rebuild Preview",
        correlation_id,
    )


@router.post(
    "/cases/{case_no}/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_payroll_rebuild(
    body: PayrollRebuildApplyBody,
    background_tasks: BackgroundTasks,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: PayrollRebuildApplication = Depends(
        get_payroll_rebuild_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    request = PayrollRebuildRequest(
        case_no,
        ExpectedVersion(body.expected_payroll_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason,
        CorrelationId(correlation_id),
    )
    
    job_id = str(uuid.uuid4())
    try:
        job_id = job_repository.enqueue_job(job_id, request.idempotency_key)
        
        def _background_worker():
            job_repository.mark_running(job_id)
            try:
                receipt = _receipt_payload(application.apply(request))
                job_repository.mark_succeeded(job_id, receipt)
            except PayrollRebuildError as error:
                job_repository.mark_failed(job_id, {"error": _materialize(error.error)})
            except PayrollRebuildRepositoryUnavailable as error:
                job_repository.mark_failed(job_id, {"error": {"category": "UNAVAILABLE" if error.retryable else "INTERNAL", "code": "transaction_failed", "message": str(error)}})
            except (TypeError, ValueError) as error:
                category, status_c = _validation_error_category(str(error) or "invalid_payroll_facts")
                job_repository.mark_failed(job_id, {"error": {"category": category.name, "code": str(error) or "invalid_payroll_facts", "message": "Payroll root facts 未通過驗證。"}})
            except Exception as error:
                job_repository.mark_failed(job_id, {"error": {"category": "INTERNAL", "code": "transaction_failed", "message": str(error)}})

        background_tasks.add_task(_background_worker)
        
    except JobIdempotencyConflict as e:
        job_id = e.job_id

    return BaseResponse(
        data=JobAcceptedResponse(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}"),
        message="202 Accepted",
    )


@router.get(
    "/staff/{staff_id}/months/{year}/{month}",
    response_model=BaseResponse[StaffMonthlyPayrollSummaryView],
)
def query_staff_monthly_payroll(
    staff_id: int = Path(..., gt=0),
    year: int = Path(..., ge=2000, le=2200),
    month: int = Path(..., ge=1, le=12),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: PayrollRebuildApplication = Depends(
        get_payroll_rebuild_application
    ),
):
    del principal
    correlation_id = CorrelationId(
        f"staff-monthly-payroll:{staff_id}:{year:04d}-{month:02d}"
    )
    return _call(
        lambda: _monthly_payload(
            application.query_staff_month(staff_id, year, month)
        ),
        "成功取得月嫂月份薪資加總",
        correlation_id,
    )


def _preview_payload(case_no, preview):
    payroll = preview.payroll
    return {
        "case_no": case_no,
        "payroll_version": preview.payroll_version,
        "assignments": [
            _assignment_payload(item) for item in payroll.assignments
        ],
        "actions": [_action_payload(item) for item in preview.actions],
        "earned_floor_fee_ntd": payroll.earned_floor_fee.amount,
        "total_payable_ntd": payroll.total_payable.amount,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _assignment_payload(assignment):
    return {
        "assignment_identity": assignment.assignment_identity,
        "staff_id": assignment.staff_id,
        "official_service_day_count": assignment.official_service_day_count,
        "actual_hours": assignment.actual_hours,
        "double_pay_hours": assignment.double_pay_hours,
        "hourly_rate_ntd": assignment.hourly_rate.amount,
        "service_salary_ntd": assignment.service_salary.amount,
        "floor_fee_allocated_ntd": assignment.floor_fee_allocated.amount,
        "effective_adjustments_ntd": assignment.effective_adjustments.amount,
        "total_payable_ntd": assignment.total_payable.amount,
    }


def _action_payload(action):
    return {
        "assignment_identity": action.assignment_identity,
        "obligation_identity": action.obligation_identity,
        "action": action.action.value,
        "before_amount_ntd": action.before_amount.amount,
        "after_amount_ntd": action.after_amount.amount,
        "delta_amount_ntd": action.delta_amount.amount,
    }


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "payroll_version": receipt.payroll_version,
        "action_count": receipt.action_count,
        "total_payable_ntd": receipt.total_payable.amount,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _monthly_payload(summary):
    return {
        "staff_id": summary.staff_id,
        "year": summary.year,
        "month": summary.month,
        "case_count": summary.case_count,
        "obligation_count": summary.obligation_count,
        "payable_total_ntd": summary.payable_total.amount,
        "receivable_total_ntd": summary.receivable_total.amount,
        "net_payable_ntd": summary.net_payable.amount,
        "obligations": [
            _monthly_obligation_payload(item) for item in summary.obligations
        ],
    }


def _monthly_obligation_payload(item):
    return {
        "obligation_identity": item.obligation_identity,
        "case_no": item.case_no,
        "assignment_id": item.assignment_id,
        "staff_id": item.staff_id,
        "due_date": item.due_date,
        "direction": item.direction.value,
        "amount_due_ntd": item.amount_due.amount,
    }


def _call(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except PayrollRebuildError as error:
        raise _typed_http_error(error.error) from error
    except PayrollRebuildRepositoryUnavailable as error:
        raise _storage_http_error(error, correlation_id) from error
    except (TypeError, ValueError) as error:
        raise _validation_http_error(error, correlation_id) from error
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_http_error(correlation_id) from error


def _typed_http_error(error):
    status = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.NOT_FOUND: 404,
    }.get(error.category, 500)
    return _http_error(status, error)


def _storage_http_error(error, correlation_id):
    code = "transaction_failed"
    category = ErrorCategory.UNAVAILABLE if error.retryable else ErrorCategory.INTERNAL
    typed = TypedError(
        category,
        code,
        "Payroll rebuild 暫時無法完成。" if error.retryable else "Payroll rebuild 失敗。",
        correlation_id,
        retryable=error.retryable,
    )
    headers = {"Retry-After": "1"} if error.retryable else None
    return _http_error(503 if error.retryable else 500, typed, headers)


def _validation_http_error(error, correlation_id):
    code = str(error) or "invalid_payroll_facts"
    category, status = _validation_error_category(code)
    typed = TypedError(
        category,
        code,
        "Payroll root facts 未通過驗證。",
        correlation_id,
    )
    return _http_error(status, typed)


def _validation_error_category(code):
    if code == "payroll_candidate_stale":
        return ErrorCategory.CONFLICT, 409
    if code == "staff_obligation_frozen":
        return ErrorCategory.DOMAIN_BLOCKED, 409
    return ErrorCategory.VALIDATION, 422


def _internal_http_error(correlation_id):
    typed = TypedError(
        ErrorCategory.INTERNAL,
        "transaction_failed",
        "Payroll rebuild 交易失敗。",
        correlation_id,
    )
    return _http_error(500, typed)


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
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


__all__ = ["router"]
