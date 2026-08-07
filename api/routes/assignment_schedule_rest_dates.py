"""Retired direct leave/rest-date writers retained as explicit Gone routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path

from api.dependencies.admin_auth import require_system_admin
from api.schemas.orders import (
    AssignmentLeaveResolutionApplyRequest,
    AssignmentLeaveResolutionBatchApplyRequest,
    AssignmentLeaveResolutionBatchPreviewRequest,
    AssignmentLeaveResolutionPreviewRequest,
    AssignmentRestDatesUpdateRequest,
)
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(
    prefix="/api/v1/assignment-schedules",
    tags=["Assignment Schedules 排班與排休"],
)


@router.post("/{assignment_id}/rest-dates/leave-resolution/batch-preview")
def preview_assignment_leave_resolution_batch_route(
    req: AssignmentLeaveResolutionBatchPreviewRequest,
    assignment_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
) -> Any:
    del req, assignment_id, principal
    _raise_retired()


@router.post("/{assignment_id}/rest-dates/leave-resolution/batch-apply")
def apply_assignment_leave_resolution_batch_route(
    req: AssignmentLeaveResolutionBatchApplyRequest,
    assignment_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
) -> Any:
    del req, assignment_id, principal
    _raise_retired()


@router.put("/{assignment_id}/rest-dates")
def save_assignment_rest_dates(
    req: AssignmentRestDatesUpdateRequest,
    assignment_id: int = Path(..., gt=0),
) -> Any:
    del req, assignment_id
    _raise_retired()


@router.post("/{assignment_id}/rest-dates/leave-resolution/preview")
def preview_assignment_leave_resolution_route(
    req: AssignmentLeaveResolutionPreviewRequest,
    assignment_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
) -> Any:
    del req, assignment_id, principal
    _raise_retired()


@router.post("/{assignment_id}/rest-dates/leave-resolution/apply")
def apply_assignment_leave_resolution_route(
    req: AssignmentLeaveResolutionApplyRequest,
    assignment_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
) -> Any:
    del req, assignment_id, principal
    _raise_retired()


def _raise_retired() -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_leave_schedule_writer_retired",
            "message": "Use the order leave-substitution Preview and Apply API.",
            "replacement": (
                "/api/v1/orders/{case_no}/leave-substitution/preview"
            ),
        },
    )
