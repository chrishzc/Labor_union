"""LIFF transport adapter for accepted staff-leave customer defer handling.

This module does not own leave or scheduling facts. It authenticates the current
LINE-bound admin and delegates reads/Preview/Apply to the existing Staff Leave
and Leave Substitution owners.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.leave_substitution import (
    LeaveSubstitutionApplication,
    get_leave_substitution_application,
)
from api.error_contracts import typed_http_error
from api.routes import leave_substitution as leave_substitution_routes
from api.routes import staff_leave_management as staff_leave_management_routes
from api.routes.line_mobile_admin import _mobile_admin_context
from api.schemas.base import BaseResponse
from api.schemas.leave_substitution import (
    CustomerLeaveDeferApplyBody,
    CustomerLeaveDeferPreviewBody,
    CustomerLeaveDeferPreviewView,
    LeaveAssignmentSummaryView,
    LeaveSubstitutionReceiptView,
)
from api.schemas.staff_leave_management import StaffLeaveCoordinationContextView
from subsystems.line.capabilities import LineCapability


router = APIRouter(
    prefix="/api/v1/line/mobile-admin/staff-leave-requests",
    tags=["LINE Mobile Admin"],
)


class _MobileCoordinationContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    line_id_token: str = Field(min_length=1, max_length=4096)
    expected_version: int = Field(ge=1)


class _MobileAssignmentsRequest(_MobileCoordinationContextRequest):
    pass


class _MobileCustomerDeferPreviewRequest(CustomerLeaveDeferPreviewBody):
    line_id_token: str = Field(min_length=1, max_length=4096)


class _MobileCustomerDeferApplyRequest(CustomerLeaveDeferApplyBody):
    line_id_token: str = Field(min_length=1, max_length=4096)
    idempotency_key: str = Field(min_length=1, max_length=191)


def _require_request_identity(request_id: int, payload_request_id: int) -> None:
    if request_id != payload_request_id:
        raise typed_http_error(
            422,
            "validation",
            "staff_leave_request_identity_mismatch",
            "請假申請識別與操作內容不一致，請重新載入待辦。",
            "line-mobile-admin:staff-leave-customer-defer-identity",
        )


def _customer_defer_principal(line_id_token: str):
    principal, _ = _mobile_admin_context(line_id_token, LineCapability.REVIEW_DECIDE)
    if principal.role != "system_admin":
        raise typed_http_error(
            403,
            "forbidden",
            "staff_leave_customer_defer_system_admin_required",
            "客戶同意順延後的正式排班套用僅限系統管理員。",
            "line-mobile-admin:staff-leave-customer-defer-authority",
        )
    return principal


def _coordination_context(
    request_id: int,
    expected_version: int,
    principal,
):
    return staff_leave_management_routes.get_staff_leave_coordination_context(
        request_id,
        expected_version,
        principal,
    )


def _coordination_data(response) -> StaffLeaveCoordinationContextView:
    return StaffLeaveCoordinationContextView.model_validate(response.data)


def _require_case_target(context: StaffLeaveCoordinationContextView, case_no: str) -> None:
    if not any(target.case_no == case_no for target in context.targets):
        raise typed_http_error(
            409,
            "conflict",
            "staff_leave_coordination_case_not_current",
            "此案件已不在這筆請假的目前協調範圍，請重新整理。",
            "line-mobile-admin:staff-leave-customer-defer-case",
        )


@router.post(
    "/{request_id}/coordination-context",
    response_model=BaseResponse[StaffLeaveCoordinationContextView],
)
def mobile_staff_leave_coordination_context(
    request_id: int,
    payload: _MobileCoordinationContextRequest,
):
    principal, _ = _mobile_admin_context(payload.line_id_token, LineCapability.REVIEW_READ)
    return _coordination_context(request_id, payload.expected_version, principal)


@router.post(
    "/{request_id}/customer-defer/{case_no}/assignments",
    response_model=BaseResponse[list[LeaveAssignmentSummaryView]],
)
def mobile_customer_defer_assignments(
    request_id: int,
    case_no: str,
    payload: _MobileAssignmentsRequest,
    application: LeaveSubstitutionApplication = Depends(get_leave_substitution_application),
):
    principal = _customer_defer_principal(payload.line_id_token)
    context_response = _coordination_context(request_id, payload.expected_version, principal)
    _require_case_target(_coordination_data(context_response), case_no)
    return leave_substitution_routes.list_leave_assignments(case_no, principal, application)


@router.post(
    "/{request_id}/customer-defer/{case_no}/preview",
    response_model=BaseResponse[CustomerLeaveDeferPreviewView],
)
def mobile_customer_defer_preview(
    request_id: int,
    case_no: str,
    payload: _MobileCustomerDeferPreviewRequest,
    application: LeaveSubstitutionApplication = Depends(get_leave_substitution_application),
):
    _require_request_identity(request_id, payload.leave_request_id)
    principal = _customer_defer_principal(payload.line_id_token)
    context_response = _coordination_context(
        request_id,
        payload.expected_leave_request_version,
        principal,
    )
    _require_case_target(_coordination_data(context_response), case_no)
    body = CustomerLeaveDeferPreviewBody.model_validate(
        payload.model_dump(exclude={"line_id_token"})
    )
    return leave_substitution_routes.preview_customer_leave_defer(
        body,
        case_no,
        f"mobile-leave-customer-defer-preview:{request_id}:{uuid4()}",
        principal,
        application,
    )


@router.post(
    "/{request_id}/customer-defer/{case_no}/apply",
    response_model=BaseResponse[LeaveSubstitutionReceiptView],
)
def mobile_customer_defer_apply(
    request_id: int,
    case_no: str,
    payload: _MobileCustomerDeferApplyRequest,
    application: LeaveSubstitutionApplication = Depends(get_leave_substitution_application),
):
    _require_request_identity(request_id, payload.leave_request_id)
    principal = _customer_defer_principal(payload.line_id_token)
    body = CustomerLeaveDeferApplyBody.model_validate(
        payload.model_dump(exclude={"line_id_token", "idempotency_key"})
    )
    return leave_substitution_routes.apply_customer_leave_defer(
        body,
        case_no,
        payload.idempotency_key,
        f"mobile-leave-customer-defer-apply:{request_id}:{uuid4()}",
        principal,
        application,
    )


__all__ = ["router"]
