"""Owner-routed Staff Profile and Bank Account mutation endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import IntegrityError, OperationalError, ProgrammingError

from api.dependencies.admin_auth import admin_actor_context, require_registry_writer
from api.dependencies.staff_registry_mutation import (
    get_staff_bank_account_workflow,
    get_staff_profile_mutation_workflow,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.staff_registry_mutation import (
    StaffBankAccountApplyRequest,
    StaffBankAccountPreviewRequest,
    StaffBankAccountPreviewView,
    StaffBankAccountReceiptView,
    StaffProfileMutationApplyRequest,
    StaffProfileMutationPreviewRequest,
    StaffProfileMutationPreviewView,
    StaffProfileMutationReceiptView,
)
from domains.staff.bank_account import StaffBankAccountValidationError
from domains.staff.profile import StaffProfileValidationError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.bank_account_workflow import (
    StaffBankAccountConflict,
    StaffBankAccountNotFound,
    StaffBankAccountWorkflow,
)
from subsystems.staff.profile_workflow import (
    StaffProfileMutationConflict,
    StaffProfileMutationNotFound,
    StaffProfileMutationWorkflow,
)


router = APIRouter(prefix="/api/v1/staff", tags=["Staff Registry Mutations"])


@router.post("/{staff_id}/profile/preview", response_model=BaseResponse[StaffProfileMutationPreviewView])
def preview_staff_profile(
    body: StaffProfileMutationPreviewRequest,
    staff_id: int = Path(..., ge=1),
    principal: AdminPrincipal = Depends(require_registry_writer),
    workflow: StaffProfileMutationWorkflow = Depends(get_staff_profile_mutation_workflow),
):
    del principal
    correlation = uuid4().hex
    try:
        preview = workflow.preview(
            staff_id,
            body.changes.model_dump(exclude_unset=True, mode="json"),
            ExpectedVersion(body.expected_version),
        )
        return BaseResponse(data=StaffProfileMutationPreviewView(
            staff_id=preview.staff_id,
            current_version=preview.current_version,
            before=dict(preview.before),
            after=dict(preview.after),
            preview_fingerprint=preview.preview_fingerprint.value,
        ), message="成功產生月嫂資料變更預覽")
    except Exception as error:
        _raise_staff_error(error, correlation, "月嫂資料變更無法預覽。")


@router.post("/{staff_id}/profile/apply", response_model=BaseResponse[StaffProfileMutationReceiptView])
def apply_staff_profile(
    body: StaffProfileMutationApplyRequest,
    staff_id: int = Path(..., ge=1),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_registry_writer),
    workflow: StaffProfileMutationWorkflow = Depends(get_staff_profile_mutation_workflow),
):
    try:
        receipt = workflow.apply(
            staff_id,
            body.changes.model_dump(exclude_unset=True, mode="json"),
            ExpectedVersion(body.expected_version),
            PreviewFingerprint(body.preview_fingerprint),
            IdempotencyKey(idempotency_key),
            admin_actor_context(principal),
            body.reason,
            CorrelationId(correlation_id),
        )
        return BaseResponse(data=StaffProfileMutationReceiptView(
            staff_id=receipt.staff_id,
            resulting_version=receipt.resulting_version,
            changed_fields=receipt.changed_fields,
            preview_fingerprint=receipt.preview_fingerprint.value,
            idempotency_key=receipt.idempotency_key.value,
            replayed=receipt.replayed,
            readback=dict(receipt.readback.values),
        ), message="月嫂個人資料已更新")
    except Exception as error:
        _raise_staff_error(error, correlation_id, "月嫂資料更新失敗。")


@router.post("/{staff_id}/bank-accounts/preview", response_model=BaseResponse[StaffBankAccountPreviewView])
def preview_staff_bank_account(
    body: StaffBankAccountPreviewRequest,
    staff_id: int = Path(..., ge=1),
    principal: AdminPrincipal = Depends(require_registry_writer),
    workflow: StaffBankAccountWorkflow = Depends(get_staff_bank_account_workflow),
):
    del principal
    correlation = uuid4().hex
    try:
        preview = workflow.preview(
            staff_id,
            body.command.model_dump(exclude_none=True),
            ExpectedVersion(body.expected_version),
        )
        return BaseResponse(data=StaffBankAccountPreviewView(
            staff_id=preview.staff_id,
            current_version=preview.current_version,
            operation=preview.operation,
            before=preview.before,
            after=preview.after,
            preview_fingerprint=preview.preview_fingerprint.value,
        ), message="成功產生銀行帳戶變更預覽")
    except Exception as error:
        _raise_staff_error(error, correlation, "銀行帳戶變更無法預覽。")


@router.post("/{staff_id}/bank-accounts/apply", response_model=BaseResponse[StaffBankAccountReceiptView])
def apply_staff_bank_account(
    body: StaffBankAccountApplyRequest,
    staff_id: int = Path(..., ge=1),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_registry_writer),
    workflow: StaffBankAccountWorkflow = Depends(get_staff_bank_account_workflow),
):
    try:
        receipt = workflow.apply(
            staff_id,
            body.command.model_dump(exclude_none=True),
            ExpectedVersion(body.expected_version),
            PreviewFingerprint(body.preview_fingerprint),
            IdempotencyKey(idempotency_key),
            admin_actor_context(principal),
            body.reason,
            CorrelationId(correlation_id),
        )
        return BaseResponse(data=StaffBankAccountReceiptView(
            staff_id=receipt.staff_id,
            account_id=receipt.account_id,
            operation=receipt.operation,
            resulting_version=receipt.resulting_version,
            preview_fingerprint=receipt.preview_fingerprint.value,
            idempotency_key=receipt.idempotency_key.value,
            replayed=receipt.replayed,
            readback=tuple({
                "account_id": account.account_id,
                "bank_code": account.bank_code or None,
                "branch_code": account.branch_code or None,
                "account_last4": account.account_no[-4:] if account.account_no else None,
                "is_primary": account.is_primary,
                "is_active": account.is_active,
            } for account in receipt.readback.accounts),
        ), message="銀行帳戶已更新")
    except Exception as error:
        _raise_staff_error(error, correlation_id, "銀行帳戶更新失敗。")


def _raise_staff_error(error: Exception, correlation: str, message: str) -> None:
    code = str(error) or "staff_registry_mutation_failed"
    if isinstance(error, (StaffProfileMutationNotFound, StaffBankAccountNotFound)):
        status, category = 404, "not_found"
    elif isinstance(error, (StaffProfileMutationConflict, StaffBankAccountConflict)) or "stale" in code or "idempotency" in code or "collision" in code:
        status = 409
        category = "idempotency_mismatch" if "idempotency" in code else "conflict"
    elif isinstance(error, (StaffProfileValidationError, StaffBankAccountValidationError, ValueError)):
        status, category = 422, "validation"
    elif isinstance(error, IntegrityError):
        status, category, code = 409, "conflict", "staff_registry_unique_conflict"
    elif isinstance(error, (OperationalError, ProgrammingError)):
        raise internal_query_error("staff_registry_database_error", message, correlation) from error
    elif isinstance(error, HTTPException):
        raise error
    else:
        raise internal_query_error("staff_registry_mutation_internal_error", message, correlation) from error
    raise typed_http_error(status, category, code, message, correlation) from error


__all__ = ["router"]
