"""
File: caregiver_availability_locks.py
Description: 提供等待訂金檔期鎖 typed Preview／Apply，並回傳可處理的業務阻擋。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.dependencies.admin_auth import require_system_admin
from api.schemas.base import BaseResponse
from api.schemas.waiting_deposit_lock import (
    WaitingDepositLockApplyBody,
    WaitingDepositLockPreviewView,
    WaitingDepositLockReleaseApplyBody,
    WaitingDepositLockReleasePreviewView,
    WaitingDepositLockReleaseReceiptView,
    WaitingDepositLockReceiptView,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.availability_lock_release_workflow import (
    preview_caregiver_availability_lock_release,
    release_caregiver_availability_lock,
)
from subsystems.scheduling.availability_lock_acquisition_workflow import (
    acquire_caregiver_availability_lock,
    preview_caregiver_availability_lock,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.scheduling import availability_lock_acquisition_workflow as _lock_acquisition
from subsystems.scheduling import availability_lock_release_workflow as _lock_release


_lock_acquisition.get_connection = get_connection
_lock_release.get_connection = get_connection


router = APIRouter(
    prefix="/api/v1/orders",
    tags=["Caregiver availability locks"],
)
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=100),
]


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcquireAvailabilityLockRequest(_StrictRequest):
    event_key: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)


class ReleaseAvailabilityLockRequest(AcquireAvailabilityLockRequest):
    reason: str = Field(..., min_length=1)


class AssignmentTerm(_StrictRequest):
    segment_id: int = Field(..., strict=True, gt=0)
    hourly_rate: Decimal = Field(..., ge=0)
    floor_fee_allocated: Decimal = Field(..., ge=0)

    @field_validator("hourly_rate", "floor_fee_allocated", mode="before")
    @classmethod
    def _reject_float_money(cls, value: Any) -> Any:
        if isinstance(value, (bool, float)):
            raise ValueError("money values must not be bool or float")
        return value


class ConvertAvailabilityLockRequest(ReleaseAvailabilityLockRequest):
    assignment_terms: list[AssignmentTerm] = Field(..., min_length=1, max_length=4)


def _service_response(result: dict[str, Any], message: str) -> BaseResponse[dict[str, Any]]:
    return BaseResponse(data=result, message=message)


def _service_error(exc: Exception, operation: str) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(
        status_code=500,
        detail=f"Unexpected error during availability lock {operation}",
    )


def _require_actor(principal: AdminPrincipal, actor: str) -> None:
    if str(principal.username or "").strip() != actor.strip():
        raise HTTPException(
            status_code=403,
            detail="actor does not match authenticated principal",
        )


@router.post(
    "/{case_no}/matching-plans/{plan_id}/waiting-deposit-lock/acquire/preview",
    response_model=BaseResponse[WaitingDepositLockPreviewView],
)
def preview_waiting_deposit_lock_acquisition(
    case_no: str = Path(..., min_length=1),
    plan_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    correlation = CorrelationId(f"waiting-lock-preview:{case_no}:{plan_id}")
    return _call_waiting_lock(
        lambda: preview_caregiver_availability_lock(case_no, plan_id),
        "成功產生等待訂金檔期鎖 Preview",
        correlation,
    )


@router.post(
    "/{case_no}/matching-plans/{plan_id}/waiting-deposit-lock/acquire/apply",
    response_model=BaseResponse[WaitingDepositLockReceiptView],
)
def apply_waiting_deposit_lock_acquisition(
    request: WaitingDepositLockApplyBody,
    case_no: str = Path(..., min_length=1),
    plan_id: int = Path(..., gt=0),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    actor = str(principal.username or "").strip()
    correlation = CorrelationId(correlation_id)
    return _call_waiting_lock(
        lambda: acquire_caregiver_availability_lock(
            case_no,
            plan_id,
            idempotency_key,
            actor,
            request.preview_fingerprint,
        ),
        "成功鎖定服務日期與七日緩衝",
        correlation,
    )


@router.post(
    "/{case_no}/matching-plans/{plan_id}/availability-lock/acquire",
    response_model=BaseResponse[None],
)
def acquire_availability_lock(
    request: AcquireAvailabilityLockRequest,
    case_no: str = Path(..., min_length=1),
    plan_id: int = Path(..., strict=True, gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
) -> BaseResponse[None]:
    _require_actor(principal, request.actor)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_waiting_deposit_lock_acquire_retired",
            "message": "Use waiting-deposit-lock Preview and Apply.",
            "preview_path": (
                f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/"
                "waiting-deposit-lock/acquire/preview"
            ),
            "apply_path": (
                f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/"
                "waiting-deposit-lock/acquire/apply"
            ),
        },
    )


@router.post(
    "/{case_no}/matching-plans/{plan_id}/waiting-deposit-locks/{lock_id}/release/preview",
    response_model=BaseResponse[WaitingDepositLockReleasePreviewView],
)
def preview_waiting_deposit_lock_release(
    case_no: str = Path(..., min_length=1),
    plan_id: int = Path(..., strict=True, gt=0),
    lock_id: int = Path(..., strict=True, gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    correlation = CorrelationId(
        f"waiting-lock-release-preview:{case_no}:{plan_id}:{lock_id}"
    )
    return _call_waiting_lock(
        lambda: preview_caregiver_availability_lock_release(
            case_no,
            plan_id,
            lock_id,
        ),
        "成功產生等待訂金檔期鎖解除 Preview",
        correlation,
    )


@router.post(
    "/{case_no}/matching-plans/{plan_id}/waiting-deposit-locks/{lock_id}/release/apply",
    response_model=BaseResponse[WaitingDepositLockReleaseReceiptView],
)
def apply_waiting_deposit_lock_release(
    request: WaitingDepositLockReleaseApplyBody,
    case_no: str = Path(..., min_length=1),
    plan_id: int = Path(..., strict=True, gt=0),
    lock_id: int = Path(..., strict=True, gt=0),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    actor = str(principal.username or "").strip()
    correlation = CorrelationId(correlation_id)
    return _call_waiting_lock(
        lambda: release_caregiver_availability_lock(
            case_no=case_no,
            plan_id=plan_id,
            lock_id=lock_id,
            event_key=idempotency_key,
            actor=actor,
            reason=request.reason,
            expected_preview_fingerprint=request.preview_fingerprint,
        ),
        "成功解除等待訂金檔期鎖",
        correlation,
    )


@router.post(
    "/{case_no}/matching-plans/{plan_id}/availability-locks/{lock_id}/release",
    response_model=BaseResponse[None],
)
def release_availability_lock(
    request: ReleaseAvailabilityLockRequest,
    case_no: str = Path(..., min_length=1),
    plan_id: int = Path(..., strict=True, gt=0),
    lock_id: int = Path(..., strict=True, gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
) -> BaseResponse[None]:
    _require_actor(principal, request.actor)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_waiting_deposit_lock_release_retired",
            "message": "Use waiting-deposit-lock release Preview and Apply.",
            "preview_path": (
                f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/"
                f"waiting-deposit-locks/{lock_id}/release/preview"
            ),
            "apply_path": (
                f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/"
                f"waiting-deposit-locks/{lock_id}/release/apply"
            ),
        },
    )


@router.post(
    "/{case_no}/availability-locks/{lock_id}/convert",
    response_model=BaseResponse[None],
)
def convert_availability_lock(
    request: ConvertAvailabilityLockRequest,
    case_no: str = Path(..., min_length=1),
    lock_id: int = Path(..., strict=True, gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
) -> BaseResponse[None]:
    _require_actor(principal, request.actor)
    del lock_id
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_availability_lock_conversion_retired",
            "message": "Use Assignment Plan Preview and Apply.",
            "query_path": f"/api/v1/orders/{case_no}/assignment-plan",
            "preview_path": f"/api/v1/orders/{case_no}/assignment-plan/preview",
            "apply_path": f"/api/v1/orders/{case_no}/assignment-plan/apply",
        },
    )


def _call_waiting_lock(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except ValueError as error:
        raise _waiting_lock_value_error(error, correlation) from error
    except HTTPException:
        raise
    except Exception as error:
        typed = TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "等待訂金檔期鎖交易失敗。",
            correlation,
        )
        raise _waiting_lock_http_error(500, typed) from error


def _waiting_lock_value_error(error, correlation):
    message = str(error)
    if message == "stale_preview":
        return _typed_waiting_lock_error(
            ErrorCategory.CONFLICT,
            "stale_preview",
            "檔期或配對方案已變更，請重新產生 Preview。",
            correlation,
        )
    if message.startswith('{"conflicts":'):
        return _typed_waiting_lock_error(
            ErrorCategory.CONFLICT,
            "waiting_lock_conflict",
            "服務日期或七日緩衝與既有檔期衝突。",
            correlation,
            blockers=("waiting_lock_conflict",),
        )
    if "not found" in message:
        return _typed_waiting_lock_error(
            ErrorCategory.NOT_FOUND,
            "case_not_found",
            "找不到案件或配對方案。",
            correlation,
        )
    if "active proposed plan" in message or "negotiation stage" in message:
        return _typed_waiting_lock_error(
            ErrorCategory.DOMAIN_BLOCKED,
            "invalid_scheduling_intent",
            "目前配對方案狀態不允許鎖定檔期。",
            correlation,
            blockers=("invalid_scheduling_intent",),
        )
    if message == "active staff service commitment is required":
        return _typed_waiting_lock_error(
            ErrorCategory.DOMAIN_BLOCKED,
            "staff_service_commitment_required",
            "月嫂尚未完成簽約前服務承諾，不能建立等待訂金檔期鎖。",
            correlation,
            blockers=("staff_service_commitment_required",),
        )
    if message == "active staff service commitment days mismatch":
        return _typed_waiting_lock_error(
            ErrorCategory.DOMAIN_BLOCKED,
            "staff_service_commitment_days_mismatch",
            "月嫂簽約前服務日與訂單約定天數不一致，請重新建立正確媒合方案。",
            correlation,
            blockers=("staff_service_commitment_days_mismatch",),
        )
    if message == "customer has not accepted the matching plan":
        return _typed_waiting_lock_error(
            ErrorCategory.DOMAIN_BLOCKED,
            "customer_matching_acceptance_required",
            "客戶尚未接受正式媒合方案，不能建立等待訂金檔期鎖。",
            correlation,
            blockers=("customer_matching_acceptance_required",),
        )
    return _typed_waiting_lock_error(
        ErrorCategory.VALIDATION,
        "invalid_scheduling_intent",
        "等待訂金檔期鎖請求未通過驗證。",
        correlation,
    )


def _typed_waiting_lock_error(
    category,
    code,
    message,
    correlation,
    blockers=(),
):
    typed = TypedError(
        category,
        code,
        message,
        correlation,
        domain_blockers=blockers,
    )
    status = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.CONFLICT: 409,
    }[category]
    return _waiting_lock_http_error(status, typed)


def _waiting_lock_http_error(status, error):
    payload = {
        "category": error.category.value,
        "code": error.code,
        "message": error.message,
        "correlation_id": error.correlation_id.value,
        "field_errors": [],
        "domain_blockers": list(error.domain_blockers),
        "retryable": error.retryable,
        "current_version": None,
    }
    return HTTPException(status_code=status, detail={"error": payload})
