"""
File: staff_retirement.py
Description: 提供管理端 Staff lifecycle Query、Preview、Apply 與 Global typed error API。
"""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_retirement import StaffRetirementApplication, get_staff_retirement_application
from api.schemas.base import BaseResponse
from api.schemas.staff_retirement import (
    StaffLifecycleApplyInput,
    StaffLifecycleApplyReceiptView,
    StaffLifecyclePreviewView,
    StaffLifecycleTransitionInput,
    StaffLifecycleView,
)
from domains.staff.retirement import StaffLifecycleTransition
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.retirement_workflow import StaffLifecycleApplyRequest


router = APIRouter(prefix="/api/v1/staff", tags=["Staff lifecycle"])


@router.get("/{staff_id}/lifecycle", response_model=BaseResponse[StaffLifecycleView])
def query_lifecycle(
    staff_id: int = Path(gt=0),
    correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffRetirementApplication = Depends(get_staff_retirement_application),
):
    del principal
    correlation = CorrelationId(correlation_id or uuid4().hex)
    try:
        return BaseResponse(data=_view(application.workflow.query(staff_id)))
    except (TypeError, ValueError) as error:
        _raise(error, correlation)
    except (LookupError, RuntimeError) as error:
        _raise_line_effect_error(error, correlation)


@router.post("/{staff_id}/{action}/preview", response_model=BaseResponse[StaffLifecyclePreviewView])
def preview_lifecycle(
    body: StaffLifecycleTransitionInput,
    staff_id: int = Path(gt=0),
    action: str = Path(pattern="^(retirement|reactivation)$"),
    correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffRetirementApplication = Depends(get_staff_retirement_application),
):
    del principal
    correlation = CorrelationId(correlation_id or uuid4().hex)
    try:
        preview = application.workflow.preview(staff_id, _transition(action), body.effective_at, body.reason_code)
        return BaseResponse(data={**_view(preview.candidate.before), "after_state": preview.candidate.after.state.value, "preview_fingerprint": preview.fingerprint.value})
    except (TypeError, ValueError) as error:
        _raise(error, correlation)
    except (LookupError, RuntimeError) as error:
        _raise_line_effect_error(error, correlation)


@router.post("/{staff_id}/{action}/apply", response_model=BaseResponse[StaffLifecycleApplyReceiptView])
def apply_lifecycle(
    body: StaffLifecycleApplyInput,
    staff_id: int = Path(gt=0),
    action: str = Path(pattern="^(retirement|reactivation)$"),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffRetirementApplication = Depends(get_staff_retirement_application),
):
    correlation = CorrelationId(correlation_id)
    try:
        receipt = application.workflow.apply(StaffLifecycleApplyRequest(staff_id, _transition(action), body.effective_at, body.reason_code, ExpectedVersion(body.expected_version), PreviewFingerprint(body.preview_fingerprint), IdempotencyKey(idempotency_key), ActorContext(str(principal.username or "").strip()), CorrelationId(correlation_id)))
        return BaseResponse(
            data={
                "staff_id": receipt.staff_id,
                "state": receipt.state.value,
                "resulting_version": receipt.version,
                "preview_fingerprint": receipt.preview_fingerprint.value,
                "idempotency_key": (
                    receipt.idempotency_key.value
                    if receipt.idempotency_key is not None
                    else idempotency_key
                ),
            }
        )
    except (TypeError, ValueError) as error:
        _raise(error, correlation)
    except (LookupError, RuntimeError) as error:
        _raise_line_effect_error(error, correlation)


def _transition(action: str) -> StaffLifecycleTransition:
    return StaffLifecycleTransition.RETIRE if action == "retirement" else StaffLifecycleTransition.REACTIVATE


def _view(fact):
    return {
        "staff_id": fact.staff_id,
        "state": fact.state.value,
        "version": fact.version,
        "effective_at": fact.effective_at,
        "reason_code": _canonical_reason_code(fact.reason_code),
    }


def _canonical_reason_code(reason_code: str | None) -> str | None:
    if reason_code is None:
        return None
    value = str(reason_code).strip()
    return value or None


_LINE_NOT_FOUND_CODES = frozenset({
    "line_identity_binding_not_found",
})
_LINE_IDEMPOTENCY_CODES = frozenset({
    "line_identity_revocation_idempotency_conflict",
})
_LINE_DOMAIN_BLOCKED_CODES = frozenset({
    "line_identity_binding_not_bound",
    "line_identity_default_menu_not_published",
    "line_identity_revocation_in_progress",
    "line_identity_staff_retirement_revocation_blocked",
    "line_identity_revocation_not_retryable",
    "line_identity_manual_completion_forbidden",
})
_LINE_CONFLICT_CODES = frozenset({
    "line_identity_binding_version_conflict",
    "line_identity_owner_projection_conflict",
})


def _raise_line_effect_error(error: Exception, correlation: CorrelationId) -> None:
    if str(error) not in (
        _LINE_NOT_FOUND_CODES
        | _LINE_IDEMPOTENCY_CODES
        | _LINE_DOMAIN_BLOCKED_CODES
        | _LINE_CONFLICT_CODES
    ):
        raise error
    _raise(error, correlation)


def _raise(error: Exception, correlation: CorrelationId) -> None:
    code = str(error)
    if code in _LINE_NOT_FOUND_CODES or code == "staff_not_found":
        status = 404
        category = ErrorCategory.NOT_FOUND
    elif code in _LINE_IDEMPOTENCY_CODES or code == "idempotency_mismatch":
        status = 409
        category = ErrorCategory.IDEMPOTENCY_MISMATCH
    elif code in _LINE_DOMAIN_BLOCKED_CODES:
        status = 409
        category = ErrorCategory.DOMAIN_BLOCKED
    elif code in {"stale_version", "stale_preview", "staff_lifecycle_transition_invalid", "staff_retirement_open_assignments"}:
        status = 409
        category = ErrorCategory.CONFLICT
    elif code in _LINE_CONFLICT_CODES:
        status = 409
        category = ErrorCategory.CONFLICT
    else:
        status = 422
        category = ErrorCategory.VALIDATION
    typed = TypedError(category, code or "staff_lifecycle_validation_error", "Staff lifecycle 操作被拒絕。", correlation)
    raise HTTPException(status_code=status, detail={"error": _materialize(typed)}) from error


def _materialize(value):
    if isinstance(value, CorrelationId):
        return value.value
    if isinstance(value, ErrorCategory):
        return value.value
    if isinstance(value, TypedError):
        return {
            "category": value.category.value,
            "code": value.code,
            "message": value.message,
            "field_errors": [],
            "domain_blockers": [],
            "retryable": False,
            "correlation_id": value.correlation_id.value,
            "current_version": None,
        }
    return value
