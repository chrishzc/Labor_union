"""
File: staff_retirement.py
Description: 提供管理端 Staff retirement 與 reactivation typed API。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_retirement import StaffRetirementApplication, get_staff_retirement_application
from api.schemas.base import BaseResponse
from api.schemas.staff_retirement import StaffLifecycleApplyInput, StaffLifecyclePreviewView, StaffLifecycleTransitionInput, StaffLifecycleView
from domains.staff.retirement import StaffLifecycleTransition
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.retirement_workflow import StaffLifecycleApplyRequest


router = APIRouter(prefix="/api/v1/staff", tags=["Staff lifecycle"])


@router.get("/{staff_id}/lifecycle", response_model=BaseResponse[StaffLifecycleView])
def query_lifecycle(staff_id: int = Path(gt=0), principal: AdminPrincipal = Depends(require_admin), application: StaffRetirementApplication = Depends(get_staff_retirement_application)):
    del principal
    try:
        return BaseResponse(data=_view(application.workflow.query(staff_id)))
    except ValueError as error:
        _raise(error)


@router.post("/{staff_id}/{action}/preview", response_model=BaseResponse[StaffLifecyclePreviewView])
def preview_lifecycle(body: StaffLifecycleTransitionInput, staff_id: int = Path(gt=0), action: str = Path(pattern="^(retirement|reactivation)$"), principal: AdminPrincipal = Depends(require_admin), application: StaffRetirementApplication = Depends(get_staff_retirement_application)):
    del principal
    try:
        preview = application.workflow.preview(staff_id, _transition(action), body.effective_at, body.reason_code)
        return BaseResponse(data={**_view(preview.candidate.before), "after_state": preview.candidate.after.state.value, "preview_fingerprint": preview.fingerprint.value})
    except ValueError as error:
        _raise(error)


@router.post("/{staff_id}/{action}/apply", response_model=BaseResponse[StaffLifecycleView])
def apply_lifecycle(body: StaffLifecycleApplyInput, staff_id: int = Path(gt=0), action: str = Path(pattern="^(retirement|reactivation)$"), idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ..., correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ..., principal: AdminPrincipal = Depends(require_admin), application: StaffRetirementApplication = Depends(get_staff_retirement_application)):
    try:
        receipt = application.workflow.apply(StaffLifecycleApplyRequest(staff_id, _transition(action), body.effective_at, body.reason_code, ExpectedVersion(body.expected_version), PreviewFingerprint(body.preview_fingerprint), IdempotencyKey(idempotency_key), ActorContext(str(principal.username or "").strip()), CorrelationId(correlation_id)))
        return BaseResponse(data={"staff_id": receipt.staff_id, "state": receipt.state.value, "version": receipt.version})
    except ValueError as error:
        _raise(error)


def _transition(action: str) -> StaffLifecycleTransition:
    return StaffLifecycleTransition.RETIRE if action == "retirement" else StaffLifecycleTransition.REACTIVATE


def _view(fact):
    return {
        "staff_id": fact.staff_id,
        "state": fact.state.value,
        "version": fact.version,
        "effective_at": fact.effective_at,
        "masked_reason_code": _masked_reason_code(fact.reason_code),
    }


def _masked_reason_code(reason_code: str | None) -> str | None:
    if reason_code is None:
        return None
    return reason_code[:1] + "***"


def _raise(error: ValueError) -> None:
    code = str(error)
    status = 404 if code == "staff_not_found" else 409 if code in {"stale_version", "stale_preview", "idempotency_mismatch", "staff_lifecycle_transition_invalid"} else 422
    raise HTTPException(status_code=status, detail={"code": code, "message": "Staff lifecycle 操作被拒絕。"}) from error
