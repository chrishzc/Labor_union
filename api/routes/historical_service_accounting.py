"""Authenticated Q/P/A API for historical service-day accounting."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.historical_service_accounting import (
    get_historical_service_accounting_workflow,
    get_historical_precision_restart_workflow,
)
from api.schemas.base import BaseResponse
from api.schemas.historical_service_accounting import (
    HistoricalServiceAccountingApplyBody,
    HistoricalServiceAccountingPreviewBody,
    HistoricalServiceAccountingPreviewView,
    HistoricalServiceAccountingQueryView,
    HistoricalServiceAccountingReceiptView,
    HistoricalPrecisionRestartApplyBody,
    HistoricalPrecisionRestartPreviewBody,
    HistoricalPrecisionRestartPreviewView,
    HistoricalPrecisionRestartQueryView,
    HistoricalPrecisionRestartReceiptView,
)
from domains.orders.historical_precision_restart import HistoricalPrecisionRestartIntent
from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_service_accounting_workflow import (
    ApplyHistoricalServiceAccounting,
    ConfirmHistoricalServiceDaysIntent,
    HistoricalServiceAccountingError,
)
from subsystems.orders.historical_precision_restart_workflow import (
    ApplyHistoricalPrecisionRestart,
    HistoricalPrecisionRestartError,
)


router = APIRouter(
    prefix="/api/v1/orders/{case_no}/historical-service-accounting",
    tags=["Orders Historical Accounting"],
)
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]


@router.get("", response_model=BaseResponse[HistoricalServiceAccountingQueryView])
def query_historical_service_accounting(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_historical_service_accounting_workflow),
):
    del principal
    correlation = CorrelationId(f"historical-service-accounting-query:{case_no}")
    return _call(lambda: _query_view(workflow.query(case_no.strip())), "成功取得歷史服務帳務資料", correlation)


@router.post("/preview", response_model=BaseResponse[HistoricalServiceAccountingPreviewView])
def preview_historical_service_accounting(
    body: HistoricalServiceAccountingPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "historical-service-accounting-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_historical_service_accounting_workflow),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(lambda: _preview_view(workflow.preview(_intent(case_no, body))), "歷史服務帳務 Preview 已完成", correlation)


@router.post("/apply", response_model=BaseResponse[HistoricalServiceAccountingReceiptView])
def apply_historical_service_accounting(
    body: HistoricalServiceAccountingApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_historical_service_accounting_workflow),
):
    correlation = CorrelationId(correlation_id)
    request = ApplyHistoricalServiceAccounting(
        _intent(case_no, body),
        body.expected_lifecycle_version,
        body.expected_historical_day_revision,
        body.expected_client_finance_version,
        body.expected_payroll_version,
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        correlation,
    )
    return _call(lambda: _receipt_view(workflow.apply(request)), "歷史服務帳務 Apply 已完成", correlation)


@router.get("/precision-restart", response_model=BaseResponse[HistoricalPrecisionRestartQueryView])
def query_historical_precision_restart(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_historical_precision_restart_workflow),
):
    del principal
    correlation = CorrelationId(f"historical-precision-restart-query:{case_no}")
    return _call(lambda: _precision_query_view(workflow.query(case_no.strip())), "成功取得重啟正常流程條件", correlation)


@router.post("/precision-restart/preview", response_model=BaseResponse[HistoricalPrecisionRestartPreviewView])
def preview_historical_precision_restart(
    body: HistoricalPrecisionRestartPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "historical-precision-restart-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_historical_precision_restart_workflow),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(lambda: _precision_preview_view(workflow.preview(_precision_intent(case_no, body))), "重啟正常流程 Preview 已完成", correlation)


@router.post("/precision-restart/apply", response_model=BaseResponse[HistoricalPrecisionRestartReceiptView])
def apply_historical_precision_restart(
    body: HistoricalPrecisionRestartApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_historical_precision_restart_workflow),
):
    correlation = CorrelationId(correlation_id)
    request = ApplyHistoricalPrecisionRestart(
        _precision_intent(case_no, body), body.expected_order_version, body.expected_scheduling_version,
        body.expected_historical_day_revision, body.expected_confirmed_service_date_version,
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key), ActorContext(str(principal.username or "").strip()),
        body.reason.strip(), correlation,
    )
    return _call(lambda: _precision_receipt_view(workflow.apply(request)), "重啟正常流程 Apply 已完成", correlation)


def _intent(case_no, body):
    return ConfirmHistoricalServiceDaysIntent(
        case_no.strip(),
        tuple(
            HistoricalActualServiceDaysInput(
                item.assignment_identity.strip(), item.staff_id, item.actual_service_days
            )
            for item in body.caregivers
        ),
    )


def _precision_intent(case_no, body):
    del body
    return HistoricalPrecisionRestartIntent(case_no.strip())


def _precision_query_view(preview):
    facts = preview.domain.facts
    return {
        "case_no": facts.case_no, "lifecycle_status": facts.lifecycle_status.value,
        "order_version": facts.order_version, "scheduling_version": facts.scheduling_version,
        "client_finance_version": facts.client_finance_version, "payroll_version": facts.payroll_version,
        "historical_day_revision": facts.historical_day_revision,
        "confirmed_service_date_version": facts.confirmed_service_date_version,
        "planned_start_date": facts.planned_start_date, "actual_start_date": facts.actual_start_date,
        "contracted_service_days": facts.contracted_service_days,
        "assignments": [{"assignment_identity": item.assignment_identity, "staff_id": item.staff_id, "staff_name": item.staff_name} for item in facts.assignments],
        "blockers": list(preview.domain.blockers),
    }


def _precision_preview_view(preview):
    value = _precision_query_view(preview)
    value.update({
        "target_status": preview.domain.target_status.value,
        "actual_end_date": preview.domain.actual_end_date,
        "official_service_dates": [],
        "client_finance_resulting_version": preview.domain.facts.client_finance_version,
        "payroll_resulting_version": preview.domain.facts.payroll_version,
        "preview_fingerprint": preview.fingerprint.value,
    })
    return value


def _precision_receipt_view(receipt):
    return {**{name: getattr(receipt, name) for name in (
        "case_no", "lifecycle_status", "order_version", "scheduling_version", "scheduling_generation",
        "client_finance_version", "payroll_version", "historical_day_revision", "replayed",
    )}, "preview_fingerprint": receipt.preview_fingerprint.value}


def _query_view(facts):
    return {
        "case_no": facts.case_no,
        "lifecycle_status": facts.lifecycle_status.value,
        "lifecycle_version": facts.lifecycle_version,
        "adoption_receipt_id": facts.adoption_receipt_id,
        "adoption_source_identity": facts.adoption_source_identity,
        "historical_day_revision": facts.historical_day_revision,
        "client_finance_version": facts.client_finance_version,
        "payroll_version": facts.payroll_version,
        "contracted_service_days": facts.contracted_service_days,
        "service_hours_per_day": facts.service_hours_per_day,
        "contractual_floor_fee_ntd": facts.contractual_floor_fee.amount,
        "client_identity_status": facts.client_identity_status,
        "assignments": [
            {
                "assignment_identity": item.assignment_identity,
                "staff_id": item.staff_id,
                "staff_name": item.staff_name,
                "policy_version": item.rate_snapshot.policy_version,
                "policy_kind": item.rate_snapshot.policy_kind.value,
                "hourly_rate_ntd": item.rate_snapshot.hourly_rate.amount,
            }
            for item in facts.assignments
        ],
    }


def _preview_view(candidate):
    return {
        "facts": _query_view(candidate.facts),
        "total_actual_service_days": candidate.service_days.total_actual_service_days,
        "total_actual_service_hours": str(candidate.service_days.total_actual_service_hours),
        "historical_floor_fee_ntd": candidate.service_days.historical_floor_fee_ntd,
        "historical_double_pay_days": candidate.service_days.historical_double_pay_days,
        "historical_double_pay_hours": str(candidate.service_days.historical_double_pay_hours),
        "allocations": [
            {
                "assignment_identity": item.assignment_identity,
                "staff_id": item.staff_id,
                "actual_service_days": item.actual_service_days,
                "actual_service_hours": str(item.actual_service_hours),
                "floor_fee_ntd": item.floor_fee_ntd,
            }
            for item in candidate.service_days.allocations
        ],
        "payroll_assignments": [
            {
                "assignment_identity": item.assignment_identity,
                "staff_id": item.staff_id,
                "actual_service_days": item.actual_service_days,
                "actual_hours": item.actual_hours,
                "double_pay_hours": item.double_pay_hours,
                "hourly_rate_ntd": item.hourly_rate.amount,
                "service_salary_ntd": item.service_salary.amount,
                "floor_fee_allocated_ntd": item.floor_fee_allocated.amount,
                "effective_adjustments_ntd": item.effective_adjustments.amount,
                "total_payable_ntd": item.total_payable.amount,
            }
            for item in candidate.payroll.assignments
        ],
        "staff_obligation_amount_ntd": candidate.payroll.total_payable.amount,
        "client_obligation_amount_ntd": candidate.client_finance.total_receivable.amount,
        "client_service_receivable_ntd": candidate.client_finance.service_receivable.amount,
        "client_subsidy_hours": candidate.client_finance.subsidy_hours,
        "client_self_pay_service_hours": candidate.client_finance.self_pay_service_hours,
        "preview_fingerprint": candidate.fingerprint.value,
    }


def _receipt_view(receipt):
    return {
        "case_no": receipt.case_no,
        "resulting_historical_day_revision": receipt.resulting_historical_day_revision,
        "resulting_client_finance_version": receipt.resulting_client_finance_version,
        "resulting_payroll_version": receipt.resulting_payroll_version,
        "total_actual_service_days": receipt.total_actual_service_days,
        "client_obligation_amount_ntd": receipt.client_obligation_amount_ntd,
        "staff_obligation_amount_ntd": receipt.staff_obligation_amount_ntd,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "replayed": receipt.replayed,
    }


def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except (HistoricalServiceAccountingError, HistoricalPrecisionRestartError) as error:
        _raise(error.error)
    except ValueError as error:
        code = str(error) or "historical_actual_service_days_invalid"
        status = 404 if code == "historical_order_not_found" else 422
        category = ErrorCategory.NOT_FOUND if status == 404 else ErrorCategory.VALIDATION
        _raise(TypedError(category, code, "歷史服務帳務資料未通過驗證。", correlation))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={"error": {"category": "internal", "code": "transaction_failed", "message": "歷史服務帳務交易失敗。", "correlation_id": correlation.value}},
        ) from error


def _raise(error):
    status = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.UNAVAILABLE: 503,
        ErrorCategory.INTERNAL: 500,
    }[error.category]
    raise HTTPException(status_code=status, detail={"error": _typed_payload(error)})


def _typed_payload(error):
    return {
        "category": error.category.value,
        "code": error.code,
        "message": error.message,
        "field_errors": [],
        "domain_blockers": list(error.domain_blockers),
        "retryable": error.retryable,
        "correlation_id": error.correlation_id.value,
        "current_version": None if error.current_version is None else error.current_version.value,
    }


__all__ = ["router"]
